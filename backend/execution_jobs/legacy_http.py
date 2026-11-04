"""Compatibility routes return durable receipts; they never own numerical work."""

import json
from pathlib import Path

from django.conf import settings
from rest_framework.response import Response

from execution_jobs import legacy_execution as legacy, service
from execution_jobs.models import NativeJob


def launch(request, operation):
    from execution_jobs.views import ERRORS, failure

    try:
        if not isinstance(request.data, dict):
            raise ValueError("Supply a request object.")
        options = {k: v for k, v in request.data.items() if k != "execution_request"}
        binding = request.data.get("execution_request")
        if binding is None and request.headers.get("X-DeclarAI-Execution-Protocol") != "native-reviewed-v1":
            from execution_jobs.legacy_compatibility import launch as compatibility_launch

            return compatibility_launch(request, operation, options)
        if not isinstance(binding, dict) or set(binding) != {"request_id", "plan_sha256", "inputs_sha256"}:
            return Response(
                {
                    "error_code": "job_legacy_preview_required",
                    "operation": operation,
                    "error": "Review the frozen input version and execution budget before submitting.",
                    "preview_endpoint": f"/api/jobs/datasets/{options.get('file_id')}/legacy-input/",
                },
                status=409,
            )
        result = service.submit(
            request.user,
            options.get("file_id"),
            {"kind": legacy.KIND, "operation": operation, "options": options, **binding},
        )
        return Response(adapt(result, operation), status=200 if result["replayed"] else 202)
    except ERRORS as error:
        return failure(error)


def adapt(receipt, operation):
    state = receipt["state"]
    result = receipt.get("result") or {}
    payload = result.get("payload") or {}
    status = (
        "completed"
        if state == "succeeded"
        else "stopped"
        if state == "cancelled"
        else "error"
        if state in {"failed", "blocked"}
        else "running"
    )
    if operation == "training":
        status = "ok" if state == "succeeded" else status
    progress = (
        next(
            (e["detail"].get("progress") for e in reversed(receipt["events"]) if e["event_type"] == "legacy_progress"),
            {},
        )
        or {}
    )
    checkpoint = next(
        (e["detail"] for e in reversed(receipt["events"]) if e["event_type"] == "legacy_checkpoint"), None
    )
    return {
        **payload,
        **progress,
        "resume_checkpoint": ({**checkpoint, "job_id": receipt["id"]} if checkpoint else None),
        "native_operation": receipt["specification"]["legacy"]["operation"],
        "status": status,
        "job_status": "completed"
        if state == "succeeded"
        else "error"
        if state in {"failed", "blocked"}
        else "stopped"
        if state == "cancelled"
        else state,
        "file_id": receipt["file_id"],
        "native_job_id": receipt["id"],
        "operation_id": receipt["id"],
        "native_state": state,
        "result_sha256": receipt["result_sha256"],
        "reason_code": receipt["reason_code"],
        "immutable_candidate": state == "succeeded",
        "model_adopted": False,
        "legacy_projection_updated": False,
        "selected_for_development": False,
        "progress": 1.0 if state == "succeeded" else progress.get("progress", 0.0),
        "failure": next(
            (e["detail"].get("failure") for e in reversed(receipt["events"]) if e["event_type"] == "legacy_failure"),
            None,
        ),
        "error": None if status not in {"error", "stopped"} else receipt["reason_code"],
        "budget": receipt["specification"]["limits"],
        "review_approved": False,
        "production_use_approved": False,
    }


def read_current(actor, file_id, operation, *, job_id=None, execution_id=None, selected=False):
    from django.db.models import Q
    from execution_jobs import history
    from execution_jobs.legacy_selection import current as selected_pointer, candidate, verified_pointer

    service.scope(actor, file_id)
    if job_id:
        import uuid

        job_id = str(uuid.UUID(str(job_id)))
    if selected and operation == "training":
        _, payload = selected_pointer(file_id)
        if payload and "native_job_selection" in payload:
            job = verified_pointer(actor, payload)
            if job.dataset_id != file_id:
                legacy.conflict("dataset_mismatch")
            return {
                **payload,
                "native_job_id": str(job.pk),
                "result_sha256": job.result_sha256,
                "immutable_candidate": True,
                "selected_for_development": True,
                "native_state": "succeeded",
                "job_status": "completed",
                "status": "ok",
            }
        if payload:
            return None
    query = NativeJob.objects.filter(dataset_id=file_id, specification__kind=legacy.KIND)
    if execution_id:
        import uuid

        execution_id = str(uuid.UUID(execution_id))
        query = query.filter(
            Q(result__payload__execution_id=execution_id)
            | Q(result__payload__forward_execution_id=execution_id)
            | Q(result__payload__backward_execution_id=execution_id)
            | Q(result__payload__forward_from_backward_execution_id=execution_id)
        )
    else:
        query = query.filter(specification__legacy__operation=operation)
    if job_id:
        query = query.filter(pk=job_id)
    with history._bounded_read():
        job = query.order_by("-created_at", "-id").first()
    if job is None:
        if job_id:
            legacy.conflict("execution_unavailable")
        return None
    receipt = service.read(actor, job.pk)
    if job.state == "succeeded" and job.specification["legacy"]["options"].get("legacy_response_contract") == "v1":
        from execution_jobs.legacy_compatibility import materialize

        materialize(actor, job.pk)
    reply = adapt(receipt, operation)
    if execution_id and job.state == "succeeded":
        payload, _ = candidate(job, execution_id)
        reply = {**reply, **payload, "status": "ok", "job_status": "completed"}
    _, payload = selected_pointer(file_id)
    stamp = (payload or {}).get("native_job_selection") or {}
    reply["selected_for_development"] = (
        stamp.get("job_id") == str(job.pk) and stamp.get("result_sha256") == job.result_sha256
    )
    if reply["selected_for_development"]:
        verified_pointer(actor, payload)
        if execution_id and stamp.get("execution_id") != execution_id:
            reply["selected_for_development"] = False
    reply["selected_execution_id"] = stamp.get("execution_id") if reply["selected_for_development"] else None
    return reply


def current(request, file_id, operation):
    return read_current(
        request.user,
        file_id,
        operation,
        job_id=request.query_params.get("job_id"),
        execution_id=request.query_params.get("execution_id"),
        selected=request.query_params.get("selected") == "true"
        or (
            operation == "training"
            and not request.query_params.get("job_id")
            and not request.query_params.get("execution_id")
        ),
    )


def status(request, file_id, operation):
    from execution_jobs.views import ERRORS, failure

    try:
        value = current(request, file_id, operation)
        if value is not None:
            return Response(value)
        return None
    except ERRORS as error:
        return failure(error)


def cancel(request, file_id, operation):
    from execution_jobs.views import ERRORS, failure

    try:
        service.scope(request.user, file_id)
        identifier = request.data.get("operation_id")
        if not identifier:
            if not NativeJob.objects.filter(
                dataset_id=file_id, specification__kind=legacy.KIND, specification__legacy__operation=operation
            ).exists():
                return Response({"status": "not_running", "file_id": file_id})
            raise ValueError("Select the exact operation to cancel.")
        job = NativeJob.objects.get(pk=identifier)
        if (
            job.dataset_id != file_id
            or job.specification.get("kind") != legacy.KIND
            or job.specification["legacy"]["operation"] != operation
        ):
            legacy.conflict("operation_changed")
        return Response(adapt(service.cancel(request.user, identifier, {"action": "cancel"}), operation))
    except ERRORS as error:
        return failure(error)
