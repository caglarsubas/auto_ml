"""CI-safe RAG intent telemetry contract using golden questions.

Classifier labels are injected (not live gemma). Asserts that when R is / is
not present, workflow + retrieval stamp the expected ``declarai.rag.*`` attrs
and ``rag_sources`` payload shape. Live gemma FP/FN lives under
``tests/live_engine/``.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from tests.rag_intent_goldens import ALL_CASES, SHOULD_NOT_RAG, SHOULD_RAG


@pytest.mark.unit
class TestRagIntentGoldenCatalog:
    def test_catalog_has_both_polarities(self):
        assert SHOULD_RAG and SHOULD_NOT_RAG
        assert all(c.should_rag for c in SHOULD_RAG)
        assert all(not c.should_rag for c in SHOULD_NOT_RAG)
        ids = [c.case_id for c in ALL_CASES]
        assert len(ids) == len(set(ids)), "duplicate case_id in golden catalog"


@pytest.mark.unit
class TestRagIntentTelemetryContract:
    """Drive ``_chat_workflow`` with forced intent labels and capture span attrs."""

    MODEL = "engine-gemma4-26b"

    def _patch(self, monkeypatch, *, force_labels: list[str], attrs: dict):
        from ai_assistant import knowledge_bank as kb
        from ai_assistant import views
        from ai_assistant.rag import retriever as retriever_mod
        from django.conf import settings

        monkeypatch.setattr(settings, "RAG_MODE", "lexical", raising=False)
        monkeypatch.setenv("RAG_MODE", "lexical")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "", raising=False)

        def capture(key, value):
            attrs[key] = value

        def fake_call_llm(messages, model_key, tools=None):
            first = (messages[0].get("content") if messages else "") or ""
            if "DeclarAI's intent classifier" in first:
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({
                                "labels": force_labels,
                                "confidence": "high",
                                "uncertain": False,
                                "decomposition": [{
                                    "segment": "test",
                                    "labels": force_labels,
                                }],
                                "reason": "forced golden label",
                            }),
                        },
                        "finish_reason": "stop",
                    }],
                    "usage": {"total_tokens": 8},
                }
            return {
                "choices": [{
                    "message": {"role": "assistant", "content": "Telemetry contract reply."},
                    "finish_reason": "stop",
                }],
                "usage": {"total_tokens": 12},
            }

        @contextmanager
        def fake_prompt_render(*, template_version=None, raw_rendered_prompt=None):
            class _Handle:
                def assembled(self, **kwargs):
                    return None
            yield _Handle()

        def fake_get_model_config(key):
            return {
                "provider": "engine",
                "model_id": "gemma4:26b",
                "display_name": "gemma4:26b",
                "supports_tools": False,
                "max_tokens": 1024,
                "temperature": 0.2,
            }

        monkeypatch.setattr(views, "_call_llm", fake_call_llm)
        monkeypatch.setattr(views, "set_span_attr", capture)
        monkeypatch.setattr(kb, "set_span_attr", capture)
        monkeypatch.setattr(retriever_mod, "set_span_attr", capture)
        monkeypatch.setattr(views, "prompt_render", fake_prompt_render)
        monkeypatch.setattr(views, "get_model_config", fake_get_model_config)
        monkeypatch.setattr(views, "cache_list_artifacts", lambda fid: [])
        monkeypatch.setattr(views, "set_session_id", lambda *a, **k: None)
        monkeypatch.setattr(views, "set_customer_id", lambda *a, **k: None)
        monkeypatch.setattr(views, "set_request_model", lambda *a, **k: None)

        @contextmanager
        def fake_model_route(*a, **k):
            class _H:
                def cost(self, **kwargs):
                    return None
            yield _H()

        monkeypatch.setattr(views, "model_route", fake_model_route)

        # Avoid nested Prometa retrieval CM noise; keep lexical retrieve real.
        @contextmanager
        def fake_retrieval_query(system, *, query_text, top_k, raw_retrieved=None):
            class _H:
                def results(self, **kwargs):
                    attrs["retrieval.system"] = system
                    attrs["retrieval.result_ids"] = list(kwargs.get("result_ids") or [])
            yield _H()

        monkeypatch.setattr(kb, "retrieval_query", fake_retrieval_query)
        monkeypatch.setattr(retriever_mod, "retrieval_query", fake_retrieval_query)

    @pytest.mark.parametrize(
        "case",
        SHOULD_RAG,
        ids=[c.case_id for c in SHOULD_RAG],
    )
    def test_should_rag_stamps_retrieval_telemetry(self, monkeypatch, case):
        from ai_assistant import views

        attrs: dict = {}
        self._patch(monkeypatch, force_labels=["A", "R"], attrs=attrs)

        out = views._chat_workflow(
            user_message=case.question,
            context=None,
            section="general",
            history=[],
            file_id=None,
            model=self.MODEL,
        )

        assert "R" in (out.get("intent_labels") or [])
        assert attrs.get("declarai.rag.in_prompt") is True
        assert attrs.get("declarai.rag.called") is True
        assert attrs.get("declarai.rag.result_count", 0) >= 1
        assert out.get("rag_sources"), "expected rag_sources when R retrieves docs"
        assert all("chunk_id" in s for s in out["rag_sources"])

    @pytest.mark.parametrize(
        "case",
        SHOULD_NOT_RAG,
        ids=[c.case_id for c in SHOULD_NOT_RAG],
    )
    def test_should_not_rag_skips_retrieval_telemetry(self, monkeypatch, case):
        from ai_assistant import views

        attrs: dict = {}
        self._patch(monkeypatch, force_labels=["C"], attrs=attrs)

        out = views._chat_workflow(
            user_message=case.question,
            context=None,
            section="general",
            history=[],
            file_id=None,
            model=self.MODEL,
        )

        assert "R" not in (out.get("intent_labels") or [])
        assert attrs.get("declarai.rag.called") is False
        assert attrs.get("declarai.rag.in_prompt") is False
        assert "rag_sources" not in out
