"""Offline RAG eval + citation / payload contract tests (no live LLM)."""
from __future__ import annotations

import inspect

import pytest


@pytest.mark.unit
class TestRagCitationContract:
    def test_format_context_requires_kb_citations(self):
        from ai_assistant.knowledge_bank import _format_context

        context = _format_context([{
            "chunk_id": "c1",
            "source": "terminology-glossary.md",
            "title": "Glossary",
            "heading": "PSI",
            "score": 1.0,
            "snippet": "Population Stability Index.",
        }])
        assert "[KB1]" in context
        assert "cite the matching" in context.lower() or "[KBn]" in context
        assert "Do not invent source labels" in context

    def test_rag_sources_api_shape_includes_chunk_id(self):
        """Structural guard: chat response builds rag_sources with chunk_id."""
        from ai_assistant import views

        source = inspect.getsource(views._chat_workflow)
        assert "rag_sources" in source
        assert "'chunk_id'" in source or '"chunk_id"' in source


@pytest.mark.unit
class TestLexicalRagGoldenQueries:
    """Golden queries against lexical retrieve — no OpenAI required."""

    def test_psi_retrieves_glossary(self, monkeypatch):
        monkeypatch.setenv("RAG_MODE", "lexical")
        from ai_assistant.knowledge_bank import retrieve_knowledge_context_lexical

        out = retrieve_knowledge_context_lexical("What does PSI mean?")
        sources = {r["source"] for r in out["results"]}
        assert "terminology-glossary.md" in sources
        assert "[KB1]" in out["context"]
        assert all("chunk_id" in r for r in out["results"])

    def test_assistant_usage_retrieves_action_guide(self, monkeypatch):
        monkeypatch.setenv("RAG_MODE", "lexical")
        from ai_assistant.knowledge_bank import retrieve_knowledge_context_lexical

        out = retrieve_knowledge_context_lexical(
            "How should I use the assistant actions?"
        )
        sources = {r["source"] for r in out["results"]}
        assert "assistant-usage-and-action-guide.md" in sources

    def test_purifier_assumptions_retrieves_disclosure_or_manual(self, monkeypatch):
        monkeypatch.setenv("RAG_MODE", "lexical")
        from ai_assistant.knowledge_bank import retrieve_knowledge_context_lexical

        out = retrieve_knowledge_context_lexical(
            "What assumptions does the data purifier make?"
        )
        assert out["results"], "expected at least one knowledge-bank hit"
        sources = {r["source"] for r in out["results"]}
        assert sources & {
            "technical-disclosure.md",
            "platform-guideline-user-manual.md",
            "terminology-glossary.md",
        }

    def test_sfs_stopping_retrieves_platform_or_disclosure(self, monkeypatch):
        monkeypatch.setenv("RAG_MODE", "lexical")
        from ai_assistant.knowledge_bank import retrieve_knowledge_context_lexical

        out = retrieve_knowledge_context_lexical(
            "Explain SFS stopping criteria in DeclarAI."
        )
        assert out["results"]
        sources = {r["source"] for r in out["results"]}
        assert sources & {
            "technical-disclosure.md",
            "platform-guideline-user-manual.md",
            "terminology-glossary.md",
            "assistant-usage-and-action-guide.md",
        }

    def test_governance_checklist_for_review_query(self, monkeypatch):
        monkeypatch.setenv("RAG_MODE", "lexical")
        from ai_assistant.knowledge_bank import retrieve_knowledge_context_lexical

        out = retrieve_knowledge_context_lexical(
            "Give me the model governance review checklist before export."
        )
        sources = {r["source"] for r in out["results"]}
        assert "model-governance-review-checklist.md" in sources
