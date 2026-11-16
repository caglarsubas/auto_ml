"""Deterministic assessment calculations shared by the worker and offline replay."""

import numpy as np
import pandas as pd

from deployment.native_candidate import canonical, sha
from modeling.declared_metric import metric_value
from modeling.development_assessment import development_metrics


CHUNK_SIZE = 500


class AssessmentReplayError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _population(frame, development, validation, as_of):
    strategy = validation["strategy"]
    group = validation.get("group_column")
    if group:
        development_entities, assessment_entities = development[group], frame[group]
        if (
            development_entities.isna().any()
            or assessment_entities.isna().any()
            or pd.api.types.is_numeric_dtype(development_entities) != pd.api.types.is_numeric_dtype(assessment_entities)
            or assessment_entities.isin(development_entities).any()
        ):
            raise AssessmentReplayError("native_assessment_entities_overlap_or_unverified")
    if strategy == "oot":
        date, end = validation["date_column"], validation.get("label_end_column", validation["date_column"])
        train_end = pd.to_datetime(development[end], errors="coerce", utc=True)
        held_date = pd.to_datetime(frame[date], errors="coerce", utc=True)
        held_end = pd.to_datetime(frame[end], errors="coerce", utc=True)
        if (
            train_end.isna().any()
            or held_date.isna().any()
            or held_end.isna().any()
            or train_end.max() >= held_date.min()
            or (held_end < held_date).any()
            or held_end.max() > pd.Timestamp(as_of)
        ):
            raise AssessmentReplayError("native_assessment_time_or_maturity_invalid")
    return {
        "strategy": strategy,
        "entity_separation_checked": bool(group),
        "outcome_window_checked": strategy == "oot",
        "row_identity": "reviewer_declared; unknown upstream or modified imports are not linked automatically",
    }


def calculate_assessment(frame, development, validation, as_of, contract, metric, features, predict, *, check=lambda: None):
    """Recompute aggregate evidence on already admitted frames without authority or custody effects."""
    population = _population(frame, development, validation, as_of)
    target = contract["target_column"]
    if target in features:
        raise AssessmentReplayError("native_assessment_feature_contract_invalid")
    labels = frame[target]
    if labels.isna().any():
        raise AssessmentReplayError("native_assessment_labels_missing")
    if contract["task"] == "regression":
        labels = pd.to_numeric(labels, errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(labels).all():
            raise AssessmentReplayError("native_assessment_labels_invalid")
    else:
        mapping = {str(c["label"]): c["encoded"] for c in contract["class_mapping"]}
        labels = labels.astype(str).map(mapping)
        if labels.isna().any():
            raise AssessmentReplayError("native_assessment_labels_invalid")
        labels = labels.to_numpy(dtype=int)
    scores = predict(frame[features].to_csv(index=False).encode())
    check()
    try:
        primary = metric_value(metric, labels, scores)
    except ValueError:
        raise AssessmentReplayError("native_assessment_primary_metric_unavailable") from None
    metrics = development_metrics(labels, scores, contract["task"], len(contract["class_mapping"]), metric["cost_matrix"])
    check()
    return {
        "n_assessed": len(frame),
        "population_checks": population,
        "primary_value": primary,
        "metrics": metrics,
        "scores_sha256": sha(canonical(scores)),
    }
