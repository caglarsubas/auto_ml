"""Real session, audit-failure and operator-revocation boundaries."""

import copy
import json
import uuid
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from access_control.models import AuthenticationEvent, LoginThrottleBucket, SessionAuthority, AssistantActionApproval
from access_control.session_authority import reserve_login, complete_login, revoke_sessions, SESSION_REVISION_KEY

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db]
PASSWORD = "synthetic-session-governance-password"


def signin(client, username, password=PASSWORD, **headers):
    csrf = client.get("/api/auth/session/").json()["csrf_token"]
    return client.post(
        "/api/auth/login/",
        {"username": username, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
        **headers,
    )


@pytest.fixture
def actor(django_user_model):
    return django_user_model.objects.create_user(username="governance-actor", password=PASSWORD)


def test_login_and_logout_have_bound_attributable_receipts_without_credentials(actor):
    client = APIClient(enforce_csrf_checks=True)
    result = signin(client, actor.username, REMOTE_ADDR="198.51.100.24")
    assert result.status_code == 200
    event = AuthenticationEvent.objects.get(event_type="login")
    authority = SessionAuthority.objects.get(user=actor)
    assert event.outcome == "completed" and event.actor_snapshot["id"] == actor.pk
    assert event.session_revision == authority.revision
    assert client.session[SESSION_REVISION_KEY] == str(authority.revision)
    serialized = json.dumps(list(AuthenticationEvent.objects.values()), default=str)
    assert PASSWORD not in serialized and "198.51.100.24" not in serialized
    assert client.cookies["sessionid"].value not in serialized
    assert result.json()["csrf_token"] not in serialized
    assert len(event.source_key) == len(event.principal_key) == 64
    logout = client.post("/api/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=result.json()["csrf_token"])
    assert logout.status_code == 200 and logout.json()["authenticated"] is False
    assert AuthenticationEvent.objects.get(event_type="logout").actor_id == actor.pk


def test_unknown_identity_is_hashed_and_inactive_credentials_are_indistinguishable(actor):
    actor.is_active = False
    actor.save(update_fields=["is_active"])
    client = APIClient(enforce_csrf_checks=True)
    unknown = signin(client, "unknown-private-identity")
    inactive = signin(client, actor.username)
    assert unknown.status_code == inactive.status_code == 401
    assert unknown.json() == inactive.json()
    events = list(AuthenticationEvent.objects.filter(event_type="login"))
    assert len(events) == 2 and all(e.actor_id is None and e.reason_code == "invalid_credentials" for e in events)
    assert "unknown-private-identity" not in json.dumps([e.__dict__ for e in events], default=str)


def test_throttle_persists_across_clients_and_ignores_forwarded_source_headers(settings):
    settings.DECLARAI_AUTH_LOGIN_PAIR_LIMIT = 2
    first, second = APIClient(enforce_csrf_checks=True), APIClient(enforce_csrf_checks=True)
    assert signin(first, "unknown").status_code == 401
    assert signin(second, "unknown").status_code == 401
    blocked = signin(second, "unknown", HTTP_X_FORWARDED_FOR="different-untrusted-address")
    assert blocked.status_code == 429 and blocked["Retry-After"] == "60"
    assert signin(first, "unknown").status_code == 429
    assert AuthenticationEvent.objects.filter(reason_code="login_principal_rate_limited").count() == 1
    assert LoginThrottleBucket.objects.filter(blocked_attempts=2).count() == 1


def test_source_budget_blocks_identity_rotation_without_allocating_new_buckets(settings):
    settings.DECLARAI_AUTH_LOGIN_SOURCE_LIMIT = 2
    client = APIClient(enforce_csrf_checks=True)
    assert signin(client, "unknown-one").status_code == 401
    assert signin(client, "unknown-two").status_code == 401
    assert LoginThrottleBucket.objects.count() == 3
    assert signin(client, "unknown-three").status_code == 429
    assert signin(client, "unknown-four").status_code == 429
    assert LoginThrottleBucket.objects.count() == 3
    assert AuthenticationEvent.objects.filter(reason_code="login_source_rate_limited").count() == 1


def test_success_resets_pair_budget_but_does_not_reset_source_budget(actor, settings):
    settings.DECLARAI_AUTH_LOGIN_SOURCE_LIMIT = 3
    client = APIClient(enforce_csrf_checks=True)
    assert signin(client, actor.username, password="wrong").status_code == 401
    assert signin(client, actor.username).status_code == 200
    assert signin(client, actor.username).status_code == 200
    assert signin(client, actor.username).status_code == 429


def test_elapsed_window_allows_new_attempt_without_erasing_old_receipts(settings):
    settings.DECLARAI_AUTH_LOGIN_PAIR_LIMIT = 1
    client = APIClient(enforce_csrf_checks=True)
    assert signin(client, "unknown").status_code == 401
    assert signin(client, "unknown").status_code == 429
    LoginThrottleBucket.objects.update(window_started_at=timezone.now() - timedelta(seconds=61))
    assert signin(client, "unknown").status_code == 401
    assert AuthenticationEvent.objects.count() == 3


def test_missing_audit_prevents_login_and_rolls_back_admission(actor, monkeypatch):
    def unavailable(**kwargs):
        raise DatabaseError("synthetic audit outage")

    monkeypatch.setattr(AuthenticationEvent.objects, "create", unavailable)
    client = APIClient(enforce_csrf_checks=True)
    result = signin(client, actor.username)
    assert result.status_code == 503 and result.json()["error_code"] == "authentication_authority_unavailable"
    assert AuthenticationEvent.objects.count() == LoginThrottleBucket.objects.count() == Session.objects.count() == 0
    assert client.get("/api/auth/session/").json()["authenticated"] is False


def test_completion_audit_failure_cannot_issue_a_session(actor, monkeypatch):
    class FailedReceipt:
        def update(self, **kwargs):
            raise DatabaseError("synthetic completion outage")

    monkeypatch.setattr(AuthenticationEvent.objects, "filter", lambda **kwargs: FailedReceipt())
    client = APIClient(enforce_csrf_checks=True)
    assert signin(client, actor.username).status_code == 503
    assert Session.objects.count() == SessionAuthority.objects.count() == 0
    assert AuthenticationEvent.objects.get().outcome == "pending"
    assert client.get("/api/auth/session/").json()["authenticated"] is False


def test_password_changes_during_authentication_do_not_inherit_a_validated_password(actor):
    request = RequestFactory().post("/api/auth/login/")
    request.user = AnonymousUser()
    admitted, event = reserve_login(request, actor.username)
    assert admitted
    authenticated = copy.copy(actor)
    authenticated.backend = "django.contrib.auth.backends.ModelBackend"
    actor.set_password("different-synthetic-password")
    actor.save(update_fields=["password"])
    assert complete_login(request, authenticated, event) is False
    assert AuthenticationEvent.objects.get(pk=event.pk).reason_code == "credentials_changed_during_login"
    assert not SessionAuthority.objects.exists()


def test_revoke_all_sessions_but_preserve_other_users_and_allow_fresh_signin(actor, django_user_model):
    clients = [APIClient(enforce_csrf_checks=True) for _ in range(2)]
    for client in clients:
        assert signin(client, actor.username).status_code == 200
    other = django_user_model.objects.create_user(username="other-governance-actor", password=PASSWORD)
    unaffected = APIClient(enforce_csrf_checks=True)
    assert signin(unaffected, other.username).status_code == 200
    event, replayed = revoke_sessions(actor, request_id=uuid.uuid4(), operator_label="test-operator")
    assert not replayed and event.actor_id is None and event.subject_snapshot["id"] == actor.pk
    for client in clients:
        assert client.get("/api/declaration/").status_code == 403
        assert client.get("/api/auth/session/").json()["authenticated"] is False
    assert unaffected.get("/api/declaration/").status_code == 200
    assert signin(clients[0], actor.username).status_code == 200
    assert clients[0].get("/api/declaration/").status_code == 200
    assert AuthenticationEvent.objects.filter(event_type="session_rejected").count() == 2


def test_revocation_command_replays_same_receipt_without_invalidating_new_session(actor):
    identifier = str(uuid.uuid4())
    output = StringIO()
    call_command(
        "revoke_web_sessions",
        "--user",
        actor.username,
        "--request-id",
        identifier,
        "--operator-label",
        "ops-ticket-17",
        stdout=output,
    )
    first = json.loads(output.getvalue())
    client = APIClient(enforce_csrf_checks=True)
    assert signin(client, actor.username).status_code == 200
    revision = SessionAuthority.objects.get(user=actor).revision
    replay = StringIO()
    call_command(
        "revoke_web_sessions",
        "--user",
        actor.username,
        "--request-id",
        identifier,
        "--operator-label",
        "ops-ticket-17",
        stdout=replay,
    )
    assert json.loads(replay.getvalue())["event_id"] == first["event_id"]
    assert json.loads(replay.getvalue())["replayed_receipt"] is True
    assert SessionAuthority.objects.get(user=actor).revision == revision
    assert client.get("/api/declaration/").status_code == 200
    with pytest.raises(CommandError, match="another operation"):
        call_command(
            "revoke_web_sessions",
            "--user",
            actor.username,
            "--request-id",
            identifier,
            "--operator-label",
            "changed-operator",
            stdout=StringIO(),
        )


@pytest.mark.parametrize("state", ["prepared", "approved", "dispatching", "completed", "failed"])
def test_revocation_cancels_only_unused_approvals(actor, state):
    approval = AssistantActionApproval.objects.create(
        actor=actor,
        file_id=1,
        action_type="update_notes",
        actor_snapshot={"id": actor.pk},
        payload={},
        context={},
        environment={},
        budget={},
        proposal_sha256="a" * 64,
        expires_at=timezone.now() + timedelta(minutes=1),
        state=state,
    )
    event, _ = revoke_sessions(actor, request_id=uuid.uuid4(), operator_label="operator")
    approval.refresh_from_db()
    assert approval.state == ("cancelled" if state in ("prepared", "approved") else state)
    assert event.details["cancelled_actions"] == int(state in ("prepared", "approved"))


def test_deactivation_blocks_web_and_existing_mcp_actor(actor, monkeypatch):
    from access_control.authority import configured_actor, AccessDenied

    client = APIClient(enforce_csrf_checks=True)
    assert signin(client, actor.username).status_code == 200
    monkeypatch.setenv("DECLARAI_MCP_ACTOR_USER_ID", str(actor.pk))
    assert configured_actor().pk == actor.pk
    revoke_sessions(actor, request_id=uuid.uuid4(), operator_label="operator", deactivate=True)
    assert client.get("/api/declaration/").status_code == 403
    assert signin(client, actor.username).status_code == 401
    with pytest.raises(AccessDenied, match="mcp_actor_identity_unavailable"):
        configured_actor()


def test_unbound_legacy_session_is_rejected_without_reconstructing_authority(actor):
    client = APIClient()
    client.force_login(actor)
    session = client.session
    del session[SESSION_REVISION_KEY]
    session.save()
    assert client.get("/api/declaration/").status_code == 403
    assert AuthenticationEvent.objects.get(event_type="session_rejected").reason_code == "session_revision_unavailable"


def test_authority_failure_withholds_protected_response(actor, monkeypatch):
    client = APIClient()
    client.force_login(actor)

    def unavailable(**kwargs):
        raise DatabaseError("synthetic authority outage")

    monkeypatch.setattr(SessionAuthority.objects, "filter", unavailable)
    result = client.get("/api/declaration/")
    assert result.status_code == 503 and result["Cache-Control"] == "no-store"
    assert "synthetic" not in result.content.decode()


def test_operator_audit_failure_rolls_back_revision_deactivation_and_cancellation(actor, monkeypatch):
    client = APIClient()
    client.force_login(actor)
    revision = SessionAuthority.objects.get(user=actor).revision

    def unavailable(**kwargs):
        raise DatabaseError("synthetic operator audit outage")

    monkeypatch.setattr(AuthenticationEvent.objects, "create", unavailable)
    with pytest.raises(DatabaseError):
        revoke_sessions(actor, request_id=uuid.uuid4(), operator_label="operator", deactivate=True)
    actor.refresh_from_db()
    assert actor.is_active and SessionAuthority.objects.get(user=actor).revision == revision
    assert client.get("/api/declaration/").status_code == 200


def test_identity_snapshot_survives_actor_deletion(actor):
    client = APIClient(enforce_csrf_checks=True)
    assert signin(client, actor.username).status_code == 200
    event = AuthenticationEvent.objects.get(event_type="login")
    actor_id = actor.pk
    actor.delete()
    event.refresh_from_db()
    assert event.actor_id is None and event.actor_snapshot["id"] == actor_id
    assert client.get("/api/declaration/").status_code == 403


def test_admin_and_api_share_login_admission_and_admin_binding(actor, settings):
    settings.DECLARAI_AUTH_LOGIN_PAIR_LIMIT = 1
    actor.is_staff = True
    actor.save(update_fields=["is_staff"])
    client = APIClient(enforce_csrf_checks=True)
    assert signin(client, actor.username, password="wrong").status_code == 401
    client.get("/admin/login/")
    response = client.post(
        "/admin/login/",
        {"username": actor.username, "password": PASSWORD, "next": "/admin/"},
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 200  # Admin's generic denied-login form.
    assert client.get("/api/auth/session/").json()["authenticated"] is False
    assert (
        AuthenticationEvent.objects.get(reason_code="login_principal_rate_limited").authority_source
        == "django_password_backend"
    )
    LoginThrottleBucket.objects.update(window_started_at=timezone.now() - timedelta(seconds=61))
    response = client.post(
        "/admin/login/",
        {"username": actor.username, "password": PASSWORD, "next": "/admin/"},
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 302
    assert client.get("/api/auth/session/").json()["authenticated"] is True
    assert AuthenticationEvent.objects.get(event_type="credentials_validated").actor_id == actor.pk
    assert AuthenticationEvent.objects.get(event_type="session_bound").actor_id == actor.pk
    revoke_sessions(actor, request_id=uuid.uuid4(), operator_label="operator")
    assert client.get("/admin/").status_code == 302


def test_oversized_password_payload_is_never_admitted_or_echoed():
    client = APIClient(enforce_csrf_checks=True)
    result = signin(client, "unknown", password="synthetic-sensitive-value-" * 1000)
    assert result.status_code == 400
    assert not AuthenticationEvent.objects.exists() and not LoginThrottleBucket.objects.exists()
    assert "synthetic-sensitive" not in result.content.decode()


def test_logout_audit_failure_does_not_report_completed_logout(actor, monkeypatch):
    client = APIClient(enforce_csrf_checks=True)
    result = signin(client, actor.username)

    def unavailable(**kwargs):
        raise DatabaseError("synthetic logout audit outage")

    monkeypatch.setattr(AuthenticationEvent.objects, "create", unavailable)
    response = client.post("/api/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=result.json()["csrf_token"])
    assert response.status_code == 503
    assert not AuthenticationEvent.objects.filter(event_type="logout").exists()
    assert client.get("/api/auth/session/").json()["authenticated"] is True


@pytest.mark.parametrize(
    "name,value",
    [
        ("DECLARAI_AUTH_LOGIN_WINDOW_SECONDS", "0"),
        ("DECLARAI_AUTH_LOGIN_WINDOW_SECONDS", "86401"),
        ("DECLARAI_AUTH_LOGIN_PAIR_LIMIT", "0"),
        ("DECLARAI_AUTH_LOGIN_PAIR_LIMIT", "1001"),
        ("DECLARAI_AUTH_LOGIN_SOURCE_LIMIT", "0"),
        ("DECLARAI_AUTH_LOGIN_SOURCE_LIMIT", "10001"),
    ],
)
def test_invalid_admission_settings_block_startup(tmp_path, name, value):
    from backend.runtime_config import load_runtime
    from django.core.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured, match=name):
        load_runtime(tmp_path, "synthetic-development-key", {name: value})
