"""Native job pagination refuses unsupported offsets before job storage access."""

import hashlib
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.test import Client
from django.utils import timezone

from access_control import projects
from access_control.models import Project, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.models import NativeJob

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def listing(django_user_model, settings):
    settings.DECLARAI_JOBS_ENABLED = True
    ProjectPolicy.objects.create()
    project = Project.objects.create(name="Job-list project")
    dataset = Declaration.objects.create(name="Job-list dataset")
    projects.bind_dataset(dataset, project.pk)
    clients, actors = {}, {}
    for role in ["developer", "reviewer", "admin", "outsider"]:
        actor = django_user_model.objects.create(username=role)
        if role != "outsider":
            ProjectMembership.objects.create(actor=actor, project=project, role=role)
        client = Client()
        client.force_login(actor)
        actors[role], clients[role] = actor, client
    clients["anonymous"] = Client()
    now = timezone.now()
    # Owned queue-summary metadata only: no model training, dispatch or scoring.
    rows = [NativeJob(
        id=uuid.UUID(int=i), project=project, dataset=dataset, actor=actors["developer"],
        actor_snapshot={}, authority={}, specification={"kind": service.KIND, "bundle_id": str(uuid.UUID(int=1000))},
        request_sha256=hashlib.sha256(str(i).encode()).hexdigest(), expires_at=now + timedelta(hours=1),
        created_at=now - timedelta(seconds=54 - i),
    ) for i in range(1, 54)]
    NativeJob.objects.bulk_create(rows)
    return SimpleNamespace(url=f"/api/jobs/datasets/{dataset.pk}/", clients=clients, rows=rows)


@pytest.mark.parametrize("value", [str(2**63), str(2**128), "9" * 256])
@pytest.mark.parametrize("role", ["developer", "reviewer", "admin"])
def test_oversized_offsets_are_static_request_errors_before_job_queries(listing, monkeypatch, value, role):
    response = listing.clients[role].get(listing.url, {"offset": value})
    assert response.status_code == 400 and response.json() == {"error_code": "job_request_invalid"}

    def forbidden(*args, **kwargs):
        raise AssertionError("unsupported offset reached job storage")

    monkeypatch.setattr(NativeJob.objects, "filter", forbidden)
    response = listing.clients[role].get(listing.url, {"offset": value})
    assert response.status_code == 400 and response.json() == {"error_code": "job_request_invalid"}


@pytest.mark.parametrize("value", ["-1", "1.5", "not-an-offset", "9" * 5000])
def test_existing_invalid_offset_diagnostics_remain(listing, monkeypatch, value):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid offset reached job storage")

    monkeypatch.setattr(NativeJob.objects, "filter", forbidden)
    response = listing.clients["developer"].get(listing.url, {"offset": value})
    assert response.status_code == 400 and response.json() == {"error_code": "job_request_invalid"}


@pytest.mark.parametrize("role", ["anonymous", "outsider"])
@pytest.mark.parametrize("value", [str(2**128), "not-an-offset"])
def test_denied_access_precedes_offset_diagnostics(listing, monkeypatch, role, value):
    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized listing reached job storage")

    monkeypatch.setattr(NativeJob.objects, "filter", forbidden)
    response = listing.clients[role].get(listing.url, {"offset": value})
    assert response.status_code == 403
    assert "jobs" not in response.json() and "total" not in response.json()


@pytest.mark.parametrize("value,start", [("0", 0), ("1", 1), ("50", 50), ("+50", 50), (" 50 ", 50), ("٥٠", 50), (str(2**63 - 1), 2**63 - 1)])
def test_supported_offsets_preserve_order_page_size_and_response(listing, value, start):
    response = listing.clients["reviewer"].get(listing.url, {"offset": value})
    assert response.status_code == 200
    result = response.json()
    expected = list(reversed(listing.rows))[start:start + 50]
    assert set(result) == {"jobs_enabled", "jobs", "total", "next_offset"}
    assert result["jobs_enabled"] is True and result["total"] == 53
    assert [row["id"] for row in result["jobs"]] == [str(row.pk) for row in expected]
    assert len(result["jobs"]) <= 50
    assert result["next_offset"] == (start + 50 if start + 50 < 53 else None)
    assert all(set(row) == {"id", "state", "kind", "bundle_id", "created_at"} for row in result["jobs"])


def test_absent_offset_still_selects_the_first_page(listing):
    response = listing.clients["developer"].get(listing.url)
    assert response.status_code == 200
    assert len(response.json()["jobs"]) == 50 and response.json()["next_offset"] == 50
