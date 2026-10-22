"""Incomplete lease metadata never authorizes work, publication or silent repair."""

import time
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connection
from django.utils import timezone

from access_control import projects
from access_control.models import Project, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
MISSING = ["token", "expiry", "both", "caller"]


@pytest.fixture
def worker(settings, django_user_model, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.DECLARAI_RUNTIME_PROFILE = "development"
    settings.DECLARAI_JOBS_ENABLED = True
    ProjectPolicy.objects.create()
    project = Project.objects.create(name="Incomplete lease fixture")
    actor = django_user_model.objects.create_user(username="incomplete-lease-worker")
    ProjectMembership.objects.create(project=project, actor=actor, role="reviewer")
    dataset = Declaration.objects.create(name="Incomplete lease dataset")
    projects.bind_dataset(dataset, project.pk)
    authority = projects.dataset_authority(actor.pk, dataset.pk)
    job = NativeJob.objects.create(
        id=uuid.uuid4(), project=project, dataset=dataset, actor=actor,
        actor_snapshot={"private": "actor"}, authority=authority,
        specification={"kind": service.KIND, "runtime": service.runtime(), "limits": service.limits(service.KIND),
                       "bundle_id": str(uuid.uuid4()), "manifest_sha256": "c" * 64},
        request_sha256="a" * 64, state="running", revision=5, attempts=1,
        lease_token=uuid.uuid4(), lease_until=timezone.now() + timedelta(seconds=180),
        expires_at=timezone.now() + timedelta(hours=1),
        result={"private": "retained payload" * 1024}, result_sha256="b" * 64,
    )
    return SimpleNamespace(job=job, actor=actor)


def row(job):
    return NativeJob.objects.values().get(pk=job.pk)


def missing(kind):
    return {**({"lease_token": None} if kind in {"token", "both"} else {}),
            **({"lease_until": None} if kind in {"expiry", "both"} else {})}


def caller(worker, kind):
    return None if kind in {"token", "both", "caller"} else worker.job.lease_token


@pytest.mark.parametrize("kind", MISSING)
def test_initial_checkpoint_denies_incomplete_lease_before_authority_without_writes(worker, monkeypatch, kind):
    NativeJob.objects.filter(pk=worker.job.pk).update(**missing(kind))
    before = row(worker.job)
    monkeypatch.setattr(service, "recheck_execution", lambda *args: pytest.fail("authority reached without lease ownership"))
    with pytest.raises(service.JobStopped):
        service.checkpoint(worker.job.pk, caller(worker, kind), time.monotonic() + 120)
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("kind", ["token", "expiry", "both"])
@pytest.mark.parametrize("stage", ["authority", "metadata_read"])
def test_refreshed_checkpoint_denies_metadata_lost_during_real_reads(worker, monkeypatch, kind, stage):
    before, changes = row(worker.job), missing(kind)
    real_recheck = projects.recheck
    observed = {"authority": 0, "reads": 0, "changed": False}

    def change():
        NativeJob.objects.filter(pk=worker.job.pk).update(**changes)
        observed["changed"] = True

    def recheck(authority):
        real_recheck(authority)
        observed["authority"] += 1
        if stage == "authority":
            change()

    def execute(execute_query, sql, params, many, context):
        if sql.lstrip().startswith("SELECT") and '"execution_jobs_nativejob"' in sql:
            observed["reads"] += 1
            if stage == "metadata_read" and observed["reads"] == 2:
                change()
        return execute_query(sql, params, many, context)

    monkeypatch.setattr(projects, "recheck", recheck)
    with connection.execute_wrapper(execute):
        with pytest.raises(service.JobStopped):
            service.checkpoint(worker.job.pk, worker.job.lease_token, time.monotonic() + 120)
    assert observed == {"authority": 1, "reads": 2, "changed": True}
    assert row(worker.job) == {**before, **changes}
    assert not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("kind", MISSING)
@pytest.mark.parametrize("state", ["succeeded", "blocked", "failed", "cancelled"])
def test_finish_without_complete_lease_cannot_publish_or_write_terminal_receipts(worker, monkeypatch, kind, state):
    NativeJob.objects.filter(pk=worker.job.pk).update(**missing(kind))
    before = row(worker.job)
    monkeypatch.setattr(service, "lock_authority", lambda *args: pytest.fail("authority reached without lease ownership"))
    assert service.finish(worker.job.pk, caller(worker, kind), state, "owned_fixture", {"candidate": "unadopted"}) is None
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("kind", ["token", "expiry", "both"])
def test_cancellation_acknowledgement_also_requires_complete_live_lease(worker, kind):
    NativeJob.objects.filter(pk=worker.job.pk).update(state="cancel_requested", **missing(kind))
    before = row(worker.job)
    assert service.finish(worker.job.pk, caller(worker, kind), "succeeded", result={"candidate": "unadopted"}) is None
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("state", ["running", "cancel_requested"])
def test_valid_lease_keeps_real_authority_publication_and_cancellation_behavior(worker, state):
    NativeJob.objects.filter(pk=worker.job.pk).update(state=state)
    before = row(worker.job)
    result = {"schema_version": 1, "fixture": "valid"}
    assert service.finish(worker.job.pk, worker.job.lease_token, "succeeded", result=result) is None
    after = row(worker.job)
    assert after["state"] == ("succeeded" if state == "running" else "cancelled")
    assert after["reason_code"] == ("" if state == "running" else "actor_cancelled")
    assert after["result"] == (result if state == "running" else before["result"])
    assert after["result_sha256"] == (service.digest(result) if state == "running" else before["result_sha256"])
    assert after["attempts"] == before["attempts"] and after["revision"] == before["revision"] + 1
    assert after["lease_token"] is None and after["lease_until"] is None
    event = JobEvent.objects.get(job=worker.job)
    assert event.event_type == after["state"] and event.detail == {"reason_code": after["reason_code"]}


@pytest.mark.parametrize("kind", ["token", "expiry", "both"])
def test_actual_worker_stops_safely_when_committed_claim_metadata_loses_lease(worker, monkeypatch, kind):
    from execution_jobs.tasks import run_native_job

    NativeJob.objects.filter(pk=worker.job.pk).update(state="queued", attempts=0, lease_token=None, lease_until=None)
    original_claim = service.claim
    captured = {}

    def claim(identifier):
        selected = original_claim(identifier)
        assert selected is not None
        NativeJob.objects.filter(pk=identifier).update(**missing(kind))
        captured["row"] = row(worker.job)
        return selected

    monkeypatch.setattr(service, "claim", claim)
    monkeypatch.setattr(service, "header", lambda *args: pytest.fail("package work reached after lease metadata loss"))
    with patch.object(projects, "recheck", wraps=projects.recheck):
        assert run_native_job.run(str(worker.job.pk)) is None
    assert row(worker.job) == captured["row"]
    event = JobEvent.objects.get(job=worker.job)
    assert event.event_type == "started" and event.detail == {"attempt": 1}
