"""Retrieval over DeclarAI's versioned knowledge bank.

Chunks curated Markdown under ``docs/knowledge-bank/``.  Primary retrieval is
OpenAI embeddings + local Chroma (hybrid with lexical re-rank).  Lexical-only
scoring remains available as a fallback when embeddings are unavailable.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

from .prometa_config import (
    record_retrieval_raw,
    retrieval_query,
    set_span_attr,
    tool as prometa_tool,
)


KNOWLEDGE_BANK_DIR = (
    Path(__file__).resolve().parents[2] / "docs" / "knowledge-bank"
)

MAX_SNIPPET_CHARS = 1400
DEFAULT_MAX_CHUNKS = 4
DEFAULT_MAX_CONTEXT_CHARS = 5200

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+-]*")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_STOP_WORDS = frozenset({
    "a", "about", "after", "all", "an", "and", "are", "as", "at",
    "be", "by", "can", "do", "does", "for", "from", "give", "has",
    "have", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "our", "should", "show", "tell", "the", "their", "this",
    "to", "use", "used", "using", "what", "when", "where", "which",
    "why", "with", "you",
})


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    source: str
    title: str
    heading: str
    content: str
    tokens: tuple[str, ...]


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN_RE.findall((text or "").lower())
        if token not in _STOP_WORDS and len(token) > 1
    ]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "section"


def _read_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match and match.group(1) == "#":
            return match.group(2).strip()
    return path.stem.replace("-", " ").title()


def _make_chunk(path: Path, title: str, heading: str,
                lines: list[str]) -> KnowledgeChunk | None:
    content = "\n".join(lines).strip()
    if not content:
        return None
    chunk_id = f"{path.stem}#{_slugify(heading)}"
    weighted_text = f"{title}\n{heading}\n{content}"
    return KnowledgeChunk(
        chunk_id=chunk_id,
        source=path.name,
        title=title,
        heading=heading,
        content=content,
        tokens=tuple(_tokenize(weighted_text)),
    )


def _parse_markdown(path: Path) -> list[KnowledgeChunk]:
    text = path.read_text(encoding="utf-8")
    title = _read_title(path, text)
    chunks: list[KnowledgeChunk] = []
    current_heading = title
    current_lines: list[str] = []

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            maybe_chunk = _make_chunk(path, title, current_heading, current_lines)
            if maybe_chunk:
                chunks.append(maybe_chunk)
            current_heading = match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    maybe_chunk = _make_chunk(path, title, current_heading, current_lines)
    if maybe_chunk:
        chunks.append(maybe_chunk)
    return chunks


@lru_cache(maxsize=1)
def load_knowledge_chunks() -> tuple[KnowledgeChunk, ...]:
    """Load and chunk all Markdown files from the user-facing docs folder."""
    if not KNOWLEDGE_BANK_DIR.exists():
        return tuple()

    chunks: list[KnowledgeChunk] = []
    for path in sorted(KNOWLEDGE_BANK_DIR.glob("*.md")):
        chunks.extend(_parse_markdown(path))
    return tuple(chunks)


def _score_chunk(chunk: KnowledgeChunk, query_terms: list[str]) -> float:
    if not query_terms:
        return 0.0

    counts = Counter(chunk.tokens)
    heading_terms = set(_tokenize(f"{chunk.title} {chunk.heading} {chunk.source}"))
    haystack = " ".join(chunk.tokens)
    score = 0.0

    for term in query_terms:
        if term in counts:
            score += counts[term]
        if term in heading_terms:
            score += 3.0

    for first, second in zip(query_terms, query_terms[1:]):
        if f"{first} {second}" in haystack:
            score += 4.0

    # Reward chunks that cover a larger share of the distinct query terms.
    coverage = len(set(query_terms).intersection(counts)) / max(len(set(query_terms)), 1)
    return score + coverage * 5.0


def _clip_snippet(text: str, max_chars: int = MAX_SNIPPET_CHARS) -> str:
    clean = (text or "").strip()
    if len(clean) <= max_chars:
        return clean
    cut = clean.rfind("\n", 0, max_chars)
    if cut < max_chars // 2:
        cut = clean.rfind(" ", 0, max_chars)
    if cut < max_chars // 2:
        cut = max_chars
    return clean[:cut].rstrip() + "\n..."


def _format_context(results: list[dict]) -> str:
    if not results:
        return ""

    lines = [
        "Knowledge bank context retrieved for this turn.",
        "Use these snippets for stable platform guidance, terminology, and technical disclosure.",
        "When you rely on a knowledge-bank fact in your reply, cite the matching "
        "[KBn] marker inline (for example: PSI measures population stability [KB1]).",
        "Do not invent source labels or cite documents that are not listed below.",
        "For current pipeline values, still use live pipeline tools rather than these docs.",
    ]
    for idx, item in enumerate(results, start=1):
        lines.append("")
        lines.append(
            f"[KB{idx}] {item['title']} / {item['heading']} "
            f"(source: {item['source']})"
        )
        lines.append(item["snippet"])
    return "\n".join(lines)


def retrieve_knowledge_context_lexical(
    query: str,
    *,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> dict:
    """Lexical (keyword) retrieval — used for RAG_MODE=lexical and fallbacks."""
    with retrieval_query(
        "keyword",
        query_text=query or "",
        top_k=max_chunks,
    ) as r:
        query_terms = _tokenize(query or "")
        chunks = load_knowledge_chunks()
        ranked = []

        for chunk in chunks:
            score = _score_chunk(chunk, query_terms)
            if score > 0:
                ranked.append((score, chunk))

        ranked.sort(key=lambda item: (-item[0], item[1].source, item[1].heading))

        results: list[dict] = []
        used_chars = 0
        for score, chunk in ranked[:max(max_chunks * 3, max_chunks)]:
            snippet = _clip_snippet(chunk.content)
            next_chars = len(snippet)
            if results and used_chars + next_chars > max_context_chars:
                break
            results.append({
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "title": chunk.title,
                "heading": chunk.heading,
                "score": round(score, 3),
                "snippet": snippet,
            })
            used_chars += next_chars
            if len(results) >= max_chunks:
                break

        context = _format_context(results)
        r.results(
            result_ids=[item["chunk_id"] for item in results],
            scores=[float(item["score"]) for item in results],
            permissions_enforced=False,
        )
        record_retrieval_raw(context)
        set_span_attr("declarai.rag.called", True)
        set_span_attr("declarai.rag.backend", "lexical")
        set_span_attr("declarai.rag.mode", "lexical")
        set_span_attr("declarai.rag.query_chars", len(query or ""))
        set_span_attr("declarai.rag.result_count", len(results))
        set_span_attr("declarai.rag.context_chars", len(context))
        set_span_attr(
            "declarai.rag.sources",
            ",".join(dict.fromkeys(item["source"] for item in results)),
        )
        set_span_attr(
            "declarai.rag.chunk_ids",
            ",".join(item["chunk_id"] for item in results),
        )

        return {
            "query": query or "",
            "results": results,
            "context": context,
        }


@prometa_tool(name="knowledge-bank-rag")
def retrieve_knowledge_context(query: str,
                               *,
                               max_chunks: int = DEFAULT_MAX_CHUNKS,
                               max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> dict:
    """Retrieve knowledge-bank snippets for a user query (vector/hybrid + fallback)."""
    # Lazy import avoids a circular dependency with ai_assistant.rag.indexer.
    from ai_assistant.rag.retriever import retrieve_vector_context

    return retrieve_vector_context(
        query,
        max_chunks=max_chunks,
        max_context_chars=max_context_chars,
        lexical_fallback=retrieve_knowledge_context_lexical,
    )
