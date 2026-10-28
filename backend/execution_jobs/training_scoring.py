"""Export owned native training candidates and queue pinned feature-only scoring."""

import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from access_control import projects
from access_control.authority import actor_snapshot
from deployment import native_candidate
from deployment.reviews import digest, lock_authority
from deployment.scoring_receipts import require_digest
from execution_jobs import csv_scoring, training_search
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess

KIND = "native_training_scoring_v1"
BUDGET = {**csv_scoring.BUDGET, "max_columns": 32, "chunk_size": 500}
FIELDS = {"training_job_id", "training_result_sha256", "input_file_id", "input_sha256", "scoring_sha256"}


def export(actor, identifier, expected):
    from execution_jobs import service

    with service.locked():
        return _export(actor, identifier, expected)


def _export(actor, identifier, expected):
    from execution_jobs import service

    expected = require_digest(expected)
    job = NativeJob.objects.get(pk=identifier)
    scopes = service.read_authority(actor, job)
    if job.state != "succeeded" or job.specification["kind"] != training_search.KIND or job.result_sha256 != expected:
        raise service.JobConflict("job_training_result_unavailable")
    raw = native_candidate.export_candidate(job.pk, job.dataset_id, job.project_id, job.result, expected)
    for current in scopes:
        projects.recheck(current)
    return raw


def prepare(actor, file_id, identifier, expected, input_id, check=lambda: None, expected_source=None):
    from execution_jobs import service

    authority = service.scope(actor, file_id)
    if authority["role"] != "developer":
        raise projects.ProjectDenied("job_submit_role_required")
    if type(input_id) is not int or not 0 < input_id <= 2**63 - 1:
        raise ValueError("Supply a positive scoring input dataset ID.")
    trained = NativeJob.objects.get(pk=identifier)
    if trained.dataset_id != file_id or str(trained.project_id) != authority["project_id"]:
        raise projects.ProjectDenied("job_training_project_mismatch")
    raw_export = _export(actor, identifier, expected)
    raw, source, source_authority = csv_scoring.input_bytes(actor.pk, input_id, check, expected_source)
    if source_authority["project_id"] != authority["project_id"]:
        raise projects.ProjectDenied("job_input_project_mismatch")
    # Do not turn known protected/evaluated populations into prediction input.
    # Unknown/imported/reordered history remains explicitly unverified.
    root = Path(settings.MEDIA_ROOT)
    if any(os.path.lexists(root / path) for path in (
        f"splits/{input_id}_split.json", f"modeling/{input_id}_status.json", f"train_data/{input_id}_train_data.pkl"
    )) or HoldoutAccess.objects.filter(Q(file_id=input_id) | Q(dataset_sha256=source["sha256"])).exists():
        raise service.JobConflict("job_scoring_requires_unprotected_feature_input")
    native_candidate.numeric_input(raw, native_candidate.validate(raw_export, native_candidate.sha(raw_export)))
    plan = {
        "schema_version": 1, "kind": KIND, "training_job_id": str(trained.pk),
        "training_result_sha256": trained.result_sha256, "export_sha256": native_candidate.sha(raw_export),
        "source": source, "source_authority": source_authority,
        "runtime": service.runtime(KIND), "limits": service.limits(KIND),
    }
    check()
    projects.recheck(authority)
    projects.recheck(source_authority)
    return plan, raw_export, raw


def preview(actor, identifier, data):
    from execution_jobs import service

    if not isinstance(data, dict) or set(data) != {"input_file_id", "training_result_sha256"}:
        raise ValueError("Supply the selected training result and feature-only input dataset ID.")
    trained = NativeJob.objects.get(pk=identifier)
    authority = service.scope(actor, trained.dataset_id)
    plan, raw_export, _ = prepare(actor, trained.dataset_id, identifier, require_digest(data["training_result_sha256"]), data["input_file_id"])
    candidate = json.loads(raw_export)
    result = {
        "kind": KIND, "training_job_id": str(identifier), "training_result_sha256": plan["training_result_sha256"],
        "input_file_id": data["input_file_id"], "input_sha256": plan["source"]["sha256"],
        "scoring_sha256": digest(plan), "export_sha256": plan["export_sha256"],
        "features": candidate["result"]["features"], "prediction_contract": candidate["result"]["prediction_contract"],
        "budget": plan["limits"], "runtime": plan["runtime"],
        "evidence_scope": "Candidate predictions only. Feature-only numeric CSV; missing values use frozen training means. No adoption, evaluation or production approval.",
    }
    projects.recheck(authority)
    projects.recheck(plan["source_authority"])
    return result


def submit(actor, file_id, data):
    from execution_jobs import service

    if set(data) != FIELDS | {"kind", "request_id"}:
        raise ValueError("Supply exactly the reviewed native candidate scoring fields.")
    identifier, trained_id = uuid.UUID(str(data["request_id"])), uuid.UUID(str(data["training_job_id"]))
    expected, input_sha, plan_sha = [require_digest(data[k]) for k in ("training_result_sha256", "input_sha256", "scoring_sha256")]
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
        lock_authority(actor, data["input_file_id"], None)
        plan, _, _ = prepare(actor, file_id, trained_id, expected, data["input_file_id"])
        if plan["source"]["sha256"] != input_sha or digest(plan) != plan_sha:
            raise service.JobConflict("job_scoring_input_or_plan_changed")
        job = NativeJob.objects.create(
            id=identifier, actor=actor, actor_snapshot=actor_snapshot(actor), project_id=current["project_id"],
            dataset_id=file_id, source_dataset_id=data["input_file_id"], authority=current,
            specification={**plan, "scoring_sha256": plan_sha}, request_sha256=request_sha,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        projects.recheck(current)
        service.record(job, "submitted", actor=actor, update_fields=["revision"])
        return service.authorized_receipt(job, [current, plan["source_authority"]])


def score(job, check):
    from django.contrib.auth import get_user_model
    from execution_jobs import service

    spec = job.specification
    actor = get_user_model().objects.get(pk=job.authority["actor_id"])
    plan, raw_export, raw = prepare(actor, job.dataset_id, spec["training_job_id"], spec["training_result_sha256"], job.source_dataset_id, check, spec["source"])
    if digest(plan) != spec["scoring_sha256"] or {k: v for k, v in spec.items() if k != "scoring_sha256"} != plan:
        raise service.JobConflict("job_scoring_input_or_plan_changed")
    result = native_candidate.score(raw_export, spec["export_sha256"], raw, chunk_size=spec["limits"]["chunk_size"], check=check)
    result.update(job_id=str(job.pk), scope=KIND, runtime=spec["runtime"], scoring_sha256=spec["scoring_sha256"])
    if len(csv_scoring.canonical_bytes(result)) > BUDGET["max_output_bytes"]:
        raise service.JobConflict("job_output_budget_exceeded")
    check()
    return result
