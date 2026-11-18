"""Descriptive paired comparisons of scores from the same development folds."""

import math


_LIMITATIONS = [
    "Every matched fold has equal weight, matching native development selection. "
    "The metric is calculated separately within each fold.",
    "The sensitivity range recalculates the recorded comparison after omitting each validation fold. "
    "The models are held fixed.",
    "Training sets may overlap and observations within groups or neighboring time periods can be dependent. "
    "Sampling uncertainty is unavailable from these fold scores.",
    "Development scores may inform model selection. The comparison provides exploratory evidence.",
]


def _rows(provenance, partition):
    rows = provenance.get(partition)
    if (not isinstance(rows, list) or not rows or
            any(type(row) is not int or row < 0 for row in rows) or len(set(rows)) != len(rows)):
        return None
    return rows


def _finite_score(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _fold_mean(folds, key):
    return math.fsum(row[key] / len(folds) for row in folds)


def compare_paired_folds(reference_folds, candidate_folds, *, metric, validation):
    """Describe a candidate-minus-reference effect in the trusted metric's units.

    Both inputs are fold records from one accepted development plan. Each
    contains a metric score and the ordered train/validation row provenance.
    The caller binds the inputs to the same metric, plan and source; row numbers
    alone cannot establish those identities across plans.
    """
    metric = metric if isinstance(metric, dict) else {}
    validation = validation if isinstance(validation, dict) else {}
    name, direction = metric.get("primary_metric"), metric.get("direction")
    strategy, n_splits = validation.get("strategy"), validation.get("n_splits")
    record = {
        "schema_version": 1,
        "scope": "paired_development_fold_diagnostic",
        "status": "unavailable",
        "metric": name if isinstance(name, str) else None,
        "direction": direction if direction in ("maximize", "minimize") else None,
        "validation_strategy": strategy if strategy in ("random", "group", "oot") else None,
        "fold_pairs": [],
        "effect": None,
        "sensitivity": None,
        "sampling_uncertainty": {"status": "unavailable", "reason_code": "comparison_unavailable"},
        "limitations": list(_LIMITATIONS),
    }

    def unavailable(code):
        return {**record, "reason_code": code}

    if not record["metric"] or not record["direction"]:
        return unavailable("unsupported_metric")
    if (not record["validation_strategy"] or type(n_splits) is not int or n_splits not in (2, 3)
            or (strategy == "group" and not validation.get("group_column"))
            or (strategy == "oot" and not validation.get("date_column"))):
        return unavailable("unsupported_validation")
    if not isinstance(reference_folds, list) or not isinstance(candidate_folds, list):
        return unavailable("invalid_fold_evidence")
    if len(reference_folds) != n_splits or len(candidate_folds) != n_splits:
        return unavailable("incomplete_fold_pairs")

    sign = 1 if direction == "maximize" else -1
    seen_validation_rows = set()
    pairs = []
    for fold, (reference, candidate) in enumerate(zip(reference_folds, candidate_folds), 1):
        if not isinstance(reference, dict) or not isinstance(candidate, dict):
            return unavailable("invalid_fold_evidence")
        left, right = reference.get("preprocessing"), candidate.get("preprocessing")
        if not isinstance(left, dict) or not isinstance(right, dict):
            return unavailable("invalid_fold_membership")
        train, valid = _rows(left, "train_rows"), _rows(left, "valid_rows")
        other_train, other_valid = _rows(right, "train_rows"), _rows(right, "valid_rows")
        if (train is None or len(train) < 2 or valid is None or other_train is None or other_valid is None
                or not set(train).isdisjoint(valid)):
            return unavailable("invalid_fold_membership")
        if train != other_train or valid != other_valid:
            return unavailable("unmatched_fold_membership")
        if not seen_validation_rows.isdisjoint(valid):
            return unavailable("overlapping_validation_folds")
        seen_validation_rows.update(valid)

        baseline, trial = reference.get("score"), candidate.get("score")
        if not _finite_score(baseline) or not _finite_score(trial):
            return unavailable("unavailable_fold_metric")
        difference = float(trial) - float(baseline)
        if not math.isfinite(difference):
            return unavailable("unavailable_fold_metric")
        # PostgreSQL JSONB normalizes signed zero. Store a stable receipt for ties.
        improvement = sign * difference + 0.0
        pairs.append({
            "fold": fold, "n_validation_rows": len(valid),
            "reference_score": float(baseline), "candidate_score": float(trial),
            "difference": difference, "improvement": improvement,
        })

    try:
        difference = _fold_mean(pairs, "difference")
        mean_reference = _fold_mean(pairs, "reference_score")
        mean_candidate = _fold_mean(pairs, "candidate_score")
        omissions = [
            {"omitted_fold": fold["fold"],
             "improvement": _fold_mean(pairs[:index] + pairs[index + 1:], "improvement")}
            for index, fold in enumerate(pairs)
        ]
    except OverflowError:
        return unavailable("unavailable_fold_metric")
    return {
        **record,
        "status": "completed",
        "fold_pairs": pairs,
        "effect": {
            "method": "equal_weight_matched_fold_mean",
            "n_validation_rows": len(seen_validation_rows),
            "reference_score": mean_reference,
            "candidate_score": mean_candidate,
            "difference": difference,
            "improvement": _fold_mean(pairs, "improvement"),
        },
        "sensitivity": {
            "method": "leave_one_validation_fold_out",
            "lower_improvement": min(row["improvement"] for row in omissions),
            "upper_improvement": max(row["improvement"] for row in omissions),
            "omissions": omissions,
        },
        "sampling_uncertainty": {"status": "unavailable", "reason_code": "dependent_development_folds"},
    }
