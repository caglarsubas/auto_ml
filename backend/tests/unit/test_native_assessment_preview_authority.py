"""A protected preview must retain live reviewer authority through materialization."""

import uuid

import pytest
from django.db import DatabaseError

from access_control import projects
from access_control.models import ProjectDataset, ProjectMembership
from execution_jobs import native_assessment as assessment, service
from execution_jobs.models import NativeAdoption, NativeAdoptionEvent, NativeJob, NativeProtectedInput
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import post, world  # noqa: F401
from tests.unit.test_native_protected_assessment import approve, candidate, proposal, seal  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def protected(candidate):  # noqa: F811
    sealed, _, _ = seal(candidate, approve(candidate, proposal(candidate)))
    return candidate, sealed["id"]


def snapshot():
    return [list(model.objects.order_by("pk").values()) for model in
            [NativeJob, NativeAdoption, NativeAdoptionEvent, NativeProtectedInput, HoldoutAccess]]


def late(monkeypatch, boundary, callback):
    observed = []
    if boundary == "runtime":
        original = service.runtime

        def runtime(kind):
            value = original(kind)
            if kind == assessment.KIND and not observed:
                observed.append(True)
                callback()
            return value

        monkeypatch.setattr(service, "runtime", runtime)
    else:
        original = assessment.digest

        def digest(value):
            result = original(value)
            if isinstance(value, dict) and value.get("kind") == assessment.KIND and not observed:
                observed.append(True)
                callback()
            return result

        monkeypatch.setattr(assessment, "digest", digest)
    return observed


def invoke(w, identifier, entry):
    if entry == "service":
        return assessment.preview(w.users["reviewer"], identifier)
    return post(w.clients["reviewer"], f"/api/native-protected-inputs/{identifier}/preview/", {})


@pytest.mark.parametrize("entry", ["service", "http"])
@pytest.mark.parametrize("boundary", ["runtime", "digest"])
@pytest.mark.parametrize("guard", ["actor", "membership", "binding"])
def test_late_revocation_withholds_complete_protected_preview(protected, monkeypatch, entry, boundary, guard):
    w, identifier = protected
    before = snapshot()

    def revoke():
        actor = w.users["reviewer"]
        if guard == "actor":
            type(actor).objects.filter(pk=actor.pk).update(is_active=False)
        elif guard == "membership":
            ProjectMembership.objects.filter(project=w.project, actor=actor).update(revision=uuid.uuid4())
        else:
            ProjectDataset.objects.filter(dataset_id=w.file_id).update(revision=uuid.uuid4())

    observed = late(monkeypatch, boundary, revoke)
    if entry == "service":
        with pytest.raises(projects.ProjectDenied):
            invoke(w, identifier, entry)
    else:
        response = invoke(w, identifier, entry)
        assert response.status_code == 403, response.content
        assert b"input_metadata" not in response.content and b"assessment_sha256" not in response.content
    assert observed == [True]
    assert snapshot() == before


@pytest.mark.parametrize("entry", ["service", "http"])
@pytest.mark.parametrize("boundary", ["runtime", "digest"])
def test_late_authority_storage_failure_is_not_a_successful_preview(protected, monkeypatch, entry, boundary):
    w, identifier = protected
    before = snapshot()
    original = projects.recheck
    after = late(monkeypatch, boundary, lambda: None)

    def unavailable(scope, **kwargs):
        if after:
            raise DatabaseError("private SQL must stay private")
        return original(scope, **kwargs)

    monkeypatch.setattr(projects, "recheck", unavailable)
    if entry == "service":
        with pytest.raises(DatabaseError):
            invoke(w, identifier, entry)
    else:
        response = invoke(w, identifier, entry)
        assert response.status_code == 503, response.content
        assert b"private SQL" not in response.content and b"input_metadata" not in response.content
    assert after == [True]
    assert snapshot() == before


@pytest.mark.parametrize("entry", ["service", "http"])
def test_valid_previews_remain_read_only_and_reproduce_the_exact_plan(protected, entry):
    w, identifier = protected
    before = snapshot()
    values = []
    for _ in range(2):
        value = invoke(w, identifier, entry)
        if entry == "http":
            assert value.status_code == 200, value.content
            value = value.json()
        values.append(value)
    assert values[0] == values[1]
    prepared = {k: v for k, v in values[0].items() if k not in {"assessment_sha256", "input_metadata", "limitation"}}
    assert assessment.digest(prepared) == values[0]["assessment_sha256"]
    assert values[0]["input_metadata"]["confirmatory"] is False
    assert values[0]["input_metadata"]["upstream_history"] == "unverified"
    assert snapshot() == before
