"""Bounded native development training/search; only fenced DB results publish.

This profile accepts development-only numeric CSVs and fixed native candidates.
It never reads a final assessment, imports fitted state, executes expert code,
adopts a champion or writes legacy model/search projections.
"""

import csv
import io
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from access_control import projects
from access_control.authority import actor_snapshot
from deployment.reviews import digest, lock_authority
from deployment.scoring_receipts import require_digest
from execution_jobs import csv_scoring
from execution_jobs.models import NativeJob
from modeling.declared_metric import bind_declared_metric, metric_spec, metric_value
from modeling.development_validation import development_folds, prepare_fold
from modeling.prediction_contract import resolve_prediction_contract
from modeling.models import HoldoutAccess

KIND = "native_numeric_training_search_v1"
BUDGET = {
    "max_input_bytes": csv_scoring.BUDGET["max_input_bytes"],
    "max_rows": 1000,
    "max_columns": 40,
    "max_features": 32,
    "max_output_bytes": 8 * 1024**2,
    "candidates": 2,
    "boost_rounds": 16,
    "nthread": 1,
}
OPTIONS = {"business_understanding", "features", "validation", "data_role"}


def parsed_frame(raw):
    from execution_jobs.service import JobConflict

    try:
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
        raise JobConflict("job_training_csv_profile_invalid") from None


def prepare(actor_id, file_id, options, check=lambda: None, expected=None):
    """Bind the displayed declaration and exact input before queue admission."""
    from execution_jobs import service
    from execution_jobs.service import JobConflict

    current = projects.dataset_authority(actor_id, file_id, "read")
    if current["role"] != "developer":
        raise projects.ProjectDenied("job_submit_role_required")
    if not isinstance(options, dict) or set(options) != OPTIONS or options["data_role"] != "development_only":
        raise ValueError("Supply the development-only declaration, features and validation specification.")
    if len(json.dumps(options, allow_nan=False).encode()) > 32768:
        raise JobConflict("job_training_spec_budget_exceeded")
    raw, source, authority = csv_scoring.input_bytes(actor_id, file_id, check, expected)
    # This first raw-input profile cannot consume a legacy dataset's mixed
    # development/final partitions. Inspect metadata existence only; never open
    # a protected fitted-state or final-outcome file to decide eligibility.
    root = Path(settings.MEDIA_ROOT)
    if (
        any(
            os.path.lexists(root / relative)
            for relative in [
                f"splits/{file_id}_split.json",
                f"modeling/{file_id}_status.json",
                f"train_data/{file_id}_train_data.pkl",
            ]
        )
        or HoldoutAccess.objects.filter(Q(file_id=file_id) | Q(dataset_sha256=source["sha256"])).exists()
    ):
        raise JobConflict("job_training_requires_fresh_development_input")
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
        raise JobConflict("job_training_task_unsupported")
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
            raise JobConflict("job_training_numeric_features_required")
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
    folds = list(development_folds(context, frame.index, labels, validation["n_splits"]))
    plan = {
        "schema_version": 1,
        "profile": {"kind": KIND, "runtime": service.runtime(KIND), "limits": service.limits(KIND)},
        "source": source,
        "options": options,
        "prediction_contract": contract,
        "folds": [{"train_rows": list(map(int, train)), "valid_rows": list(map(int, valid))} for train, valid in folds],
    }
    check()
    projects.recheck(authority)
    return plan, context


def preview(actor, file_id, options):
    from execution_jobs import service

    authority = service.scope(actor, file_id)
    plan, _ = prepare(actor.pk, file_id, options)
    result = {
        "kind": KIND,
        "input_sha256": plan["source"]["sha256"],
        "training_sha256": digest(plan),
        "prediction_contract": plan["prediction_contract"],
        "folds": plan["folds"],
        "budget": plan["profile"]["limits"],
        "runtime": plan["profile"]["runtime"],
        "evidence_scope": "Exploratory development-only selection; no final assessment or model adoption.",
    }
    projects.recheck(authority)
    return result


def submit(actor, file_id, data):
    from execution_jobs import service

    service.scope(actor, file_id)
    if set(data) != OPTIONS | {"request_id", "kind", "input_sha256", "training_sha256"}:
        raise ValueError("Supply exactly the reviewed native training/search fields.")
    identifier = uuid.UUID(str(data["request_id"]))
    input_sha, plan_sha = require_digest(data["input_sha256"]), require_digest(data["training_sha256"])
    request_sha = digest({"actor_id": actor.pk, "file_id": file_id, "request": data})
    with service.locked():
        current = lock_authority(actor, file_id, None)
        if current["role"] != "developer":
            raise projects.ProjectDenied("job_submit_role_required")
        previous = NativeJob.objects.filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != request_sha:
                raise service.JobConflict("job_request_reused")
            scopes = service.read_authority(actor, previous)
            for authority in scopes:
                projects.recheck(authority)
            return service.authorized_receipt(previous, scopes, replayed=True)
        if NativeJob.objects.filter(state__in=service.ACTIVE | {"queued"}).count() >= service.LIMITS["max_pending"]:
            raise service.JobConflict("job_queue_full")
        plan, _ = prepare(actor.pk, file_id, {key: data[key] for key in OPTIONS})
        if plan["source"]["sha256"] != input_sha or digest(plan) != plan_sha:
            raise service.JobConflict("job_training_input_or_plan_changed")
        job = NativeJob.objects.create(
            id=identifier,
            actor=actor,
            actor_snapshot=actor_snapshot(actor),
            project_id=current["project_id"],
            dataset_id=file_id,
            authority=current,
            specification={
                "schema_version": 1,
                "kind": KIND,
                "training": plan,
                "training_sha256": plan_sha,
                "runtime": plan["profile"]["runtime"],
                "limits": plan["profile"]["limits"],
            },
            request_sha256=request_sha,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        projects.recheck(current)
        service.record(job, "submitted", actor=actor, update_fields=["revision"])
        return service.authorized_receipt(job, [current])


def train(job, check):
    from execution_jobs import service
    from modeling.booster_adapters import XGBoostAdapter

    spec = job.specification
    plan, context = prepare(
        job.authority["actor_id"], job.dataset_id, spec["training"]["options"], check, spec["training"]["source"]
    )
    if digest(plan) != spec["training_sha256"] or plan != spec["training"]:
        raise service.JobConflict("job_training_input_or_plan_changed")
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
                "nthread": 1,
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

    for depth in (1, 2):
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
        "job_id": str(job.pk),
        "training_sha256": spec["training_sha256"],
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
        "runtime": spec["runtime"],
        "data_role": "development_only",
        "evidence_scope": "Exploratory selection and all-development refit; fold variation is not an independent confidence interval.",
        "final_holdout_accessed": False,
        "legacy_projection_updated": False,
        "model_adopted": False,
        "review_approved": False,
        "production_use_approved": False,
    }
    if len(csv_scoring.canonical_bytes(result)) > BUDGET["max_output_bytes"]:
        raise service.JobConflict("job_output_budget_exceeded")
    check()
    return result
