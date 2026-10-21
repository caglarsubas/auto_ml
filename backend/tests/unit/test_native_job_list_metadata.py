"""Legacy native-job lists fetch only bounded metadata and never cache it."""

import uuid
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection
from django.test.utils import CaptureQueriesContext

from access_control import projects
from access_control.models import Project
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.models import NativeJob
from tests.unit.test_native_job_pagination import listing  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("role", ["developer", "reviewer", "admin"])
@pytest.mark.parametrize("offset", [0, 50, 2**63 - 1])
def test_list_uses_only_project_scoped_metadata_without_job_materialization(listing, role, offset):
    # Whole rows may contain native model state, outcomes and request payloads.
    NativeJob.objects.all().update(result={"private-model": "x" * 32768}, authority={"secret": "do-not-fetch"})
    with patch.object(NativeJob, "from_db", side_effect=AssertionError("full job materialized")):
        with CaptureQueriesContext(connection) as queries:
            response = listing.clients[role].get(listing.url, {"offset": str(offset)})
    assert response.status_code == 200
    value = response.json()
    expected = list(reversed(listing.rows))[offset:offset + 50]
    assert value["total"] == 53 and value["next_offset"] == (offset + 50 if offset + 50 < 53 else None)
    assert [r["id"] for r in value["jobs"]] == [str(j.pk) for j in expected]
    assert all(set(r) == {"id", "state", "kind", "bundle_id", "created_at"} for r in value["jobs"])
    job_sql = [q["sql"] for q in queries if '"execution_jobs_nativejob"' in q["sql"]]
    assert job_sql
    assert not any(f'"{field}"' in sql for sql in job_sql for field in ["result", "authority", "actor_snapshot", "request_sha256", "result_sha256"])
    assert "private-model" not in response.content.decode() and "do-not-fetch" not in response.content.decode()
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("kind", ["package_integrity_v1", "native_csv_scoring_v1", "native_numeric_training_search_v1",
                                  "native_training_scoring_v1", "native_protected_assessment_v1"])
def test_list_preserves_supported_kind_optional_bundle_and_creation_values(listing, kind):
    job = listing.rows[-1]
    NativeJob.objects.filter(pk=job.pk).update(specification={"kind": kind, "private-input": "not-projected"})
    response = listing.clients["reviewer"].get(listing.url)
    assert response.status_code == 200
    first = response.json()["jobs"][0]
    assert first == {"id": str(job.pk), "state": job.state, "kind": kind, "bundle_id": None,
                     "created_at": job.created_at.isoformat()}
    assert "not-projected" not in response.content.decode()


@pytest.mark.parametrize("role", ["outsider", "anonymous"])
def test_denied_list_is_not_cached_and_does_not_read_job_storage(listing, monkeypatch, role):
    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized job storage read")
    monkeypatch.setattr(NativeJob.objects, "filter", forbidden)
    response = listing.clients[role].get(listing.url)
    assert response.status_code == 403 and "jobs" not in response.json()
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("offset", ["-1", "invalid", str(2**63), "9" * 5000], ids=["negative", "text", "oversized", "digit_limit"])
def test_invalid_offset_failure_is_not_cached(listing, offset):
    response = listing.clients["developer"].get(listing.url, {"offset": offset})
    assert response.status_code == 400 and response.json() == {"error_code": "job_request_invalid"}
    assert response["Cache-Control"] == "no-store"


def test_database_failure_has_safe_uncached_diagnostics(listing, monkeypatch):
    def unavailable(*args, **kwargs):
        raise DatabaseError("private driver connection details")
    monkeypatch.setattr(NativeJob.objects, "filter", unavailable)
    response = listing.clients["developer"].get(listing.url)
    assert response.status_code == 503 and response.json() == {"error_code": "job_storage_unavailable"}
    assert response["Cache-Control"] == "no-store"


def test_authority_recheck_still_blocks_a_prepared_metadata_page(listing, monkeypatch):
    def revoked(*args, **kwargs):
        raise projects.ProjectDenied("project_access_denied")
    monkeypatch.setattr(projects, "recheck", revoked)
    response = listing.clients["developer"].get(listing.url)
    assert response.status_code == 403 and "jobs" not in response.json()
    assert response["Cache-Control"] == "no-store"


def test_disabled_admission_does_not_hide_or_enable_historical_jobs(listing, settings):
    settings.DECLARAI_JOBS_ENABLED = False
    response = listing.clients["reviewer"].get(listing.url, {"offset": "50"})
    assert response.status_code == 200 and response.json()["jobs_enabled"] is False
    assert len(response.json()["jobs"]) == 3
    assert response["Cache-Control"] == "no-store"


def test_bundle_metadata_keeps_the_original_uuid_value(listing):
    response = listing.clients["reviewer"].get(listing.url)
    assert response.status_code == 200
    assert {r["bundle_id"] for r in response.json()["jobs"]} == {str(uuid.UUID(int=1000))}
    assert {r["kind"] for r in response.json()["jobs"]} == {service.KIND}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("scope", ["dataset", "project"])
def test_other_dataset_and_project_metadata_remain_excluded(listing, scope):
    original = listing.rows[0]
    project = original.project if scope == "dataset" else Project.objects.create(name="Other project")
    dataset = Declaration.objects.create(name="Other dataset")
    projects.bind_dataset(dataset, project.pk)
    foreign = NativeJob.objects.create(
        id=uuid.uuid4(), project=project, dataset=dataset, actor=original.actor,
        actor_snapshot={}, authority={}, specification={"kind": service.KIND},
        request_sha256="f" * 64, expires_at=original.expires_at,
    )
    response = listing.clients["reviewer"].get(listing.url)
    assert response.status_code == 200 and response.json()["total"] == 53
    assert str(foreign.pk) not in response.content.decode()
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("role,status", [("reviewer", 200), ("outsider", 403), ("anonymous", 403)])
def test_head_metadata_and_early_denials_are_not_cached(listing, role, status):
    response = listing.clients[role].head(listing.url)
    assert response.status_code == status and response.content == b""
    assert response["Cache-Control"] == "no-store"
