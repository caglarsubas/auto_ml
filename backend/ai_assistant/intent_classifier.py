"""Intent classification for DeclarAI assistant chat turns.

The classifier is intentionally deterministic.  It runs before the chat LLM
does any tool use or action proposal, and it avoids spending a second LLM call
just to label traces.  Button-triggered prompts can pass preclassified labels
from the frontend; those labels are normalized here and used directly.
"""
from __future__ import annotations

import re
from typing import Iterable


CLASSIFIER_VERSION = "intent-v2-rag"

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


def normalize_intent_labels(labels) -> list[str]:
    """Return unique known labels in canonical order, ignoring invalid input."""
    if labels is None:
        return []
    if isinstance(labels, str):
        raw = re.split(r"[\s,;|]+", labels.strip())
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


def resolve_intent_classification(user_message: str,
                                  *,
                                  section: str = "",
                                  context: dict | None = None,
                                  preclassified_labels=None,
                                  preclassified_source: str | None = None) -> dict:
    """Resolve intent labels, preferring trusted preclassified button labels.

    Returns a small dict suitable for both API responses and span attributes.
    """
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
        )

    return classify_query_intents(
        user_message,
        section=section,
        context=context or {},
    )


def classify_query_intents(user_message: str,
                           *,
                           section: str = "",
                           context: dict | None = None) -> dict:
    """Classify a free-text user message into one or more intent labels.

    The implementation decomposes compound requests into short clauses, labels
    each clause, then unions the results in canonical order.
    """
    text = (user_message or "").strip()
    segments = _decompose_query(text)
    section_key = (section or "").strip().lower()
    has_context = bool(context)

    segment_results = []
    found = set()
    for segment in segments:
        labels = _classify_segment(segment, section=section_key, has_context=has_context)
        for label in labels:
            found.add(label)
        segment_results.append({
            "segment": segment,
            "labels": labels,
        })

    if not found:
        found.add("A")

    labels = [label for label in INTENT_LABELS if label in found]
    return _build_result(
        labels=labels,
        source="deterministic_classifier",
        preclassified=False,
        decomposition=segment_results,
    )


def _build_result(*, labels: list[str], source: str,
                  preclassified: bool, decomposition: list[dict]) -> dict:
    return {
        "labels": labels,
        "label_names": [INTENT_LABEL_NAMES[label] for label in labels],
        "source": source,
        "preclassified": preclassified,
        "classifier_version": CLASSIFIER_VERSION,
        "decomposition": decomposition,
    }


def _decompose_query(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(
        r"(?:[.!?;\n]+|\b(?:and then|then|also|plus|and)\b)",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = [p.strip(" \t\r\n,:") for p in parts if p and p.strip(" \t\r\n,:")]
    return cleaned or [text]


_FLOW_TERMS_RE = re.compile(
    r"\b("
    r"pipeline|flow|workflow|step|stage|process|preprocessing|preprocess|"
    r"purifier|data quality|encoding|modeling|model training|sfs|"
    r"sequential feature selection|feature selection|hyperparameter|tuning"
    r")\b",
    re.IGNORECASE,
)

_CURRENT_TERMS_RE = re.compile(
    r"\b("
    r"current|ongoing|now|status|state|progress|result|results|summary|"
    r"metric|metrics|score|scores|value|values|row|rows|column|columns|"
    r"flag|flags|configuration|config|setting|settings|"
    r"selected feature|selected features|encoding plan|purifier summary|"
    r"modeling status|sfs status|what happened|how many|which feature|"
    r"which features|show|review|analyze|interpret|compare"
    r")\b",
    re.IGNORECASE,
)

_FLOW_INFO_RE = re.compile(
    r"\b("
    r"how does|how do|how should|how is|explain|what are|what is|"
    r"default|mechanism|sequence|order|steps|stages|flow|workflow|pipeline"
    r")\b",
    re.IGNORECASE,
)

_CONFIG_EDIT_RE = re.compile(
    r"\b("
    r"set|change|update|edit|modify|configure|adjust|switch|select|choose|"
    r"drop|keep|exclude|include|mark|unmark|rank|rename|create|derive|add|"
    r"remove|delete|save|clear|tighten|relax|replace|use|implement"
    r")\b",
    re.IGNORECASE,
)

_EXECUTION_RE = re.compile(
    r"\b("
    r"run|start|apply|trigger|execute|kick off|launch|resume|continue|stop|"
    r"rerun|restart|move|go|proceed|advance|next step|previous step|"
    r"step back|go back|train|preprocess|encode|tune|optimize"
    r")\b",
    re.IGNORECASE,
)

_GENERAL_INFO_RE = re.compile(
    r"\b("
    r"what is|what does|explain|teach|define|why|when should|best practice|"
    r"rule of thumb|data science|machine learning|statistics|statistical|"
    r"roc-auc|pr-auc|auc|psi|csi|vif|shap|woe|iv|xgboost|lightgbm|catboost"
    r")\b",
    re.IGNORECASE,
)

_RAG_TERMS_RE = re.compile(
    r"\b("
    r"rag|knowledge bank|manual|user manual|guide|guideline|documentation|docs|"
    r"glossary|terminology|term|terms|abbreviation|abbreviations|definition|"
    r"define|disclosure|assumption|assumptions|calculation|calculations|"
    r"formula|formulas|methodology|rationale|capabilities|how to use|"
    r"assistant usage|settings|configurations"
    r")\b",
    re.IGNORECASE,
)


def _classify_segment(segment: str, *, section: str, has_context: bool) -> list[str]:
    lower = segment.lower()
    labels = set()

    has_flow_term = bool(_FLOW_TERMS_RE.search(segment))
    has_current_term = bool(_CURRENT_TERMS_RE.search(segment))
    has_flow_info = bool(_FLOW_INFO_RE.search(segment)) and has_flow_term
    has_config_edit = bool(_CONFIG_EDIT_RE.search(segment))
    has_execution = bool(_EXECUTION_RE.search(segment))
    has_general_info = bool(_GENERAL_INFO_RE.search(segment))
    has_direct_rag_term = bool(_RAG_TERMS_RE.search(segment))
    has_explicit_current_anchor = bool(re.search(
        r"\b(current|ongoing|now|status|state|progress|result|results|my|this|these|our)\b",
        lower,
    ))
    is_doc_only_query = has_direct_rag_term and not has_explicit_current_anchor
    section_is_pipeline = bool(section and section != "general")

    if has_execution and (has_flow_term or section_is_pipeline):
        labels.add("E")

    if has_config_edit and (
        has_flow_term
        or section_is_pipeline
        or re.search(
            r"\b(config|setting|parameter|threshold|feature|column|note|"
            r"ranking|algorithm|max_features|min_features|top_k|n_jobs)\b",
            lower,
        )
    ):
        labels.add("D")

    is_command = has_config_edit or has_execution
    if (
        not is_command
        and not is_doc_only_query
        and (
            has_current_term
            or (section_is_pipeline and (has_context or has_flow_term))
            or (re.search(r"\b(my|this|these|our)\b", lower) and has_flow_term)
        )
    ):
        labels.add("C")

    if has_flow_info and not labels.intersection({"C", "D", "E"}):
        labels.add("B")

    if has_general_info and not labels.intersection({"B", "C", "D", "E"}):
        labels.add("A")

    if _should_call_knowledge_bank(
        has_direct_rag_term=has_direct_rag_term,
        has_general_info=has_general_info,
        has_flow_info=has_flow_info,
        has_current_term=has_current_term,
        has_config_edit=has_config_edit,
        has_execution=has_execution,
    ):
        labels.add("R")

    return [label for label in INTENT_LABELS if label in labels]


def _should_call_knowledge_bank(*,
                                has_direct_rag_term: bool,
                                has_general_info: bool,
                                has_flow_info: bool,
                                has_current_term: bool,
                                has_config_edit: bool,
                                has_execution: bool) -> bool:
    """Return True when stable docs should be retrieved for this segment."""
    if has_config_edit or has_execution:
        return False
    if has_direct_rag_term:
        return True
    if has_current_term:
        return False
    return has_general_info or has_flow_info
