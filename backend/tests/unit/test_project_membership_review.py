"""Membership changes must commit under the authority and state reviewed."""

import uuid

import pytest
from django.test import Client

from access_control import project_views, projects
from access_control.authority import AccessDenied, authorized_access
from access_control.models import MCPDatasetGrant, ProjectAuthorityEvent, ProjectMembership
from access_control.session_authority import revoke_sessions
from tests.unit.test_project_authority import post, world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def test_membership_review_requires_admin_and_csrf_then_revokes_cross_channel_access(world, monkeypatch):
    project, other, users, clients, files, _ = world
    route = f"/api/projects/{project.pk}/members/"
    body = {"operation": "preview", "username": "developer"}
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(users["admin"])
    assert post(csrf_client, route, body).status_code == 403
    for role in ["developer", "reviewer", "outsider"]:
        assert post(clients[role], route, body).status_code == 403
    assert post(clients["admin"], f"/api/projects/{other.pk}/members/", body).status_code == 403
    assert post(clients["admin"], route, {**body, "username": "admin"}).status_code == 400

    review = post(clients["admin"], route, body)
    assert review.status_code == 200
    assert review["Cache-Control"] == "private, no-store"
    assert review.json()["role"] == "developer"
    assert not ProjectAuthorityEvent.objects.filter(operation="member").exists()
    MCPDatasetGrant.objects.create(actor=users["developer"], dataset=files[0], role="read")
    from ai_assistant.mcp_server.auth import SCOPE_PIPELINE_READ

    monkeypatch.setenv("DECLARAI_MCP_ACTOR_USER_ID", str(users["developer"].pk))
    monkeypatch.setenv("DECLARAI_MCP_SCOPES", SCOPE_PIPELINE_READ)
    with authorized_access(files[0].pk, "read", "membership-review", SCOPE_PIPELINE_READ):
        assert clients["developer"].get(f"/api/declaration/{files[0].pk}/").status_code == 200
    payload = {
        "username": "developer",
        "role": "none",
        "expected": review.json()["expected"],
        "request_id": str(uuid.uuid4()),
    }
    result = post(clients["admin"], route, payload)
    assert result.status_code == 200, result.content
    event = ProjectAuthorityEvent.objects.get(pk=payload["request_id"])
    assert event.actor == users["admin"] and event.resource["role"] == "none"
    assert post(clients["admin"], route, payload).json()["replayed"] is True
    stale = post(clients["admin"], route, {**payload, "role": "reviewer", "request_id": str(uuid.uuid4())})
    assert stale.status_code == 409
    assert stale.json()["error_code"] == "project_membership_changed"
    assert ProjectAuthorityEvent.objects.filter(operation="member").count() == 1
    assert clients["developer"].get(f"/api/declaration/{files[0].pk}/").status_code == 403
    assert clients["developer"].get("/media/" + files[0].file.name).status_code == 403
    with pytest.raises(AccessDenied), authorized_access(files[0].pk, "read", "membership-review", SCOPE_PIPELINE_READ):
        pytest.fail("Revoked membership reached MCP data")
    assert clients["developer"].get("/api/auth/session/").json()["authenticated"] is True


@pytest.mark.parametrize("boundary", ["session", "password", "admin_membership"])
def test_admin_authority_changed_after_request_admission_blocks_commit(world, monkeypatch, boundary):
    project, _, users, clients, _, _ = world
    route = f"/api/projects/{project.pk}/members/"
    before = ProjectMembership.objects.get(project=project, actor=users["developer"])
    review = post(clients["admin"], route, {"operation": "preview", "username": "developer"}).json()
    original = projects.admin_change

    def changed(*args, **kwargs):
        if boundary == "session":
            revoke_sessions(users["admin"], request_id=uuid.uuid4(), operator_label="test-operator")
        elif boundary == "password":
            users["admin"].set_unusable_password()
            users["admin"].save(update_fields=["password"])
        else:
            # Same effective role after rotation must not reuse the admitted revision.
            member = ProjectMembership.objects.get(project=project, actor=users["admin"])
            member.save()
        return original(*args, **kwargs)

    monkeypatch.setattr(project_views.projects, "admin_change", changed)
    payload = {"username": "developer", "role": "reviewer", "request_id": str(uuid.uuid4())}
    if boundary == "session":
        payload["expected"] = review["expected"]
    response = post(clients["admin"], route, payload)
    assert response.status_code == 403
    assert response.json()["error_code"] == (
        "project_authority_changed" if boundary == "admin_membership" else "project_session_authority_changed"
    )
    before.refresh_from_db()
    assert before.role == "developer"
    assert not ProjectAuthorityEvent.objects.filter(operation="member").exists()


def test_review_detects_replaced_target_account_with_no_membership(world, django_user_model):
    project, _, users, clients, _, _ = world
    route = f"/api/projects/{project.pk}/members/"
    preview = post(clients["admin"], route, {"operation": "preview", "username": "outsider"}).json()
    assert preview["role"] == "none"
    users["outsider"].delete()
    replacement = django_user_model.objects.create_user(username="outsider")
    result = post(
        clients["admin"],
        route,
        {"username": "outsider", "role": "developer", "expected": preview["expected"], "request_id": str(uuid.uuid4())},
    )
    assert result.status_code == 409
    assert not ProjectMembership.objects.filter(project=project, actor=replacement).exists()


def test_two_reviews_of_same_membership_can_commit_only_one_change(world):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connection

    project, _, users, clients, _, _ = world
    route = f"/api/projects/{project.pk}/members/"
    review = post(clients["admin"], route, {"operation": "preview", "username": "developer"}).json()
    barrier = Barrier(2)

    def submit(role, concurrent):
        try:
            client = Client()
            client.cookies = clients["admin"].cookies.copy()
            if concurrent:
                barrier.wait(timeout=10)
            return post(
                client,
                route,
                {
                    "username": "developer",
                    "role": role,
                    "request_id": str(uuid.uuid4()),
                    "expected": review["expected"],
                },
            ).status_code
        finally:
            if concurrent:
                close_old_connections()

    roles = ["reviewer", "none"]
    if connection.vendor == "postgresql":
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda role: submit(role, True), roles))
    else:
        results = [submit(role, False) for role in roles]
    assert sorted(results) == [200, 409]
    event = ProjectAuthorityEvent.objects.get(operation="member")
    member = ProjectMembership.objects.get(project=project, actor=users["developer"])
    assert event.resource["role"] == roles[results.index(200)]
    assert str(member.revision) == event.resource["membership_revision"]
