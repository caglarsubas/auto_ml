"""Handoff history validation cannot allocate from an inconsistent revision counter."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from access_control import projects
from access_control.models import Project, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs import operational_handoff as handoff, service
from execution_jobs.models import JobEvent, NativeJob, QueueLock
from modeling.models import HoldoutAccess

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
MISMATCHES = [(events, revision) for events in [[], [1], [1, 2]]
              for revision in [len(events) + 1, 10_000, 2**31 - 1]]


@pytest.fixture
def world(settings, django_user_model, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.DECLARAI_RUNTIME_PROFILE = "development"
    ProjectPolicy.objects.create()
    QueueLock.objects.get_or_create(pk=1)
    project = Project.objects.create(name="Handoff counter fixture")
    actor = django_user_model.objects.create_user(username="handoff-counter-reviewer")
    outsider = django_user_model.objects.create_user(username="handoff-counter-outsider")
    ProjectMembership.objects.create(project=project, actor=actor, role="reviewer")
    dataset = Declaration.objects.create(name="Handoff counter dataset")
    projects.bind_dataset(dataset, project.pk)
    job = NativeJob.objects.create(
        id=uuid.uuid4(), project=project, dataset=dataset, actor=actor,
        actor_snapshot={"fixture": "retained actor"}, authority=projects.dataset_authority(actor.pk, dataset.pk),
        specification={"kind": service.KIND, "limits": service.limits(service.KIND)},
        request_sha256="a" * 64, expires_at=timezone.now() + timedelta(hours=1),
    )
    return SimpleNamespace(actor=actor, outsider=outsider, job=job)


def history(world, revisions, counter):
    NativeJob.objects.filter(pk=world.job.pk).update(revision=counter)
    JobEvent.objects.bulk_create([JobEvent(job=world.job, revision=n, event_type="fixture_receipt") for n in revisions])


def state():
    return (list(NativeJob.objects.values()), list(JobEvent.objects.order_by("revision").values()), HoldoutAccess.objects.count())


def allocation_tripwire(monkeypatch, recorded):
    # Intercept the old module's range before a huge materialization can occur.
    # This is a safety tripwire, not a host-memory or throughput benchmark.
    actual = range

    def guarded(*args):
        requested = actual(*args)
        if len(requested) > recorded:
            pytest.fail("revision counter requested an allocation larger than recorded history")
        return requested

    monkeypatch.setattr(handoff, "range", guarded, raising=False)


def forbid_outcomes(monkeypatch):
    monkeypatch.setattr(HoldoutAccess.objects, "filter", lambda *a, **k: pytest.fail("outcome history read before event validation"))


@pytest.mark.parametrize("revisions,counter", MISMATCHES)
def test_inconsistent_counter_rejected_without_counter_sized_allocation_or_outcome_reads(world, monkeypatch, revisions, counter):
    history(world, revisions, counter)
    before = state()
    allocation_tripwire(monkeypatch, len(revisions))
    forbid_outcomes(monkeypatch)
    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(service.JobConflict, match="job_event_history_invalid"):
            handoff.read(world.actor, world.job.pk, str(counter))
    assert not any(q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries)
    assert state() == before


@pytest.mark.parametrize("counter", [10_000, 2**31 - 1])
@pytest.mark.parametrize("method", ["get", "head"])
def test_http_large_counter_returns_uncached_structured_conflict_without_export(world, monkeypatch, counter, method):
    history(world, [1], counter)
    before = state()
    allocation_tripwire(monkeypatch, 1)
    forbid_outcomes(monkeypatch)
    client = APIClient()
    client.force_authenticate(user=world.actor)
    response = getattr(client, method)(f"/api/jobs/{world.job.pk}/operational-handoff/", {"revision": str(counter)})
    assert response.status_code == 409 and response["Cache-Control"] == "no-store"
    if method == "head":
        assert response.content == b""
    else:
        assert response.json() == {"error_code": "job_event_history_invalid"}
    assert "sha256" not in response.headers and state() == before


@pytest.mark.parametrize("observed", [0, 1])
def test_stale_revision_precedes_history_validation(world, monkeypatch, observed):
    history(world, [1], 2**31 - 1)
    before = state()
    allocation_tripwire(monkeypatch, 0)
    forbid_outcomes(monkeypatch)
    with pytest.raises(service.JobConflict, match="job_handoff_stale"):
        handoff.read(world.actor, world.job.pk, str(observed))
    assert state() == before


@pytest.mark.parametrize("denial", ["outsider", "revoked"])
def test_real_project_denial_precedes_history_validation(world, monkeypatch, denial):
    history(world, [1], 2**31 - 1)
    actor = world.outsider if denial == "outsider" else world.actor
    if denial == "revoked":
        ProjectMembership.objects.filter(actor=actor).update(active=False)
    before = state()
    allocation_tripwire(monkeypatch, 0)
    forbid_outcomes(monkeypatch)
    with pytest.raises(projects.ProjectDenied):
        handoff.read(actor, world.job.pk, str(2**31 - 1))
    assert state() == before


@pytest.mark.parametrize("count", [0, 1, 8, 32])
def test_contiguous_history_retains_full_receipts_and_repeatable_digest_without_a_new_cap(world, monkeypatch, count):
    history(world, list(range(1, count + 1)), count)
    before = state()
    allocation_tripwire(monkeypatch, count)
    with CaptureQueriesContext(connection) as queries:
        result = handoff.read(world.actor, world.job.pk, str(count))
        assert handoff.read(world.actor, world.job.pk, str(count), result["sha256"]) == result
    assert [e["revision"] for e in result["events"]] == list(range(1, count + 1))
    assert result["revision"] == count and result["next_action"] == handoff.NEXT["queued"]
    assert result["sha256"] == service.digest({k: v for k, v in result.items() if k != "sha256"})
    assert result["read_only"] and not any(result[k] for k in ["recovery_authorized", "review_approved", "production_use_approved"])
    assert not any('"payload"' in q["sql"] or q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries)
    assert state() == before


@pytest.mark.parametrize("revisions", [[0], [2], [1, 3], [2, 3], [0, 1], [1, 2, 4]])
def test_matching_count_does_not_hide_a_missing_first_or_noncontiguous_revision(world, monkeypatch, revisions):
    history(world, revisions, len(revisions))
    before = state()
    allocation_tripwire(monkeypatch, len(revisions))
    forbid_outcomes(monkeypatch)
    with pytest.raises(service.JobConflict, match="job_event_history_invalid"):
        handoff.read(world.actor, world.job.pk, str(len(revisions)))
    assert state() == before
