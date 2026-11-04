"""Explicit disposable-fixture bootstrap before worker services are started.

This is not an HTTP/MCP entrypoint. Qualification owns the database, source rows
and actor. It delivers a real queued request through production claim/execution
and exact development selection, without a broker or background test thread.
"""

import os
import uuid

from django.conf import settings

from access_control import projects
from execution_jobs import legacy_execution as legacy, service
from execution_jobs.legacy_selection import current, select


def train_for_qualification(actor, options):
    if os.environ.get("DECLARAI_TEST_INSTALLATION") != "1":
        raise RuntimeError("Disposable qualification installation required.")
    file_id = options["file_id"]
    scope = projects.dataset_authority(actor.pk, file_id, "read")
    if scope["role"] != "developer":
        raise projects.ProjectDenied("job_submit_role_required")
    if not settings.DECLARAI_JOBS_ENABLED:
        from modeling.views import execute_legacy_training

        response = execute_legacy_training(options)
        if response.status_code != 200:
            raise RuntimeError("Disposable native model preparation failed.")
        return response.data
    expected, _ = current(file_id)
    preview = legacy.preview(actor, file_id, "training", options)
    receipt = service.submit(
        actor,
        file_id,
        {
            "kind": legacy.KIND,
            "operation": "training",
            "options": options,
            "request_id": str(uuid.uuid4()),
            "plan_sha256": preview["plan_sha256"],
            "inputs_sha256": preview["inputs_sha256"],
        },
    )
    service.execute(receipt["id"])
    completed = service.read(actor, receipt["id"])
    if completed["state"] != "succeeded":
        raise RuntimeError("Disposable native model preparation failed: " + completed["reason_code"])
    payload = completed["result"]["payload"]
    select(
        actor,
        receipt["id"],
        {
            "request_id": str(uuid.uuid4()),
            "result_sha256": completed["result_sha256"],
            "execution_id": payload["execution_id"],
            "expected_projection_sha256": expected,
        },
    )
    return payload
