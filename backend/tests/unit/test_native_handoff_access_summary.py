"""Handoff access summaries return scalar counts, never one value per access."""

import re
import uuid
from contextlib import contextmanager

import pytest
from django.db import connection
from django.db.models.query import QuerySet
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from access_control import projects
from access_control.models import ProjectAuthorityEvent, ProjectMembership
from execution_jobs import operational_handoff as handoff, service
from execution_jobs.models import JobEvent, NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_native_handoff_history_counter import history, world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
STATES = ("started", "failed", "completed")
COUNTS = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1), (5, 3, 2), (32, 16, 8)]


def add_accesses(w, counts=(1, 1, 1)):
    HoldoutAccess.objects.bulk_create([
        HoldoutAccess(file_id=w.job.dataset_id, attempt_state=state,
                      parameters={"scope": "native_protected_assessment_v1", "job_id": str(w.job.pk)})
        for state, count in zip(STATES, counts) for _ in range(count)
    ])


def snapshot():
    return (list(NativeJob.objects.values()), list(JobEvent.objects.order_by("revision").values()),
            list(HoldoutAccess.objects.order_by("id").values()))


@contextmanager
def scalar_access_reads(monkeypatch):
    original_fetch, original_iterator = QuerySet._fetch_all, QuerySet.iterator

    def fetch(query):
        if query.model is HoldoutAccess:
            pytest.fail("handoff materialized individual outcome-access rows")
        return original_fetch(query)

    def iterator(query, *args, **kwargs):
        if query.model is HoldoutAccess:
            pytest.fail("handoff streamed individual outcome-access rows")
        return original_iterator(query, *args, **kwargs)

    # Local tripwire only: real authority/event queries and SQL aggregation run.
    with monkeypatch.context() as patch:
        patch.setattr(QuerySet, "_fetch_all", fetch)
        patch.setattr(QuerySet, "iterator", iterator)
        with CaptureQueriesContext(connection) as queries:
            yield queries


def check_queries(queries, *, summary=True, allow_access_audit=False):
    sql = [q["sql"] for q in queries]
    for query in sql:
        if query.lstrip().startswith(("INSERT", "UPDATE", "DELETE")):
            target = re.match(r'^\s*(?:INSERT INTO|UPDATE|DELETE FROM) "([^"]+)"', query)
            assert allow_access_audit and target and target[1] == ProjectAuthorityEvent._meta.db_table
    accesses = [q for q in sql if '"modeling_holdoutaccess"' in q]
    assert len(accesses) == int(summary)
    if summary:
        selected = accesses[0].split(" FROM ", 1)[0]
        assert "COUNT(" in selected and '"parameters"' not in selected and '"holdout_spec"' not in selected


@pytest.mark.parametrize("counts", COUNTS)
def test_counts_and_receipt_digest_do_not_require_individual_access_rows(world, monkeypatch, counts):
    history(world, [1, 2], 2)
    add_accesses(world, counts)
    before = snapshot()
    with scalar_access_reads(monkeypatch) as queries:
        value = handoff.read(world.actor, world.job.pk, "2")
    check_queries(queries)
    assert value["outcome_accesses"] == {"total": sum(counts), **dict(zip(STATES, counts))}
    assert [e["revision"] for e in value["events"]] == [1, 2]
    assert value["sha256"] == service.digest({k: v for k, v in value.items() if k != "sha256"})
    assert value["read_only"] and not any(value[k] for k in ["recovery_authorized", "review_approved", "production_use_approved"])
    with scalar_access_reads(monkeypatch) as queries:
        assert handoff.read(world.actor, world.job.pk, "2", value["sha256"]) == value
    check_queries(queries)
    assert snapshot() == before


@pytest.mark.parametrize("unknown", ["historical_unknown", "", "pending", "complete", "COMPLETED", " started", "failed ", "unrecognized"])
def test_any_in_scope_unknown_state_still_fails_closed_without_materialization(world, monkeypatch, unknown):
    history(world, [1], 1)
    add_accesses(world)
    HoldoutAccess.objects.create(file_id=world.job.dataset_id, attempt_state=unknown,
                                parameters={"scope": "native_protected_assessment_v1", "job_id": str(world.job.pk)})
    before = snapshot()
    with scalar_access_reads(monkeypatch) as queries:
        with pytest.raises(service.JobConflict, match="job_access_history_invalid"):
            handoff.read(world.actor, world.job.pk, "1")
    check_queries(queries)
    assert snapshot() == before


@pytest.mark.parametrize("excluded", ["dataset", "job", "scope", "missing_job", "missing_scope", "missing_both"])
def test_other_or_incomplete_access_scopes_do_not_change_counts_or_block_handoff(world, monkeypatch, excluded):
    history(world, [1], 1)
    add_accesses(world, (3, 2, 4))
    file_id = world.job.dataset_id
    parameters = {"scope": "native_protected_assessment_v1", "job_id": str(world.job.pk)}
    if excluded == "dataset":
        file_id += 1
    elif excluded == "job":
        parameters["job_id"] = str(uuid.uuid4())
    elif excluded == "scope":
        parameters["scope"] = "other"
    elif excluded == "missing_job":
        del parameters["job_id"]
    elif excluded == "missing_scope":
        del parameters["scope"]
    else:
        parameters = {}
    HoldoutAccess.objects.bulk_create([
        HoldoutAccess(file_id=file_id, attempt_state="historical_unknown", parameters=parameters) for _ in range(9)
    ])
    before = snapshot()
    with scalar_access_reads(monkeypatch) as queries:
        value = handoff.read(world.actor, world.job.pk, "1")
    check_queries(queries)
    assert value["outcome_accesses"] == dict(total=9, started=3, failed=2, completed=4)
    assert snapshot() == before


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("invalid", [False, True])
def test_http_get_head_keep_uncached_receipts_or_structured_conflicts(world, monkeypatch, method, invalid):
    history(world, [1], 1)
    add_accesses(world, (3, 2, 4))
    if invalid:
        HoldoutAccess.objects.create(file_id=world.job.dataset_id, attempt_state="historical_unknown",
                                    parameters={"scope": "native_protected_assessment_v1", "job_id": str(world.job.pk)})
    before = snapshot()
    audits = ProjectAuthorityEvent.objects.count()
    client = APIClient()
    client.force_authenticate(user=world.actor)
    with scalar_access_reads(monkeypatch) as queries:
        response = getattr(client, method)(f"/api/jobs/{world.job.pk}/operational-handoff/", {"revision": "1"})
    check_queries(queries, allow_access_audit=True)
    assert ProjectAuthorityEvent.objects.count() == audits + 1
    assert ProjectAuthorityEvent.objects.get(operation="native_access").actor_id == world.actor.pk
    assert response.status_code == (409 if invalid else 200)
    assert response["Cache-Control"] == "no-store"
    if method == "head":
        assert response.content == b""
    elif invalid:
        assert response.json() == {"error_code": "job_access_history_invalid"}
    else:
        value = response.json()
        assert value["outcome_accesses"] == dict(total=9, started=3, failed=2, completed=4)
        assert value["sha256"] == service.digest({k: v for k, v in value.items() if k != "sha256"})
    assert snapshot() == before


@pytest.mark.parametrize("guard", ["outsider", "revoked", "stale", "event_gap"])
def test_authority_revision_and_event_guards_still_precede_outcome_queries(world, monkeypatch, guard):
    history(world, [2] if guard == "event_gap" else [1], 1)
    add_accesses(world)
    actor = world.outsider if guard == "outsider" else world.actor
    if guard == "revoked":
        ProjectMembership.objects.filter(actor=actor).update(active=False)
    before = snapshot()
    with scalar_access_reads(monkeypatch) as queries:
        if guard in {"outsider", "revoked"}:
            with pytest.raises(projects.ProjectDenied):
                handoff.read(actor, world.job.pk, "1")
        else:
            with pytest.raises(service.JobConflict, match="job_handoff_stale" if guard == "stale" else "job_event_history_invalid"):
                handoff.read(actor, world.job.pk, "0" if guard == "stale" else "1")
    check_queries(queries, summary=False)
    assert snapshot() == before


@pytest.mark.parametrize("next_state", ["failed", "completed"])
def test_access_state_changes_invalidate_old_handoff_digest_without_erasing_possible_access(world, monkeypatch, next_state):
    history(world, [1], 1)
    add_accesses(world, (1, 0, 0))
    with scalar_access_reads(monkeypatch) as queries:
        first = handoff.read(world.actor, world.job.pk, "1")
    check_queries(queries)
    HoldoutAccess.objects.update(attempt_state=next_state)
    before = snapshot()
    with scalar_access_reads(monkeypatch) as queries:
        with pytest.raises(service.JobConflict, match="job_handoff_stale"):
            handoff.read(world.actor, world.job.pk, "1", first["sha256"])
    check_queries(queries)
    with scalar_access_reads(monkeypatch) as queries:
        current = handoff.read(world.actor, world.job.pk, "1")
    check_queries(queries)
    assert current["outcome_accesses"] == {"total": 1, **{s: int(s == next_state) for s in STATES}}
    assert current["sha256"] != first["sha256"] and current["revision"] == first["revision"]
    assert snapshot() == before
