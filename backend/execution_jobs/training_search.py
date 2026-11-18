"""Bounded native development training/search; only fenced DB results publish.

This profile accepts development-only numeric CSVs and fixed native candidates.
It never reads a final assessment, imports fitted state, executes expert code,
adopts a champion or writes legacy model/search projections.
"""

import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from access_control import projects
from access_control.authority import actor_snapshot
from deployment.reviews import digest, lock_authority
from deployment.scoring_receipts import require_digest
from execution_jobs import csv_scoring
from execution_jobs.models import NativeJob
from modeling import native_training_replay as replay
from modeling.models import HoldoutAccess
from modeling.prediction_contract import PredictionContractError

KIND = replay.KIND
BUDGET = replay.BUDGET
OPTIONS = replay.OPTIONS


def parsed_frame(raw):
    from execution_jobs.service import JobConflict

    try:
        return replay.parsed_frame(raw)
    except replay.TrainingReplayError as error:
        raise JobConflict(error.code) from None


def prepare(actor_id, file_id, options, check=lambda: None, expected=None, *, preview_actor=None):
    """Bind the displayed declaration and exact input before queue admission."""
    from execution_jobs import service
    from execution_jobs.service import JobConflict

    current = projects.dataset_authority(actor_id, file_id, "read")
    if current["role"] != "developer":
        raise projects.ProjectDenied("job_submit_role_required")
    try:
        replay.validate_options(options)
    except replay.TrainingReplayError as error:
        raise JobConflict(error.code) from None
    raw, source, authority = csv_scoring.unprotected_input_bytes(actor_id, file_id, check, expected)
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
    if preview_actor is not None:
        from execution_jobs.assessment_intake import admit_generic_input

        if not admit_generic_input(preview_actor, [authority], source['sha256'], 'native_training_preview'):
            raise JobConflict('job_prospective_outcomes_protected')
    try:
        contract, folds, context = replay.prepare_training(raw, options)
    except replay.TrainingReplayError as error:
        raise JobConflict(error.code) from None
    window = contract['target_contract'].get('outcome_window')
    if window and datetime.fromisoformat(window['development_as_of']) > timezone.now():
        raise PredictionContractError('The development as-of timestamp must be at or before admission time.')
    plan = {
        "schema_version": replay.PLAN_SCHEMA,
        "profile": {"kind": KIND, "runtime": service.runtime(KIND), "limits": service.limits(KIND)},
        "source": source,
        "options": options,
        "prediction_contract": contract,
        "folds": folds,
    }
    check()
    projects.recheck(authority)
    return plan, context


def preview(actor, file_id, options):
    from execution_jobs import service

    authority = service.scope(actor, file_id)
    plan, _ = prepare(actor.pk, file_id, options, preview_actor=actor)
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

    spec = job.specification
    plan, context = prepare(
        job.authority["actor_id"], job.dataset_id, spec["training"]["options"], check, spec["training"]["source"]
    )
    if digest(plan) != spec["training_sha256"] or plan != spec["training"]:
        raise service.JobConflict("job_training_input_or_plan_changed")
    try:
        return replay.fit_prepared(
            plan, context, job_id=job.pk, training_sha256=spec["training_sha256"],
            runtime=spec["runtime"], check=check,
        )
    except replay.TrainingReplayError as error:
        raise service.JobConflict(error.code) from None
