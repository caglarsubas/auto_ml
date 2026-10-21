"""Native HTTP reads never retain private results or denied evidence in caches."""

import json
import uuid
from unittest.mock import patch

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, connection
from django.test.utils import CaptureQueriesContext

from access_control.models import ProjectMembership
from deployment import native_candidate
from execution_jobs import service
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import admission, post, queue, world  # noqa: F401
from tests.unit.test_native_protected_assessment import approve, proposal, seal
from tests.unit.test_native_training_scoring import candidate, preview, submit  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]

READS = ["list", "history", "input", "detail", "scores", "candidate", "adoptions", "adoption", "handoff"]
POST_ONLY = ["training-input", "scoring-input", "protected-input", "assessment-input"]


def location(w, endpoint):
    job = getattr(w, "trained", None)
    job_id = job.pk if job else uuid.UUID(int=1)
    adoption_id = getattr(w, "adoption_id", uuid.UUID(int=2))
    urls = {
        "list": f"/api/jobs/datasets/{w.file_id}/",
        "history": f"/api/jobs/datasets/{w.file_id}/history/",
        "input": f"/api/jobs/datasets/{w.file_id}/input/",
        "detail": f"/api/jobs/{job_id}/",
        "candidate": f"/api/jobs/{job_id}/candidate/?sha256={job.result_sha256 if job else '0' * 64}",
        "scores": f"/api/jobs/{w.scored.pk if hasattr(w, 'scored') else job_id}/scores/?sha256={w.scored.result_sha256 if hasattr(w, 'scored') else '0' * 64}",
        "adoptions": f"/api/jobs/{job_id}/adoptions/",
        "adoption": f"/api/native-adoptions/{adoption_id}/",
        "handoff": f"/api/jobs/{job_id}/operational-handoff/?revision={job.revision if job else 0}",
        "training-input": f"/api/jobs/datasets/{w.file_id}/training-input/",
        "scoring-input": f"/api/jobs/{job_id}/scoring-input/",
        "protected-input": f"/api/native-adoptions/{adoption_id}/protected-inputs/",
        "assessment-input": f"/api/native-protected-inputs/{getattr(w, 'protected_id', uuid.UUID(int=3))}/preview/",
    }
    return urls[endpoint]


@pytest.fixture
def evidence(candidate):
    w = candidate
    identifier = submit(w, preview(w))
    service.execute(identifier)
    w.scored = NativeJob.objects.get(pk=identifier)
    assert w.scored.state == "succeeded"
    p = approve(w, proposal(w))
    w.adoption_id = p["id"]
    sealed, _, _ = seal(w, p)
    w.protected_id = sealed["id"]
    return w


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("endpoint", READS + POST_ONLY)
def test_early_authentication_denials_are_uncached_before_native_storage(world, endpoint, method):
    with CaptureQueriesContext(connection) as queries:
        response = getattr(world.clients["anonymous"], method)(location(world, endpoint))
    assert response.status_code == 403
    assert response.get("Cache-Control") == "no-store"
    assert not any('"execution_jobs_' in q["sql"] for q in queries)
    if method == "head":
        assert response.content == b""


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("role", ["developer", "reviewer", "admin"])
def test_actual_private_results_reviews_and_downloads_keep_payloads_and_never_cache(evidence, role, method):
    w = evidence
    before = (list(NativeJob.objects.values_list("id", "revision", "state", "result_sha256")), HoldoutAccess.objects.count())
    for endpoint in READS:
        response = getattr(w.clients[role], method)(location(w, endpoint))
        assert response.status_code == 200, (endpoint, response.content)
        assert response.get("Cache-Control") == "no-store", endpoint
        if method == "head":
            assert response.content == b""
        elif endpoint == "detail":
            assert response.json()["result"] == w.trained.result
        elif endpoint == "scores":
            assert response.content == service.csv_scoring.canonical_bytes(w.scored.result)
            assert response["X-DeclarAI-Receipt-SHA256"] == w.scored.result_sha256
            assert response["Content-Disposition"] == f'attachment; filename="scoring-{w.scored.pk}.json"'
        elif endpoint == "candidate":
            assert response["X-DeclarAI-Export-SHA256"] == native_candidate.sha(response.content)
            assert response["Content-Disposition"] == f'attachment; filename="candidate-{w.trained.pk}.json"'
            assert response["Access-Control-Expose-Headers"] == "X-DeclarAI-Export-SHA256"
        elif endpoint == "adoption":
            assert response.json()["state"] == "accepted"
            assert all(set(p) == {"id", "specification", "specification_sha256"} for p in response.json()["protected_inputs"])
    assert before == (list(NativeJob.objects.values_list("id", "revision", "state", "result_sha256")), HoldoutAccess.objects.count())


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("role", ["outsider", "revoked"])
def test_current_project_denials_never_return_cached_or_private_evidence(evidence, role, method):
    w = evidence
    if role == "revoked":
        ProjectMembership.objects.filter(actor=w.users["reviewer"], project=w.project).update(active=False)
    client = w.clients["reviewer" if role == "revoked" else role]
    for endpoint in READS:
        response = getattr(client, method)(location(w, endpoint))
        assert response.status_code == 403, endpoint
        assert response.get("Cache-Control") == "no-store", endpoint
        assert w.trained.result_sha256.encode() not in response.content
        assert w.scored.result_sha256.encode() not in response.content


FAILURES = {
    "list": "service.scope", "history": "service.scope", "input": "csv_scoring.prepare",
    "detail": "service.read", "scores": "service.scoring_receipt", "candidate": "training_scoring.export",
    "adoptions": "NativeJob.objects.get", "adoption": "native_assessment.NativeAdoption.objects.select_related",
    "handoff": "operational_handoff.read",
}


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("endpoint", READS)
def test_storage_failure_diagnostics_are_safe_and_uncached(evidence, endpoint, method):
    world = evidence
    target = ("execution_jobs." if endpoint == "handoff" else "execution_jobs.views.") + FAILURES[endpoint]
    with patch(target, side_effect=DatabaseError("private driver connection details")):
        response = getattr(world.clients["developer"], method)(location(world, endpoint))
    assert response.status_code == 503
    assert response.get("Cache-Control") == "no-store"
    if method == "get":
        if endpoint in {"adoptions", "adoption"}:
            assert response.json()["error_code"] == "project_authority_unavailable"
            assert "private driver" not in response.content.decode()
        else:
            assert response.json() == {"error_code": "job_storage_unavailable"}
    else:
        assert response.content == b""


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("endpoint", ["candidate", "scores"])
def test_rejected_download_digests_do_not_serve_or_cache_previous_evidence(evidence, endpoint, method):
    w = evidence
    url = location(w, endpoint).split("?")[0] + "?sha256=" + "0" * 64
    response = getattr(w.clients["reviewer"], method)(url)
    assert response.status_code == 409
    assert response.get("Cache-Control") == "no-store"
    assert "Content-Disposition" not in response and "X-DeclarAI-Export-SHA256" not in response
    assert "X-DeclarAI-Receipt-SHA256" not in response


def test_mutating_requests_keep_admission_replay_and_cancellation_semantics(world):
    body, _ = admission(world)
    response = post(world.clients["developer"], location(world, "list"), body)
    assert response.status_code == 202 and "Cache-Control" not in response
    identifier = response.json()["id"]
    replay = post(world.clients["developer"], location(world, "list"), body)
    assert replay.status_code == 200 and replay.json()["replayed"] and "Cache-Control" not in replay
    cancelled = post(world.clients["developer"], f"/api/jobs/{identifier}/", {"action": "cancel"})
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    assert "Cache-Control" not in cancelled and NativeJob.objects.count() == 1
    assert service.claim(identifier) is None and json.loads(cancelled.content)["result"] is None


@pytest.mark.parametrize("method", ["get", "head"])
def test_authenticated_unsupported_reads_are_uncached_without_creating_jobs(evidence, method):
    world = evidence
    before = list(NativeJob.objects.values_list("id", "revision"))
    for endpoint in POST_ONLY:
        response = getattr(world.clients["developer"], method)(location(world, endpoint))
        assert response.status_code == 405 and response.get("Cache-Control") == "no-store"
    assert list(NativeJob.objects.values_list("id", "revision")) == before


@pytest.mark.parametrize("method", ["get", "head"])
def test_job_or_review_disappearing_after_authorization_is_uncached(evidence, method):
    world = evidence
    for endpoint, target in [("detail", "service.read"), ("adoption", "native_assessment.serialize")]:
        with patch("execution_jobs.views." + target, side_effect=ObjectDoesNotExist):
            response = getattr(world.clients["reviewer"], method)(location(world, endpoint))
        assert response.status_code == 404 and response.get("Cache-Control") == "no-store"
        if method == "get":
            assert response.json() == {"error_code": "job_unavailable"}
