"""Due request batches have a stable time/UUID prefix, including lease recovery."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from access_control.models import Project
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
KINDS = [service.KIND, service.csv_scoring.KIND, service.training_search.KIND,
         service.training_scoring.KIND, service.native_assessment.KIND]


@pytest.fixture
def queue(settings, monkeypatch, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.DECLARAI_JOBS_ENABLED = True
    now = timezone.now()
    monkeypatch.setattr(service.timezone, "now", lambda: now)
    project = Project.objects.create(name="Stable dispatch fixture")
    dataset = Declaration.objects.create(name="Stable dispatch dataset")

    def add(numbers, **overrides):
        values = dict(
            project=project, dataset=dataset, actor_snapshot={"private": "retained actor"},
            authority={"private": "retained authority"}, specification={"kind": service.KIND},
            request_sha256="a" * 64, state="queued", revision=5, attempts=0,
            created_at=now, next_dispatch=now, expires_at=now + timedelta(hours=1),
            result={"private": "retained result"}, result_sha256="b" * 64,
        )
        values.update(overrides)
        return NativeJob.objects.bulk_create([NativeJob(id=uuid.UUID(int=n), **values) for n in numbers])

    return SimpleNamespace(now=now, add=add)


def rows():
    return list(NativeJob.objects.order_by("pk").values())


def identifiers(numbers):
    return [uuid.UUID(int=n) for n in numbers]


@pytest.mark.parametrize("kind", KINDS)
def test_equal_creation_times_dispatch_by_uuid_without_kind_priority_or_writes(queue, kind):
    queue.add([4, 1, 3, 2], specification={"kind": kind})
    before = rows()
    assert service.reconcile() == identifiers([1, 2, 3, 4])
    assert service.reconcile() == identifiers([1, 2, 3, 4])
    assert rows() == before and not JobEvent.objects.exists()


@pytest.mark.parametrize("count", [2, 50, 100, 103])
def test_stable_batch_prefix_precedes_original_hundred_id_slice(queue, count):
    # Restored metadata can exceed normal admission bounds. Observation must
    # retain the existing slice rather than raising the scheduling limit.
    queue.add(list(range(count, 0, -1)))
    before = rows()
    expected = identifiers(range(1, min(count, 100) + 1))
    assert service.reconcile() == expected
    assert service.reconcile() == expected
    assert rows() == before and not JobEvent.objects.exists()


@pytest.mark.parametrize("attempts", [0, 2])
def test_recovered_lease_joins_tied_due_jobs_without_changing_transitions_or_filters(queue, attempts):
    queue.add([1, 3])
    active = queue.add([2], state="running", attempts=attempts, lease_token=uuid.uuid4(),
                       lease_until=queue.now - timedelta(seconds=1))[0]
    expired = queue.add([4], expires_at=queue.now)[0]
    future = queue.add([5], next_dispatch=queue.now + timedelta(seconds=1))[0]
    terminal = queue.add([6], state="succeeded")[0]
    before = {r["id"]: r for r in rows()}
    expected = identifiers([1, 2, 3])
    assert service.reconcile() == expected
    after = {r["id"]: r for r in rows()}
    assert after[active.pk] == {**before[active.pk], "state": "queued", "revision": 6,
                                "lease_token": None, "lease_until": None, "next_dispatch": queue.now}
    assert after[expired.pk] == {**before[expired.pk], "state": "failed", "revision": 6,
                                "reason_code": "job_expired", "finished_at": queue.now}
    assert after[future.pk] == before[future.pk] and after[terminal.pk] == before[terminal.pk]
    assert JobEvent.objects.get(job=active).detail == {"reason_code": "worker_lease_expired"}
    assert JobEvent.objects.get(job=expired).detail == {"reason_code": "job_expired"}
    assert JobEvent.objects.count() == 2
    assert service.reconcile() == expected and rows() == list(after.values())
    assert JobEvent.objects.count() == 2


@pytest.mark.parametrize("broker_failure", [False, True])
def test_real_outbox_pump_publishes_stable_uuid_order_and_retains_failure_backoff(queue, monkeypatch, broker_failure):
    from execution_jobs.tasks import run_native_job

    queue.add([3, 2, 1])
    before = {r["id"]: r for r in rows()}
    calls = []

    def publish(*, args, retry):
        assert len(args) == 1 and retry is False
        calls.append(args[0])
        if broker_failure and len(calls) == 2:
            raise OSError("owned broker fixture")

    monkeypatch.setattr(run_native_job, "apply_async", publish)
    monkeypatch.setattr(service, "claim", lambda *args: pytest.fail("dispatcher claimed work"))
    monkeypatch.setattr(service, "execute", lambda *args: pytest.fail("dispatcher executed work"))
    assert service.dispatch_once() == {"delivered": 1 if broker_failure else 3, "broker_unavailable": int(broker_failure)}
    assert calls == [str(v) for v in identifiers([1, 2] if broker_failure else [1, 2, 3])]
    delivered = set(identifiers([1] if broker_failure else [1, 2, 3]))
    for current in rows():
        expected = before[current["id"]]
        if current["id"] in delivered:
            expected = {**expected, "next_dispatch": queue.now + timedelta(seconds=30)}
        assert current == expected
    assert not JobEvent.objects.exists()


@pytest.mark.parametrize("spacing", [1, 10, 100])
def test_creation_time_stays_primary_when_uuid_order_disagrees(queue, spacing):
    for n, age in [(4, 3), (1, 2), (3, 1)]:
        queue.add([n], created_at=queue.now - timedelta(seconds=age * spacing))
    before = rows()
    assert service.reconcile() == identifiers([4, 1, 3])
    assert rows() == before and not JobEvent.objects.exists()
