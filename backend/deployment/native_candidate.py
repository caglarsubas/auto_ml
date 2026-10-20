"""Portable, bounded native candidate scoring. No Django, pickle or expert code.

An export hash detects changes relative to a separately retained server receipt;
it does not establish authenticity or confer review/production approval.
"""

import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from importlib.metadata import version

import numpy as np
import pandas as pd

SCOPE = "native_training_candidate_export_v1"
MAX_EXPORT_BYTES = 10 * 1024**2
MAX_INPUT_BYTES = 5 * 1024**2
MAX_ROWS = 10000
FLAGS = ("final_holdout_accessed", "legacy_projection_updated", "model_adopted", "review_approved", "production_use_approved")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def export_candidate(job_id, dataset_id, project_id, result, result_sha256):
    if sha(canonical(result)) != result_sha256:
        raise ValueError("candidate_result_changed")
    payload = {
        "schema_version": 1, "scope": SCOPE, "training_job_id": str(job_id),
        "dataset_id": dataset_id, "project_id": str(project_id), "result_sha256": result_sha256,
        "scoring_runtime": {"python": sys.version.split()[0], "packages": {p: version(p) for p in ("numpy", "pandas", "xgboost")}, "reader_sha256": sha(Path(__file__).read_bytes())},
        "result": result, "scoring_profile": "ordered_numeric_mean_imputation_xgboost_v1",
        "evidence_scope": "Exploratory all-development refit; export is not model adoption or production approval.",
    }
    raw = canonical(payload)
    validate(raw, sha(raw))
    return raw


def validate(raw, expected_sha256):
    # This portable reader requires a caller-held digest, never a self-declared
    # hash from a downloaded file. JSON/numeric/native state only.
    if not isinstance(raw, bytes) or len(raw) > MAX_EXPORT_BYTES or sha(raw) != expected_sha256:
        raise ValueError("candidate_export_changed_or_oversized")
    try:
        value = json.loads(raw)
        result = value["result"]
        features = result["features"]
        means = result["refit_preprocessing"]["impute_means"]
        contract = result["prediction_contract"]
        runtime = result["runtime"]
        scoring_runtime = value["scoring_runtime"]
        if (
            not isinstance(runtime["python"], str) or not isinstance(scoring_runtime["python"], str)
            or not isinstance(scoring_runtime["reader_sha256"], str)
            or any(not isinstance(env["packages"][p], str) for env in (runtime, scoring_runtime) for p in ("numpy", "pandas", "xgboost"))
            or value["schema_version"] != 1 or value["scope"] != SCOPE
            or value["scoring_profile"] != "ordered_numeric_mean_imputation_xgboost_v1"
            or sha(canonical(result)) != value["result_sha256"]
            or result["scope"] != "native_numeric_training_search_v1"
            or result["schema_version"] != 1 or result["job_id"] != value["training_job_id"]
            or result["model_format"] != "xgboost_json" or result["data_role"] != "development_only"
            or any(result.get(key) is not False for key in FLAGS)
            or not isinstance(features, list) or not 1 <= len(features) <= 32
            or any(not isinstance(f, str) or not f for f in features) or len(set(features)) != len(features)
            or set(means) != set(features) or any(not np.isfinite(float(n)) for n in means.values())
            or result["refit_preprocessing"].get("encoding") != []
            or result["refit_preprocessing"].get("purifier") is not None
            or contract["task"] not in {"classification", "regression"}
            or contract["target_column"] in features
            or not isinstance(result["model_json"], str)
        ):
            raise ValueError
        model = json.loads(result["model_json"])
        learner = model["learner"]
        objective = "binary:logistic" if contract["task"] == "classification" else "reg:squarederror"
        if (
            learner["objective"]["name"] != objective or learner["feature_names"] != features
            or int(learner["learner_model_param"]["num_feature"]) != len(features)
            or learner["gradient_booster"]["name"] != "gbtree"
        ):
            raise ValueError
    except (KeyError, TypeError, OverflowError, json.JSONDecodeError, ValueError):
        raise ValueError("candidate_export_invalid") from None
    return value


def numeric_input(raw, candidate):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_INPUT_BYTES:
        raise ValueError("candidate_input_budget_exceeded")
    result = candidate["result"]
    features = result["features"]
    try:
        records = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
        header = next(row for row in records if row)
        # Feature-only CSVs exclude labels, controls, identifiers and arbitrary
        # extra fields. Header order can vary; model order is always frozen.
        if len(header) != len(features) or set(header) != set(features):
            raise ValueError
        count = 0
        for row in records:
            if row:
                count += 1
                if len(row) != len(header) or count > MAX_ROWS:
                    raise ValueError
        if not count:
            raise ValueError
        frame = pd.read_csv(io.BytesIO(raw))
        if len(frame) != count or list(frame.columns) != header:
            raise ValueError
        for name in features:
            if frame[name].notna().any() and not pd.api.types.is_numeric_dtype(frame[name]):
                raise ValueError
        values = frame.loc[:, features].astype(float)
        if np.isinf(values.to_numpy()).any():
            raise ValueError
        return values.fillna(result["refit_preprocessing"]["impute_means"])
    except (ValueError, csv.Error, UnicodeError, StopIteration, OverflowError):
        raise ValueError("candidate_feature_only_numeric_csv_required") from None


def score(raw_export, export_sha256, raw_input, *, chunk_size=500, check=lambda: None):
    candidate = validate(raw_export, export_sha256)
    result = candidate["result"]
    # The same native library versions as fitting are required. Source changes
    # are recorded by the job runtime; portable runner source is separately pinned.
    if (candidate["scoring_runtime"] != {"python": sys.version.split()[0], "packages": {p: version(p) for p in ("numpy", "pandas", "xgboost")}, "reader_sha256": sha(Path(__file__).read_bytes())}
            or sys.version.split()[0] != result["runtime"]["python"]
            or any(version(p) != result["runtime"]["packages"][p] for p in ("numpy", "pandas", "xgboost"))):
        raise ValueError("candidate_scoring_runtime_changed")
    if type(chunk_size) is not int or not 1 <= chunk_size <= MAX_ROWS:
        raise ValueError("candidate_chunk_size_invalid")
    check()
    frame = numeric_input(raw_input, candidate)
    check()
    # Native JSON is loaded only by the worker or explicit offline runner. The
    # controller only validates declarative JSON; no arbitrary fitted state.
    import xgboost as xgb

    booster = xgb.Booster(params={"nthread": 1})
    try:
        booster.load_model(bytearray(result["model_json"].encode()))
        scores = []
        for start in range(0, len(frame), chunk_size):
            check()
            predicted = booster.predict(xgb.DMatrix(frame.iloc[start:start + chunk_size], nthread=1))
            if predicted.ndim != 1 or not np.isfinite(predicted).all():
                raise ValueError("candidate_prediction_invalid")
            scores.extend(float(n) for n in predicted)
        check()
    except xgb.core.XGBoostError:
        raise ValueError("candidate_native_model_invalid") from None
    return {
        "schema_version": 1, "scope": "native_training_candidate_scores_v1",
        "training_job_id": candidate["training_job_id"], "training_result_sha256": candidate["result_sha256"],
        "export_sha256": export_sha256, "model_sha256": sha(result["model_json"].encode()),
        "input_sha256": sha(raw_input), "features": result["features"], "prediction_contract": result["prediction_contract"],
        "n_scored": len(scores), "row_alignment": "Zero-based parsed CSV data-row order; blank records ignored.",
        "scores": scores, "scores_calibrated": False,
        "score_semantics": "positive_class_probability" if result["prediction_contract"]["task"] == "classification" else "target_prediction",
        "evidence_scope": "Candidate predictions only; no outcome evaluation, threshold selection or final assessment.",
        **{key: False for key in FLAGS},
    }
