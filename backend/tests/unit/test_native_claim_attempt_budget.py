"""Every delivery must respect the native attempt ceiling, including restored rows."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.utils import timezone

from access_control import projects
from access_control.models import Project, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
KINDS = [service.KIND, service.csv_scoring.KIND, service.training_search.KIND,
         service.training_scoring.KIND, service.native_assessment.KIND]


@pytest.fixture
def worker(settings, django_user_model, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.DECLARAI_RUNTIME_PROFILE = "development"
    settings.DECLARAI_JOBS_ENABLED = True
    ProjectPolicy.objects.create()
    project = Project.objects.create(name="Claim budget fixture")
    actor = django_user_model.objects.create_user(username="claim-budget-worker")
    ProjectMembership.objects.create(project=project, actor=actor, role="reviewer")
    dataset = Declaration.objects.create(name="Claim budget dataset")
    projects.bind_dataset(dataset, project.pk)
    authority = projects.dataset_authority(actor.pk, dataset.pk)
    job = NativeJob.objects.create(
        id=uuid.uuid4(), project=project, dataset=dataset, actor=actor,
        actor_snapshot={"private": "actor"}, authority=authority,
        specification={"kind": service.KIND, "runtime": service.runtime(), "limits": service.limits(service.KIND)},
        request_sha256="a" * 64, revision=7, attempts=3,
        expires_at=timezone.now() + timedelta(hours=1),
        result={"private": "retained payload" * 1024}, result_sha256="b" * 64,
    )
    return SimpleNamespace(job=job, actor=actor)


def row(job):
    return NativeJob.objects.values().get(pk=job.pk)


def assert_exhausted(job, before):
    after = row(job)
    changed = {key for key in before if before[key] != after[key]}
    assert changed == {"state", "reason_code", "finished_at", "revision"}
    assert after["state"] == "failed" and after["reason_code"] == "job_attempts_exhausted"
    assert after["revision"] == before["revision"] + 1
    assert after["attempts"] == before["attempts"]
    assert after["lease_token"] is None and after["lease_until"] is None
    assert after["finished_at"] is not None
    event = JobEvent.objects.get(job=job)
    assert event.revision == after["revision"] and event.event_type == "failed"
    assert event.actor_snapshot == {} and event.detail == {"reason_code": "job_attempts_exhausted"}


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("attempts", [3, 4, 32767], ids=["at_limit", "over_limit", "far_over_limit"])
def test_exhausted_queued_delivery_never_rechecks_authority_runtime_or_starts_work(worker, monkeypatch, kind, attempts):
    NativeJob.objects.filter(pk=worker.job.pk).update(attempts=attempts, specification={"kind": kind, "private": "opaque"})
    before = row(worker.job)
    monkeypatch.setattr(service, "recheck_execution", lambda *args: pytest.fail("authority reached after exhausted attempts"))
    monkeypatch.setattr(service, "runtime", lambda *args: pytest.fail("runtime reached after exhausted attempts"))
    assert service.claim(worker.job.pk) is None
    assert_exhausted(worker.job, before)


@pytest.mark.parametrize("state", ["running", "cancel_requested", "succeeded", "blocked", "failed", "cancelled"])
def test_nonqueued_state_keeps_precedence_and_receipts_unchanged(worker, state):
    NativeJob.objects.filter(pk=worker.job.pk).update(state=state)
    before = row(worker.job)
    assert service.claim(worker.job.pk) is None
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("attempts", [3, 4])
def test_expired_queued_request_keeps_expiry_precedence(worker, attempts):
    NativeJob.objects.filter(pk=worker.job.pk).update(attempts=attempts, expires_at=timezone.now() - timedelta(seconds=1))
    assert service.claim(worker.job.pk) is None
    after = row(worker.job)
    assert after["state"] == "failed" and after["reason_code"] == "job_expired"
    assert after["attempts"] == attempts
    assert JobEvent.objects.get(job=worker.job).detail == {"reason_code": "job_expired"}


def test_full_capacity_does_not_mutate_queued_request(worker):
    for _ in range(2):
        values = {key: value for key, value in row(worker.job).items() if key != "id"}
        NativeJob.objects.create(id=uuid.uuid4(), **{**values, "state": "running"})
    before = row(worker.job)
    assert service.claim(worker.job.pk) is None
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("attempts", [0, 1, 2])
def test_remaining_attempts_still_claim_with_real_authority_and_original_lease_budget(worker, attempts):
    NativeJob.objects.filter(pk=worker.job.pk).update(attempts=attempts)
    before = row(worker.job)
    started = timezone.now()
    selected, token = service.claim(worker.job.pk)
    after = row(worker.job)
    assert selected.pk == worker.job.pk and after["state"] == "running"
    assert token == after["lease_token"] and after["attempts"] == attempts + 1
    assert started + timedelta(seconds=180) <= after["lease_until"] <= timezone.now() + timedelta(seconds=180)
    assert after["specification"] == before["specification"] and after["result"] == before["result"]
    event = JobEvent.objects.get(job=worker.job)
    assert event.event_type == "started" and event.detail == {"attempt": attempts + 1}
    assert service.claim(worker.job.pk) is None
    assert JobEvent.objects.filter(job=worker.job).count() == 1


@pytest.mark.parametrize("attempts", [3, 4, 32767])
def test_actual_worker_delivery_stops_before_package_work(worker, monkeypatch, attempts):
    from execution_jobs.tasks import run_native_job

    NativeJob.objects.filter(pk=worker.job.pk).update(attempts=attempts)
    before = row(worker.job)
    monkeypatch.setattr(service, "header", lambda *args: pytest.fail("package work entered after exhausted attempts"))
    assert run_native_job.run(str(worker.job.pk)) is None
    assert_exhausted(worker.job, before)


def test_duplicate_delivery_cannot_repeat_exhaustion_receipt(worker):
    before = row(worker.job)
    assert service.claim(worker.job.pk) is None
    assert_exhausted(worker.job, before)
    closed = row(worker.job)
    assert service.claim(worker.job.pk) is None
    assert row(worker.job) == closed and JobEvent.objects.filter(job=worker.job).count() == 1


def test_receipt_storage_failure_rolls_back_without_claiming_or_incrementing(worker):
    before = row(worker.job)
    with patch.object(JobEvent.objects, "create", side_effect=DatabaseError("owned receipt failure")):
        with pytest.raises(DatabaseError, match="owned receipt failure"):
            service.claim(worker.job.pk)
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()
