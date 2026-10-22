"""Authority validation cannot carry an expired or cancelled checkpoint forward."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from access_control import projects
from access_control.models import Project, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs import service, training_search
from execution_jobs.models import JobEvent, NativeJob

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]

FENCE_FIELDS = {"id", "state", "lease_token", "lease_until", "expires_at"}
CHANGES = [
    "cancel_requested", "queued", "cancelled", "failed", "blocked", "succeeded", "token",
    "lease_at", "lease_after", "request_now", "request_past", "request_clock_at", "request_clock_after",
    "deadline_at", "deadline_after",
]


@pytest.fixture
def worker(settings, monkeypatch, django_user_model, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.DECLARAI_RUNTIME_PROFILE = "development"
    settings.DECLARAI_JOBS_ENABLED = True
    ProjectPolicy.objects.create()
    project = Project.objects.create(name="Checkpoint fixture")
    actor = django_user_model.objects.create_user(username="checkpoint-worker")
    ProjectMembership.objects.create(project=project, actor=actor, role="reviewer")
    dataset = Declaration.objects.create(name="Checkpoint dataset")
    projects.bind_dataset(dataset, project.pk)
    authority = projects.dataset_authority(actor.pk, dataset.pk)
    base = timezone.now()
    wall, work = [base], [1000.0]
    monkeypatch.setattr(service.timezone, "now", lambda: wall[0])
    monkeypatch.setattr(service.time, "monotonic", lambda: work[0])
    job = NativeJob.objects.create(
        id=uuid.uuid4(), project=project, dataset=dataset, actor=actor,
        actor_snapshot={"private": "actor"}, authority=authority, specification={"kind": service.KIND},
        request_sha256="a" * 64, state="running", revision=1, attempts=1,
        lease_token=uuid.uuid4(), lease_until=base + timedelta(seconds=180),
        expires_at=base + timedelta(hours=1), result={"private": "opaque" * 1024}, result_sha256="b" * 64,
    )
    return SimpleNamespace(job=job, actor=actor, base=base, wall=wall, work=work, project=project)


def add_source(worker):
    source = Declaration.objects.create(name="Checkpoint source")
    projects.bind_dataset(source, worker.project.pk)
    spec = {**worker.job.specification, "source_authority": projects.dataset_authority(worker.actor.pk, source.pk)}
    NativeJob.objects.filter(pk=worker.job.pk).update(source_dataset=source, specification=spec)


def prepare(worker, change):
    if change.startswith("request_clock") or change == "read_request":
        NativeJob.objects.filter(pk=worker.job.pk).update(expires_at=worker.base + timedelta(seconds=60))


def change_guard(worker, change):
    updates = {}
    if change in service.TERMINAL | {"queued", "cancel_requested"}:
        updates["state"] = change
    elif change == "token":
        updates["lease_token"] = uuid.uuid4()
    elif change.startswith("lease"):
        worker.wall[0] = worker.base + timedelta(seconds=180, microseconds=1 if change.endswith("after") else 0)
    elif change in {"request_now", "request_past"}:
        updates["expires_at"] = worker.wall[0] - timedelta(microseconds=1 if change == "request_past" else 0)
    elif change.startswith("request_clock"):
        worker.wall[0] = worker.base + timedelta(seconds=60, microseconds=1 if change.endswith("after") else 0)
    elif change.startswith("deadline"):
        worker.work[0] = 1120.001 if change.endswith("after") else 1120.0
    else:
        raise AssertionError("unsupported fixture change")
    if updates:
        NativeJob.objects.filter(pk=worker.job.pk).update(**updates)


def expected_error(change):
    if change.startswith("request") or change == "read_request":
        return service.JobConflict, "job_expired"
    if change.startswith("deadline"):
        return service.JobConflict, "job_time_budget_exceeded"
    return service.JobStopped, None


@pytest.mark.parametrize("source", [False, True], ids=["primary", "primary_and_source"])
@pytest.mark.parametrize("change", CHANGES)
def test_checkpoint_rejects_changes_during_real_authority_validation(worker, monkeypatch, source, change):
    if source:
        add_source(worker)
    prepare(worker, change)
    original = projects.recheck
    observations = {"calls": 0}

    def delayed(authority):
        original(authority)
        observations["calls"] += 1
        if observations["calls"] == (2 if source else 1):
            change_guard(worker, change)
            observations["row"] = NativeJob.objects.values().get(pk=worker.job.pk)

    monkeypatch.setattr(projects, "recheck", delayed)
    kind, reason = expected_error(change)
    with pytest.raises(kind) as error:
        service.checkpoint(worker.job.pk, worker.job.lease_token, 1120.0)
    if reason:
        assert error.value.code == reason
    assert observations["calls"] == (2 if source else 1)
    assert NativeJob.objects.values().get(pk=worker.job.pk) == observations["row"]
    assert not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("source", [False, True])
def test_live_checkpoint_refreshes_only_guard_metadata_without_writes(worker, source):
    if source:
        add_source(worker)
    before = NativeJob.objects.values().get(pk=worker.job.pk)
    with patch.object(NativeJob, "from_db", wraps=NativeJob.from_db) as loaded:
        with patch.object(projects, "recheck", wraps=projects.recheck) as authority:
            with CaptureQueriesContext(connection) as queries:
                assert service.checkpoint(worker.job.pk, worker.job.lease_token, 1120.0) is None
    assert authority.call_count == (2 if source else 1)
    assert loaded.call_count == 2 and set(loaded.call_args.args[1]) == FENCE_FIELDS
    reads = [q["sql"] for q in queries if '"execution_jobs_nativejob"' in q["sql"]]
    assert len(reads) == 2 and all(sql.lstrip().startswith("SELECT") for sql in reads)
    assert "FOR UPDATE" not in reads[-1]
    for field in {f.attname for f in NativeJob._meta.concrete_fields} - FENCE_FIELDS:
        assert f'"{field}"' not in reads[-1]
    assert NativeJob.objects.values().get(pk=worker.job.pk) == before
    assert not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("change", ["cancel_requested", "token", "lease_at", "request_now", "deadline_at"])
def test_initial_fence_still_precedes_authority_validation(worker, monkeypatch, change):
    change_guard(worker, change)
    before = NativeJob.objects.values().get(pk=worker.job.pk)
    monkeypatch.setattr(projects, "recheck", lambda *args: pytest.fail("authority reached after failed initial fence"))
    kind, reason = expected_error(change)
    with pytest.raises(kind) as error:
        service.checkpoint(worker.job.pk, worker.job.lease_token, 1120.0)
    if reason:
        assert error.value.code == reason
    assert NativeJob.objects.values().get(pk=worker.job.pk) == before
    assert not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("kind", [projects.ProjectDenied, service.JobConflict, DatabaseError])
def test_authority_failure_is_preserved_without_late_refresh_or_writes(worker, monkeypatch, kind):
    failure = kind("owned_authority_failure")
    before = NativeJob.objects.values().get(pk=worker.job.pk)

    def unavailable(*args):
        raise failure

    monkeypatch.setattr(projects, "recheck", unavailable)
    with patch.object(NativeJob, "from_db", wraps=NativeJob.from_db) as loaded:
        with pytest.raises(kind) as error:
            service.checkpoint(worker.job.pk, worker.job.lease_token, 1120.0)
    assert error.value is failure and loaded.call_count == 1
    assert NativeJob.objects.values().get(pk=worker.job.pk) == before
    assert not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("boundary", ["lease_at", "read_request", "deadline_at"])
def test_guards_are_sampled_after_metadata_read_returns(worker, monkeypatch, boundary):
    prepare(worker, boundary)
    before = NativeJob.objects.values().get(pk=worker.job.pk)
    original, observations = NativeJob.from_db, []

    def delayed(database, fields, values):
        job = original(database, fields, values)
        if set(fields) == FENCE_FIELDS:
            observations.append("metadata")
            change_guard(worker, "request_clock_at" if boundary == "read_request" else boundary)
        return job

    monkeypatch.setattr(NativeJob, "from_db", delayed)
    kind, reason = expected_error(boundary)
    with pytest.raises(kind) as error:
        service.checkpoint(worker.job.pk, worker.job.lease_token, 1120.0)
    if reason:
        assert error.value.code == reason
    assert observations == ["metadata"]
    assert NativeJob.objects.values().get(pk=worker.job.pk) == before
    assert not JobEvent.objects.filter(job=worker.job).exists()


def test_failed_late_metadata_read_does_not_invent_success_or_receipts(worker, monkeypatch):
    before = NativeJob.objects.values().get(pk=worker.job.pk)
    original = NativeJob.from_db

    def unavailable(database, fields, values):
        if set(fields) == FENCE_FIELDS:
            raise DatabaseError("owned late metadata failure")
        return original(database, fields, values)

    monkeypatch.setattr(NativeJob, "from_db", unavailable)
    with pytest.raises(DatabaseError, match="owned late metadata failure"):
        service.checkpoint(worker.job.pk, worker.job.lease_token, 1120.0)
    assert NativeJob.objects.values().get(pk=worker.job.pk) == before
    assert not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("change", ["cancel_requested", "token", "lease_at", "request_now", "deadline_at"])
def test_execute_stops_before_training_after_late_checkpoint_change(worker, monkeypatch, change):
    job = worker.job
    kind = training_search.KIND
    job.specification = {"kind": kind, "runtime": service.runtime(kind), "limits": service.limits(kind)}
    job.state, job.lease_token, job.lease_until = "queued", None, None
    job.result, job.result_sha256, job.revision, job.attempts = None, "", 0, 0
    service.record(job, "submitted", actor=worker.actor)
    original, observations = service.recheck_execution, {"changed": 0, "work": 0}

    def delayed(current):
        original(current)
        if current.state == "running" and not observations["changed"]:
            observations["token"] = current.lease_token
            observations["changed"] += 1
            change_guard(worker, change)

    def training(*args):
        observations["work"] += 1
        return {"synthetic": "work must not begin"}

    monkeypatch.setattr(service, "recheck_execution", delayed)
    monkeypatch.setattr(training_search, "train", training)
    service.execute(job.pk)
    assert observations["changed"] == 1 and observations["work"] == 0
    job.refresh_from_db()
    expected = {
        "cancel_requested": ("cancelled", "actor_cancelled"), "token": ("running", ""),
        "lease_at": ("running", ""), "request_now": ("failed", "job_expired"),
        "deadline_at": ("blocked", "job_time_budget_exceeded"),
    }
    assert (job.state, job.reason_code) == expected[change]
    assert job.result is None and job.result_sha256 == "" and job.attempts == 1
    events = list(job.events.values_list("event_type", flat=True))
    if change in {"token", "lease_at"}:
        assert job.lease_token is not None and job.lease_until is not None
        assert events == ["submitted", "started"]
        if change == "token":
            assert job.lease_token != observations["token"]
    else:
        assert job.lease_token is None and job.lease_until is None
        assert events == ["submitted", "started", expected[change][0]]
