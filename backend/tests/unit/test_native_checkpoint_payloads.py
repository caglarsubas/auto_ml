"""Worker fences read required authority metadata without materializing stored outputs."""

import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from access_control import projects
from access_control.models import Project, ProjectDataset, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs import service, training_scoring, training_search
from execution_jobs.models import JobEvent, NativeJob

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
REQUIRED = {"id", "state", "lease_token", "lease_until", "expires_at", "authority", "specification",
            "project_id", "dataset_id", "source_dataset_id"}
GUARDS = {"id", "state", "lease_token", "lease_until", "expires_at"}
UNRELATED = {"actor_id", "actor_snapshot", "request_sha256", "result", "result_sha256", "created_at",
             "finished_at", "revision", "attempts", "next_dispatch", "reason_code"}


@pytest.fixture
def worker(settings, django_user_model, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.DECLARAI_RUNTIME_PROFILE = "development"
    settings.DECLARAI_JOBS_ENABLED = True
    ProjectPolicy.objects.create()
    project = Project.objects.create(name="Checkpoint projection fixture")
    actor = django_user_model.objects.create_user(username="checkpoint-projection-worker")
    ProjectMembership.objects.create(project=project, actor=actor, role="reviewer")
    dataset = Declaration.objects.create(name="Checkpoint primary")
    source = Declaration.objects.create(name="Checkpoint source")
    for item in [dataset, source]:
        projects.bind_dataset(item, project.pk)
    authority = projects.dataset_authority(actor.pk, dataset.pk)
    job = NativeJob.objects.create(
        id=uuid.uuid4(), project=project, dataset=dataset, actor=actor,
        actor_snapshot={"private": "unrelated actor data"}, authority=authority,
        specification={"kind": service.KIND, "runtime": service.runtime(), "limits": service.limits(service.KIND)},
        request_sha256="a" * 64, state="running", revision=5, attempts=1,
        lease_token=uuid.uuid4(), lease_until=timezone.now() + timedelta(seconds=180),
        expires_at=timezone.now() + timedelta(hours=1),
        result={"private": "historical output" * 8192}, result_sha256="b" * 64,
    )
    return SimpleNamespace(job=job, actor=actor, source=source, project=project)


def row(job):
    return NativeJob.objects.values().get(pk=job.pk)


@contextmanager
def checkpoint_reads(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("checkpoint decoded an unrelated output or actor payload")

    with monkeypatch.context() as scoped:
        for name in ["result", "actor_snapshot"]:
            scoped.setattr(NativeJob._meta.get_field(name), "from_db_value", forbidden)
        with patch.object(NativeJob, "from_db", wraps=NativeJob.from_db) as materialized:
            with patch.object(NativeJob, "refresh_from_db", side_effect=AssertionError("checkpoint lazy-loaded a deferred field")):
                with CaptureQueriesContext(connection) as queries:
                    yield materialized, queries


def assert_projection(materialized, queries, refreshed=True):
    assert [set(c.args[1]) for c in materialized.call_args_list] == ([REQUIRED, GUARDS] if refreshed else [REQUIRED])
    sql = [q["sql"] for q in queries if '"execution_jobs_nativejob"' in q["sql"]]
    assert len(sql) == (2 if refreshed else 1)
    assert all(q.lstrip().startswith("SELECT") and "FOR UPDATE" not in q for q in sql)
    assert all(f'"{field}"' not in q for q in sql for field in UNRELATED)


@pytest.mark.parametrize("kind", [service.KIND, service.csv_scoring.KIND, training_search.KIND])
@pytest.mark.parametrize("payload", [{"private": "unrelated" * 16384}, ["legacy", {"opaque": True}]])
@pytest.mark.parametrize("has_source", [False, True])
def test_checkpoint_projects_required_fields_and_rechecks_real_scopes_without_writes(worker, monkeypatch, kind, payload, has_source):
    specification = {"kind": kind}
    if has_source:
        specification["source_authority"] = projects.dataset_authority(worker.actor.pk, worker.source.pk)
    NativeJob.objects.filter(pk=worker.job.pk).update(
        specification=specification, result=payload, actor_snapshot=payload,
        source_dataset=worker.source if has_source else None,
    )
    before = row(worker.job)
    with patch.object(projects, "recheck", wraps=projects.recheck) as rechecked:
        with checkpoint_reads(monkeypatch) as (materialized, queries):
            assert service.checkpoint(worker.job.pk, worker.job.lease_token, time.monotonic() + 120) is None
    assert_projection(materialized, queries)
    assert [c.args[0] for c in rechecked.call_args_list] == [before["authority"], *([specification["source_authority"]] if has_source else [])]
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("cause", ["cancel", "terminal", "token", "missing_token", "missing_expiry", "lease_expired", "request_expired", "deadline"])
def test_rejected_checkpoint_does_not_decode_outputs_or_reach_authority(worker, monkeypatch, cause):
    changes = {"cancel": {"state": "cancel_requested"}, "terminal": {"state": "succeeded"},
               "token": {"lease_token": uuid.uuid4()}, "missing_token": {"lease_token": None},
               "missing_expiry": {"lease_until": None}, "lease_expired": {"lease_until": timezone.now()},
               "request_expired": {"expires_at": timezone.now()}, "deadline": {}}[cause]
    NativeJob.objects.filter(pk=worker.job.pk).update(**changes)
    before = row(worker.job)
    monkeypatch.setattr(service, "recheck_execution", lambda *args: pytest.fail("authority reached after failed guards"))
    error = service.JobConflict if cause in {"request_expired", "deadline"} else service.JobStopped
    with checkpoint_reads(monkeypatch) as (materialized, queries):
        with pytest.raises(error) as caught:
            service.checkpoint(worker.job.pk, worker.job.lease_token, time.monotonic() + (-1 if cause == "deadline" else 120))
    if error is service.JobConflict:
        assert caught.value.code == ("job_expired" if cause == "request_expired" else "job_time_budget_exceeded")
    assert_projection(materialized, queries, refreshed=False)
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("source_revoked", [False, True])
def test_projection_preserves_real_primary_and_source_authority_revocation(worker, monkeypatch, source_revoked):
    specification = {"kind": service.KIND, "source_authority": projects.dataset_authority(worker.actor.pk, worker.source.pk)}
    NativeJob.objects.filter(pk=worker.job.pk).update(specification=specification, source_dataset=worker.source)
    affected = worker.source if source_revoked else worker.job.dataset
    ProjectDataset.objects.filter(dataset=affected).update(revision=uuid.uuid4())
    before = row(worker.job)
    with checkpoint_reads(monkeypatch) as (materialized, queries):
        with pytest.raises(projects.ProjectDenied):
            service.checkpoint(worker.job.pk, worker.job.lease_token, time.monotonic() + 120)
    assert_projection(materialized, queries, refreshed=False)
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("changed", [False, True])
def test_scoring_checkpoint_still_reads_and_verifies_referenced_training_result(worker, changed):
    result = {"candidate": "referenced training evidence"}
    trained = NativeJob.objects.create(
        id=uuid.uuid4(), project=worker.project, dataset=worker.job.dataset, actor=worker.actor,
        actor_snapshot={}, authority=worker.job.authority, specification={"kind": training_search.KIND},
        request_sha256="c" * 64, state="succeeded", result=result, result_sha256=service.digest(result),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    specification = {"kind": training_scoring.KIND, "training_job_id": str(trained.pk), "training_result_sha256": trained.result_sha256}
    NativeJob.objects.filter(pk=worker.job.pk).update(specification=specification)
    if changed:
        NativeJob.objects.filter(pk=trained.pk).update(result={"candidate": "tampered"})
    before = row(worker.job)
    with CaptureQueriesContext(connection) as queries:
        if changed:
            with pytest.raises(service.JobConflict, match="job_training_result_changed"):
                service.checkpoint(worker.job.pk, worker.job.lease_token, time.monotonic() + 120)
        else:
            assert service.checkpoint(worker.job.pk, worker.job.lease_token, time.monotonic() + 120) is None
    sql = [q["sql"] for q in queries if '"execution_jobs_nativejob"' in q["sql"]]
    assert len(sql) == (2 if changed else 3)
    # Only the explicitly referenced training result is an integrity input.
    assert '"result"' not in sql[0] and '"result"' in sql[1]
    if not changed:
        assert '"result"' not in sql[2]
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


def test_actual_worker_keeps_cancellation_and_opaque_outputs_with_projected_checkpoints(worker, monkeypatch):
    from execution_jobs.tasks import run_native_job

    specification = {"kind": training_search.KIND, "runtime": service.runtime(training_search.KIND),
                     "limits": service.limits(training_search.KIND)}
    NativeJob.objects.filter(pk=worker.job.pk).update(state="queued", attempts=0, lease_token=None, lease_until=None, specification=specification)
    before = row(worker.job)

    def training(job, check):
        with checkpoint_reads(monkeypatch) as (materialized, queries):
            check()
        assert_projection(materialized, queries)
        NativeJob.objects.filter(pk=job.pk).update(state="cancel_requested", reason_code="actor_cancelled")
        with checkpoint_reads(monkeypatch) as (materialized, queries):
            with pytest.raises(service.JobStopped):
                check()
        assert_projection(materialized, queries, refreshed=False)
        raise service.JobStopped

    monkeypatch.setattr(training_search, "train", training)
    assert run_native_job.run(str(worker.job.pk)) is None
    after = row(worker.job)
    assert after["state"] == "cancelled" and after["reason_code"] == "actor_cancelled"
    assert after["result"] == before["result"] and after["actor_snapshot"] == before["actor_snapshot"]
    assert after["result_sha256"] == before["result_sha256"] and after["attempts"] == 1
    assert after["revision"] == before["revision"] + 2 and after["lease_token"] is after["lease_until"] is None
    assert list(JobEvent.objects.filter(job=worker.job).values_list("event_type", flat=True)) == ["started", "cancelled"]
