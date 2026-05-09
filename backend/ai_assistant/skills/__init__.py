"""Bundled AI assistant skills.

Each skill lives in its own subdirectory containing at least a ``SKILL.md``
file with YAML frontmatter (``name``, ``description``) and a markdown body
that the LLM reads when the skill is invoked.

The registry in :mod:`ai_assistant.skill_registry` discovers and loads them.
"""
