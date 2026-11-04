"""Frozen native legacy requests on the shared queue; no fitted-state reads here."""

import csv
import io
import json
import os
import shutil
import uuid
from datetime import timedelta
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.utils import timezone

from access_control import projects
from access_control.authority import actor_snapshot
from access_control.storage import managed_path, positive_file_id
from deployment.reviews import digest, lock_authority
from deployment.scoring_receipts import require_digest
from execution_jobs.models import NativeJob

KIND = "legacy_native_execution_v1"
OPERATIONS = {"training", "sfs", "hpo"}
BUDGET = {
    "max_input_bytes": 64 * 1024**2,
    "max_output_bytes": 64 * 1024**2,
    "max_result_bytes": 8 * 1024**2,
    "max_rows": 10000,
    "max_columns": 256,
    "max_native_jobs": 2,
    "native_threads": 1,
    "max_files": 256,
    "max_candidate_fits": 1000,
}
FIELDS = {
    "training": {
        "algorithm",
        "business_understanding",
        "encoding_plan",
        "encoding_use_native",
        "excluded_variables",
        "file_id",
        "pipeline_run_id",
        "processed_file",
    },
    "sfs": {
        "algorithm",
        "candidate_top_k",
        "cv_folds",
        "excluded_features",
        "execution_id",
        "file_id",
        "initial_features",
        "methods",
        "n_jobs",
        "resume",
        "stopping_criteria",
        "top_k",
        "use_combined_score_order",
    },
    "hpo": {
        "algorithm",
        "cv_folds",
        "execution_id",
        "features",
        "file_id",
        "fixed_params",
        "grid_points_per_param",
        "grid_points_per_param_map",
        "n_iter",
        "n_jobs",
        "param_space",
        "primary_metric",
        "search_method",
        "task",
        "threshold",
        "validation_curve_points",
    },
}
for _fields in FIELDS.values():
    _fields.add("legacy_response_contract")

SOURCE_FIELDS = {"source_job_id", "source_result_sha256", "checkpoint_job_id", "checkpoint_sha256"}
ALGORITHMS = {"xgboost", "lightgbm", "catboost", "logistic_regression", "scorecard", "isolation_forest"}


def conflict(code):
    from execution_jobs.service import JobConflict

    raise JobConflict("job_legacy_" + code)


def relative(name):
    if not isinstance(name, str) or len(name) > 1024 or "\\" in name or "\x00" in name:
        conflict("path_invalid")
    p = PurePosixPath(name)
    if (
        p.is_absolute()
        or p.as_posix() != name
        or not p.parts
        or any(x in (".", "..") or x.startswith(".") for x in p.parts)
    ):
        conflict("path_invalid")
    return name


def job_root(identifier):
    root = Path(settings.MEDIA_ROOT).resolve()
    path = root / "native_legacy_jobs" / str(uuid.UUID(str(identifier)))
    if any(part.is_symlink() for part in [path, path.parent]):
        conflict("artifact_invalid")
    return path


def read(path, limit=None):
    from execution_jobs.service import _artifact_bytes

    path = Path(path)
    root = Path(settings.MEDIA_ROOT).resolve()
    if not path.is_relative_to(root) or any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
        conflict("artifact_invalid")
    return _artifact_bytes(path, limit or BUDGET["max_input_bytes"], "job_legacy_input_budget")


def inventory(files):
    if len(files) > BUDGET["max_files"] or sum(len(raw) for raw in files.values()) > BUDGET["max_input_bytes"]:
        conflict("input_budget")
    import hashlib

    return {
        relative(name): {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        for name, raw in sorted(files.items())
    }


def output_root(job):
    token = str(uuid.UUID(job.result["attempt_token"]))
    return job_root(job.pk) / "attempts" / token / "work"


def source_files(actor, file_id, options):
    from execution_jobs import service

    try:
        identifier = str(uuid.UUID(str(options["source_job_id"])))
        pin = require_digest(options["source_result_sha256"])
        execution = str(uuid.UUID(str(options["execution_id"])))
        source = NativeJob.objects.get(pk=identifier)
    except (KeyError, ValueError, NativeJob.DoesNotExist):
        conflict("source_job_required")
    service.read_authority(actor, source)
    if (
        source.dataset_id != file_id
        or source.specification.get("kind") != KIND
        or source.state != "succeeded"
        or source.result_sha256 != pin
        or digest(source.result) != pin
    ):
        conflict("source_changed")
    prefix = f"execution_runs/{execution}/"
    entries = {name: entry for name, entry in source.result["files"].items() if name.startswith(prefix)}
    if not entries or prefix + "manifest.json" not in entries or prefix + "modeling_status.json" not in entries:
        conflict("source_execution_unavailable")
    root = output_root(source)
    files = {}
    import hashlib

    for name, entry in entries.items():
        raw = read(root / relative(name))
        if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            conflict("source_changed")
        files[name] = raw
    payload = json.loads(files[prefix + "modeling_status.json"])
    if payload.get("file_id") != file_id or payload.get("execution_id") != execution:
        conflict("source_changed")
    model = payload["model"]
    train = relative(model["train_data_path"])
    if not train.startswith(prefix) or train not in files:
        conflict("source_changed")
    files[f"modeling/{file_id}_status.json"] = files[prefix + "modeling_status.json"]
    files[f"train_data/{file_id}_train_data.pkl"] = files[train]
    # All pickle bytes come from one completed fixed native job, never uploads
    # or a mutable legacy projection. Only the fixed child will deserialize it.
    return {"job_id": identifier, "result_sha256": pin, "execution_id": execution}, files


def training_files(actor, file_id, options):
    path = Path(managed_path(options.get("processed_file"), table=True))
    if path.suffix.lower() != ".csv":
        conflict("versioned_csv_required")
    projects.path_authority(actor.pk, path, file_id=file_id)
    root = Path(settings.MEDIA_ROOT).resolve()
    name = str(path.relative_to(root))
    options["processed_file"] = name
    files = {name: read(path)}
    try:
        rows = csv.reader(io.StringIO(files[name].decode("utf-8-sig")), strict=True)
        header = next(rows)
        if not 1 <= len(header) <= BUDGET["max_columns"] or len(set(header)) != len(header):
            conflict("table_budget")
        count = 0
        for row in rows:
            if row:
                count += 1
                if len(row) != len(header) or count > BUDGET["max_rows"]:
                    conflict("table_budget")
        if count < 8:
            conflict("table_budget")
    except (UnicodeError, csv.Error, StopIteration):
        conflict("table_invalid")
    for suffix in (".meta.json", ".purifier.json"):
        side = path.with_suffix(suffix)
        if side.exists():
            files[str(side.relative_to(root))] = read(side, 2 * 1024**2)
    recipe = files.get(str(path.with_suffix(".purifier.json").relative_to(root)))
    if recipe:
        value = json.loads(recipe)
        if value.get("file_id") != file_id:
            conflict("recipe_dataset_mismatch")
        raw_name = relative(value["raw_input"]["path"])
        raw_path = root / raw_name
        projects.path_authority(actor.pk, raw_path, file_id=file_id)
        files[raw_name] = read(raw_path)
        import hashlib

        if (
            value.get("schema_version") != 2
            or value.get("processed_input", {}).get("path") != name
            or value.get("processed_input", {}).get("sha256") != hashlib.sha256(files[name]).hexdigest()
            or value["raw_input"].get("sha256") != hashlib.sha256(files[raw_name]).hexdigest()
        ):
            conflict("recipe_changed")
    for name in (
        f"splits/{file_id}_split.json",
        f"data_quality/{file_id}_datq_summary.json",
        f"purifier/{file_id}_purifier.json",
    ):
        if (root / name).exists():
            files[name] = read(root / name, 2 * 1024**2)
    return files


def prepare(actor, file_id, operation, options):
    from execution_jobs import service

    file_id = positive_file_id(file_id)
    authority = service.scope(actor, file_id)
    if authority["role"] != "developer":
        raise projects.ProjectDenied("job_submit_role_required")
    if operation not in OPERATIONS or not isinstance(options, dict) or set(options) - FIELDS[operation] - SOURCE_FIELDS:
        raise ValueError("Select training, sfs or hpo with supported native options.")
    options = json.loads(json.dumps(options, allow_nan=False))
    if len(json.dumps(options).encode()) > 32768:
        conflict("spec_budget")
    if positive_file_id(options.get("file_id")) != file_id:
        conflict("dataset_mismatch")
    if options.get("legacy_response_contract") not in (None, "v1"):
        conflict("response_contract_invalid")
    source = None
    semantic_contract = {}
    checkpoint = None
    if operation == "training":
        if SOURCE_FIELDS.intersection(options):
            conflict("source_invalid")
        if options.get("pipeline_run_id") is not None:
            projects.pipeline_authority(actor.pk, options["pipeline_run_id"], "read")
            from modeling.models import PipelineRun

            run = PipelineRun.objects.get(pk=options["pipeline_run_id"], file_id=file_id)
            state = run.state or {}
            options.setdefault(
                "business_understanding",
                state.get("business_understanding") or (state.get("crisp_dm") or {}).get("business_understanding"),
            )
            options.pop("pipeline_run_id")
        if not isinstance(options.get("business_understanding"), dict):
            raise ValueError("Supply the accepted business declaration.")
        semantic_contract = options["business_understanding"]
        files = training_files(actor, file_id, options)
        algorithm = options.get("algorithm") or "xgboost"
    else:
        source, files = source_files(actor, file_id, options)
        payload = json.loads(files[f"modeling/{file_id}_status.json"])
        semantic_contract = payload.get("model", {}).get("prediction_contract", {})
        declared_task = payload.get("model", {}).get("task")
        if options.get("task") is not None and options["task"] != declared_task:
            raise ValueError("The task is bound to the source candidate. Start a new training version to change it.")
        algorithm = options.get("algorithm") or payload.get("algorithm")
        options.setdefault("n_jobs", 1)
        options.setdefault("cv_folds", 3 if operation == "sfs" else 5)
        for key in ("n_jobs", "cv_folds"):
            value = options[key]
            if type(value) is not int or not 1 <= value <= (2 if key == "n_jobs" else 5):
                raise ValueError("Use one/two candidate workers and two to five folds within the displayed budget.")
        if options.get("cv_folds", 3) < 2:
            raise ValueError("Use at least two folds.")
        if algorithm not in {"xgboost", "lightgbm", "catboost"}:
            conflict("search_algorithm_unsupported")
        if operation == "hpo":
            from modeling.hyperparam_utils import (
                DEFAULT_FIXED_PARAMS,
                _PARAM_BOUNDS,
                validate_param_space,
                recommend_search_method,
            )
            import math

            for key, default, low, high in (
                ("n_iter", 40, 2, 100),
                ("validation_curve_points", 8, 2, 25),
                ("grid_points_per_param", 5, 2, 12),
            ):
                options.setdefault(key, default)
                if type(options[key]) is not int or not low <= options[key] <= high:
                    conflict("trial_budget")
            space, warnings = validate_param_space(options.get("param_space"))
            options["param_space"] = space
            fixed = {**DEFAULT_FIXED_PARAMS, **(options.get("fixed_params") or {})}
            for key, value in fixed.items():
                if (
                    key not in _PARAM_BOUNDS
                    or type(value) not in (int, float)
                    or not math.isfinite(value)
                    or not _PARAM_BOUNDS[key][0] <= value <= _PARAM_BOUNDS[key][1]
                ):
                    conflict("parameter_invalid")
            options["fixed_params"] = fixed
            points = options.get("grid_points_per_param_map") or {}
            if (
                not isinstance(points, dict)
                or set(points) - set(space)
                or any(type(v) is not int or not 2 <= v <= 500 for v in points.values())
            ):
                conflict("grid_budget")
            options["grid_points_per_param_map"] = points
            recommendation = recommend_search_method(
                space,
                options["cv_folds"],
                options["n_jobs"],
                options["grid_points_per_param"],
                points_map=points or None,
            )
            method = options.get("search_method", "auto")
            if method not in {"auto", "grid", "random", "bayesian", "optuna"}:
                conflict("search_method_invalid")
            options["search_method"] = recommendation["method"] if method == "auto" else method
            candidates = recommendation["grid_candidates"] if options["search_method"] == "grid" else options["n_iter"]
            fits = (
                candidates + sum(bool(v.get("enabled")) for v in space.values()) * options["validation_curve_points"]
            ) * options["cv_folds"] + 3
            if candidates > 100 or fits > BUDGET["max_candidate_fits"]:
                conflict("candidate_fit_budget")
            semantic_contract = {
                **semantic_contract,
                "search_budget": {
                    "candidates": candidates,
                    "candidate_fit_upper_bound": fits,
                    "normalization_notes": warnings,
                },
            }
        if options.get("resume") or options.get("checkpoint_job_id"):
            # Bound checkpoint replay is added below; never consume an implicit
            # latest checkpoint merely because resume=true was supplied.
            from execution_jobs.legacy_process import checkpoint_files

            if operation != "sfs" or options.get("resume") is not True:
                conflict("checkpoint_required")
            files.update(checkpoint_files(actor, file_id, options, source))
            checkpoint = {"job_id": options["checkpoint_job_id"], "sha256": options["checkpoint_sha256"]}
    if algorithm not in ALGORITHMS:
        conflict("algorithm_unsupported")
    options["algorithm"] = algorithm
    if source:
        for key in SOURCE_FIELDS:
            options.pop(key, None)
    manifest = inventory(files)
    plan = {
        "schema_version": 1,
        "operation": operation,
        "file_id": file_id,
        "actor_id": actor.pk,
        "authority": authority,
        "options": options,
        "source": source,
        "checkpoint": checkpoint,
        "semantic_contract": semantic_contract,
        "inputs": manifest,
        "runtime": service.runtime(KIND),
        "limits": service.limits(KIND),
    }
    projects.recheck(authority)
    return plan, files


def preview(actor, file_id, operation, options):
    plan, _ = prepare(actor, file_id, operation, options)
    return {
        "kind": KIND,
        "operation": operation,
        "plan_sha256": digest(plan),
        "inputs_sha256": digest(plan["inputs"]),
        "source": plan["source"],
        "execution_options": plan["options"],
        "semantic_contract": plan["semantic_contract"],
        "budget": plan["limits"],
        "runtime": plan["runtime"],
        "scope": "Native development candidate only; no global projection, review or production approval.",
    }


def submit(actor, file_id, data):
    from execution_jobs import service

    if set(data) != {"kind", "operation", "options", "plan_sha256", "inputs_sha256", "request_id"}:
        raise ValueError("Supply exactly the reviewed legacy execution fields.")
    identifier = uuid.UUID(str(data["request_id"]))
    pin = require_digest(data["plan_sha256"])
    inputs_pin = require_digest(data["inputs_sha256"])
    request_sha = digest({"actor_id": actor.pk, "file_id": file_id, "request": data})
    with service.locked():
        authority = lock_authority(actor, file_id, None)
        if authority["role"] != "developer":
            raise projects.ProjectDenied("job_submit_role_required")
        previous = NativeJob.objects.filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != request_sha:
                conflict("request_reused")
            return service.authorized_receipt(previous, service.read_authority(actor, previous), replayed=True)
        if NativeJob.objects.filter(state__in=service.ACTIVE | {"queued"}).count() >= service.LIMITS["max_pending"]:
            raise service.JobConflict("job_queue_full")
        plan, files = prepare(actor, file_id, data["operation"], data["options"])
        if digest(plan) != pin or digest(plan["inputs"]) != inputs_pin:
            conflict("plan_changed")
        root = job_root(identifier)
        snapshot = root / "inputs"
        if snapshot.exists():
            if not (root / "plan.json").is_file() or json.loads(read(root / "plan.json")) != plan:
                conflict("snapshot_exists")
            if inventory({name: read(snapshot / name) for name in plan["inputs"]}) != plan["inputs"]:
                conflict("snapshot_changed")
        else:
            root.mkdir(parents=True, exist_ok=True)
            stage = root / ("staging-" + uuid.uuid4().hex)
            stage.mkdir()
            try:
                for name, raw in files.items():
                    path = stage / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                    path.chmod(0o400)
                plan_path = root / "plan.json"
                if os.path.lexists(plan_path):
                    if json.loads(read(plan_path)) != plan:
                        conflict("snapshot_exists")
                else:
                    with plan_path.open("xb") as stream:
                        stream.write(json.dumps(plan, sort_keys=True, allow_nan=False).encode())
                    plan_path.chmod(0o400)
                stage.rename(snapshot)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        job = NativeJob.objects.create(
            id=identifier,
            actor=actor,
            actor_snapshot=actor_snapshot(actor),
            project_id=authority["project_id"],
            dataset_id=file_id,
            authority=authority,
            specification={
                "schema_version": 1,
                "kind": KIND,
                "legacy": plan,
                "legacy_sha256": pin,
                "runtime": plan["runtime"],
                "limits": plan["limits"],
            },
            request_sha256=request_sha,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        projects.recheck(authority)
        service.record(job, "submitted", actor=actor, update_fields=["revision"])
        return service.authorized_receipt(job, [authority])


def recheck(job):
    try:
        plan = job.specification.get("legacy")
        if (
            not isinstance(plan, dict)
            or digest(plan) != job.specification.get("legacy_sha256")
            or type(plan.get("file_id")) is not int
            or plan["file_id"] != job.dataset_id
            or plan.get("actor_id") != job.authority.get("actor_id")
            or plan.get("authority") != job.authority
            or plan.get("operation") not in OPERATIONS
            or not isinstance(plan.get("options"), dict)
            or not isinstance(plan.get("inputs"), dict)
            or not 1 <= len(plan["inputs"]) <= BUDGET["max_files"]
        ):
            conflict("specification_invalid")
        total = 0
        for name, entry in plan["inputs"].items():
            relative(name)
            if (
                not isinstance(entry, dict)
                or set(entry) != {"sha256", "bytes"}
                or type(entry["bytes"]) is not int
                or entry["bytes"] < 0
            ):
                conflict("specification_invalid")
            require_digest(entry["sha256"])
            total += entry["bytes"]
        if total > BUDGET["max_input_bytes"]:
            conflict("specification_invalid")
        source = plan.get("source")
        if source is not None:
            if not isinstance(source, dict) or set(source) != {"job_id", "result_sha256", "execution_id"}:
                conflict("specification_invalid")
            if str(uuid.UUID(source["job_id"])) != source["job_id"] or source["job_id"] == str(job.pk):
                conflict("specification_invalid")
            if str(uuid.UUID(source["execution_id"])) != source["execution_id"]:
                conflict("specification_invalid")
            require_digest(source["result_sha256"])
    except (TypeError, KeyError, AttributeError, ValueError):
        conflict("specification_invalid")
    if source:
        previous = NativeJob.objects.get(pk=source["job_id"])
        if (
            previous.dataset_id != job.dataset_id
            or previous.project_id != job.project_id
            or previous.state != "succeeded"
            or previous.specification.get("kind") != KIND
            or previous.result_sha256 != source["result_sha256"]
            or digest(previous.result) != previous.result_sha256
        ):
            conflict("source_changed")
