"""Durable native queue admission, fencing, authority, cancellation and budgets."""

import json
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from django.db import connections, DatabaseError
from django.db.models.deletion import ProtectedError
from django.test import Client
from django.utils import timezone
from access_control.models import ProjectMembership, ProjectPolicy
from deployment.deploy_utils import bundle_dir
from execution_jobs import service
from execution_jobs.models import NativeJob, JobEvent
from execution_jobs.config import load_job_config
from tests.unit.test_package_reviews import packaged, world, post  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def configured(settings):
    settings.DECLARAI_JOBS_ENABLED = True
    settings.CELERY_BROKER_URL = "redis://127.0.0.1:9/15"


def submit(world, role="reviewer", **overrides):
    data = {
        "request_id": str(uuid.uuid4()),
        "kind": service.KIND,
        "bundle_id": world[2]["bundle_id"],
        "manifest_sha256": world[2]["manifest_sha256"],
        **overrides,
    }
    return post(world[4][role], f"/api/jobs/datasets/{world[0]}/", data), data


def test_real_request_receipt_replay_completion_without_deserialization(world):
    response, body = submit(world)
    assert response.status_code == 202
    identifier = response.json()["id"]
    replay = post(world[4]["reviewer"], f"/api/jobs/datasets/{world[0]}/", body)
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert NativeJob.objects.count() == JobEvent.objects.count() == 1
    with (
        patch("joblib.load", side_effect=AssertionError("native state loaded")),
        patch("pickle.load", side_effect=AssertionError("state loaded")),
    ):
        service.execute(identifier)
        service.execute(identifier)
    result = world[4]["admin"].get(f"/api/jobs/{identifier}/").json()
    assert result["state"] == "succeeded" and result["attempts"] == 1
    assert result["result_sha256"] == service.digest(result["result"])
    assert result["result"]["model_state_loaded"] is False
    assert result["result"]["manifest_sha256"] == body["manifest_sha256"]
    assert result["result"]["verified_bytes"] > 0 and result["result"]["artifact_count"] > 5
    assert [e["event_type"] for e in result["events"]] == ["submitted", "started", "succeeded"]
    assert not result["review_approved"] and not result["production_use_approved"]


@pytest.mark.parametrize("role,status", [("developer", 202), ("reviewer", 202), ("admin", 403), ("outsider", 403)])
def test_submit_roles_and_unauthorized_downloads(world, role, status):
    assert submit(world, role)[0].status_code == status
    if status == 202:
        job = NativeJob.objects.get()
        assert world[4]["outsider"].get(f"/api/jobs/{job.pk}/").status_code == 403
        assert Client().get(f"/api/jobs/{job.pk}/").status_code == 403


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "expert_python"},
        {"code": "print(1)"},
        {"actor_id": 1},
        {"request_id": "invalid"},
        {"manifest_sha256": "X" * 64},
        {"max_bytes": 1000000000000},
    ],
)
def test_rejects_unsupported_spoofed_and_unbounded_requests(world, overrides):
    assert submit(world, **overrides)[0].status_code == 400
    assert not NativeJob.objects.exists()


def test_conflicting_request_and_manifest_never_create_a_second_job(world):
    response, body = submit(world)
    assert response.status_code == 202
    changed = {**body, "manifest_sha256": "0" * 64}
    assert (
        post(world[4]["reviewer"], f"/api/jobs/datasets/{world[0]}/", changed).json()["error_code"]
        == "job_request_reused"
    )
    assert submit(world, manifest_sha256="0" * 64)[0].status_code == 409
    assert NativeJob.objects.count() == 1


def test_disabled_and_legacy_services_fail_closed(world, settings):
    settings.DECLARAI_JOBS_ENABLED = False
    assert submit(world)[0].status_code == 503
    settings.DECLARAI_JOBS_ENABLED = True
    ProjectPolicy.objects.all().delete()
    assert submit(world)[0].status_code == 403
    assert not NativeJob.objects.exists()


def test_csrf_is_required(world):
    client = Client(enforce_csrf_checks=True)
    client.force_login(world[3]["reviewer"])
    _, body = submit(world, "admin")
    assert post(client, f"/api/jobs/datasets/{world[0]}/", body).status_code == 403
    assert not NativeJob.objects.exists()


def test_queued_cancellation_is_idempotent_and_submitter_only(world):
    response, _ = submit(world)
    identifier = response.json()["id"]
    url = f"/api/jobs/{identifier}/"
    assert post(world[4]["developer"], url, {"action": "cancel"}).status_code == 403
    for _ in range(2):
        assert post(world[4]["reviewer"], url, {"action": "cancel"}).json()["state"] == "cancelled"
    service.execute(identifier)
    job = NativeJob.objects.get()
    assert job.attempts == 0 and job.events.count() == 2
    assert post(world[4]["reviewer"], url, {"action": "promote"}).status_code == 400


def test_running_cancel_retains_slot_until_acknowledged(world):
    response, _ = submit(world)
    job, token = service.claim(response.json()["id"])
    assert (
        post(world[4]["reviewer"], f"/api/jobs/{job.pk}/", {"action": "cancel"}).json()["state"] == "cancel_requested"
    )
    with pytest.raises(service.JobStopped):
        service.checkpoint(job.pk, token, float("inf"))
    service.finish(job.pk, token, "succeeded", result={"should": "not publish"})
    job.refresh_from_db()
    assert job.state == "cancelled" and not job.result and not job.lease_token


@pytest.mark.parametrize("change", ["revoked", "role", "runtime", "tamper", "missing", "time"])
def test_changed_authority_package_runtime_and_budget_block_publication(world, change):
    response, _ = submit(world)
    job = NativeJob.objects.get(pk=response.json()["id"])
    if change in {"revoked", "role"}:
        member = ProjectMembership.objects.get(actor=world[3]["reviewer"])
        if change == "revoked":
            member.active = False
        else:
            member.revision = uuid.uuid4()
        member.save()
    elif change == "runtime":
        job.specification["runtime"]["python"] = "unsupported"
        job.save()
    elif change in {"tamper", "missing"}:
        path = Path(bundle_dir(world[0], world[2]["bundle_id"])) / "model_card.json"
        if change == "tamper":
            path.write_text("{}")
        else:
            path.unlink()
    if change == "time":
        original_checkpoint = service.checkpoint
        with patch(
            "execution_jobs.service.checkpoint",
            side_effect=lambda identifier, token, deadline: original_checkpoint(identifier, token, float("-inf")),
        ):
            service.execute(job.pk)
    else:
        service.execute(job.pk)
    job.refresh_from_db()
    assert job.state == "blocked" and job.result is None


def test_revocation_after_read_withholds_result(world):
    response, _ = submit(world)
    original = service.finish

    def revoke(*args, **kwargs):
        ProjectMembership.objects.filter(actor=world[3]["reviewer"]).update(active=False)
        return original(*args, **kwargs)

    with patch("execution_jobs.service.finish", side_effect=revoke):
        service.execute(response.json()["id"])
    job = NativeJob.objects.get()
    assert job.state == "blocked" and not job.result
    assert world[4]["reviewer"].get(f"/api/jobs/{job.pk}/").status_code == 403


def test_lease_recovery_fences_old_workers_and_exhausts_attempt_budget(world):
    identifier = submit(world)[0].json()["id"]
    _, old_token = service.claim(identifier)
    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1))
    assert uuid.UUID(identifier) in service.reconcile()
    _, new_token = service.claim(identifier)
    service.finish(identifier, old_token, "succeeded", result={"old": True})
    job = NativeJob.objects.get()
    assert job.state == "running" and job.lease_token == new_token
    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1), attempts=3)
    service.reconcile()
    job.refresh_from_db()
    assert job.state == "failed" and not job.result


def test_expired_queue_and_cancelled_lease_are_terminal(world):
    identifier = submit(world)[0].json()["id"]
    NativeJob.objects.filter(pk=identifier).update(expires_at=timezone.now() - timedelta(seconds=1))
    service.reconcile()
    assert NativeJob.objects.get().state == "failed"
    second = submit(world)[0].json()["id"]
    service.claim(second)
    post(world[4]["reviewer"], f"/api/jobs/{second}/", {"action": "cancel"})
    NativeJob.objects.filter(pk=second).update(lease_until=timezone.now() - timedelta(seconds=1))
    service.reconcile()
    assert NativeJob.objects.get(pk=second).state == "cancelled"


def test_claim_concurrency_is_bounded_across_threads(world):
    identifiers = [submit(world)[0].json()["id"] for _ in range(3)]

    def claim(identifier):
        try:
            return service.claim(identifier) is not None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=3) as pool:
        values = list(pool.map(claim, identifiers))
    assert sum(values) == 2 and NativeJob.objects.filter(state="running").count() == 2


def test_full_queue_rejects_new_admission_but_accepts_exact_retry(world):
    response, data = submit(world)
    with patch.dict(service.LIMITS, max_pending=1):
        assert submit(world)[0].json()["error_code"] == "job_queue_full"
        assert post(world[4]["reviewer"], f"/api/jobs/datasets/{world[0]}/", data).status_code == 200


def test_broker_failure_keeps_committed_request_and_republishes_only_identifier(world):
    identifier = submit(world)[0].json()["id"]
    with patch(
        "execution_jobs.tasks.run_native_job.apply_async", side_effect=RuntimeError("synthetic secret connection")
    ):
        assert service.dispatch_once() == {"delivered": 0, "broker_unavailable": 1}
    assert NativeJob.objects.get().state == "queued"
    with patch("execution_jobs.tasks.run_native_job.apply_async") as delivered:
        assert service.dispatch_once()["delivered"] == 1
        delivered.assert_called_once_with(args=[identifier], retry=False)
    assert JobEvent.objects.count() == 1


def test_storage_failure_rolls_back_admission_and_preserves_existing_request(world):
    with patch("execution_jobs.service.record", side_effect=DatabaseError("synthetic")):
        assert submit(world)[0].status_code == 503
    assert not NativeJob.objects.exists()
    job = submit(world)[0].json()
    with patch("execution_jobs.service.serialize", side_effect=DatabaseError("synthetic")):
        assert world[4]["reviewer"].get(f"/api/jobs/{job['id']}/").status_code == 503
    assert NativeJob.objects.count() == 1


def test_actor_snapshot_and_protected_history_survive_user_deletion(world):
    submit(world)
    world[3]["reviewer"].delete()
    job = NativeJob.objects.get()
    assert job.actor is None and job.actor_snapshot["username"] == "reviewer"
    service.execute(job.pk)
    job.refresh_from_db()
    assert job.state == "blocked"
    with pytest.raises(ProtectedError):
        world[1].delete()


@pytest.mark.parametrize(
    "env",
    [
        {"DECLARAI_JOB_BROKER_URL": "redis://host/0"},
        {"DECLARAI_JOB_BROKER_URL": "rediss://host/0?ssl_cert_reqs=none"},
        {"DECLARAI_JOB_BROKER_URL": "http://host/0"},
        {"DECLARAI_JOB_BROKER_URL": "rediss://host/0"},
    ],
)
def test_private_broker_requires_tls_and_explicit_verified_ca(env):
    from django.core.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured):
        load_job_config("private", env)
    assert load_job_config("development", {})["DECLARAI_JOBS_ENABLED"] is False
