"""Native work deadlines survive publication waits without adopting late results."""

from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.utils import timezone

from execution_jobs import service
from execution_jobs.models import NativeJob
from tests.unit.test_package_reviews import world, packaged  # noqa: F401
from tests.unit.test_durable_scoring import source, submit as submit_scoring  # noqa: F401
from tests.unit.test_native_jobs import submit as submit_integrity

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]

BOUNDARIES = [
    (kind, boundary)
    for kind in ("integrity", "scoring")
    for boundary in ("entry", "queue_lock", "authority", "recheck", "digest")
] + [("scoring", "source_authority")]


@pytest.fixture(autouse=True)
def configured(settings):
    settings.DECLARAI_JOBS_ENABLED = True


def queued(world, source, kind):
    response, _ = submit_scoring(world, source) if kind == "scoring" else submit_integrity(world)
    assert response.status_code == 202
    return NativeJob.objects.get(pk=response.json()["id"])


@contextmanager
def delayed_publication(monkeypatch, boundary, instant):
    """Advance only the work clock at a real publication boundary, after execution."""
    clock, active, observations = [1000.0], [False], {"delays": 0, "authority_calls": 0}
    actual_finish, actual_locked = service.finish, service.locked
    actual_authority, actual_recheck, actual_digest = service.lock_authority, service.recheck_execution, service.digest

    def advance():
        clock[0] = instant
        observations["delays"] += 1

    def finish(*args, **kwargs):
        active[0] = args[2] == "succeeded"
        try:
            if active[0] and boundary == "entry":
                advance()
            return actual_finish(*args, **kwargs)
        finally:
            active[0] = False

    @contextmanager
    def locked():
        with actual_locked():
            if active[0] and boundary == "queue_lock":
                advance()
            yield

    def authority(*args, **kwargs):
        result = actual_authority(*args, **kwargs)
        if active[0]:
            observations["authority_calls"] += 1
            if (boundary, observations["authority_calls"]) in {("authority", 1), ("source_authority", 2)}:
                advance()
        return result

    def recheck(*args, **kwargs):
        result = actual_recheck(*args, **kwargs)
        if active[0] and boundary == "recheck":
            advance()
        return result

    def digest(value):
        result = actual_digest(value)
        if active[0] and boundary == "digest":
            advance()
        return result

    with monkeypatch.context() as patch:
        patch.setattr(service.time, "monotonic", lambda: clock[0])
        patch.setattr(service, "finish", finish)
        patch.setattr(service, "locked", locked)
        patch.setattr(service, "lock_authority", authority)
        patch.setattr(service, "recheck_execution", recheck)
        patch.setattr(service, "digest", digest)
        yield observations


@pytest.mark.parametrize("kind,boundary", BOUNDARIES)
@pytest.mark.parametrize("elapsed", [120.0, 120.001])
def test_work_deadline_blocks_result_after_publication_wait(world, source, monkeypatch, kind, boundary, elapsed):
    job = queued(world, source, kind)
    assert service.LIMITS["seconds"] == 120
    with delayed_publication(monkeypatch, boundary, 1000.0 + elapsed) as observations:
        service.execute(job.pk)
    assert observations["delays"] == 1
    job.refresh_from_db()
    assert job.state == "blocked" and job.reason_code == "job_time_budget_exceeded"
    assert job.result is None and job.result_sha256 == ""
    assert job.attempts == 1 and job.lease_token is None and job.lease_until is None
    assert job.finished_at is not None
    assert list(job.events.values_list("event_type", flat=True)) == ["submitted", "started", "blocked"]
    # A terminal timeout is inspectable and cannot automatically consume a new attempt.
    assert world[4]["reviewer"].get(f"/api/jobs/{job.pk}/").json()["reason_code"] == "job_time_budget_exceeded"
    assert service.claim(job.pk) is None and job.pk not in service.reconcile()


@pytest.mark.parametrize("kind,boundary", BOUNDARIES)
def test_result_still_publishes_just_before_work_deadline(world, source, monkeypatch, kind, boundary):
    job = queued(world, source, kind)
    with delayed_publication(monkeypatch, boundary, 1119.999) as observations:
        service.execute(job.pk)
    assert observations["delays"] == 1
    job.refresh_from_db()
    assert job.state == "succeeded" and job.attempts == 1 and not job.reason_code
    assert job.result and job.result_sha256 == service.digest(job.result)
    assert job.lease_token is None and job.lease_until is None
    assert list(job.events.values_list("event_type", flat=True)) == ["submitted", "started", "succeeded"]


@pytest.mark.parametrize("kind", ["integrity", "scoring"])
@pytest.mark.parametrize("precedence", ["cancel", "lease", "request"])
def test_existing_cancellation_and_expiry_fences_take_precedence(world, source, monkeypatch, kind, precedence):
    job = queued(world, source, kind)
    actual_finish = service.finish

    def changed(*args, **kwargs):
        assert args[2] == "succeeded"
        updates = {
            "cancel": {"state": "cancel_requested"},
            "lease": {"lease_until": timezone.now() - timedelta(seconds=1)},
            "request": {"expires_at": timezone.now() - timedelta(seconds=1)},
        }
        NativeJob.objects.filter(pk=job.pk).update(**updates[precedence])
        return actual_finish(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(service, "finish", changed)
        with delayed_publication(patch, "entry", 1120.0):
            service.execute(job.pk)
    job.refresh_from_db()
    expected = {"cancel": ("cancelled", "actor_cancelled"), "lease": ("running", ""),
                "request": ("failed", "job_expired")}
    assert (job.state, job.reason_code) == expected[precedence]
    assert job.result is None and job.result_sha256 == "" and job.attempts == 1
    if precedence == "lease":
        assert job.lease_token is not None
        assert list(job.events.values_list("event_type", flat=True)) == ["submitted", "started"]
    else:
        assert job.lease_token is None and job.lease_until is None
        assert job.events.count() == 3


@pytest.mark.parametrize("kind", ["integrity", "scoring"])
def test_unexpected_publication_failure_keeps_lease_for_reconciliation(world, source, monkeypatch, kind):
    job = queued(world, source, kind)

    def unavailable(value):
        raise RuntimeError("synthetic publication failure")

    monkeypatch.setattr(service, "digest", unavailable)
    with pytest.raises(RuntimeError, match="synthetic publication failure"):
        service.execute(job.pk)
    job.refresh_from_db()
    assert job.state == "running" and job.attempts == 1
    assert job.result is None and job.result_sha256 == ""
    assert job.lease_token is not None and job.lease_until is not None
    assert list(job.events.values_list("event_type", flat=True)) == ["submitted", "started"]
