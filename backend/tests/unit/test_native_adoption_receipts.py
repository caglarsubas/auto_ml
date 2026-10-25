"""Final receipt authority with real training, custody, SQL and transactions.

The late hook observes the real protected-metadata query after its fetch; it
does not replace rows, candidate validation, authorization or receipt output.
"""
import uuid
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.db.models.query import QuerySet

from access_control import projects
from access_control.models import ProjectDataset, ProjectMembership
from execution_jobs import native_assessment as assessment
from execution_jobs.models import NativeAdoption, NativeAdoptionEvent, NativeJob, NativeProtectedInput
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import post, world  # noqa: F401
from tests.unit.test_native_protected_assessment import approve, candidate, proposal, seal  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
ACTIONS = ["propose", "approve", "revoke", "seal"]


def snapshot():
    return [list(model.objects.order_by("pk").values()) for model in
            [NativeJob, NativeAdoption, NativeAdoptionEvent, NativeProtectedInput, HoldoutAccess]]


def prepare(w, action, mode):
    role = "developer" if action == "propose" else "reviewer"
    p = proposal(w) if action != "propose" else None
    if action in {"revoke", "seal"}:
        p = approve(w, p)
    body = {"request_id": str(uuid.uuid4()), "rationale": "Exact private receipt under independent review."}
    raw = b"x,z,outcome\n" + b"11,2,bad\n12,4,good\n" * 30
    if action == "propose":
        body["training_result_sha256"] = w.trained.result_sha256
        url = f"/api/jobs/{w.trained.pk}/adoptions/"
    else:
        body["proposal_sha256"] = p["proposal_sha256"]
        url = f"/api/native-adoptions/{p['id']}/"
        if action == "seal":
            url += "protected-inputs/"
            body.update(assessment_as_of="2026-10-21T00:00:00+00:00", population_and_maturity_attested="true")
        else:
            body.update(expected_revision=p["revision"], action=action)
    request = SimpleNamespace(w=w, action=action, role=role, p=p, body=body, raw=raw, url=url)
    if mode == "replay":
        invoke(request, "service")
    return request


def invoke(r, entry):
    upload = SimpleUploadedFile("protected.csv", r.raw, content_type="text/csv")
    if entry == "http":
        if r.action == "seal":
            return r.w.clients[r.role].post(r.url, {**r.body, "file": upload})
        return post(r.w.clients[r.role], r.url, r.body)
    actor = r.w.users[r.role]
    if r.action == "propose":
        return assessment.propose(actor, r.w.trained.pk, r.body)
    if r.action == "seal":
        return assessment.seal(actor, r.p["id"], r.body, upload)
    return assessment.decide(actor, r.p["id"], r.body)


def late_fetch(monkeypatch, callback):
    original = QuerySet._fetch_all
    observed = []

    def fetch(query):
        original(query)
        deferred, is_defer = query.query.deferred_loading
        if (not observed and query.model is NativeProtectedInput and is_defer and "payload" in deferred
                and tuple(query.query.order_by) == ("created_at", "pk")):
            observed.append(True)
            callback()

    monkeypatch.setattr(QuerySet, "_fetch_all", fetch)
    return observed


def revoke(w, role, guard):
    actor = w.users[role]
    if guard == "actor":
        type(actor).objects.filter(pk=actor.pk).update(is_active=False)
    elif guard == "binding":
        ProjectDataset.objects.filter(dataset_id=w.file_id).update(revision=uuid.uuid4())
    else:
        ProjectMembership.objects.filter(project=w.project, actor=actor).update(revision=uuid.uuid4())


def assert_denied(call, entry, before, error=projects.ProjectDenied):
    if entry == "service":
        with pytest.raises(error):
            call()
    else:
        response = call()
        assert response.status_code == (503 if error is DatabaseError else 403), response.content
        assert b"Exact private receipt" not in response.content and b"private SQL" not in response.content
        assert b"protected_inputs" not in response.content and b"proposal_sha256" not in response.content
    assert snapshot() == before


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("mode", ["new", "replay"])
@pytest.mark.parametrize("entry", ["service", "http"])
@pytest.mark.parametrize("guard", ["actor", "binding", "membership"])
def test_late_revocation_blocks_receipts_and_rolls_back_new_writes(candidate, monkeypatch, action, mode, entry, guard):
    r = prepare(candidate, action, mode)
    before = snapshot()
    observed = late_fetch(monkeypatch, lambda: revoke(candidate, r.role, guard))
    assert_denied(lambda: invoke(r, entry), entry, before)
    assert observed == [True]


@pytest.mark.parametrize("entry", ["service", "detail", "list"])
@pytest.mark.parametrize("role", ["developer", "reviewer", "admin"])
@pytest.mark.parametrize("guard", ["actor", "binding", "membership"])
def test_late_revocation_blocks_private_reads(candidate, monkeypatch, entry, role, guard):
    w = candidate
    p = approve(w, proposal(w))
    seal(w, p)
    before = snapshot()
    observed = late_fetch(monkeypatch, lambda: revoke(w, role, guard))

    def read():
        if entry == "service":
            return assessment.serialize(w.users[role], NativeAdoption.objects.select_related("training_job").get(pk=p["id"]))
        url = f"/api/native-adoptions/{p['id']}/" if entry == "detail" else f"/api/jobs/{w.trained.pk}/adoptions/"
        return w.clients[role].get(url)

    assert_denied(read, entry, before)
    assert observed == [True]


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("mode", ["new", "replay"])
@pytest.mark.parametrize("entry", ["service", "http"])
def test_valid_receipts_preserve_status_evidence_and_replay(candidate, action, mode, entry):
    r = prepare(candidate, action, mode)
    before = snapshot()
    response = invoke(r, entry)
    value = response if entry == "service" else response.json()
    if entry == "http":
        assert response.status_code == (201 if action == "propose" and mode == "new" else 200)
    assert value["replayed"] is (mode == "replay")
    assert value["confirmatory"] is value["production_use_approved"] is False
    assert value["state"] == {"propose": "proposed", "approve": "accepted", "revoke": "revoked", "seal": "accepted"}[action]
    assert value["proposal"]["training_result_sha256"] == candidate.trained.result_sha256
    assert all(set(p) == {"id", "specification", "specification_sha256"} for p in value["protected_inputs"])
    after = snapshot()
    assert after[0] == before[0] and after[4] == before[4] == []
    if mode == "replay":
        assert after == before
    else:
        increments = [len(a) - len(b) for a, b in zip(after, before)]
        assert increments == {"propose": [0, 1, 0, 0, 0], "approve": [0, 0, 1, 0, 0],
                              "revoke": [0, 0, 1, 0, 0], "seal": [0, 0, 0, 1, 0]}[action]


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("mode", ["new", "replay"])
@pytest.mark.parametrize("entry", ["service", "http"])
@pytest.mark.parametrize("failure", ["final_authority", "materialization"])
def test_late_storage_failures_fail_closed_without_partial_writes(candidate, monkeypatch, action, mode, entry, failure):
    r = prepare(candidate, action, mode)
    before = snapshot()
    original = projects.recheck

    def unavailable(*args, **kwargs):
        raise DatabaseError("private SQL final authority unavailable")

    def late():
        if failure == "materialization":
            unavailable()
        monkeypatch.setattr(projects, "recheck", unavailable)

    observed = late_fetch(monkeypatch, late)
    assert_denied(lambda: invoke(r, entry), entry, before, DatabaseError)
    assert observed == [True]
    monkeypatch.setattr(projects, "recheck", original)
