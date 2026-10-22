"""Lease recovery reads and saves transition metadata, never opaque payloads."""

import datetime as dt
import uuid
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from access_control.models import Project
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]

METADATA = {
    "id", "state", "revision", "attempts", "lease_token", "lease_until",
    "next_dispatch", "expires_at", "reason_code", "finished_at",
}
OPAQUE = {
    "project_id", "dataset_id", "source_dataset_id", "actor_id", "actor_snapshot",
    "authority", "specification", "request_sha256", "result", "result_sha256",
}
SCENARIOS = [
    ("running", 0, False, "queued", "worker_lease_expired"),
    ("running", 2, False, "queued", "worker_lease_expired"),
    ("running", 3, False, "failed", "job_attempts_exhausted"),
    ("running", 0, True, "failed", "job_attempts_exhausted"),
    ("running", 3, True, "failed", "job_attempts_exhausted"),
    ("cancel_requested", 0, False, "cancelled", "actor_cancelled_after_lease"),
    ("cancel_requested", 3, False, "cancelled", "actor_cancelled_after_lease"),
    ("cancel_requested", 3, True, "cancelled", "actor_cancelled_after_lease"),
    ("queued", 0, True, "failed", "job_expired"),
]


@pytest.fixture
def queue(monkeypatch):
    now = timezone.now()
    monkeypatch.setattr(service.timezone, "now", lambda: now)
    project = Project.objects.create(name="Reconciliation SQL fixture")
    dataset = Declaration.objects.create(name="Opaque reconciliation fixture")

    def add(**overrides):
        values = dict(
            id=uuid.uuid4(), project=project, dataset=dataset, source_dataset=dataset,
            actor_snapshot={"private": "actor"}, authority={"private": "authority"},
            specification={"private": "specification"}, request_sha256="a" * 64,
            result={"private": "result"}, result_sha256="b" * 64,
            revision=7, attempts=0, state="running", lease_token=uuid.uuid4(),
            lease_until=now - dt.timedelta(seconds=1),
            next_dispatch=now + dt.timedelta(minutes=1),
            expires_at=now + dt.timedelta(hours=1), created_at=now,
            reason_code="retained_reason", finished_at=now - dt.timedelta(days=1),
        )
        values.update(overrides)
        return NativeJob.objects.create(**values)

    return now, add


@pytest.mark.parametrize("state,attempts,expired,expected,reason", SCENARIOS)
@pytest.mark.parametrize("payload", ["mapping", "large", "non_mapping"])
def test_reconcile_projects_and_saves_only_metadata(queue, state, attempts, expired, expected, reason, payload):
    now, add = queue
    if payload == "mapping":
        opaque = {"private": ["untouched", {"nested": True}]}
    elif payload == "large":
        opaque = {"private": "opaque-marker" * 8192}
    else:
        # Recovery must not interpret old/invalid payloads; execution validates them later.
        opaque = ["opaque", {"kind": "unsupported"}]
    job = add(state=state, attempts=attempts, expires_at=now if expired else now + dt.timedelta(hours=1),
              actor_snapshot=opaque, authority=opaque, specification=opaque, result=opaque)
    before = NativeJob.objects.values().get(pk=job.pk)
    with patch.object(NativeJob, "from_db", wraps=NativeJob.from_db) as materialized:
        with patch.object(NativeJob, "refresh_from_db", side_effect=AssertionError("deferred payload fetched")):
            with CaptureQueriesContext(connection) as queries:
                due = service.reconcile()
    assert materialized.call_count == 1
    assert set(materialized.call_args.args[1]) == METADATA
    sql = [q["sql"] for q in queries if '"execution_jobs_nativejob"' in q["sql"]]
    assert len([q for q in sql if q.lstrip().startswith("SELECT")]) == 3
    assert len([q for q in sql if q.lstrip().startswith("UPDATE")]) == 1
    assert all(f'"{field}"' not in q for q in sql for field in OPAQUE)
    if connection.vendor == "postgresql":
        assert sum("FOR UPDATE" in q for q in sql) == 2
    after = NativeJob.objects.values().get(pk=job.pk)
    assert {f: after[f] for f in OPAQUE} == {f: before[f] for f in OPAQUE}
    assert after["created_at"] == before["created_at"]
    assert after["state"] == expected and after["revision"] == 8 and after["attempts"] == attempts
    assert after["lease_token"] is after["lease_until"] is None
    assert after["expires_at"] == before["expires_at"]
    if expected == "queued":
        assert due == [job.pk] and after["next_dispatch"] == now
        assert after["reason_code"] == before["reason_code"] and after["finished_at"] == before["finished_at"]
    else:
        assert due == [] and after["finished_at"] == now and after["reason_code"] == reason
        assert after["next_dispatch"] == before["next_dispatch"]
    receipt = JobEvent.objects.get(job=job)
    assert receipt.revision == 8 and receipt.event_type == ("requeued" if expected == "queued" else expected)
    assert receipt.detail == {"reason_code": reason} and receipt.actor_snapshot == {}
    # The model's bound default is its real creation clock, independent of the
    # sampled recovery clock above.
    assert now <= receipt.created_at <= dt.datetime.now(dt.timezone.utc)
    assert service.reconcile() == due
    assert JobEvent.objects.filter(job=job).count() == 1
    assert NativeJob.objects.values().get(pk=job.pk) == after


@pytest.mark.parametrize("state", ["running", "cancel_requested", "queued"])
def test_recovery_and_receipt_rollback_together(queue, monkeypatch, state):
    now, add = queue
    job = add(state=state, expires_at=now if state == "queued" else now + dt.timedelta(hours=1))
    before = NativeJob.objects.values().get(pk=job.pk)
    original = JobEvent.objects.create

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("owned receipt failure")

    monkeypatch.setattr(JobEvent.objects, "create", fail_after_insert)
    with pytest.raises(RuntimeError, match="owned receipt failure"):
        service.reconcile()
    assert NativeJob.objects.values().get(pk=job.pk) == before
    assert not JobEvent.objects.filter(job=job).exists()
    monkeypatch.setattr(JobEvent.objects, "create", original)
    service.reconcile()
    assert JobEvent.objects.filter(job=job, revision=8).count() == 1


@pytest.mark.parametrize("state", ["running", "cancel_requested", "queued", "succeeded", "failed", "cancelled"])
def test_unexpired_or_terminal_rows_are_untouched(queue, state):
    now, add = queue
    job = add(state=state, lease_until=now + dt.timedelta(seconds=1))
    before = NativeJob.objects.values().get(pk=job.pk)
    assert service.reconcile() == []
    assert NativeJob.objects.values().get(pk=job.pk) == before
    assert not JobEvent.objects.filter(job=job).exists()


def test_mixed_recovery_keeps_due_id_order_and_original_hundred_limit(queue):
    now, add = queue
    # The requeued lease joins normal queued work; expiry/cancellation never dispatch.
    requeued = add(created_at=now - dt.timedelta(days=2))
    normal = [add(state="queued", lease_token=None, lease_until=None, next_dispatch=now,
                  created_at=now + dt.timedelta(seconds=i)) for i in range(103)]
    expired = add(state="queued", expires_at=now, next_dispatch=now)
    cancelled = add(state="cancel_requested", expires_at=now, attempts=3)
    future = add(state="queued", next_dispatch=now + dt.timedelta(seconds=1))
    assert service.reconcile() == [requeued.pk, *[j.pk for j in normal[:99]]]
    assert list(JobEvent.objects.filter(job=requeued).values_list("event_type", flat=True)) == ["requeued"]
    assert JobEvent.objects.get(job=expired).detail == {"reason_code": "job_expired"}
    assert JobEvent.objects.get(job=cancelled).event_type == "cancelled"
    assert not JobEvent.objects.filter(job_id__in=[future.pk, *[j.pk for j in normal]]).exists()
    assert service.reconcile() == [requeued.pk, *[j.pk for j in normal[:99]]]
    assert JobEvent.objects.count() == 3
