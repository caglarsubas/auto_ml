"""Malformed handoff metadata is a conflict, never a partial receipt or repair."""

import pytest
from django.db import connection, models
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from access_control import projects
from access_control.models import ProjectAuthorityEvent, ProjectMembership
from execution_jobs import operational_handoff as handoff, service
from execution_jobs.models import JobEvent, NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_native_handoff_history_counter import history, world  # noqa: F401
from tests.unit.test_native_handoff_access_summary import add_accesses, snapshot

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
DETAILS = [None, [], ["private-fixture"], "private-fixture", 0, False]
UNKNOWN_STATES = ["", "QUEUED", "queued ", "legacy_state", "complete", "cancelled "]


def setup_history(w):
    history(w, [1, 2, 3], 3)
    add_accesses(w, (1, 1, 1))


def detail(value):
    # Value(None, JSONField) stores JSON null, not a SQL NULL that would fail
    # the existing column constraint before handoff could inspect the record.
    JobEvent.objects.filter(revision=2).update(detail=models.Value(value, output_field=models.JSONField()))


def invalid(w, kind):
    if kind == "event_detail":
        detail(None)
    else:
        NativeJob.objects.filter(pk=w.job.pk).update(state="legacy_state")


def error(kind):
    return "job_event_history_invalid" if kind == "event_detail" else "job_handoff_state_invalid"


def forbid_accesses(monkeypatch):
    monkeypatch.setattr(HoldoutAccess.objects, "filter", lambda *a, **k: pytest.fail("outcomes read before metadata guard"))


@pytest.mark.parametrize("value", DETAILS)
def test_non_object_event_detail_fails_before_outcome_reads_without_mutation(world, monkeypatch, value):  # noqa: F811
    setup_history(world)
    detail(value)
    before = snapshot()
    forbid_accesses(monkeypatch)
    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(service.JobConflict, match="job_event_history_invalid"):
            handoff.read(world.actor, world.job.pk, "3")
    assert not any(q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries)
    assert snapshot() == before


@pytest.mark.parametrize("value", UNKNOWN_STATES)
def test_unknown_job_state_fails_before_event_and_outcome_reads(world, monkeypatch, value):  # noqa: F811
    setup_history(world)
    NativeJob.objects.filter(pk=world.job.pk).update(state=value)
    before = snapshot()
    forbid_accesses(monkeypatch)
    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(service.JobConflict, match="job_handoff_state_invalid"):
            handoff.read(world.actor, world.job.pk, "3")
    assert not any('"execution_jobs_jobevent"' in q["sql"] for q in queries)
    assert snapshot() == before


@pytest.mark.parametrize("kind", ["event_detail", "state"])
@pytest.mark.parametrize("method", ["get", "head"])
def test_actual_http_returns_uncached_structured_conflict_and_retains_attributable_audit(world, kind, method):  # noqa: F811
    setup_history(world)
    invalid(world, kind)
    before = snapshot()
    audits = ProjectAuthorityEvent.objects.count()
    client = APIClient()
    client.force_authenticate(user=world.actor)
    client.raise_request_exception = False
    response = getattr(client, method)(f"/api/jobs/{world.job.pk}/operational-handoff/", {"revision": "3"})
    assert response.status_code == 409 and response["Cache-Control"] == "no-store"
    if method == "head":
        assert response.content == b""
    else:
        assert response.json() == {"error_code": error(kind)}
    assert ProjectAuthorityEvent.objects.count() == audits + 1
    assert ProjectAuthorityEvent.objects.get(operation="native_access").actor_id == world.actor.pk
    assert snapshot() == before


@pytest.mark.parametrize("kind", ["event_detail", "state"])
@pytest.mark.parametrize("guard", ["outsider", "revoked", "stale", "result_changed"])
def test_authority_revision_and_result_integrity_keep_precedence(world, monkeypatch, kind, guard):  # noqa: F811
    setup_history(world)
    invalid(world, kind)
    actor = world.outsider if guard == "outsider" else world.actor
    if guard == "revoked":
        ProjectMembership.objects.filter(actor=actor).update(active=False)
    if guard == "result_changed":
        NativeJob.objects.filter(pk=world.job.pk).update(result={"private-fixture": True}, result_sha256="0" * 64)
    before = snapshot()
    forbid_accesses(monkeypatch)
    expected = projects.ProjectDenied if guard in {"outsider", "revoked"} else service.JobConflict
    code = "project_access_denied" if guard in {"outsider", "revoked"} else "job_handoff_stale" if guard == "stale" else "job_result_changed"
    with pytest.raises(expected) as caught:
        handoff.read(actor, world.job.pk, "2" if guard == "stale" else "3")
    assert caught.value.code == code and snapshot() == before


@pytest.mark.parametrize("metadata", [{}, {"reason_code": None}, {"reason_code": "true"},
                                      {"reason_code": False}, {"reason_code": 17},
                                      {"reason_code": ["historical"]}, {"reason_code": {"historical": 1}},
                                      {"reason_code": "retained", "not_exported": "private-fixture"}])
def test_object_details_keep_existing_reason_values_full_history_counts_and_digest(world, metadata):  # noqa: F811
    setup_history(world)
    detail(metadata)
    before = snapshot()
    value = handoff.read(world.actor, world.job.pk, "3")
    assert value["events"][1]["reason_code"] == metadata.get("reason_code", "")
    assert [e["revision"] for e in value["events"]] == [1, 2, 3]
    assert value["outcome_accesses"] == dict(total=3, started=1, failed=1, completed=1)
    assert "not_exported" not in str(value) and "private-fixture" not in str(value)
    assert value["sha256"] == service.digest({k: v for k, v in value.items() if k != "sha256"})
    assert handoff.read(world.actor, world.job.pk, "3", value["sha256"]) == value
    assert value["read_only"] and not any(value[k] for k in ["recovery_authorized", "review_approved", "production_use_approved"])
    assert snapshot() == before


@pytest.mark.parametrize("kind", ["event_detail", "state"])
def test_corruption_cannot_export_an_old_receipt_or_erase_possible_access(world, kind):  # noqa: F811
    setup_history(world)
    original = handoff.read(world.actor, world.job.pk, "3")
    invalid(world, kind)
    before = snapshot()
    with pytest.raises(service.JobConflict, match=error(kind)):
        handoff.read(world.actor, world.job.pk, "3", original["sha256"])
    assert snapshot() == before
    assert HoldoutAccess.objects.count() == 3
