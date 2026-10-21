"""History is bounded, permission scoped and observational even under queue failure."""

import hashlib
import json
import uuid
from datetime import timedelta

import pytest
from django.core import signing
from django.db import DatabaseError
from django.http import QueryDict
from django.utils import timezone

from access_control import projects
from access_control.models import Project, ProjectMembership
from declaration.models import Declaration
from execution_jobs import history, service
from execution_jobs.models import JobEvent, NativeJob
from tests.unit.test_native_job_pagination import listing  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def url(fixture):
    return fixture.url + "history/"


def fetch(fixture, **params):
    response = fixture.clients["developer"].get(url(fixture), params)
    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "no-store"
    return response.json()


def add(fixture, *, other=False, **fields):
    template = fixture.rows[0]
    project, dataset = template.project, template.dataset
    if other:
        project = Project.objects.create(name="Never disclose this project")
        dataset = Declaration.objects.create(name="Never disclose this dataset")
        projects.bind_dataset(dataset, project.pk)
    identifier = uuid.uuid4()
    return NativeJob.objects.create(id=identifier, project=project, dataset=dataset, actor=template.actor,
                                    actor_snapshot={}, authority={}, specification={"kind": service.KIND},
                                    request_sha256=hashlib.sha256(str(identifier).encode()).hexdigest(),
                                    **({"expires_at": timezone.now() + timedelta(hours=1)} | fields))


@pytest.mark.parametrize("role", ["developer", "reviewer", "admin"])
def test_all_read_roles_get_only_current_dataset_metadata(listing, role, monkeypatch):
    hidden = add(listing, other=True, result={"secret": "never load"})
    NativeJob.objects.filter(pk=listing.rows[0].pk).update(result={"secret": "never load"}, specification={"kind": service.KIND, "secret": "never load"})
    monkeypatch.setattr(NativeJob, "from_db", lambda *a, **k: pytest.fail("full job including result fetched"))
    response = listing.clients[role].get(url(listing))
    assert response.status_code == 200
    value = response.json()
    assert value["read_only"] is True and len(value["jobs"]) == 50
    assert value["queue"]["states"]["queued"] == 53
    assert str(hidden.pk) not in json.dumps(value) and "never load" not in json.dumps(value)
    assert all(set(j) == {"id", "created_at", "state", "kind", "attempts", "reason_code"} for j in value["jobs"])


@pytest.mark.parametrize("role", ["anonymous", "outsider"])
def test_access_denial_precedes_job_queries_or_cursor_diagnostics(listing, role, monkeypatch):
    monkeypatch.setattr(NativeJob.objects, "filter", lambda *a, **k: pytest.fail("unauthorized metadata query"))
    response = listing.clients[role].get(url(listing), {"cursor": "invalid"})
    assert response.status_code == 403 and "queue" not in response.json()


def test_both_directions_and_timestamp_ties_remain_bounded_without_duplicates(listing):
    NativeJob.objects.all().update(created_at=listing.rows[0].created_at)
    for _ in range(60):
        add(listing, created_at=listing.rows[0].created_at)
    expected = [str(pk) for pk in NativeJob.objects.order_by("-created_at", "-pk").values_list("pk", flat=True)]
    first = fetch(listing)
    second = fetch(listing, cursor=first["next_cursor"])
    third = fetch(listing, cursor=second["next_cursor"])
    assert [len(v["jobs"]) for v in [first, second, third]] == [50, 50, 13]
    assert [j["id"] for v in [first, second, third] for j in v["jobs"]] == expected
    assert first["previous_cursor"] is None and third["next_cursor"] is None
    back = fetch(listing, cursor=third["previous_cursor"])
    assert back["jobs"] == second["jobs"]
    assert fetch(listing, cursor=back["previous_cursor"])["jobs"] == first["jobs"]


def test_new_submissions_do_not_shift_an_existing_navigation(listing):
    first = fetch(listing)
    added = add(listing)
    second = fetch(listing, cursor=first["next_cursor"])
    assert len(second["jobs"]) == 3 and second["history_cutoff"] == first["history_cutoff"]
    assert str(added.pk) not in [j["id"] for j in first["jobs"] + second["jobs"]]
    assert fetch(listing)["jobs"][0]["id"] == str(added.pk)
    assert second["queue"]["states"]["queued"] == 54  # observations are current, not the history cutoff


@pytest.mark.parametrize("state", history.STATES)
def test_state_filters_and_unfiltered_queue_counts_are_distinct(listing, state):
    selected = add(listing, state=state)
    result = fetch(listing, state=state)
    assert all(j["state"] == state for j in result["jobs"])
    assert str(selected.pk) in [j["id"] for j in result["jobs"]]
    assert sum(result["queue"]["states"].values()) == 54


@pytest.mark.parametrize("kind", history.KINDS)
def test_every_supported_job_kind_can_be_filtered(listing, kind):
    row = listing.rows[-1]
    NativeJob.objects.filter(pk=row.pk).update(specification={"kind": kind}, state="failed")
    result = fetch(listing, kind=kind, state="failed")
    assert [j["id"] for j in result["jobs"]] == [str(row.pk)]


@pytest.mark.parametrize("params", [{"state": "unknown"}, {"kind": "expert_python"}, {"cursor": "a" * 2049}, {"offset": "1"}, {"limit": "1000000"}])
def test_bad_filters_or_unbounded_parameters_stop_before_storage(listing, monkeypatch, params):
    monkeypatch.setattr(NativeJob.objects, "filter", lambda *a, **k: pytest.fail("bad parameters reached storage"))
    assert listing.clients["developer"].get(url(listing), params).status_code == 400


def test_duplicate_parameters_are_rejected(listing):
    response = listing.clients["developer"].get(url(listing) + "?state=queued&state=failed")
    assert response.status_code == 400


@pytest.mark.parametrize("change", ["tamper", "actor", "dataset", "state", "kind", "expired"])
def test_cursor_is_authenticated_expiring_and_context_bound(listing, change, monkeypatch):
    token = fetch(listing)["next_cursor"]
    params = {"cursor": token}
    client, target = listing.clients["developer"], url(listing)
    if change == "tamper":
        params["cursor"] = token + "x"
    elif change == "actor":
        client = listing.clients["reviewer"]
    elif change == "dataset":
        dataset = Declaration.objects.create(name="Same-project different dataset")
        projects.bind_dataset(dataset, listing.rows[0].project_id)
        target = f"/api/jobs/datasets/{dataset.pk}/history/"
    elif change in {"state", "kind"}:
        params[change] = "queued" if change == "state" else service.KIND
    else:
        now = signing.time.time()
        monkeypatch.setattr(signing.time, "time", lambda: now + history.CURSOR_SECONDS + 1)
    response = client.get(target, params)
    assert response.status_code == 409
    assert response.json() == {"error_code": "job_history_cursor_invalid_or_expired"}


def test_revoked_membership_blocks_previously_valid_cursor(listing):
    token = fetch(listing)["next_cursor"]
    ProjectMembership.objects.filter(actor=listing.rows[0].actor).update(active=False)
    assert listing.clients["developer"].get(url(listing), {"cursor": token}).status_code == 403


def test_recheck_withholds_a_snapshot_when_authority_changes_during_observation(listing, monkeypatch):
    original = projects.recheck

    def revoke(scope, **kwargs):
        ProjectMembership.objects.filter(actor=listing.rows[0].actor).update(active=False)
        return original(scope, **kwargs)

    monkeypatch.setattr(projects, "recheck", revoke)
    response = listing.clients["developer"].get(url(listing))
    assert response.status_code == 403 and "queue" not in response.json()


def test_due_overdue_and_expired_signals_are_read_only_not_health_or_recovery(listing, monkeypatch):
    now = timezone.now()
    NativeJob.objects.all().update(next_dispatch=now - timedelta(seconds=1))
    add(listing, state="running", lease_until=now - timedelta(seconds=1), attempts=3)
    add(listing, state="cancel_requested", lease_until=None, expires_at=now - timedelta(seconds=1))
    # No execution endpoint, mutation, event or implicit lease recovery may be called.
    for name in ["claim", "execute", "reconcile", "dispatch", "cancel"]:
        if hasattr(service, name):
            monkeypatch.setattr(service, name, lambda *a, **k: pytest.fail("read executed queue work"))
    before = list(NativeJob.objects.order_by("pk").values())
    events = JobEvent.objects.count()
    result = fetch(listing, state="failed")
    signals = result["queue"]["signals"]
    assert signals["queued_due"] == 53 and signals["overdue_leases"] == 1
    assert signals["expired_requests"] == signals["missing_active_leases"] == signals["attempts_at_limit"] == 1
    assert signals["oldest_queued_seconds"] >= 53
    assert result["queue"]["live_service_health"] == "not_observed" and result["queue"]["recovery_authorized"] is False
    assert list(NativeJob.objects.order_by("pk").values()) == before and JobEvent.objects.count() == events


def test_empty_page_after_state_changes_requires_explicit_refresh(listing):
    first = fetch(listing, state="queued")
    NativeJob.objects.all().update(state="cancelled")
    value = fetch(listing, state="queued", cursor=first["next_cursor"])
    assert value["jobs"] == [] and value["restart_required"] is True
    assert value["previous_cursor"] is value["next_cursor"] is None


def test_disabled_execution_does_not_hide_retained_history(listing, settings):
    settings.DECLARAI_JOBS_ENABLED = False
    result = fetch(listing)
    assert result["jobs_enabled"] is False and len(result["jobs"]) == 50


def test_storage_outage_is_a_diagnostic_not_a_queue_health_claim(listing, monkeypatch):
    def unavailable(*a, **k):
        raise DatabaseError("do not leak connection credentials")

    monkeypatch.setattr(NativeJob.objects, "filter", unavailable)
    response = listing.clients["developer"].get(url(listing))
    assert response.status_code == 503 and response.json() == {"error_code": "job_storage_unavailable"}


def test_direct_read_rejects_post_like_or_unknown_query_fields(listing):
    with pytest.raises(ValueError):
        history.read(listing.rows[0].actor, listing.rows[0].dataset_id, QueryDict("action=recover"))
