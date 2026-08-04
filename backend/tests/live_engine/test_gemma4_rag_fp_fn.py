"""Live gemma4:26b RAG intent FP/FN evaluation + telemetry cross-check.

Run (requires a reachable Inference Engine with gemma4:26b)::

    cd backend && python -m pytest -m live_engine -q \\
        tests/live_engine/test_gemma4_rag_fp_fn.py --tb=short

Not included in default pre-commit markers (unit/functional/…).
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from tests.live_engine.conftest import ENGINE_MODEL_KEY
from tests.rag_intent_goldens import (
    ALL_CASES,
    RagIntentCase,
    confusion_bucket,
)


pytestmark = [
    pytest.mark.live_engine,
    pytest.mark.timeout(180),
]


def _patch_span_capture(monkeypatch, attrs: dict) -> None:
    from ai_assistant import knowledge_bank as kb
    from ai_assistant import views
    from ai_assistant.rag import retriever as retriever_mod

    def capture(key, value):
        attrs[key] = value

    monkeypatch.setattr(views, "set_span_attr", capture)
    monkeypatch.setattr(kb, "set_span_attr", capture)
    monkeypatch.setattr(retriever_mod, "set_span_attr", capture)


def _patch_answer_llm_only(monkeypatch) -> None:
    """Keep live gemma for intent classification; stub the chat answer call."""
    from ai_assistant import views

    real_call_llm = views._call_llm

    def selective_call(messages, model_key, tools=None):
        first = (messages[0].get("content") if messages else "") or ""
        if "DeclarAI's intent classifier" in first:
            return real_call_llm(messages, model_key, tools=None)
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Live gemma RAG FP/FN probe reply.",
                },
                "finish_reason": "stop",
            }],
            "usage": {"total_tokens": 16},
        }

    monkeypatch.setattr(views, "_call_llm", selective_call)


def _patch_workflow_noise(monkeypatch) -> None:
    from ai_assistant import knowledge_bank as kb
    from ai_assistant import views
    from ai_assistant.rag import retriever as retriever_mod
    from django.conf import settings

    monkeypatch.setattr(settings, "RAG_MODE", "lexical", raising=False)
    monkeypatch.setenv("RAG_MODE", "lexical")
    # Prefer lexical path so live FP/FN does not require OpenAI embeddings.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "", raising=False)

    @contextmanager
    def fake_prompt_render(*, template_version=None, raw_rendered_prompt=None):
        class _Handle:
            def assembled(self, **kwargs):
                return None
        yield _Handle()

    monkeypatch.setattr(views, "prompt_render", fake_prompt_render)
    monkeypatch.setattr(views, "cache_list_artifacts", lambda fid: [])
    monkeypatch.setattr(views, "set_session_id", lambda *a, **k: None)
    monkeypatch.setattr(views, "set_customer_id", lambda *a, **k: None)

    @contextmanager
    def recording_retrieval_query(
        system, *, query_text, top_k, namespace=None, raw_retrieved=None,
    ):
        class _Handle:
            def results(self, **kwargs):
                return None
        yield _Handle()

    monkeypatch.setattr(kb, "retrieval_query", recording_retrieval_query)
    monkeypatch.setattr(retriever_mod, "retrieval_query", recording_retrieval_query)


def _run_case(monkeypatch, case: RagIntentCase, model_key: str) -> dict:
    from ai_assistant import views

    attrs: dict = {}
    _patch_span_capture(monkeypatch, attrs)
    _patch_workflow_noise(monkeypatch)
    _patch_answer_llm_only(monkeypatch)

    out = views._chat_workflow(
        user_message=case.question,
        context=None,
        section="general",
        history=[],
        file_id=None,
        model=model_key,
    )
    labels = list(out.get("intent_labels") or [])
    predicted_rag = "R" in labels
    bucket = confusion_bucket(
        should_rag=case.should_rag,
        predicted_rag=predicted_rag,
    )
    return {
        "case_id": case.case_id,
        "question": case.question,
        "should_rag": case.should_rag,
        "predicted_rag": predicted_rag,
        "labels": labels,
        "bucket": bucket,
        "strict": case.strict,
        "intent_source": attrs.get("declarai.intent.source"),
        "intent_labels_attr": attrs.get("declarai.intent.labels"),
        "rag_called": attrs.get("declarai.rag.called"),
        "rag_in_prompt": attrs.get("declarai.rag.in_prompt"),
        "rag_result_count": attrs.get("declarai.rag.result_count"),
        "rag_sources": out.get("rag_sources"),
        "message": (out.get("message") or "")[:120],
        "attrs": attrs,
        "out": out,
    }


def _assert_telemetry_matches_prediction(row: dict) -> None:
    """Cross-check Prometa/declarai.rag attrs against predicted R label."""
    if row["predicted_rag"]:
        assert row["rag_called"] is True, (
            f"{row['case_id']}: predicted R but declarai.rag.called={row['rag_called']!r}"
        )
        assert row["rag_in_prompt"] is True, (
            f"{row['case_id']}: predicted R but declarai.rag.in_prompt="
            f"{row['rag_in_prompt']!r}"
        )
        assert row["rag_sources"], (
            f"{row['case_id']}: predicted R but response missing rag_sources"
        )
        assert (row["rag_result_count"] or 0) >= 1
    else:
        assert row["rag_called"] is False, (
            f"{row['case_id']}: no R but declarai.rag.called={row['rag_called']!r}"
        )
        assert row["rag_in_prompt"] is False, (
            f"{row['case_id']}: no R but declarai.rag.in_prompt="
            f"{row['rag_in_prompt']!r}"
        )
        assert not row["rag_sources"], (
            f"{row['case_id']}: no R but rag_sources present: {row['rag_sources']}"
        )


@pytest.mark.parametrize(
    "case",
    ALL_CASES,
    ids=[c.case_id for c in ALL_CASES],
)
def test_gemma4_rag_intent_case(monkeypatch, require_gemma4_26b, case):
    """Per-question live classify + RAG gate + telemetry cross-check."""
    row = _run_case(monkeypatch, case, require_gemma4_26b)

    # Telemetry must always agree with whatever gemma predicted.
    _assert_telemetry_matches_prediction(row)

    # Intent attrs stamped for the model route under test.
    assert row["intent_labels_attr"], row
    assert ENGINE_MODEL_KEY == require_gemma4_26b

    if case.strict:
        assert row["bucket"] in {"TP", "TN"}, (
            f"gemma4:26b {row['bucket']} on strict case {case.case_id}: "
            f"should_rag={case.should_rag} predicted_rag={row['predicted_rag']} "
            f"labels={row['labels']} source={row['intent_source']} "
            f"question={case.question!r}"
        )


@pytest.mark.timeout(900)
def test_gemma4_rag_confusion_matrix_summary(monkeypatch, require_gemma4_26b):
    """Single-pass aggregate over all goldens — prints TP/TN/FP/FN + telemetry.

    Run::

        pytest -m live_engine -k confusion_matrix -s --tb=line
    """
    rows = [_run_case(monkeypatch, case, require_gemma4_26b) for case in ALL_CASES]

    for row in rows:
        _assert_telemetry_matches_prediction(row)

    counts = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    for row in rows:
        counts[row["bucket"]] += 1

    strict_errors = [
        row for row in rows
        if row["strict"] and row["bucket"] in {"FP", "FN"}
    ]

    summary = {
        "model": require_gemma4_26b,
        "counts": counts,
        "rows": [
            {
                "case_id": r["case_id"],
                "bucket": r["bucket"],
                "should_rag": r["should_rag"],
                "predicted_rag": r["predicted_rag"],
                "labels": r["labels"],
                "rag_called": r["rag_called"],
                "rag_in_prompt": r["rag_in_prompt"],
                "rag_result_count": r["rag_result_count"],
                "sources": [
                    s.get("source") for s in (r["rag_sources"] or [])
                ],
            }
            for r in rows
        ],
    }
    print("\n=== gemma4:26b RAG intent confusion ===")
    print(json.dumps(summary, indent=2))

    assert not strict_errors, (
        "Strict FP/FN failures for gemma4:26b:\n"
        + "\n".join(
            f"  {r['bucket']} {r['case_id']}: labels={r['labels']} "
            f"q={r['question']!r}"
            for r in strict_errors
        )
    )
    assert counts["TP"] + counts["FN"] == len([c for c in ALL_CASES if c.should_rag])
    assert counts["TN"] + counts["FP"] == len([c for c in ALL_CASES if not c.should_rag])


def test_gemma4_classifies_via_engine_model_id(monkeypatch, require_gemma4_26b):
    """Smoke: classifier path really hits engine-gemma4-26b (not cloud fallback)."""
    from ai_assistant import views

    seen: dict = {"model_keys": []}
    real = views._call_llm

    def tracking(messages, model_key, tools=None):
        seen["model_keys"].append(model_key)
        first = (messages[0].get("content") if messages else "") or ""
        if "DeclarAI's intent classifier" in first:
            return real(messages, model_key, tools=None)
        return {
            "choices": [{
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }],
            "usage": {"total_tokens": 4},
        }

    attrs: dict = {}
    _patch_span_capture(monkeypatch, attrs)
    _patch_workflow_noise(monkeypatch)
    monkeypatch.setattr(views, "_call_llm", tracking)

    views._chat_workflow(
        user_message="What does PSI mean?",
        context=None,
        section="general",
        history=[],
        file_id=None,
        model=require_gemma4_26b,
    )

    assert seen["model_keys"], "expected at least one _call_llm invocation"
    assert seen["model_keys"][0] == require_gemma4_26b
    assert "R" in str(attrs.get("declarai.intent.labels", ""))
