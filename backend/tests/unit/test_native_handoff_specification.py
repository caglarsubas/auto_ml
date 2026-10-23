"""A malformed saved request cannot become an operational handoff receipt."""

import copy

import pytest
from django.db import connection, models
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from access_control import projects
from access_control.models import ProjectAuthorityEvent, ProjectMembership
from execution_jobs import operational_handoff as handoff, service
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_native_handoff_history_counter import history, world  # noqa: F401
from tests.unit.test_native_handoff_access_summary import add_accesses, snapshot

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
MISSING = "missing-field-fixture"
KINDS = [service.KIND, service.csv_scoring.KIND, service.training_search.KIND,
         service.training_scoring.KIND, service.native_assessment.KIND]
INVALID = (
    [("root", v) for v in [None, [], ["private-fixture"], "private-fixture", 0, False]]
    + [("kind", v) for v in [MISSING, "", "UNKNOWN", None, [], {}, 1, True]]
    + [("limits", v) for v in [MISSING, None, [], ["private-fixture"], "private-fixture", 0, False]]
    + [("attempts", v) for v in [MISSING, None, "3", True, False, 0, -1, 1.5, [], {}]]
)


def setup_history(w):
    history(w, [1, 2, 3], 3)
    add_accesses(w, (1, 1, 1))


def specification(w, field, value):
    spec = copy.deepcopy(w.job.specification)
    if field == "root":
        spec = value
    else:
        container = spec["limits"] if field == "attempts" else spec
        if value == MISSING:
            del container[field]
        else:
            container[field] = value
    NativeJob.objects.filter(pk=w.job.pk).update(specification=models.Value(spec, output_field=models.JSONField()))


def forbid_history(monkeypatch):
    monkeypatch.setattr(HoldoutAccess.objects, "filter", lambda *a, **k: pytest.fail("outcomes read before specification guard"))


@pytest.mark.parametrize("field,value", INVALID)
def test_invalid_saved_specification_refuses_before_history_without_repair(world, monkeypatch, field, value):  # noqa: F811
    setup_history(world)
    specification(world, field, value)
    before = snapshot()
    forbid_history(monkeypatch)
    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(service.JobConflict, match="job_handoff_specification_invalid"):
            handoff.read(world.actor, world.job.pk, "3")
    assert not any('"execution_jobs_jobevent"' in q["sql"] for q in queries)
    assert not any(q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries)
    assert snapshot() == before


@pytest.mark.parametrize("field,value", [("kind", []), ("limits", None)])
@pytest.mark.parametrize("method", ["get", "head"])
def test_actual_http_returns_uncached_conflict_with_attributable_audit(world, field, value, method):  # noqa: F811
    setup_history(world)
    specification(world, field, value)
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
        assert response.json() == {"error_code": "job_handoff_specification_invalid"}
    assert ProjectAuthorityEvent.objects.count() == audits + 1
    assert ProjectAuthorityEvent.objects.get(operation="native_access").actor_id == world.actor.pk
    assert snapshot() == before


@pytest.mark.parametrize("field,value", [("root", None), ("kind", [])])
@pytest.mark.parametrize("guard", ["outsider", "revoked", "stale", "result_changed"])
def test_earlier_authority_revision_and_result_guards_keep_precedence(world, monkeypatch, field, value, guard):  # noqa: F811
    setup_history(world)
    specification(world, field, value)
    actor = world.outsider if guard == "outsider" else world.actor
    if guard == "revoked":
        ProjectMembership.objects.filter(actor=actor).update(active=False)
    if guard == "result_changed":
        NativeJob.objects.filter(pk=world.job.pk).update(result={"private-fixture": True}, result_sha256="0" * 64)
    before = snapshot()
    forbid_history(monkeypatch)
    expected = projects.ProjectDenied if guard in {"outsider", "revoked"} else service.JobConflict
    code = "project_access_denied" if guard in {"outsider", "revoked"} else "job_handoff_stale" if guard == "stale" else "job_result_changed"
    with pytest.raises(expected) as caught:
        handoff.read(actor, world.job.pk, "2" if guard == "stale" else "3")
    assert caught.value.code == code and snapshot() == before


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("attempts", [1, 9])
def test_supported_kinds_keep_saved_positive_limits_full_receipts_and_exact_digests(world, kind, attempts):  # noqa: F811
    setup_history(world)
    specification(world, "kind", kind)
    world.job.refresh_from_db()
    specification(world, "attempts", attempts)
    before = snapshot()
    value = handoff.read(world.actor, world.job.pk, "3")
    assert value["kind"] == kind and value["attempt_limit"] == attempts
    assert [e["revision"] for e in value["events"]] == [1, 2, 3]
    assert value["outcome_accesses"] == dict(total=3, started=1, failed=1, completed=1)
    assert value["sha256"] == service.digest({k: v for k, v in value.items() if k != "sha256"})
    assert handoff.read(world.actor, world.job.pk, "3", value["sha256"]) == value
    assert value["read_only"] and not any(value[k] for k in ["recovery_authorized", "review_approved", "production_use_approved"])
    assert snapshot() == before


@pytest.mark.parametrize("field,value", [("root", None), ("attempts", False)])
def test_invalid_specification_cannot_export_old_receipt_or_erase_possible_access(world, field, value):  # noqa: F811
    setup_history(world)
    original = handoff.read(world.actor, world.job.pk, "3")
    specification(world, field, value)
    before = snapshot()
    with pytest.raises(service.JobConflict, match="job_handoff_specification_invalid"):
        handoff.read(world.actor, world.job.pk, "3", original["sha256"])
    assert snapshot() == before and HoldoutAccess.objects.count() == 3
