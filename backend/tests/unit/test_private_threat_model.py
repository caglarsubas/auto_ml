"""Compose sealed policy, native evidence and both application authority paths."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.db import DatabaseError, connection, connections
from django.test.utils import CaptureQueriesContext
from mcp.shared.memory import create_connected_server_and_client_session

from access_control import data_policy, projects
from access_control.models import MCPAccessEvent, MCPDatasetGrant, Project
from ai_assistant.mcp_server.server import create_mcp_server
from execution_jobs import service
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import admission, post, queue, world  # noqa: F401
from tests.unit.test_independent_review import action, actor, native_evidence, success
from tests.unit.test_native_training_scoring import preview, submit, write_scoring_input

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
TOOL = "declarai.get_execution_job"


def tool_text(result):
    return "\n".join(item.text for item in result.content if item.type == "text")


async def read_job(session, file_id, identifier):
    return await session.call_tool(TOOL, {"file_id": file_id, "job_id": str(identifier)})


async def assert_job_withheld(session, file_id, identifier, reason, *, subject_lookup=False):
    # Use the same thread-sensitive database connection as the MCP tool dispatcher.
    def capture():
        queries = CaptureQueriesContext(connection)
        queries.__enter__()
        return queries

    def finish(queries):
        queries.__exit__(None, None, None)
        return queries.captured_queries

    queries = await sync_to_async(capture)()
    try:
        response = await read_job(session, file_id, identifier)
    finally:
        observed = await sync_to_async(finish)(queries)
    message = tool_text(response)
    assert reason in message and str(identifier) not in message
    table = f'"{NativeJob._meta.db_table}"'
    if subject_lookup:
        assert any(table in query["sql"] for query in observed)
    assert not any(f'{table}."result"' in query["sql"]
                   or f'{table}."specification"' in query["sql"] for query in observed)
    return response


def test_sealed_private_authority_crosses_native_assessment_review_and_mcp(
    world, settings, monkeypatch, django_user_model,
):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    w = world
    body, _ = admission(w)
    w.trained = NativeJob.objects.get(pk=queue(w, body))
    service.execute(w.trained.pk)
    w.trained.refresh_from_db()
    assert w.trained.state == "succeeded", w.trained.reason_code

    technical_actor, reviewer = actor(w, django_user_model, "threat-model-reviewer", "reviewer")
    other = Project.objects.create(name="Other private project")
    projects.change_member(other, w.users["outsider"], "reviewer")
    projects.change_member(other, technical_actor, "reviewer")

    assessment, report, directory, opening = native_evidence(w)
    review = success(post(reviewer, directory, opening))
    review_url = f"/api/reviews/{review['id']}/"
    approval = action(review, "approve", report=report)
    review = success(post(reviewer, review_url, approval))
    assert review["review_approved"]
    reproduction = f"/api/jobs/{assessment.pk}/reproduction/?sha256={assessment.result_sha256}"
    for url in (review_url, reproduction):
        response = reviewer.get(url)
        assert response.status_code == 200 and response["Cache-Control"] == "no-store", response.content
        denied = w.clients["outsider"].get(url + ("&" if "?" in url else "?") + f"project_id={other.pk}")
        assert denied.status_code == 403 and assessment.result_sha256.encode() not in denied.content

    # The authenticated application still refuses external inference on this profile.
    refused = post(w.clients["developer"], "/api/ai-assistant/chat/", {
        "file_id": w.file_id, "message": "Synthetic protected evidence",
    })
    assert refused.status_code == 403 and refused.json() == data_policy.refusal()

    write_scoring_input(w, b"z,x\n2.0,1.5\n3.0,8.0\n")
    scoring_job = submit(w, preview(w))
    service.execute(scoring_job)
    source_bound = NativeJob.objects.get(pk=scoring_job)
    assert source_bound.state == "succeeded" and source_bound.source_dataset_id == w.input_id
    assert reviewer.get(f"/api/jobs/{scoring_job}/").status_code == 200

    grant = MCPDatasetGrant.objects.create(actor=technical_actor, dataset_id=w.file_id, role="read")
    monkeypatch.setenv("DECLARAI_MCP_ACTOR_USER_ID", str(technical_actor.pk))
    monkeypatch.setenv("DECLARAI_MCP_SCOPES", "declarai.pipeline.read")

    async def exercise():
        try:
            async with create_connected_server_and_client_session(
                create_mcp_server(), read_timeout_seconds=timedelta(seconds=15),
            ) as session:
                receipt = await read_job(session, w.file_id, assessment.pk)
                assert not receipt.isError
                summary = json.loads(tool_text(receipt))
                assert summary["job_id"] == str(assessment.pk) and summary["result_sha256"] == assessment.result_sha256
                assert summary["state"] == "succeeded" and not summary["production_use_approved"]
                assert not {"scores", "labels", "payload"} & summary.keys()

                reason = "Project authority is unavailable."
                await assert_job_withheld(session, w.file_id, scoring_job, reason, subject_lookup=True)
                await sync_to_async(MCPDatasetGrant.objects.create)(
                    actor=technical_actor, dataset_id=w.input_id, role="read",
                )
                await assert_job_withheld(session, w.input_id, assessment.pk, reason, subject_lookup=True)
                with patch.object(MCPAccessEvent.objects, "create", side_effect=DatabaseError("unavailable")):
                    denied = await assert_job_withheld(session, w.file_id, assessment.pk, "mcp_access_audit_unavailable")
                    assert denied.isError

                await sync_to_async(projects.change_member)(w.project, technical_actor, "none")
                denied = await assert_job_withheld(session, w.file_id, assessment.pk, "project_access_denied")
                assert denied.isError
        finally:
            await sync_to_async(connections.close_all)()

    asyncio.run(exercise())
    grant.refresh_from_db()
    assert grant.active and reviewer.get(f"/api/projects/").status_code == 200
    assert reviewer.get(reproduction).status_code == 403 and reviewer.get(review_url).status_code == 403
    invalidated = success(w.clients["reviewer"].get(review_url))
    assert not invalidated["review_approved"]
    assert invalidated["decision"]["reason_code"] == "review_approver_authority_changed"
    assert HoldoutAccess.objects.count() == 1
    assert MCPAccessEvent.objects.filter(
        actor=technical_actor, file_id=w.file_id, operation="read_tool",
        outcome="denied", reason_code="project_access_denied",
    ).exists()
