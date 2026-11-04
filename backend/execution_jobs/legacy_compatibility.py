"""The v1 HTTP response contract backed by durable jobs, never local fitting.

Existing API clients submit and select initial training in one request. New
browser clients request the reviewed protocol and select candidates separately.
Both routes retain immutable runs; search candidates require normal selection.
"""

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from django.conf import settings
from rest_framework.response import Response

from access_control import projects
from execution_jobs import legacy_execution as legacy, service
from execution_jobs.legacy_selection import bound_job, current, member, select
from execution_jobs.models import NativeJob
from modeling.execution_artifacts import projection_lock

PROTOCOL = "v1"


def bind_source(actor, file_id, options):
    execution = options.get("execution_id")
    if not execution:
        _, selected = current(file_id)
        execution = (selected or {}).get("execution_id")
    if not execution:
        return None
    execution = str(uuid.UUID(str(execution)))
    from django.db.models import Q

    rows = NativeJob.objects.filter(dataset_id=file_id, state="succeeded", specification__kind=legacy.KIND).filter(
        Q(result__payload__execution_id=execution)
        | Q(result__payload__forward_execution_id=execution)
        | Q(result__payload__backward_execution_id=execution)
        | Q(result__payload__forward_from_backward_execution_id=execution)
    )
    # An exact execution may belong to only one immutable job.
    row = rows.first()
    if row is None or rows.exclude(pk=row.pk).exists():
        return None
    service.read_authority(actor, row)
    return {"source_job_id": str(row.pk), "source_result_sha256": row.result_sha256, "execution_id": execution}


def materialize(actor, identifier):
    """Publish exact v1-compatible evidence paths after a successful receipt."""
    routing = NativeJob.objects.only("dataset_id").get(pk=identifier)
    with projection_lock(routing.dataset_id), service.locked():
        job, scopes = bound_job(actor, identifier)
        if job.specification["legacy"]["options"].get("legacy_response_contract") != PROTOCOL:
            return
        root = Path(settings.MEDIA_ROOT).resolve()
        history = f"modeling/{job.dataset_id}_runs/"
        for name in job.result["files"]:
            # Only new immutable executions and UUID-named history records are
            # made visible. A fitted-state file is copied as bytes, never loaded.
            if not (name.startswith("execution_runs/") or name.startswith(history)):
                continue
            parts = Path(name).parts
            str(uuid.UUID(parts[1] if parts[0] == "execution_runs" else Path(name).stem.split("_run_", 1)[-1]))
            raw = member(job, name)
            path = root / legacy.relative(name)
            if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
                legacy.conflict("selection_target_invalid")
            if path.exists():
                if legacy.read(path) != raw:
                    legacy.conflict("selection_target_occupied")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(raw)
                path.chmod(0o400)
            if path.suffix in {".json", ".csv", ".png", ".svg", ".pdf"}:
                projects.register_artifact(path, file_id=job.dataset_id)
        # Legacy search projections are derived from this exact terminal job.
        # The durable receipt remains authoritative; immutable history is above.
        operation = job.specification["legacy"]["operation"]
        newer = NativeJob.objects.filter(
            dataset_id=job.dataset_id,
            state="succeeded",
            specification__kind=legacy.KIND,
            specification__legacy__operation=operation,
            created_at__gt=job.created_at,
        ).exists()
        if operation in {"sfs", "hpo"} and not newer:
            folder, suffix = (
                ("sfs_results", "sfs_results") if operation == "sfs" else ("hyperparam_results", "hyperparam")
            )
            name = f"{folder}/{job.dataset_id}_{suffix}.json"
            raw = member(job, name)
            path = root / name
            if path.is_symlink() or path.parent.is_symlink():
                legacy.conflict("selection_target_invalid")
            path.parent.mkdir(parents=True, exist_ok=True)
            stage = path.with_name("." + path.name + "." + uuid.uuid4().hex)
            try:
                stage.write_bytes(raw)
                for scope in scopes:
                    projects.recheck(scope)
                os.replace(stage, path)
            finally:
                stage.unlink(missing_ok=True)
            projects.register_artifact(path, file_id=job.dataset_id)
        for scope in scopes:
            projects.recheck(scope)
        if not job.events.filter(
            event_type="legacy_compatibility_published", detail__result_sha256=job.result_sha256
        ).exists():
            service.record(
                job,
                "legacy_compatibility_published",
                actor=actor,
                detail={
                    "result_sha256": job.result_sha256,
                    "operation": operation,
                    "evidence_only": True,
                    "model_adopted": False,
                },
                update_fields=["revision"],
            )


def wait(actor, identifier):
    deadline = time.monotonic() + service.LIMITS["seconds"] + service.LIMITS["lease_seconds"]
    while True:
        receipt = service.read(actor, identifier)
        if receipt["state"] in service.TERMINAL:
            return receipt
        if time.monotonic() >= deadline:
            return receipt
        # This request observes the job. Its lifetime, failure or disconnection
        # cannot own or cancel the worker, lease, result or retry.
        time.sleep(0.2)


def launch(request, operation, options):
    from execution_jobs.legacy_http import adapt
    from execution_jobs.views import ERRORS, failure

    try:
        if not isinstance(options, dict):
            raise ValueError("Supply a request object.")
        file_id = options.get("file_id")
        if file_id is None:
            return Response({"error": "file_id is required"}, status=400)
        if operation == "champion":
            if not options.get("execution_id") or not options.get("features"):
                return Response({"error": "Send the exact execution_id and accepted feature list."}, status=409)
            _, selected = current(file_id)
            if (selected or {}).get("execution_id") != options["execution_id"]:
                return Response({"error": "The selected execution has changed. Refresh before accepting it."}, status=409)
        service.scope(request.user, file_id)
        options = {**options, "legacy_response_contract": PROTOCOL}
        base, _ = current(file_id)
        if operation != "training":
            source = bind_source(request.user, file_id, options)
            if source is None:
                return Response(
                    {"error": "Training data not found for a verified native execution. Run a new training version first.", "status": "error"},
                    status=404,
                )
            if options.get("resume") and not options.get("checkpoint_job_id"):
                return Response(
                    {
                        "error": "Start a fresh search or select an exact cancelled checkpoint to resume.",
                        "status": "resume_blocked",
                    },
                    status=409,
                )
            options.update(source)
        preview = legacy.preview(request.user, file_id, operation, options)
        receipt = service.submit(
            request.user,
            file_id,
            {
                "kind": legacy.KIND,
                "operation": operation,
                "options": options,
                "request_id": str(uuid.uuid4()),
                "plan_sha256": preview["plan_sha256"],
                "inputs_sha256": preview["inputs_sha256"],
            },
        )
        if operation in {"training", "champion"}:
            receipt = wait(request.user, receipt["id"])
            if receipt["state"] == "succeeded":
                execution = receipt["result"]["payload"]["execution_id"]
                selection = select(
                    request.user,
                    receipt["id"],
                    {
                        "request_id": receipt["id"],
                        "result_sha256": receipt["result_sha256"],
                        "execution_id": execution,
                        "expected_projection_sha256": base,
                    },
                )
                reply = adapt(receipt, operation)
                reply["selected_for_development"] = selection["currently_selected"]
                return Response(reply)
            return Response(adapt(receipt, operation), status=400 if receipt["state"] in service.TERMINAL else 202)
        return Response({**adapt(receipt, operation), "status": "started"})
    except ERRORS as error:
        return failure(error)
