"""Stop the outbox between publishes without abandoning its current unit."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
from django.db import connection
from django.utils import timezone

from execution_jobs import service
from execution_jobs.models import NativeJob, JobEvent
from tests.unit.test_package_reviews import world, packaged  # noqa: F401
from tests.unit.test_native_jobs import submit

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def configured(settings):
    settings.DECLARAI_JOBS_ENABLED = True
    settings.CELERY_BROKER_URL = "redis://127.0.0.1:9/15"


def queued(world):
    ids = [submit(world)[0].json()["id"] for _ in range(3)]
    assert NativeJob.objects.count() == JobEvent.objects.count() == 3
    return ids, list(NativeJob.objects.order_by("created_at").values()), list(JobEvent.objects.order_by("created_at").values())


@pytest.mark.parametrize("boundary", ["before_work", "reconciliation", "publish", "metadata"])
def test_stop_leaves_remaining_requests_and_evidence_unchanged(world, boundary):
    from execution_jobs.tasks import run_native_job

    ids, before, events = queued(world)
    stopping, published = [boundary == "before_work"], []
    actual_reconcile, actual_locked = service.reconcile, service.locked
    locks = []

    def reconcile():
        result = actual_reconcile()
        if boundary == "reconciliation":
            stopping[0] = True
        return result

    def publish(*, args, retry):
        assert not connection.in_atomic_block and retry is False
        published.extend(args)
        if boundary == "publish":
            stopping[0] = True

    def locked():
        locks.append(1)
        # The first scope is reconciliation; the second finalizes publication.
        if boundary == "metadata" and len(locks) == 2:
            stopping[0] = True
        return actual_locked()

    start = timezone.now()
    with (patch.object(service, "reconcile", side_effect=reconcile) as reconciliation,
          patch.object(service, "locked", side_effect=locked),
          patch.object(run_native_job, "apply_async", side_effect=publish)):
        result = service.dispatch_once(should_stop=lambda: stopping[0])
    expected = 1 if boundary in {"publish", "metadata"} else 0
    assert result == {"delivered": expected, "broker_unavailable": 0}
    assert published == ids[:expected]
    assert reconciliation.call_count == (0 if boundary == "before_work" else 1)
    after = list(NativeJob.objects.order_by("created_at").values())
    if expected:
        assert after[0]["next_dispatch"] >= start + service.timedelta(seconds=30)
        after[0]["next_dispatch"] = before[0]["next_dispatch"]
    assert after == before
    assert list(JobEvent.objects.order_by("created_at").values()) == events


def test_default_call_still_dispatches_complete_due_batch(world):
    from execution_jobs.tasks import run_native_job

    ids, _, events = queued(world)
    with patch.object(run_native_job, "apply_async") as publish:
        assert service.dispatch_once() == {"delivered": 3, "broker_unavailable": 0}
    assert [call.kwargs for call in publish.call_args_list] == [{"args": [identifier], "retry": False} for identifier in ids]
    assert list(JobEvent.objects.order_by("created_at").values()) == events
    assert all(j.state == "queued" and j.attempts == 0 for j in NativeJob.objects.all())


@pytest.mark.parametrize("published_before_failure", [0, 1])
def test_signal_during_failed_publish_preserves_redaction_and_pending_work(world, published_before_failure):
    from execution_jobs.tasks import run_native_job

    ids, before, events = queued(world)
    stopping, calls = [False], []

    def publish(*, args, retry):
        calls.extend(args)
        if len(calls) > published_before_failure:
            stopping[0] = True
            raise OSError("private-broker-credential-sentinel")

    with patch.object(run_native_job, "apply_async", side_effect=publish):
        result = service.dispatch_once(should_stop=lambda: stopping[0])
    assert result == {"delivered": published_before_failure, "broker_unavailable": 1}
    assert calls == ids[:published_before_failure + 1]
    after = list(NativeJob.objects.order_by("created_at").values())
    for index in range(published_before_failure):
        after[index]["next_dispatch"] = before[index]["next_dispatch"]
    assert after == before and list(JobEvent.objects.order_by("created_at").values()) == events
    assert "sentinel" not in str(result)


@pytest.mark.parametrize("signum", ["SIGTERM", "SIGINT"])
def test_actual_os_signal_finishes_only_current_publish_and_restores_handlers(signum):
    fixture = Path(__file__).resolve().parents[1] / "fixtures/native_dispatch_shutdown.py"
    env = dict(os.environ, PYTHONPATH=str(fixture.parents[2]), PYTHONDONTWRITEBYTECODE="1", PROMETA_DISABLE="1")
    result = subprocess.run([sys.executable, str(fixture), signum], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["signal"] == signum and receipt["published"] == receipt["finalized"] == 1
    assert receipt["ids"] == ["00000000-0000-0000-0000-000000000001"]
    assert receipt["handlers_restored"] is True and receipt["actual_broker_or_database_used"] is False
