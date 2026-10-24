"""Malformed saved request envelopes close once without starting native work."""

import copy
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection, models
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from access_control import projects
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob
from tests.unit.test_native_claim_attempt_budget import worker, row  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
INVALID = [None, [], ["private-payload"], "private-payload", 0, False,
           {}, {"kind": None}, {"kind": []}, {"kind": {}}, {"kind": 0}, {"kind": False}]


def prepare(w, spec):
    NativeJob.objects.filter(pk=w.job.pk).update(
        attempts=0, specification=models.Value(copy.deepcopy(spec), output_field=models.JSONField()))
    return row(w.job)


def assert_blocked(w, before):
    after = row(w.job)
    assert {k for k in before if after[k] != before[k]} == {"state", "reason_code", "finished_at", "revision"}
    assert after["state"] == "blocked" and after["reason_code"] == "job_specification_invalid"
    assert after["revision"] == before["revision"] + 1 and after["attempts"] == 0
    assert after["lease_token"] is None and after["lease_until"] is None
    event = JobEvent.objects.get(job=w.job)
    assert event.revision == after["revision"] and event.event_type == "blocked"
    assert event.detail == {"reason_code": "job_specification_invalid"} and event.actor_snapshot == {}
    assert service.claim(w.job.pk) is None
    assert row(w.job) == after and JobEvent.objects.filter(job=w.job).count() == 1


@pytest.mark.parametrize("spec", INVALID, ids=[f"shape-{n}" for n in range(len(INVALID))])
def test_invalid_envelope_blocks_once_before_authority_runtime_or_lease(worker, monkeypatch, spec):  # noqa: F811
    before = prepare(worker, spec)
    monkeypatch.setattr(service, "recheck_execution", lambda *a: pytest.fail("invalid envelope reached execution authority"))
    monkeypatch.setattr(service, "runtime", lambda *a: pytest.fail("invalid envelope reached runtime preparation"))
    with CaptureQueriesContext(connection) as queries:
        assert service.claim(worker.job.pk) is None
    updates = [q['sql'] for q in queries if q['sql'].lstrip().startswith('UPDATE')]
    assert len(updates) == 1
    assert all('"' + field + '"' not in updates[0] for field in
               ['specification', 'authority', 'actor_snapshot', 'result', 'result_sha256', 'attempts', 'request_sha256'])
    assert_blocked(worker, before)


@pytest.mark.parametrize("spec", [None, [], {"kind": []}, {"kind": {}}])
def test_actual_task_delivery_blocks_before_work_and_dispatch_never_replays_it(worker, monkeypatch, spec):  # noqa: F811
    from execution_jobs.tasks import run_native_job
    before = prepare(worker, spec)
    monkeypatch.setattr(service, "header", lambda *a: pytest.fail("invalid request reached package work"))
    monkeypatch.setattr(service, "checkpoint", lambda *a: pytest.fail("invalid request reached worker checkpoint"))
    assert run_native_job.run(str(worker.job.pk)) is None
    assert_blocked(worker, before)
    monkeypatch.setattr(run_native_job, "apply_async", lambda *a, **k: pytest.fail("blocked request was redispatched"))
    assert service.dispatch_once() == {"delivered": 0, "broker_unavailable": 0}
    assert JobEvent.objects.filter(job=worker.job).count() == 1


@pytest.mark.parametrize("spec", [None, {"kind": []}])
@pytest.mark.parametrize("guard", ["running", "succeeded", "cancel_requested", "capacity", "expiry", "attempts"])
def test_original_claim_guard_precedence_remains(worker, spec, guard):  # noqa: F811
    prepare(worker, spec)
    if guard in {"running", "succeeded", "cancel_requested"}:
        NativeJob.objects.filter(pk=worker.job.pk).update(state=guard)
    elif guard == "capacity":
        for _ in range(2):
            values = {k: v for k, v in row(worker.job).items() if k != "id"}
            NativeJob.objects.create(id=uuid.uuid4(), **{**values, "state": "running",
                "specification": models.Value(copy.deepcopy(spec), output_field=models.JSONField())})
    elif guard == "expiry":
        NativeJob.objects.filter(pk=worker.job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    else:
        NativeJob.objects.filter(pk=worker.job.pk).update(attempts=3)
    before = row(worker.job)
    assert service.claim(worker.job.pk) is None
    if guard in {"expiry", "attempts"}:
        after = row(worker.job)
        expected = "job_expired" if guard == "expiry" else "job_attempts_exhausted"
        assert after["state"] == "failed" and after["reason_code"] == expected
        assert after["attempts"] == before["attempts"] and after["specification"] == before["specification"]
        assert JobEvent.objects.get(job=worker.job).detail == {"reason_code": expected}
    else:
        assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("spec", [None, {"kind": []}])
def test_receipt_failure_rolls_back_instead_of_losing_the_original_request(worker, spec):  # noqa: F811
    before = prepare(worker, spec)
    with patch.object(JobEvent.objects, "create", side_effect=DatabaseError("owned receipt failure")):
        with pytest.raises(DatabaseError, match="owned receipt failure"):
            service.claim(worker.job.pk)
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize("attempts", [0, 1, 2])
def test_valid_package_still_claims_with_real_authority_and_original_lease(worker, attempts):  # noqa: F811
    NativeJob.objects.filter(pk=worker.job.pk).update(attempts=attempts)
    before = row(worker.job)
    now = timezone.now()
    selected, token = service.claim(worker.job.pk)
    after = row(worker.job)
    assert selected.pk == worker.job.pk and after["state"] == "running" and after["lease_token"] == token
    assert after["attempts"] == attempts + 1
    assert now + timedelta(seconds=180) <= after["lease_until"] <= timezone.now() + timedelta(seconds=180)
    assert after["specification"] == before["specification"] and after["result"] == before["result"]
    assert JobEvent.objects.get(job=worker.job).event_type == "started"


@pytest.mark.parametrize("kind", ["", "UNKNOWN"])
def test_unknown_string_kind_retains_authority_check_and_runtime_changed_reason(worker, monkeypatch, kind):  # noqa: F811
    prepare(worker, {"kind": kind})
    checked = []
    original = service.recheck_execution
    def recheck(job):
        checked.append(job.pk)
        return original(job)
    monkeypatch.setattr(service, "recheck_execution", recheck)
    assert service.claim(worker.job.pk) is None
    assert checked == [worker.job.pk]
    after = row(worker.job)
    assert after["state"] == "blocked" and after["reason_code"] == "job_runtime_changed"


def test_valid_envelope_keeps_real_authority_denial(worker):  # noqa: F811
    NativeJob.objects.filter(pk=worker.job.pk).update(attempts=0)
    from access_control.models import ProjectMembership
    ProjectMembership.objects.filter(actor=worker.actor).update(active=False)
    assert service.claim(worker.job.pk) is None
    assert row(worker.job)["reason_code"] == "job_authority_changed"


def test_storage_failure_during_valid_authority_is_not_reclassified_as_bad_specification(worker, monkeypatch):  # noqa: F811
    NativeJob.objects.filter(pk=worker.job.pk).update(attempts=0)
    before = row(worker.job)
    def failure(*a):
        raise DatabaseError("owned authority storage failure")
    monkeypatch.setattr(projects, "recheck", failure)
    with pytest.raises(DatabaseError, match="owned authority storage failure"):
        service.claim(worker.job.pk)
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()
