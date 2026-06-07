"""Intent classification for DeclarAI assistant chat turns.

Free-text turns are classified by an LLM before the assistant does retrieval,
tool use, or action proposal.  Regex/pattern matching is intentionally limited
to a narrow fallback used only when the classifier LLM explicitly reports
uncertainty or returns an unusable payload.  Button-triggered prompts can pass
trusted preclassified labels from the frontend; those labels bypass the LLM so
deterministic "Get AI Support" prompts do not spend extra tokens.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Iterable


CLASSIFIER_VERSION = "intent-v3-llm-rag"

INTENT_LABELS = ("A", "B", "C", "D", "E", "R")

INTENT_LABEL_NAMES = {
    "A": "general_information_gathering",
    "B": "pipeline_flow_information_gathering",
    "C": "current_status_information_gathering",
    "D": "configuration_editing_execution",
    "E": "flow_process_execution",
    "R": "knowledge_bank_rag_call",
}

INTENT_LABEL_DESCRIPTIONS = {
    "A": "General data-science or ML education not tied to the current flow.",
    "B": "General/default pipeline-flow mechanism explanation.",
    "C": "Current flow status, flags, configuration, results, or data inspection.",
    "D": "Edit/update flow configuration, parameters, metadata, or data.",
    "E": "Trigger a pipeline/process step, or move backward/forward in the flow.",
    "R": "Retrieve stable platform guidance, disclosure, glossary, or user-manual docs.",
}

_LABEL_SET = set(INTENT_LABELS)
_UNCERTAIN_CONFIDENCES = {"low", "uncertain", "unsure", "not_sure", "unknown"}


INTENT_CLASSIFIER_SYSTEM_PROMPT = """You are DeclarAI's intent classifier.

Classify the latest user message BEFORE any assistant retrieval, pipeline tool,
or executable action runs. Return JSON only; do not answer the user.

Labels are multi-label and canonical:
- A: general data-science or ML education not tied to current pipeline state.
- B: platform or default pipeline-flow explanation.
- C: current pipeline status, current metrics/results/settings/data inspection.
- D: edit/update configuration, metadata, parameters, feature usage, or data.
- E: execute/run/start/apply a pipeline process step.
- R: retrieve knowledge-bank docs for stable platform guidance, terminology,
     glossary, user manual, technical disclosure, assumptions, methodology, or
     "how the platform calculates/does X" questions.

Important routing rules:
- Use R for questions such as "how does this platform calculate VIF?",
  "what does PSI mean?", "show the manual/glossary", "technical disclosure",
  or "what assumptions/calculations are made?".
- Use C when the user asks for live/current loaded-data artifacts, current
  scores, current selected features, current SFS rows, or current settings.
- Use both C and R when the user asks for a definition/methodology AND current
  pipeline values.
- Use D/E for actionable modification or execution requests.
- If you are not sure, set uncertain=true, confidence="low", and labels=[].

JSON schema:
{
  "labels": ["A", "R"],
  "confidence": "high" | "medium" | "low",
  "uncertain": false,
  "decomposition": [
    {"segment": "user clause", "labels": ["A", "R"]}
  ],
  "reason": "short private routing rationale"
}
"""


def normalize_intent_labels(labels) -> list[str]:
    """Return unique known labels in canonical order, ignoring invalid input."""
    if labels is None:
        return []
    if isinstance(labels, str):
        text = labels
        for sep in (",", ";", "|", "\n", "\t"):
            text = text.replace(sep, " ")
        raw = text.split()
    elif isinstance(labels, Iterable):
        raw = list(labels)
    else:
        raw = []

    seen = set()
    for item in raw:
        label = str(item or "").strip().upper()
        if label in _LABEL_SET:
            seen.add(label)
    return [label for label in INTENT_LABELS if label in seen]


def build_intent_classifier_messages(user_message: str,
                                     *,
                                     section: str = "",
                                     context: dict | None = None) -> list[dict]:
    """Build the compact LLM classifier prompt."""
    context_keys = []
    if isinstance(context, dict):
        context_keys = sorted(str(k) for k in context.keys())[:30]
    payload = {
        "user_message": user_message or "",
        "current_section": section or "general",
        "has_pipeline_context": bool(context),
        "context_keys": context_keys,
    }
    return [
        {"role": "system", "content": INTENT_CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def resolve_intent_classification(
    user_message: str,
    *,
    section: str = "",
    context: dict | None = None,
    preclassified_labels=None,
    preclassified_source: str | None = None,
    llm_classifier: Callable[[list[dict]], str | dict] | None = None,
) -> dict:
    """Resolve intent labels, preferring trusted preclassified button labels."""
    labels = normalize_intent_labels(preclassified_labels)
    if labels:
        source = (preclassified_source or "preclassified").strip() or "preclassified"
        return _build_result(
            labels=labels,
            source=source,
            preclassified=True,
            decomposition=[{
                "segment": f"preclassified:{source}",
                "labels": labels,
            }],
            confidence="high",
            uncertain=False,
        )

    return classify_query_intents(
        user_message,
        section=section,
        context=context or {},
        llm_classifier=llm_classifier,
    )


def classify_query_intents(
    user_message: str,
    *,
    section: str = "",
    context: dict | None = None,
    llm_classifier: Callable[[list[dict]], str | dict] | None = None,
) -> dict:
    """Classify a free-text user message using the LLM classifier."""
    messages = build_intent_classifier_messages(
        user_message,
        section=section,
        context=context or {},
    )

    if llm_classifier is None:
        return _build_result(
            labels=["A"],
            source="llm_classifier_unavailable",
            preclassified=False,
            decomposition=[{"segment": user_message or "", "labels": ["A"]}],
            confidence="low",
            uncertain=True,
            fallback_reason="no_llm_classifier",
        )

    raw = llm_classifier(messages)
    parsed = parse_llm_intent_response(raw)
    if _llm_payload_is_uncertain(parsed):
        return _definite_pattern_fallback(
            user_message,
            reason=parsed.get("fallback_reason") or "llm_uncertain",
        )

    labels = normalize_intent_labels(parsed.get("labels"))
    decomposition = _normalize_decomposition(
        parsed.get("decomposition") or parsed.get("segments"),
        default_segment=user_message,
        default_labels=labels,
    )
    return _build_result(
        labels=labels,
        source="llm_classifier",
        preclassified=False,
        decomposition=decomposition,
        confidence=_normalize_confidence(parsed.get("confidence")) or "medium",
        uncertain=False,
        reason=str(parsed.get("reason") or "")[:500],
    )


def parse_llm_intent_response(raw) -> dict:
    """Parse the classifier LLM response into a dict.

    Accepts either an already-decoded dict or a string containing a JSON object.
    No regex is used here; fallback regex is reserved for uncertain decisions.
    """
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {"uncertain": True, "fallback_reason": "empty_llm_response"}
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {"uncertain": True, "fallback_reason": "missing_json_object"}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {"uncertain": True, "fallback_reason": "invalid_json"}


def _build_result(*, labels: list[str], source: str,
                  preclassified: bool, decomposition: list[dict],
                  confidence: str | None = None,
                  uncertain: bool = False,
                  fallback_reason: str | None = None,
                  reason: str = "") -> dict:
    labels = normalize_intent_labels(labels) or ["A"]
    return {
        "labels": labels,
        "label_names": [INTENT_LABEL_NAMES[label] for label in labels],
        "source": source,
        "preclassified": preclassified,
        "classifier_version": CLASSIFIER_VERSION,
        "confidence": confidence or ("low" if uncertain else "medium"),
        "uncertain": bool(uncertain),
        "fallback_reason": fallback_reason or "",
        "reason": reason,
        "decomposition": decomposition,
    }


def _normalize_decomposition(raw, *,
                             default_segment: str,
                             default_labels: list[str]) -> list[dict]:
    if not isinstance(raw, list):
        return [{"segment": default_segment or "", "labels": default_labels}]
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        labels = normalize_intent_labels(item.get("labels"))
        if labels:
            out.append({
                "segment": str(item.get("segment") or default_segment or ""),
                "labels": labels,
            })
    return out or [{"segment": default_segment or "", "labels": default_labels}]


def _normalize_confidence(value) -> str:
    confidence = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if confidence in {"high", "medium", "low"}:
        return confidence
    if confidence in _UNCERTAIN_CONFIDENCES:
        return "low"
    return ""


def _llm_payload_is_uncertain(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return True
    confidence = str(payload.get("confidence") or "").strip().lower()
    labels = normalize_intent_labels(payload.get("labels"))
    return (
        bool(payload.get("uncertain"))
        or confidence in _UNCERTAIN_CONFIDENCES
        or not labels
    )


_DEFINITE_EXECUTION_RE = re.compile(
    r"\b(start|run|apply|execute|trigger|kick off|train)\b.*\b("
    r"sfs|modeling|model|encoding|preprocessing|purifier|hyperparameter|tuning"
    r")\b",
    re.IGNORECASE,
)

_DEFINITE_EDIT_RE = re.compile(
    r"\b(set|change|update|edit|configure|adjust|drop|exclude|include|select|choose)\b"
    r".*\b(max_features|min_features|top_k|n_jobs|feature|column|algorithm|"
    r"setting|settings|config|threshold|model_usage|feature_usage)\b",
    re.IGNORECASE,
)

_DEFINITE_RAG_RE = re.compile(
    r"\b(how (do|does|is)|what (is|does)|define|explain)\b.*\b("
    r"calculate|calculated|calculating|calculation|formula|methodology|meaning|"
    r"mean|vif|psi|csi|shap|auc|pr-auc|roc-auc|manual|glossary|knowledge bank|"
    r"documentation|technical disclosure|platform"
    r")\b",
    re.IGNORECASE,
)

_DEFINITE_CURRENT_RE = re.compile(
    r"\b(current|status|result|results|my|this|these|our|show|analyze|review)\b"
    r".*\b(sfs|selected features|shap|vif|psi|metric|metrics|score|scores|"
    r"data quality|encoding plan)\b",
    re.IGNORECASE,
)

_DEFINITE_PLATFORM_FLOW_RE = re.compile(
    r"\b(platform|pipeline|flow|workflow|step|stage|preprocessing|encoding|"
    r"modeling|sfs|hyperparameter)\b",
    re.IGNORECASE,
)


def _definite_pattern_fallback(user_message: str, *, reason: str) -> dict:
    """Very narrow fallback used only after LLM uncertainty/unusable output."""
    text = user_message or ""
    labels = set()
    if _DEFINITE_EDIT_RE.search(text):
        labels.add("D")
    if _DEFINITE_EXECUTION_RE.search(text):
        labels.add("E")
    if _DEFINITE_CURRENT_RE.search(text):
        labels.add("C")
    if _DEFINITE_RAG_RE.search(text):
        labels.add("R")
        if not labels.intersection({"A", "B", "C"}):
            labels.add("B" if _DEFINITE_PLATFORM_FLOW_RE.search(text) else "A")

    ordered = [label for label in INTENT_LABELS if label in labels] or ["A"]
    return _build_result(
        labels=ordered,
        source="definite_regex_fallback",
        preclassified=False,
        decomposition=[{"segment": text, "labels": ordered}],
        confidence="low",
        uncertain=True,
        fallback_reason=reason,
    )
