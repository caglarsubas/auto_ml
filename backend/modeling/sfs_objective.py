"""Trusted native SFS objectives, availability and reviewable stopping semantics."""

from __future__ import annotations

import math
import hashlib
from pathlib import Path
import numpy as np

from modeling.fit_receipts import input_receipt, receipt_digest, runtime_versions

ALIASES = {"auc": "roc_auc", "average_precision": "pr_auc"}
MINIMIZE = {"rmse", "mae", "mse", "log_loss", "brier", "expected_cost"}
SUPPORTED = {
    "classification": {
        "roc_auc",
        "pr_auc",
        "log_loss",
        "accuracy",
        "f1",
        "precision",
        "recall",
        "ks",
        "brier",
        "expected_cost",
    },
    "regression": {"r2", "rmse", "mae", "mse"},
}


def canonical_metric(metric):
    name = str(metric).strip().lower()
    return ALIASES.get(name, name)


def direction(metric):
    return "minimize" if metric in MINIMIZE else "maximize"


def resolve_objective(task, context, criteria):
    if task not in SUPPORTED or (context and context["task"] != task):
        raise ValueError("Native feature selection requires the recorded classification/regression task.")
    if not isinstance(criteria, dict):
        raise ValueError("Feature-selection stopping criteria must be an object.")
    contract = (context or {}).get("prediction_contract") or {}
    if len(contract.get("class_mapping") or []) > 2:
        raise ValueError("Native feature selection does not support multiclass objectives yet.")
    declared = contract.get("objective") or {}
    requested = (
        declared.get("primary_metric")
        or criteria.get("primary_metric")
        or ("r2" if task == "regression" else "roc_auc")
    )
    primary = canonical_metric(requested)
    if primary not in SUPPORTED[task]:
        raise ValueError(f"Feature-selection objective {requested!r} is unsupported for {task}.")
    if criteria.get("primary_metric") and canonical_metric(criteria["primary_metric"]) != primary:
        raise ValueError(
            "Feature-selection ranking contradicts the accepted objective; revise the declaration in a new execution."
        )
    if declared.get("direction", direction(primary)) != direction(primary):
        raise ValueError("Feature-selection direction contradicts the accepted objective.")
    raw = criteria.get("metrics") or [{"metric": primary, "pct_change": 0.0}]
    if not isinstance(raw, list):
        raise ValueError("Feature-selection metric criteria must be a list.")
    normalized = []
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("Each feature-selection metric criterion must be an object.")
        name = canonical_metric(row.get("metric") or primary)
        if name not in SUPPORTED[task]:
            raise ValueError(
                f"Stopping metric {name!r} is unsupported for {task}; metrics are never converted to a different task."
            )
        threshold = float(row.get("pct_change", 0.0))
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError("Stopping percentages must be finite and nonnegative; zero disables that percentage gate.")
        if name in [existing["metric"] for existing in normalized]:
            raise ValueError("Feature-selection stopping metrics must be unique.")
        normalized.append({"metric": name, "pct_change": threshold})
    objective = {
        "schema_version": 1,
        "primary_metric": primary,
        "requested_primary_metric": requested,
        "direction": direction(primary),
        "cost_matrix": declared.get("cost_matrix") or {},
        "metric_semantics": "Regression errors"
        if task == "regression"
        else "Binary probabilities; threshold metrics use 0.5; expected cost is per observation.",
        "qualification": "Post-selection development evidence; screening, early stopping and selection reuse development data. Not independent assessment.",
        "training_policy": "Native fixed training/early-stopping criterion is recorded separately; full objective alignment remains open.",
    }
    return objective, normalized


def search_basis(
    X_train,
    y_train,
    X_valid,
    y_valid,
    task,
    algorithm,
    objective,
    criteria,
    cv_folds,
    top_k,
    methods,
    execution_id=None,
    n_jobs=1,
    context=None,
):
    from modeling.sfs_utils import _sfs_booster_params

    root = Path(__file__).parent
    implementation = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in (
            "sfs_utils.py",
            "sfs_objective.py",
            "development_validation.py",
            "development_assessment.py",
            "booster_adapters.py",
        )
    }
    validation = {"qualification": "Legacy; upstream preprocessing and partition provenance unverified."}
    if context and "frame" in context:
        # Hash only permitted development rows, never the protected outcome partition.
        validation = {
            "raw_train": input_receipt(context["frame"].loc[X_train.index], y_train),
            "raw_valid": input_receipt(context["frame"].loc[X_valid.index], y_valid),
            "configuration": {
                key: context.get(key)
                for key in (
                    "task",
                    "prediction_contract",
                    "target_column",
                    "split_meta",
                    "excluded_features",
                    "purifier_recipe",
                    "encoding_plan",
                    "use_native",
                )
            },
        }
    basis = {
        "schema_version": 2,
        "execution_id": execution_id,
        "task": task,
        "algorithm": algorithm,
        "train": input_receipt(X_train, y_train),
        "valid": input_receipt(X_valid, y_valid),
        "objective": objective,
        "stopping_criteria": criteria,
        "cv_folds": cv_folds,
        "top_k": top_k,
        "worker_budget": n_jobs,
        "methods": methods,
        "num_boost_round": 100,
        "early_stopping_rounds": 10,
        "validation": validation,
        "native_fit_params": _sfs_booster_params(task, 0),
        "screening_fit_params": _sfs_booster_params(task, 1 if n_jobs > 1 else 0),
        "runtime": {**runtime_versions(algorithm), "validation": runtime_versions("sklearn")},
        "implementation_sha256": implementation,
    }
    basis["sha256"] = receipt_digest(basis)
    return basis


def prepare_search(
    X_train,
    y_train,
    X_valid,
    y_valid,
    task,
    algorithm,
    context,
    criteria,
    cv_folds,
    top_k,
    methods,
    initial_features=None,
    execution_id=None,
    n_jobs=1,
):
    objective, normalized = resolve_objective(task, context, criteria)
    if (
        not isinstance(methods, list)
        or not methods
        or any(mode not in ("forward", "backward") for mode in methods)
        or len(set(methods)) != len(methods)
    ):
        raise ValueError("Select unique forward/backward feature-selection methods.")
    if initial_features is not None:
        if (
            not isinstance(initial_features, list)
            or not initial_features
            or len(set(initial_features)) != len(initial_features)
            or any(f not in X_train for f in initial_features)
        ):
            raise ValueError("Initial features must be a nonempty, unique list from the recorded feature pool.")
        X_train, X_valid = X_train[initial_features], X_valid[initial_features]
    min_features = int(criteria.get("min_features", min(3, X_train.shape[1])))
    max_features = min(int(criteria.get("max_features", min(10, X_train.shape[1]))), X_train.shape[1])
    if min_features < 1 or max_features < 1 or n_jobs < 1 or top_k < 1 or cv_folds < 2:
        raise ValueError("Feature counts, worker/top-K budgets and CV folds must be positive (at least two folds).")
    if "backward" in methods and min_features > X_train.shape[1]:
        raise ValueError("Backward minimum features exceeds the recorded feature pool.")
    config = {"metrics": normalized, "min_features": min_features, "max_features": max_features}
    basis = search_basis(
        X_train,
        y_train,
        X_valid,
        y_valid,
        task,
        algorithm,
        objective,
        config,
        cv_folds,
        top_k,
        methods,
        execution_id,
        n_jobs,
        context,
    )
    return X_train, X_valid, objective, config, basis


def validate_resume(resume_state, basis):
    if resume_state and resume_state.get("resume_basis") != basis:
        raise ValueError(
            "Saved feature selection has a different or unverified execution, objective, feature pool or budget. Start a fresh search; historical results remain inspectable."
        )


def json_record(value):
    if isinstance(value, np.generic):
        return json_record(value.item())
    if isinstance(value, dict):
        return {key: json_record(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_record(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("Feature-selection evidence contains an unsupported output type.")


def current_metrics(step, criteria):
    metrics = {}
    for row in criteria:
        name = row["metric"]
        value = step.get("cv_" + name)
        if value is None or not math.isfinite(value):
            raise ValueError(f"Stopping metric {name} is unavailable; revise the metric or validation population.")
        metrics[name] = float(value)
    return metrics


def improvement_pct(current, previous, metric):
    if previous is None or abs(previous) <= 1e-12:
        return None
    delta = previous - current if direction(metric) == "minimize" else current - previous
    return float(100 * delta / abs(previous))


def stopping_decision(current, previous, criteria, mode):
    changes, reasons = {}, []
    for row in criteria:
        name, threshold = row["metric"], row["pct_change"]
        change = improvement_pct(current[name], previous.get(name) if previous else None, name)
        changes[name] = change
        if previous is None or threshold == 0:
            continue
        if change is None:
            reasons.append(
                f"{name} percentage is undefined at a zero or missing baseline; use a fresh comparison or disable this percentage gate"
            )
        elif mode == "forward" and change <= threshold:
            reasons.append(f"{name} improvement ({change:+.2f}%) does not exceed {threshold}%")
        elif mode == "backward" and change < -threshold:
            reasons.append(f"{name} deterioration ({-change:.2f}%) exceeds {threshold}%")
    return changes, reasons
