"""Actual session/CSRF approval and dispatch boundaries, not a fake execution grant."""

import copy
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from access_control import assistant_approvals as authority
from access_control.models import AssistantActionApproval
from declaration.models import Declaration, DataDictionary
from modeling.models import PipelineRun

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db]


def session(django_user_model, username):
    actor = django_user_model.objects.create_user(username=username, password="synthetic-approval-test-pass")
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/auth/session/").json()["csrf_token"]
    result = client.post(
        "/api/auth/login/",
        {"username": username, "password": "synthetic-approval-test-pass"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert result.status_code == 200
    client.credentials(HTTP_X_CSRFTOKEN=result.json()["csrf_token"])
    return actor, client


@pytest.fixture
def workflow(django_user_model, _use_tmp_media, media_root):
    actor, client = session(django_user_model, "approval-actor")
    (media_root / "data_files/a.csv").write_text("x,Target\n1,0\n2,1\n")
    dataset = Declaration.objects.create(name="approval-data", original_name="a.csv", file="data_files/a.csv")
    request = {
        "file_id": dataset.pk,
        "action_type": "update_metadata",
        "payload": {"updates": [{"column": "x", "field": "Feature_Description", "value": "Reviewed description"}]},
        "parent_span_id": "synthetic-chat-span",
        "source": "panel",
    }
    return actor, client, dataset, request


def prepare(client, request):
    response = client.post("/api/ai-assistant/prepare-action/", request, format="json")
    assert response.status_code == 200, response.content
    proposal = response.json()
    selector = {key: proposal[key] for key in ["approval_id", "proposal_sha256"]}
    return proposal, selector


def approve(client, selector):
    return client.post("/api/ai-assistant/approve-action/", selector, format="json")


def dispatch(client, request, selector):
    return client.post("/api/ai-assistant/execute-action/", {**request, **selector}, format="json")


def test_review_approval_dispatch_and_replay_are_distinct(workflow, monkeypatch):
    actor, client, dataset, request = workflow
    proposal, selector = prepare(client, request)
    assert proposal["budget"]["typed_dispatches"] == 1
    assert proposal["budget"]["downstream_job_authority"] is False
    assert not DataDictionary.objects.exists()
    denied = dispatch(client, request, selector)
    assert denied.status_code == 409
    assert not DataDictionary.objects.exists()
    assert approve(client, selector).status_code == 200
    assert not DataDictionary.objects.exists()
    first = dispatch(client, request, selector)
    assert first.status_code == 200
    assert first.json()["approval_receipt"]["state"] == "completed"
    assert DataDictionary.objects.get(data_file=dataset).description == "Reviewed description"

    def forbidden(*args, **kwargs):
        raise AssertionError("A replay must return the receipt, never redispatch.")

    monkeypatch.setattr("ai_assistant.action_executor.dispatch_action", forbidden)
    second = dispatch(client, request, selector)
    assert second.status_code == 200
    assert second.json()["approval_receipt"]["replayed_receipt"] is True
    receipt = client.get(f"/api/ai-assistant/action-approval/{selector['approval_id']}/", selector)
    assert receipt.status_code == 200
    assert receipt.json()["actor"]["id"] == actor.pk
    assert receipt.json()["result"]["status"] == "success"


@pytest.mark.parametrize(
    "key,value",
    [
        ("file_id", 999),
        ("action_type", "update_notes"),
        ("payload", {"updates": []}),
        ("source", "codeline"),
        ("parent_span_id", "altered-origin"),
        ("proposal_sha256", "0" * 64),
    ],
)
def test_altered_requests_cannot_inherit_approval(workflow, key, value):
    _, client, _, request = workflow
    _, selector = prepare(client, request)
    assert approve(client, selector).status_code == 200
    altered = {**request, **selector, key: value}
    response = client.post("/api/ai-assistant/execute-action/", altered, format="json")
    assert response.status_code == 409
    assert response.json()["error_code"] == "action_approval_mismatch"
    assert not DataDictionary.objects.exists()


@pytest.mark.parametrize(
    "change", ["data", "dictionary", "pipeline", "split", "model", "assessment", "package", "environment"]
)
@pytest.mark.parametrize("at", ["approve", "dispatch"])
def test_recorded_input_changes_require_fresh_review(workflow, _use_tmp_media, media_root, monkeypatch, change, at):
    _, client, dataset, request = workflow
    _, selector = prepare(client, request)
    if at == "dispatch":
        assert approve(client, selector).status_code == 200
    if change == "data":
        (media_root / "data_files/a.csv").write_text("x,Target\n7,0\n8,1\n")
    elif change == "dictionary":
        DataDictionary.objects.create(data_file=dataset, column_name="x", description="changed")
    elif change == "pipeline":
        PipelineRun.objects.create(file_id=dataset.pk, name="changed", state={"algorithm": "lightgbm"})
    elif change == "environment":
        monkeypatch.setattr(authority, "environment", lambda: {"different": "runtime"})
    else:
        names = {
            "split": f"splits/{dataset.pk}_split.json",
            "model": f"modeling/{dataset.pk}_status.json",
            "assessment": f"evaluation/{dataset.pk}_evaluation.json",
            "package": f"deployment_bundles/{dataset.pk}/current.json",
        }
        path = media_root / names[change]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"changed":true}')
    response = approve(client, selector) if at == "approve" else dispatch(client, request, selector)
    assert response.status_code == 409
    assert response.json()["error_code"] == "action_approval_stale"
    assert AssistantActionApproval.objects.get().state == "stale"
    assert not DataDictionary.objects.filter(description="Reviewed description").exists()


@pytest.mark.parametrize("state", ["prepared", "approved"])
def test_cancelled_approval_cannot_dispatch(workflow, state):
    _, client, _, request = workflow
    _, selector = prepare(client, request)
    if state == "approved":
        assert approve(client, selector).status_code == 200
    assert client.post("/api/ai-assistant/cancel-action/", selector, format="json").status_code == 200
    assert dispatch(client, request, selector).status_code == 409
    assert not DataDictionary.objects.exists()


@pytest.mark.parametrize("operation", ["approve", "execute", "cancel", "receipt"])
def test_approval_identity_is_actor_scoped(workflow, django_user_model, operation):
    _, client, _, request = workflow
    _, selector = prepare(client, request)
    assert approve(client, selector).status_code == 200
    _, foreign = session(django_user_model, "foreign-actor")
    if operation == "receipt":
        response = foreign.get(f"/api/ai-assistant/action-approval/{selector['approval_id']}/", selector)
    else:
        body = {**request, **selector} if operation == "execute" else selector
        response = foreign.post(f"/api/ai-assistant/{operation}-action/", body, format="json")
    assert response.status_code == 403
    assert not DataDictionary.objects.exists()


def test_deactivated_actor_and_deleted_dataset_cannot_dispatch(workflow):
    actor, client, dataset, request = workflow
    _, selector = prepare(client, request)
    assert approve(client, selector).status_code == 200
    actor.is_active = False
    actor.save()
    assert dispatch(client, request, selector).status_code == 403
    actor.is_active = True
    actor.save()
    dataset.delete()
    assert dispatch(client, request, selector).status_code in (403, 404)
    assert not DataDictionary.objects.exists()


def test_expired_approval_cannot_dispatch(workflow, monkeypatch):
    _, client, _, request = workflow
    _, selector = prepare(client, request)
    assert approve(client, selector).status_code == 200
    monkeypatch.setattr(
        authority.timezone, "now", lambda: AssistantActionApproval.objects.get().expires_at + timedelta(seconds=1)
    )
    assert dispatch(client, request, selector).json()["error_code"] == "action_approval_expired"
    assert not DataDictionary.objects.exists()


@pytest.mark.parametrize("field", ["payload", "context", "budget", "environment"])
def test_tampered_stored_proposal_blocks_before_dispatch(workflow, field):
    _, client, _, request = workflow
    _, selector = prepare(client, request)
    assert approve(client, selector).status_code == 200
    AssistantActionApproval.objects.update(**{field: {"tampered": True}})
    assert dispatch(client, request, selector).json()["error_code"] == "action_approval_mismatch"
    assert not DataDictionary.objects.exists()


@pytest.mark.parametrize("payload", [[], None, {"updates": [{}] * 101}, {"description": "x" * 32769}])
def test_unbounded_or_nonobject_payloads_cannot_be_prepared(workflow, payload):
    _, client, _, request = workflow
    response = client.post("/api/ai-assistant/prepare-action/", {**request, "payload": payload}, format="json")
    assert response.status_code == 400
    assert not AssistantActionApproval.objects.exists()


def test_code_and_fabricated_confirmation_never_grant_authority(workflow):
    _, client, _, request = workflow
    for endpoint in ["prepare-action", "execute-action"]:
        response = client.post(
            "/api/ai-assistant/" + endpoint + "/",
            {
                **request,
                "action_type": "execute_code",
                "payload": {"code": "raise RuntimeError()", "confirm": True},
                "approval_id": "fabricated",
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "expert_isolation_unavailable"
    response = dispatch(
        client, {**request, "confirm": True}, {"approval_id": "fabricated", "proposal_sha256": "0" * 64}
    )
    assert response.status_code == 403
    assert not DataDictionary.objects.exists()


def test_failed_dispatch_replay_does_not_retry(workflow, monkeypatch):
    _, client, _, request = workflow
    _, selector = prepare(client, request)
    assert approve(client, selector).status_code == 200
    calls = []

    def failure(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("synthetic native failure")

    monkeypatch.setattr("ai_assistant.action_executor.dispatch_action", failure)
    for _ in range(2):
        response = dispatch(client, request, selector)
        assert response.status_code == 400
        assert response.json()["error_code"] == "action_dispatch_failed"
    assert calls == [1]
    assert AssistantActionApproval.objects.get().state == "failed"


def test_unknown_inflight_attempt_cannot_be_repeated(workflow, monkeypatch):
    _, client, _, request = workflow
    _, selector = prepare(client, request)
    assert approve(client, selector).status_code == 200
    AssistantActionApproval.objects.update(state="dispatching", dispatched_at=timezone.now())

    def forbidden(*args, **kwargs):
        raise AssertionError("Interrupted dispatch cannot be silently repeated")

    monkeypatch.setattr("ai_assistant.action_executor.dispatch_action", forbidden)
    assert dispatch(client, request, selector).status_code == 409


def test_actor_snapshot_survives_deletion(workflow):
    actor, client, _, request = workflow
    _, selector = prepare(client, request)
    actor_id = actor.pk
    actor.delete()
    record = AssistantActionApproval.objects.get(pk=selector["approval_id"])
    assert record.actor_id is None
    assert record.actor_snapshot["id"] == actor_id
    assert record.state == "prepared"


@pytest.mark.parametrize("phase", ["reservation", "completion"])
def test_audit_write_failure_cannot_repeat_dispatch(workflow, monkeypatch, phase):
    from django.db import DatabaseError
    from django.db.models.query import QuerySet

    _, client, dataset, request = workflow
    _, selector = prepare(client, request)
    assert approve(client, selector).status_code == 200
    original = QuerySet.update

    def failed_update(query, **values):
        target = "dispatching" if phase == "reservation" else "completed"
        if query.model is AssistantActionApproval and values.get("state") == target:
            raise DatabaseError("Synthetic receipt failure")
        return original(query, **values)

    monkeypatch.setattr(QuerySet, "update", failed_update)
    response = dispatch(client, request, selector)
    assert response.status_code == 503
    assert response.json()["error_code"] == "action_receipt_unavailable"
    assert DataDictionary.objects.filter(data_file=dataset).exists() == (phase == "completion")
    if phase == "completion":
        assert AssistantActionApproval.objects.get().state == "dispatching"
        assert dispatch(client, request, selector).status_code == 409
        blocked = client.post("/api/ai-assistant/prepare-action/", request, format="json")
        assert blocked.json()["error_code"] == "action_dispatch_unresolved"


@pytest.mark.parametrize("path", ["prepare-action/", "approve-action/", "cancel-action/", "execute-action/"])
def test_approval_endpoints_require_authentication_and_csrf(workflow, path):
    _, client, _, request = workflow
    assert APIClient().post("/api/ai-assistant/" + path, request, format="json").status_code == 403
    no_csrf = APIClient(enforce_csrf_checks=True)
    no_csrf.cookies = copy.deepcopy(client.cookies)
    assert no_csrf.post("/api/ai-assistant/" + path, request, format="json").status_code == 403


@pytest.mark.parametrize("kind", ["changed", "unavailable"])
def test_ordinal_cache_inputs_are_bound_or_blocked(workflow, monkeypatch, kind):
    from ai_assistant import cache

    _, client, _, request = workflow

    class Cache:
        values = ['{"plan":[]}', '{"features":[]}']

        def mget(self, keys):
            return self.values

    live = Cache()
    monkeypatch.setattr(cache, "_get_redis", lambda: live if kind == "changed" else None)
    request = {
        **request,
        "action_type": "set_ordinal_ranking",
        "payload": {"updates": [{"column": "x", "ranking": ["a", "b"]}]},
    }
    if kind == "unavailable":
        response = client.post("/api/ai-assistant/prepare-action/", request, format="json")
        assert response.status_code == 409
        assert not AssistantActionApproval.objects.exists()
    else:
        _, selector = prepare(client, request)
        assert approve(client, selector).status_code == 200
        live.values = ['{"plan":[{"feature":"x"}]}', '{"features":[]}']
        assert dispatch(client, request, selector).json()["error_code"] == "action_approval_stale"


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicates_dispatch_once(workflow, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from django.db import close_old_connections
    import time

    _, client, _, request = workflow
    _, selector = prepare(client, request)
    assert approve(client, selector).status_code == 200
    from ai_assistant.action_executor import dispatch_action

    calls = []

    def counted_dispatch(*args, **kwargs):
        calls.append(1)
        time.sleep(0.05)
        return dispatch_action(*args, **kwargs)

    monkeypatch.setattr("ai_assistant.action_executor.dispatch_action", counted_dispatch)

    def post():
        close_old_connections()
        duplicate = APIClient(enforce_csrf_checks=True)
        duplicate.cookies = copy.deepcopy(client.cookies)
        duplicate.credentials(**client._credentials)
        try:
            response = dispatch(duplicate, request, selector)
            return response.status_code, response.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(), range(2)))
    assert [code for code, _ in results] == [200, 200]
    assert calls == [1]
    assert sorted(body["approval_receipt"]["replayed_receipt"] for _, body in results) == [False, True]


def test_missing_confirmation_cannot_dispatch(workflow):
    _,client,_,request=workflow
    response=client.post('/api/ai-assistant/execute-action/',request,format='json')
    assert response.status_code==403
    assert response.json()['error_code']=='action_approval_unavailable'
    assert not DataDictionary.objects.exists()
