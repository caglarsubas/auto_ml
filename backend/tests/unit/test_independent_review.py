"""Exact technical decisions retain custody, evidence and independent authority."""

import copy
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.db.models import ProtectedError
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from access_control import projects
from access_control.models import ProjectMembership
from deployment import offline_reproduce
from deployment.models import PackageReviewEvent
from execution_jobs import service
from execution_jobs.models import NativeJob, NativeProtectedInput
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import post, world  # noqa: F401
from tests.unit.test_native_protected_assessment import approve, candidate, proposal, queued, seal  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def native_evidence(w):
    adoption = approve(w, proposal(w))
    protected, raw, _ = seal(w, adoption)
    identifier = queued(w, protected)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "succeeded", job.reason_code
    download = w.clients["reviewer"].get(f"/api/jobs/{identifier}/reproduction/?sha256={job.result_sha256}")
    assert download.status_code == 200, download.content
    digest = download["X-DeclarAI-Export-SHA256"]
    manifest = w.root / "exact-manifest.json"
    outcomes = w.root / "separately-held.csv"
    manifest.write_bytes(download.content)
    outcomes.write_bytes(raw)
    report = offline_reproduce.reproduce(manifest, digest, w.path, outcomes)
    directory = f"/api/reviews/datasets/{w.file_id}/"
    opening = {"request_id": str(uuid.uuid4()), "assessment_job_id": identifier,
               "assessment_result_sha256": job.result_sha256, "manifest_sha256": digest}
    return job, report, directory, opening


def action(review, kind, **fields):
    return {"request_id": str(uuid.uuid4()), "expected_revision": review["revision"],
            "event_type": kind, "text": "Independent review fixture rationale.", **fields}


def success(response):
    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "no-store"
    snapshot = response.json()
    assert snapshot["production_use_approved"] is False
    return snapshot


def actor(w, django_user_model, name, role):
    user = django_user_model.objects.create(username=name)
    ProjectMembership.objects.create(project=w.project, actor=user, role=role)
    client = Client()
    client.force_login(user)
    return user, client


def test_exact_native_review_authority_exceptions_and_retention(candidate, django_user_model):
    w = candidate
    reviewer, approver = actor(w, django_user_model, "independent-technical-approver", "reviewer")
    contributor, contributor_client = actor(w, django_user_model, "finding-response-developer", "developer")
    job, report, directory, opening = native_evidence(w)
    assert post(w.clients["admin"], directory, opening).status_code == 403
    assert post(w.clients["outsider"], directory, opening).status_code == 403
    wrong = opening | {"manifest_sha256": "0" * 64}
    assert post(approver, directory, wrong).status_code == 409
    response = post(approver, directory, opening)
    review = success(response)
    assert review["bundle_id"] is None and review["assessment_job_id"] == str(job.pk)
    assert review["assessment_result_sha256"] == job.result_sha256 and not review["review_approved"]
    assert success(post(approver, directory, opening))["replayed"]
    row = w.clients["reviewer"].get(directory).json()["reviews"][0]
    assert (row["assessment_job_id"], row["manifest_sha256"]) == (str(job.pk), opening["manifest_sha256"])
    url = f"/api/reviews/{review['id']}/"

    review = success(post(approver, url, action(review, "finding", severity="major")))
    finding = review["findings"][0]["id"]
    unaddressed = post(approver, url, action(review, "approve", report=report))
    assert unaddressed.status_code == 409 and unaddressed.json()["error_code"] == "review_findings_unaddressed"
    review = success(post(contributor_client, url, action(review, "response", finding_id=finding)))
    projects.change_member(w.project, contributor, "reviewer")
    assert post(contributor_client, url, action(review, "resolve", finding_id=finding)).status_code == 403

    assert post(approver, url, action(review, "exception", finding_id=finding, expires_at="2026-11-17")).status_code == 400
    expires = (timezone.now() + timedelta(days=5)).isoformat()
    review = success(post(w.clients["reviewer"], url, action(review, "exception", finding_id=finding, expires_at=expires)))
    assert review["findings"][0]["exception"]["status"] == "active"
    assert review["findings"][0]["state"] == "excepted" and not review["review_approved"]
    bad_report = report | {"production_use_approved": True}
    altered = post(approver, url, action(review, "approve", report=bad_report))
    assert altered.status_code == 409 and altered.json()["error_code"] == "review_reproduction_report_mismatch"

    approval = action(review, "approve", report=report)
    assert post(contributor_client, url, approval).status_code == 403
    with CaptureQueriesContext(connection) as queries:
        review = success(post(approver, url, approval))
        snapshot = success(w.clients["admin"].get(url))
    assert review["review_approved"] and snapshot["decision"]["status"] == "approved"
    assert snapshot["decision"]["actor"]["id"] == reviewer.pk
    payload = f'"{NativeProtectedInput._meta.db_table}"."payload"'
    assert not any(payload in query["sql"] for query in queries)
    assert success(post(approver, url, approval))["replayed"]
    assert post(approver, url, approval | {"text": "receipt tampered"}).status_code == 409
    with pytest.raises(ProtectedError):
        NativeJob.objects.get(pk=job.pk).delete()
    assert HoldoutAccess.objects.count() == 1

    projects.change_member(w.project, reviewer, "none")
    snapshot = success(w.clients["reviewer"].get(url))
    assert not snapshot["review_approved"]
    assert snapshot["decision"]["reason_code"] == "review_approver_authority_changed"
    assert snapshot["decision"]["decision_sha256"] == review["decision"]["decision_sha256"]
    assert snapshot["events"][-1]["details"]["report"] == report
    assert approver.get(url).status_code == 403
    projects.change_member(w.project, reviewer, "reviewer")
    assert success(approver.get(url))["decision"]["reason_code"] == "review_approver_authority_changed"
    assert PackageReviewEvent.objects.filter(review_id=review["id"]).count() == 5


def test_approval_invalidates_on_reopen_expiry_and_upstream_change(candidate):
    w = candidate
    job, report, directory, opening = native_evidence(w)
    reviewer = w.clients["reviewer"]
    review = success(post(reviewer, directory, opening))
    url = f"/api/reviews/{review['id']}/"
    review = success(post(reviewer, url, action(review, "finding", severity="minor")))
    finding = review["findings"][0]["id"]
    expiry = timezone.now() + timedelta(days=1)
    review = success(post(reviewer, url, action(review, "exception", finding_id=finding, expires_at=expiry.isoformat())))
    review = success(post(reviewer, url, action(review, "approve", report=report)))
    assert review["review_approved"]

    with patch("deployment.review_decisions.now", return_value=expiry + timedelta(seconds=1)):
        expired = success(reviewer.get(url))
    assert expired["decision"]["reason_code"] == "review_exception_unavailable"
    assert expired["findings"][0]["exception"]["status"] == "expired"
    assert expired["findings"][0]["state"] == "open" and not expired["review_approved"]

    review = success(post(reviewer, url, action(review, "reopen", finding_id=finding)))
    assert review["decision"]["reason_code"] == "review_discussion_changed" and not review["review_approved"]
    stale = action(review, "approve", report=report)
    review = success(post(reviewer, url, action(review, "resolve", finding_id=finding)))
    assert not review["review_approved"]
    assert post(reviewer, url, stale).json()["error_code"] == "review_revision_changed"
    review = success(post(reviewer, url, action(review, "approve", report=report)))
    revoked = success(post(reviewer, url, action(review, "revoke")))
    assert revoked["decision"]["status"] == "revoked" and not revoked["review_approved"]
    review = success(post(reviewer, url, action(revoked, "approve", report=report)))
    assert review["review_approved"]

    with patch("deployment.review_decisions.policy_sha256", return_value="a" * 64):
        assert success(reviewer.get(url))["decision"]["reason_code"] == "review_policy_changed"
    upstream = copy.deepcopy(job.result)
    upstream["n_assessed"] += 1
    NativeJob.objects.filter(pk=job.pk).update(result=upstream, result_sha256=service.digest(upstream))
    invalidated = success(reviewer.get(url))
    assert invalidated["decision"]["status"] == "invalidated" and not invalidated["review_approved"]
    assert invalidated["decision"]["reason_code"] == "review_upstream_evidence_changed"
    assert invalidated["decision"]["decision_sha256"] == review["decision"]["decision_sha256"]
    assert invalidated["events"] == review["events"]
    assert post(reviewer, url, action(invalidated, "finding", severity="minor")).status_code == 409
    assert HoldoutAccess.objects.count() == 1
