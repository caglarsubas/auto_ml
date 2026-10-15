"""Refresh native job deadlines after waits and before durable transitions."""
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from access_control import projects
from execution_jobs import service
from execution_jobs.models import NativeJob, JobEvent
from tests.unit.test_package_reviews import world, packaged  # noqa: F401
from tests.unit.test_durable_scoring import source, submit as submit_scoring  # noqa: F401
from tests.unit.test_native_jobs import submit as submit_integrity

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def configured(settings):
    settings.DECLARAI_JOBS_ENABLED = True


def queued(world, source, kind):
    response, _ = submit_scoring(world, source) if kind == "scoring" else submit_integrity(world)
    assert response.status_code == 202
    return NativeJob.objects.get(pk=response.json()["id"])


BOUNDARIES = [("integrity", "authority"), ("integrity", "recheck"), ("integrity", "digest"),
              ("scoring", "authority"), ("scoring", "source_authority"),
              ("scoring", "recheck"), ("scoring", "digest")]


@pytest.mark.parametrize("kind,boundary", BOUNDARIES)
@pytest.mark.parametrize("expiry", ["lease", "request"])
def test_publication_rechecks_expiry_after_authority_and_digest(world, source, kind, boundary, expiry):
    job = queued(world, source, kind)
    selected = service.claim(job.pk)
    assert selected is not None
    _, token = selected
    now = timezone.now()
    job.refresh_from_db()
    job.lease_until = now + timedelta(seconds=10 if expiry == "lease" else 30)
    job.expires_at = now + timedelta(seconds=20)
    job.save(update_fields=["lease_until", "expires_at"])
    before = NativeJob.objects.filter(pk=job.pk).values().get()
    events = list(JobEvent.objects.filter(job=job).values())
    clock = [now]
    payload = {"scope": "fencing-test", "value": 1}
    original_lock, original_recheck, original_digest = service.lock_authority, service.recheck_execution, service.digest
    calls = []

    def advance():
        clock[0] = job.lease_until if expiry == "lease" else job.expires_at

    def authority(*args, **kwargs):
        result = original_lock(*args, **kwargs)
        calls.append(args[1])
        if boundary == "authority" or boundary == "source_authority" and len(calls) == 2:
            advance()
        return result

    def recheck(*args, **kwargs):
        result = original_recheck(*args, **kwargs)
        if boundary == "recheck":
            advance()
        return result

    def digest(value):
        result = original_digest(value)
        if boundary == "digest" and value is payload:
            advance()
        return result

    with (patch.object(service.timezone, "now", side_effect=lambda: clock[0]),
          patch.object(service, "lock_authority", side_effect=authority),
          patch.object(service, "recheck_execution", side_effect=recheck),
          patch.object(service, "digest", side_effect=digest)):
        service.finish(job.pk, token, "succeeded", result=payload)
    assert calls and (boundary != "source_authority" or len(calls) == 2)
    job.refresh_from_db()
    assert job.result is None and job.result_sha256 == ""
    if expiry == "lease":
        assert NativeJob.objects.filter(pk=job.pk).values().get() == before
        assert list(JobEvent.objects.filter(job=job).values()) == events
    else:
        assert job.state == "failed" and job.reason_code == "job_expired"
        assert job.finished_at == job.expires_at and job.lease_token is None
        assert job.events.last().event_type == "failed"


@pytest.mark.parametrize("kind", ["integrity", "scoring"])
def test_current_lease_still_publishes_before_both_deadlines(world, source, kind):
    job = queued(world, source, kind)
    _, token = service.claim(job.pk)
    job.refresh_from_db()
    instant = min(job.lease_until, job.expires_at) - timedelta(microseconds=1)
    result = {"scope": "fencing-reference", "value": 1}
    with patch.object(service.timezone, "now", return_value=instant):
        service.finish(job.pk, token, "succeeded", result=result)
    job.refresh_from_db()
    assert job.state == "succeeded" and job.result == result
    assert job.result_sha256 == service.digest(result)
    assert job.events.last().event_type == "succeeded"


@pytest.mark.parametrize("kind", ["integrity", "scoring"])
def test_authority_denial_after_lease_expiry_cannot_publish_a_terminal_event(world, source, kind):
    job = queued(world, source, kind)
    _, token = service.claim(job.pk)
    job.refresh_from_db()
    before, events = NativeJob.objects.filter(pk=job.pk).values().get(), list(job.events.values())
    clock = [timezone.now()]

    def denied(*args, **kwargs):
        clock[0] = job.lease_until
        raise projects.ProjectDenied("job_authority_changed")

    with (patch.object(service.timezone, "now", side_effect=lambda: clock[0]),
          patch.object(service, "lock_authority", side_effect=denied)):
        service.finish(job.pk, token, "succeeded", result={"must": "not publish"})
    assert NativeJob.objects.filter(pk=job.pk).values().get() == before
    assert list(job.events.values()) == events


@pytest.mark.parametrize("kind", ["integrity", "scoring"])
@pytest.mark.parametrize("boundary", ["recheck", "runtime"])
def test_claim_cannot_start_a_request_that_expired_during_validation(world, source, kind, boundary):
    job = queued(world, source, kind)
    clock = [timezone.now()]
    actual = getattr(service, "recheck_execution" if boundary == "recheck" else "runtime")

    def delayed(*args, **kwargs):
        result = actual(*args, **kwargs)
        clock[0] = job.expires_at
        return result

    with (patch.object(service.timezone, "now", side_effect=lambda: clock[0]),
          patch.object(service, "recheck_execution" if boundary == "recheck" else "runtime", side_effect=delayed)):
        assert service.claim(job.pk) is None
    job.refresh_from_db()
    assert job.state == "failed" and job.reason_code == "job_expired"
    assert job.attempts == 0 and job.lease_token is None and job.result is None
    assert list(job.events.values_list("event_type", flat=True)) == ["submitted", "failed"]


@pytest.mark.parametrize("state", ["running", "cancel_requested", "queued"])
def test_reconciliation_samples_time_after_acquiring_queue_lock(world, source, state):
    job = queued(world, source, "integrity")
    now = timezone.now()
    if state != "queued":
        assert service.claim(job.pk) is not None
        NativeJob.objects.filter(pk=job.pk).update(state=state, lease_until=now + timedelta(seconds=1))
    else:
        NativeJob.objects.filter(pk=job.pk).update(expires_at=now + timedelta(seconds=1))
    clock = [now]
    actual = service.locked

    @contextmanager
    def delayed_lock():
        with actual():
            clock[0] = now + timedelta(seconds=2)
            yield

    with (patch.object(service.timezone, "now", side_effect=lambda: clock[0]),
          patch.object(service, "locked", side_effect=delayed_lock)):
        due = service.reconcile()
    job.refresh_from_db()
    expected = {"running": "queued", "cancel_requested": "cancelled", "queued": "failed"}[state]
    assert job.state == expected and job.lease_token is None
    assert (job.pk in due) is (state == "running")
