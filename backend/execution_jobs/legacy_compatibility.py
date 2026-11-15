"""The v1 HTTP response contract backed by durable jobs, never local fitting.

Existing API clients submit and select initial training in one request. New
browser clients request the reviewed protocol and select candidates separately.
Both routes retain immutable runs; search candidates require normal selection.
"""

import os
import tempfile
import time
import uuid
from pathlib import Path

from rest_framework.response import Response

from access_control import projects
from deployment.reviews import lock_authority
from execution_jobs import legacy_execution as legacy, service
from execution_jobs.legacy_selection import (
    bound_job, current, member, publication_path, publish_execution, publish_history_member, select, write_member,
)
from execution_jobs.models import NativeJob
from modeling.execution_artifacts import projection_lock
from modeling.sfs_evidence import _sync_directory

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
    with projection_lock(routing.dataset_id), service.locked(write=True):
        job, scopes = bound_job(actor, identifier)
        if job.specification["legacy"]["options"].get("legacy_response_contract") != PROTOCOL:
            return
        lock_authority(actor, job.dataset_id, None)
        history = f"modeling/{job.dataset_id}_runs/"
        executions, archives = set(), []
        for name in job.result["files"]:
            if name.startswith("execution_runs/"):
                parts = Path(legacy.relative(name)).parts
                if len(parts) < 3 or str(uuid.UUID(parts[1])) != parts[1]:
                    legacy.conflict("selection_target_invalid")
                executions.add(parts[1])
            elif name.startswith(history):
                uuid.UUID(Path(name).stem.split("_run_", 1)[-1])
                archives.append(name)
        for execution in sorted(executions):
            for name in sorted(publish_execution(job, execution)):
                if Path(name).suffix.lower() in {".json", ".csv", ".png", ".svg", ".pdf"}:
                    projects.register_artifact(publication_path(name), file_id=job.dataset_id)
        for name in sorted(archives):
            path = publish_history_member(job, name)
            if path.suffix.lower() in {".json", ".csv", ".png", ".svg", ".pdf"}:
                projects.register_artifact(path, file_id=job.dataset_id)
        # Legacy search projections are derived from this exact terminal job.
        # The durable receipt remains authoritative; immutable history is above.
        operation = job.specification["legacy"]["operation"]
        if operation in {"sfs", "hpo"}:
            latest = NativeJob.objects.filter(
                dataset_id=job.dataset_id,
                state="succeeded",
                specification__kind=legacy.KIND,
                specification__legacy__operation=operation,
            ).order_by("-created_at", "-pk").values_list("pk", flat=True).first()
            if latest == job.pk:
                folder, suffix = (
                    ("sfs_results", "sfs_results") if operation == "sfs" else ("hyperparam_results", "hyperparam")
                )
                name = f"{folder}/{job.dataset_id}_{suffix}.json"
                raw = member(job, name)
                path = publication_path(name)
                if not os.path.lexists(path) or legacy.read(path) != raw:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".staging-") as staging:
                        staged = Path(staging) / path.name
                        write_member(staged, raw)
                        for scope in scopes:
                            projects.recheck(scope)
                        os.replace(staged, path)
                _sync_directory(path.parent)
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
