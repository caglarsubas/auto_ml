"""Bounded native training computation shared by the worker and offline replay."""

import csv
import io
import json

import numpy as np
import pandas as pd

from deployment.native_candidate import MAX_INPUT_BYTES, canonical
from modeling.declared_metric import bind_declared_metric, metric_spec, metric_value
from modeling.development_validation import development_folds, prepare_fold
from modeling.prediction_contract import resolve_prediction_contract

KIND = "native_numeric_training_search_v1"
CANDIDATE_DEPTHS = (1, 2)
BUDGET = {
    "max_input_bytes": MAX_INPUT_BYTES,
    "max_rows": 1000,
    "max_columns": 40,
    "max_features": 32,
    "max_output_bytes": 8 * 1024**2,
    "candidates": len(CANDIDATE_DEPTHS),
    "boost_rounds": 16,
    "nthread": 1,
}
OPTIONS = {"business_understanding", "features", "validation", "data_role"}


class TrainingReplayError(ValueError):
    """A safe native training profile failure code."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def parsed_frame(raw):
    """Read one bounded, exact-width CSV in source row order."""
    try:
        if not isinstance(raw, bytes) or not 0 < len(raw) <= BUDGET["max_input_bytes"] or b"\x00" in raw:
            raise ValueError
        records = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
        header = next(row for row in records if row)
        if (
            not header
            or len(header) > BUDGET["max_columns"]
            or len(set(header)) != len(header)
            or any(not name for name in header)
        ):
            raise ValueError
        count = 0
        for row in records:
            if row:
                count += 1
                if len(row) != len(header) or count > BUDGET["max_rows"]:
                    raise ValueError
        if count < 30:
            raise ValueError
        frame = pd.read_csv(io.BytesIO(raw))
        if len(frame) != count or list(frame.columns) != header:
            raise ValueError
        return frame
    except (ValueError, csv.Error, UnicodeError, StopIteration):
        raise TrainingReplayError("job_training_csv_profile_invalid") from None


def validate_options(options):
    if not isinstance(options, dict) or set(options) != OPTIONS or options["data_role"] != "development_only":
        raise ValueError("Supply the development-only declaration, features and validation specification.")
    if len(json.dumps(options, allow_nan=False).encode()) > 32768:
        raise TrainingReplayError("job_training_spec_budget_exceeded")


def prepare_training(raw, options, check=lambda: None):
    """Derive the accepted contract and fold membership from development bytes."""
    validate_options(options)
    frame = parsed_frame(raw)
    business = options["business_understanding"]
    if not isinstance(business, dict) or any(
        not isinstance(business.get(key), dict)
        for key in ("target_contract", "success_criteria", "feature_availability")
    ):
        raise ValueError("Supply typed target, objective and availability declarations.")
    if not isinstance(business["success_criteria"].get("cost_matrix", {}), dict):
        raise ValueError("Business costs must be a named cost matrix.")
    contract, labels = resolve_prediction_contract(frame, business, "xgboost")
    if contract["task"] not in {"classification", "regression"} or len(contract["class_mapping"]) > 2:
        raise TrainingReplayError("job_training_task_unsupported")
    validation = options["validation"]
    if not isinstance(validation, dict) or validation.get("strategy") not in {"random", "group", "oot"}:
        raise ValueError("Select an explicit random, group or oot development validation strategy.")
    strategy = validation["strategy"]
    allowed = {"strategy", "n_splits"} | (
        {"group_column"}
        if strategy == "group"
        else {"date_column", "label_end_column", "group_column"}
        if strategy == "oot"
        else set()
    )
    if set(validation) - allowed or type(validation.get("n_splits")) is not int or validation["n_splits"] not in {2, 3}:
        raise ValueError("Use two or three development folds and supported validation fields.")
    if (
        strategy == "group"
        and not validation.get("group_column")
        or strategy == "oot"
        and not validation.get("date_column")
    ):
        raise ValueError("The declared validation strategy requires its grouping/date column.")
    controls = [value for key, value in validation.items() if key.endswith("_column")]
    if any(not isinstance(name, str) or name not in frame or name == contract["target_column"] for name in controls):
        raise ValueError("Validation columns must exist and cannot be the target.")
    features = options["features"]
    if (
        not isinstance(features, list)
        or not 1 <= len(features) <= BUDGET["max_features"]
        or any(not isinstance(name, str) or not 0 < len(name) <= 255 for name in features)
        or len(set(features)) != len(features)
        or any(
            name not in frame
            or name in controls
            or name == contract["target_column"]
            or name in contract["forbidden_features"]
            for name in features
        )
    ):
        raise ValueError("Select unique available predictors, excluding target and validation controls.")
    for name in features:
        if not pd.api.types.is_numeric_dtype(frame[name]) or np.isinf(frame[name].to_numpy(dtype=float)).any():
            raise TrainingReplayError("job_training_numeric_features_required")
        frame[name] = frame[name].astype(float)
    context = {
        "frame": frame,
        "labels": labels,
        "task": contract["task"],
        "target_column": contract["target_column"],
        "excluded_features": [name for name in frame if name not in features],
        "split_meta": {
            "strategy": strategy,
            "split_config": {k: v for k, v in validation.items() if k.endswith("_column")},
        },
        "prediction_contract": contract,
    }
    membership = [
        {"train_rows": list(map(int, train)), "valid_rows": list(map(int, valid))}
        for train, valid in development_folds(context, frame.index, labels, validation["n_splits"])
    ]
    check()
    return contract, membership, context


def fit_prepared(plan, context, *, job_id, training_sha256, runtime, check=lambda: None):
    """Repeat the approved development fold fits and all-development refit."""
    from modeling.booster_adapters import XGBoostAdapter

    contract = plan["prediction_contract"]
    metric = metric_spec(contract)
    features = plan["options"]["features"]
    candidates = []

    def fit(X, y, valid, y_valid, depth):
        check()
        params = bind_declared_metric(
            {
                "task": contract["task"],
                "objective": "reg:squarederror" if contract["task"] == "regression" else "binary:logistic",
                "max_depth": depth,
                "eta": 0.1,
                "nthread": BUDGET["nthread"],
                "seed": 42,
                "tree_method": "hist",
            },
            contract,
        )
        adapter = XGBoostAdapter().train(
            X, y, valid, y_valid, params, num_boost_round=BUDGET["boost_rounds"], early_stopping_rounds=0
        )
        check()
        return adapter

    for depth in CANDIDATE_DEPTHS:
        evidence = []
        for fold in plan["folds"]:
            check()
            tr, va = pd.Index(fold["train_rows"]), pd.Index(fold["valid_rows"])
            X, valid, provenance = prepare_fold(context, tr, va, features)
            y, y_valid = context["labels"].loc[tr], context["labels"].loc[va]
            adapter = fit(X, y, valid, y_valid, depth)
            predicted = adapter.predict(valid)
            baseline = np.full(len(va), float(y.mean()))
            evidence.append(
                {
                    "preprocessing": provenance,
                    "fit_receipt": adapter.fit_receipt,
                    "score": metric_value(metric, y_valid, predicted),
                    "reference_score": metric_value(metric, y_valid, baseline),
                }
            )
            check()
        candidates.append(
            {"max_depth": depth, "folds": evidence, "mean_score": float(np.mean([row["score"] for row in evidence]))}
        )
    selected = (min if metric["direction"] == "minimize" else max)(candidates, key=lambda item: item["mean_score"])
    # Fixed-round refit uses all declared development rows; no external holdout
    # is loaded and these in-sample inputs cannot become confirmatory evidence.
    rows = context["frame"].index
    X, _, provenance = prepare_fold(context, rows, pd.Index([], dtype=rows.dtype), features)
    labels = context["labels"]
    adapter = fit(X, labels, X, labels, selected["max_depth"])
    model_json = adapter.model.save_raw(raw_format="json").decode("utf-8")
    result = {
        "schema_version": 1,
        "scope": KIND,
        "job_id": str(job_id),
        "training_sha256": training_sha256,
        "input_sha256": plan["source"]["sha256"],
        "prediction_contract": contract,
        "metric": metric,
        "features": features,
        "candidates": candidates,
        "selected_max_depth": selected["max_depth"],
        "selection_rule": "Unweighted mean of matched development-fold scores; ties retain the first candidate.",
        "refit_receipt": adapter.fit_receipt,
        "refit_preprocessing": provenance,
        "model_format": "xgboost_json",
        "model_json": model_json,
        "runtime": runtime,
        "data_role": "development_only",
        "evidence_scope": "Exploratory selection and all-development refit; fold variation is not an independent confidence interval.",
        "final_holdout_accessed": False,
        "legacy_projection_updated": False,
        "model_adopted": False,
        "review_approved": False,
        "production_use_approved": False,
    }
    if len(canonical(result)) > BUDGET["max_output_bytes"]:
        raise TrainingReplayError("job_output_budget_exceeded")
    check()
    return result
