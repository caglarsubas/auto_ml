"""Golden questions for RAG intent routing (should_rag True/False).

Used by:
- unit telemetry contract tests (mocked classifier)
- live_engine gemma4:26b FP/FN evaluation

``should_rag`` means label ``R`` is expected on the intent result.
A false positive (FP) is predicted R when should_rag is False.
A false negative (FN) is missing R when should_rag is True.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RagIntentCase:
    case_id: str
    question: str
    should_rag: bool
    category: str
    # Strict cases fail the live suite on mismatch; soft cases are reported
    # but do not fail (borderline / multi-label ambiguity).
    strict: bool = True
    notes: str = ""


# Questions that SHOULD trigger knowledge-bank retrieval (missing R = FN).
SHOULD_RAG: tuple[RagIntentCase, ...] = (
    RagIntentCase(
        "psi_definition",
        "What does PSI mean?",
        True,
        "glossary",
        notes="terminology glossary",
    ),
    RagIntentCase(
        "vif_platform_calc",
        "How does this platform calculate feature-wise VIF?",
        True,
        "methodology",
        notes="technical disclosure / methodology",
    ),
    RagIntentCase(
        "assistant_usage",
        "How should I use the assistant actions?",
        True,
        "manual",
        notes="assistant usage guide",
    ),
    RagIntentCase(
        "purifier_assumptions",
        "What assumptions does the data purifier make?",
        True,
        "disclosure",
    ),
    RagIntentCase(
        "sfs_stopping",
        "Explain SFS stopping criteria in DeclarAI.",
        True,
        "methodology",
    ),
    RagIntentCase(
        "governance_checklist",
        "Give me the model governance review checklist before export.",
        True,
        "governance",
    ),
    RagIntentCase(
        "pipeline_stages_manual",
        "What are the pipeline stages in the platform user manual?",
        True,
        "manual",
    ),
    RagIntentCase(
        "shap_glossary",
        "What is SHAP according to the platform glossary?",
        True,
        "glossary",
    ),
    RagIntentCase(
        "mixed_def_and_current",
        "Explain what PSI means and show which current variables have high PSI.",
        True,
        "mixed",
        notes="expects R (and usually C); R must be present",
    ),
)

# Questions that should NOT trigger RAG (predicted R = FP).
SHOULD_NOT_RAG: tuple[RagIntentCase, ...] = (
    RagIntentCase(
        "current_selected_features",
        "What are my currently selected features?",
        False,
        "live_status",
    ),
    RagIntentCase(
        "current_sfs_results",
        "Analyze the current SFS results for this file.",
        False,
        "live_status",
    ),
    RagIntentCase(
        "current_auc",
        "What is the current model ROC-AUC on the test set?",
        False,
        "live_status",
    ),
    RagIntentCase(
        "start_modeling",
        "Start modeling with the selected algorithm now.",
        False,
        "execution",
        notes="E — execute, not documentation",
    ),
    RagIntentCase(
        "drop_feature",
        "Set Var_17 feature usage to drop.",
        False,
        "config_edit",
        notes="D — configuration edit",
    ),
    RagIntentCase(
        "apply_encoding",
        "Apply the encoding plan for me.",
        False,
        "execution",
    ),
    RagIntentCase(
        "current_purifier_options",
        "Which purifier options are currently selected in my pipeline?",
        False,
        "live_status",
    ),
    RagIntentCase(
        "current_notes",
        "Show the notes I already saved on this pipeline run.",
        False,
        "live_status",
    ),
)

ALL_CASES: tuple[RagIntentCase, ...] = SHOULD_RAG + SHOULD_NOT_RAG
STRICT_CASES: tuple[RagIntentCase, ...] = tuple(c for c in ALL_CASES if c.strict)


def confusion_bucket(*, should_rag: bool, predicted_rag: bool) -> str:
    if should_rag and predicted_rag:
        return "TP"
    if (not should_rag) and (not predicted_rag):
        return "TN"
    if (not should_rag) and predicted_rag:
        return "FP"
    return "FN"
