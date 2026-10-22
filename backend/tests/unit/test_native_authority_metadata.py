"""Native resource routing never materializes payloads before project authority."""

import uuid
from contextlib import ExitStack, contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection
from django.http import QueryDict
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from access_control import project_http, projects
from access_control.models import Project, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs.models import NativeAdoption, NativeJob, NativeProtectedInput

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
MODELS = (NativeJob, NativeAdoption, NativeProtectedInput)
ROUTES = {
    "job-detail": ("GET", "job_id", "/api/jobs/{id}/"),
    "job-scores": ("GET", "job_id", "/api/jobs/{id}/scores/"),
    "job-candidate": ("GET", "job_id", "/api/jobs/{id}/candidate/"),
    "job-operational-handoff": ("GET", "job_id", "/api/jobs/{id}/operational-handoff/"),
    "job-candidate-input": ("POST", "job_id", "/api/jobs/{id}/scoring-input/"),
    "native-adoption-list": ("GET", "job_id", "/api/jobs/{id}/adoptions/"),
    "native-adoption": ("GET", "adoption_id", "/api/native-adoptions/{id}/"),
    "native-protected-input": ("POST", "adoption_id", "/api/native-adoptions/{id}/protected-inputs/"),
    "native-assessment-input": ("POST", "protected_id", "/api/native-protected-inputs/{id}/preview/"),
}
FAMILIES = ("job-detail", "native-adoption", "native-assessment-input")


@pytest.fixture
def routing(django_user_model):
    ProjectPolicy.objects.create()
    project = Project.objects.create(name="Owned routing project")
    dataset = Declaration.objects.create(name="Owned routing dataset")
    projects.bind_dataset(dataset, project.pk)
    users, clients = {}, {}
    for role in ("developer", "reviewer", "admin", "outsider"):
        actor = django_user_model.objects.create(username="routing-" + role)
        if role != "outsider":
            ProjectMembership.objects.create(actor=actor, project=project, role=role)
        client = Client()
        client.force_login(actor)
        users[role], clients[role] = actor, client
    job = NativeJob.objects.create(
        id=uuid.uuid4(), project=project, dataset=dataset, actor=users["developer"],
        actor_snapshot={"private-actor": "x" * 32768}, authority={"private-authority": "x" * 32768},
        specification={"private-request": "x" * 32768}, result={"private-model": "x" * 32768},
        request_sha256="a" * 64, expires_at=timezone.now() + timedelta(hours=1),
    )
    adoption = NativeAdoption.objects.create(
        id=uuid.uuid4(), training_job=job, proposal={"private-proposal": "x" * 32768},
        proposal_sha256="b" * 64, request_sha256="c" * 64,
    )
    protected = NativeProtectedInput.objects.create(
        id=uuid.uuid4(), adoption=adoption, specification={"private-seal": "x" * 32768},
        specification_sha256="d" * 64, request_sha256="e" * 64, payload=b"private-outcomes" * 4096,
    )
    return SimpleNamespace(project=project, dataset=dataset, users=users, clients=clients,
                           job_id=job.pk, adoption_id=adoption.pk, protected_id=protected.pk)


@contextmanager
def no_native_materialization():
    with ExitStack() as stack:
        for model in MODELS:
            stack.enter_context(patch.object(model, "from_db", side_effect=AssertionError("native payload row materialized before authorization")))
        yield


def assert_metadata_queries(queries, expected=1):
    native = [q["sql"] for q in queries if '"execution_jobs_' in q["sql"]]
    assert len(native) == expected
    forbidden = {"result", "specification", "authority", "actor_snapshot", "proposal", "payload", "request_sha256",
                 "result_sha256", "proposal_sha256", "specification_sha256", "created_at", "expires_at", "lease_until"}
    assert not any('"' + field + '"' in sql for sql in native for field in forbidden)


def request(w, name, role="developer", *, query="", identifier=None):
    method, key, path = ROUTES[name]
    identifier = identifier or getattr(w, key)
    url = path.format(id=identifier)
    req = SimpleNamespace(method=method, path=url, resolver_match=SimpleNamespace(url_name=name),
                          data={}, query_params=QueryDict(query), user=w.users[role])
    return req, SimpleNamespace(kwargs={key: identifier})


def assert_cache_policy(response, name):
    if ROUTES[name][0] == "GET":
        assert response["Cache-Control"] == "no-store"
    else:
        assert "Cache-Control" not in response


def http(w, name, role="outsider", *, identifier=None):
    method, key, path = ROUTES[name]
    url = path.format(id=identifier or getattr(w, key))
    return getattr(w.clients[role], method.lower())(url, data={}, content_type="application/json")


@pytest.mark.parametrize("name", ROUTES)
@pytest.mark.parametrize("role", ["developer", "reviewer", "admin"])
def test_authority_routes_exact_resource_using_only_dataset_metadata(routing, name, role):
    req, view = request(routing, name, role)
    with no_native_materialization(), CaptureQueriesContext(connection) as queries:
        if name == "job-candidate-input" and role != "developer":
            with pytest.raises(projects.ProjectDenied):
                project_http.authorize(req, view)
        else:
            resolved, scopes = project_http.authorize(req, view)
            assert resolved == name and len(scopes) == 1
            assert scopes[0]["file_id"] == routing.dataset.pk
            assert scopes[0]["project_id"] == str(routing.project.pk)
            assert scopes[0]["role"] == role
    assert_metadata_queries(queries)


@pytest.mark.parametrize("name", ROUTES)
def test_foreign_project_http_denial_does_not_fetch_native_payloads(routing, name):
    with no_native_materialization(), CaptureQueriesContext(connection) as queries:
        response = http(routing, name)
    assert response.status_code == 403
    assert_cache_policy(response, name)
    assert "private-" not in response.content.decode()
    assert_metadata_queries(queries)


@pytest.mark.parametrize("name", FAMILIES)
@pytest.mark.parametrize("role", ["developer", "reviewer", "admin"])
def test_missing_resource_keeps_safe_uncached_denial_and_metadata_only_sql(routing, name, role):
    with no_native_materialization(), CaptureQueriesContext(connection) as queries:
        response = http(routing, name, role, identifier=uuid.uuid4())
    assert response.status_code == 403
    assert_cache_policy(response, name)
    assert response.json()["error_code"] in {"job_unavailable", "native_adoption_unavailable"}
    assert_metadata_queries(queries)


@pytest.mark.parametrize("name", FAMILIES)
@pytest.mark.parametrize("selector", ["file_id", "project_id"])
def test_cross_resource_selectors_cannot_redirect_authority(routing, name, selector):
    foreign = Project.objects.create(name="Another authorized project")
    other = Declaration.objects.create(name="Another dataset")
    projects.bind_dataset(other, foreign.pk)
    ProjectMembership.objects.create(actor=routing.users["developer"], project=foreign, role="developer")
    query = selector + "=" + str(other.pk if selector == "file_id" else foreign.pk)
    req, view = request(routing, name, query=query)
    with no_native_materialization(), CaptureQueriesContext(connection) as queries:
        with pytest.raises(projects.ProjectDenied) as exc:
            project_http.authorize(req, view)
    assert exc.value.code in {"dataset_identifiers_must_agree", "pipeline_dataset_project_mismatch"}
    assert_metadata_queries(queries)


@pytest.mark.parametrize("name,model", list(zip(FAMILIES, MODELS)))
def test_projection_storage_failure_is_safe_uncached_authority_unavailability(routing, monkeypatch, name, model):
    def unavailable(*args, **kwargs):
        raise DatabaseError("private driver details")
    monkeypatch.setattr(model.objects, "values_list", unavailable)
    response = http(routing, name, "developer")
    assert response.status_code == 503
    assert_cache_policy(response, name)
    assert response.json()["error_code"] == "project_authority_unavailable"
    assert "private driver" not in response.content.decode()


@pytest.mark.parametrize("name", FAMILIES)
def test_revoked_membership_still_denies_without_payload_materialization(routing, name):
    ProjectMembership.objects.filter(actor=routing.users["developer"], project=routing.project).update(active=False)
    with no_native_materialization(), CaptureQueriesContext(connection) as queries:
        response = http(routing, name, "developer")
    assert response.status_code == 403
    assert_cache_policy(response, name)
    assert_metadata_queries(queries)
