"""
Skill registry — discover and load bundled AI-assistant skills.

A skill is a directory under :data:`SKILLS_DIR` that contains a ``SKILL.md``
file with YAML frontmatter (``name`` and ``description``) followed by a
markdown body.  The body is the actual guidance the LLM consumes when the
skill is invoked via the ``invoke_skill`` tool.

Skills are discovered eagerly on first access and cached for the process
lifetime.  Bodies are loaded lazily.

Frontmatter parser is intentionally minimal so we don't add a PyYAML
dependency for two-line headers (``key: value`` or ``key: "value"``).

Example layout::

    backend/ai_assistant/skills/
        feature-engineering/
            SKILL.md          ← required, registered as a skill
            references/...    ← optional supplementary files
            scripts/...
            templates/...
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Directory that holds bundled skills.  Override with PROMETA_SKILLS_DIR if
# the operator wants to mount external skills at runtime (advanced).
SKILLS_DIR = os.environ.get(
    'PROMETA_SKILLS_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'skills'),
)


# Supplementary skill files larger than this are truncated to keep the LLM
# context budget bounded.  100 KB is plenty for a markdown reference doc.
MAX_SKILL_FILE_BYTES = 100_000

# Only files matching these suffixes are exposed via read_file().  We allow
# typical skill payload formats and reject anything that smells binary.
ALLOWED_SKILL_FILE_SUFFIXES = ('.md', '.txt', '.py', '.json', '.yml', '.yaml')


@dataclass
class Skill:
    """A discovered skill — frontmatter metadata + lazy body loader."""
    name: str
    description: str
    path: str  # absolute path to the skill directory

    @property
    def skill_md_path(self) -> str:
        return os.path.join(self.path, 'SKILL.md')

    def body(self) -> str:
        """Return the markdown body of SKILL.md (everything after frontmatter)."""
        try:
            with open(self.skill_md_path, 'r', encoding='utf-8') as fh:
                _, body = _split_frontmatter(fh.read())
            return body.strip()
        except OSError as exc:
            logger.warning("Failed to read skill body for %s: %s", self.name, exc)
            return ''

    # ------------------------------------------------------------------
    # Supplementary file access (references/, scripts/, templates/, ...)
    # ------------------------------------------------------------------

    def list_files(self) -> list[str]:
        """Return relative paths of all readable files inside the skill dir
        EXCEPT ``SKILL.md`` (which is delivered via :meth:`body`).

        Paths are POSIX-style (forward slashes) and sorted for stable output.
        Filtered to :data:`ALLOWED_SKILL_FILE_SUFFIXES`.
        """
        out: list[str] = []
        for root, _dirs, files in os.walk(self.path):
            for fname in files:
                if fname == 'SKILL.md' and root == self.path:
                    continue
                if not fname.lower().endswith(ALLOWED_SKILL_FILE_SUFFIXES):
                    continue
                abs_path = os.path.join(root, fname)
                rel = os.path.relpath(abs_path, self.path)
                out.append(rel.replace(os.sep, '/'))
        return sorted(out)

    def read_file(self, rel_path: str) -> tuple[str, Optional[str]]:
        """Read a supplementary file from inside the skill directory.

        Returns ``(content, error)``.  On success ``error`` is ``None``.
        Enforces:
          • no absolute paths
          • no ``..`` traversal (the resolved path must stay under ``self.path``)
          • allowed suffix only
          • payload truncated to :data:`MAX_SKILL_FILE_BYTES` bytes

        ``rel_path`` may be supplied with forward slashes; native separators
        also work.
        """
        if not rel_path:
            return '', "rel_path is required"
        # Normalize and reject obviously malicious inputs
        norm = rel_path.replace('\\', '/').lstrip('/')
        if os.path.isabs(rel_path) or '..' in norm.split('/'):
            return '', f"refusing to read '{rel_path}': path traversal not allowed"
        if not norm.lower().endswith(ALLOWED_SKILL_FILE_SUFFIXES):
            allowed = ', '.join(ALLOWED_SKILL_FILE_SUFFIXES)
            return '', f"refusing to read '{rel_path}': only files ending in {allowed} are exposed"
        # Resolve and confirm containment
        skill_root = os.path.realpath(self.path)
        target = os.path.realpath(os.path.join(skill_root, norm))
        if os.path.commonpath([skill_root, target]) != skill_root:
            return '', f"refusing to read '{rel_path}': resolves outside the skill directory"
        if not os.path.isfile(target):
            return '', f"file '{rel_path}' not found in skill '{self.name}'"
        try:
            with open(target, 'rb') as fh:
                raw = fh.read(MAX_SKILL_FILE_BYTES + 1)
        except OSError as exc:
            return '', f"read error: {exc}"
        truncated = len(raw) > MAX_SKILL_FILE_BYTES
        if truncated:
            raw = raw[:MAX_SKILL_FILE_BYTES]
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            return '', f"file '{rel_path}' is not valid UTF-8 text"
        if truncated:
            text += f"\n\n…[truncated to {MAX_SKILL_FILE_BYTES} bytes]"
        return text, None

    def to_dict(self) -> dict:
        return {'name': self.name, 'description': self.description, 'path': self.path}


# ---------------------------------------------------------------------------
# Frontmatter parser (no PyYAML dependency)
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown file with YAML-ish frontmatter into ``(meta, body)``.

    Accepts only flat ``key: value`` pairs.  Quotes around values are
    stripped.  Returns an empty meta dict if no frontmatter is present.
    """
    if not text.startswith('---'):
        return {}, text
    # Skip the opening fence (handle both \n and \r\n)
    rest = text[3:].lstrip('\n').lstrip('\r')
    end = rest.find('\n---')
    if end < 0:
        return {}, text
    header = rest[:end]
    # body starts after the closing fence + newline
    body_start = end + len('\n---')
    body = rest[body_start:].lstrip('\n').lstrip('\r')
    meta: Dict[str, str] = {}
    for line in header.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' not in line:
            continue
        key, _, value = line.partition(':')
        value = value.strip()
        # Strip surrounding quotes if present
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        meta[key.strip()] = value
    return meta, body


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_skills_cache: Optional[Dict[str, Skill]] = None


def _discover() -> Dict[str, Skill]:
    out: Dict[str, Skill] = {}
    if not os.path.isdir(SKILLS_DIR):
        logger.info("Skills directory does not exist: %s", SKILLS_DIR)
        return out
    for entry in sorted(os.listdir(SKILLS_DIR)):
        sk_dir = os.path.join(SKILLS_DIR, entry)
        sk_md = os.path.join(sk_dir, 'SKILL.md')
        if not os.path.isdir(sk_dir) or not os.path.isfile(sk_md):
            continue
        try:
            with open(sk_md, 'r', encoding='utf-8') as fh:
                meta, _ = _split_frontmatter(fh.read())
        except OSError as exc:
            logger.warning("Skipping skill %s (read error: %s)", entry, exc)
            continue
        name = (meta.get('name') or entry).strip()
        description = (meta.get('description') or '').strip()
        if not description:
            logger.warning("Skill %s has no description; using directory name.", name)
            description = f"Skill: {name}"
        out[name] = Skill(name=name, description=description, path=sk_dir)
    return out


def list_skills(refresh: bool = False) -> Dict[str, Skill]:
    """Return the registry of available skills (cached)."""
    global _skills_cache
    with _cache_lock:
        if _skills_cache is None or refresh:
            _skills_cache = _discover()
        return dict(_skills_cache)


def get_skill(name: str) -> Optional[Skill]:
    """Look up a single skill by name (case-insensitive)."""
    skills = list_skills()
    if name in skills:
        return skills[name]
    lowered = name.lower()
    for k, v in skills.items():
        if k.lower() == lowered:
            return v
    return None


def invalidate_cache() -> None:
    """Force re-discovery on the next call (used in tests)."""
    global _skills_cache
    with _cache_lock:
        _skills_cache = None
