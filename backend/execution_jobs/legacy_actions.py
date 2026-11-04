"""Bind assistant/MCP approval to the same native proposal used by the browser."""

import uuid

from django.conf import settings

from execution_jobs import legacy_execution as legacy, service

ACTIONS = {"start_modeling": "training", "start_sfs": "sfs", "start_hyperparameter": "hpo"}


def prepare(actor, file_id, action_type, payload):
    if not settings.DECLARAI_JOBS_ENABLED or action_type not in ACTIONS:
        return None
    from execution_jobs.legacy_selection import current

    operation = ACTIONS[action_type]
    options = {k: v for k, v in payload.items() if k not in {"description"}}
    options["file_id"] = file_id
    if operation != "training" and not options.get("source_job_id"):
        _, selected = current(file_id)
        stamp = (selected or {}).get("native_job_selection")
        if not stamp:
            raise ValueError("Select the exact native source job/result/execution before preparing a search action.")
        options.update(
            source_job_id=stamp["job_id"],
            source_result_sha256=stamp["result_sha256"],
            execution_id=stamp["execution_id"],
        )
    preview = legacy.preview(actor, file_id, operation, options)
    return {
        "request": {
            "kind": legacy.KIND,
            "operation": operation,
            "options": options,
            "plan_sha256": preview["plan_sha256"],
            "inputs_sha256": preview["inputs_sha256"],
            "request_id": str(uuid.uuid4()),
        },
        "source": preview["source"],
        "budget": preview["budget"],
        "purpose": "native_development_candidate_only",
    }


def recheck(actor, file_id, binding):
    request = binding["request"]
    preview = legacy.preview(actor, file_id, request["operation"], request["options"])
    if any(preview[key] != request[key] for key in ("plan_sha256", "inputs_sha256")):
        raise ValueError("The frozen native proposal changed.")


def dispatch(actor, file_id, action_type, binding):
    job = service.submit(actor, file_id, binding["request"])
    return {
        "status": "success",
        "action_type": action_type,
        "description": "Queued the reviewed native development operation.",
        "native_job_started": True,
        "native_job_id": job["id"],
        "operation": binding["request"]["operation"],
        "file_id": file_id,
        "applied": {"native_job_id": job["id"], "operation_id": job["id"], "file_id": file_id, "state": job["state"]},
        "review_approved": False,
        "production_use_approved": False,
    }
