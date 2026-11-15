"""Qualify current applicability without rewriting the inspected evidence."""

import copy
import uuid
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from access_control import projects
from declaration.models import Declaration
from execution_jobs import native_assessment as assessment, service
from execution_jobs.models import NativeAdoptionEvent, NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import admission, post, queue, world  # noqa: F401
from tests.unit.test_native_protected_assessment import approve, proposal, queued
from tests.unit.test_prospective_assessment import prospective, seal  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def _assess(w, protected_id):
    identifier = queued(w, {"id": protected_id})
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "succeeded", job.reason_code
    return job


def test_confirmation_receipt_keeps_history_but_checks_live_approval_policy_and_access(prospective):  # noqa: F811
    w = prospective
    response, _, protected_id = seal(w, w.outcomes)
    assert response.status_code == 200, response.content
    job = _assess(w, protected_id)
    original = job.result
    assert original["confirmatory"] is True
    access = HoldoutAccess.objects.get(pk=original["outcome_access_id"])
    assert original["assessment_sha256"] == service.digest({
        key: value for key, value in job.specification.items() if key != "assessment_sha256"
    })
    assert original["assessment_policy_sha256"] == service.digest(original["assessment_policy"])
    assert original["approval_sha256"] == w.adoption["events"][0]["payload_sha256"]
    assert original["prediction_contract_sha256"] == service.digest(original["prediction_contract"])
    assert original["metric_sha256"] == service.digest(original["metric"])
    assert original["training_specification_sha256"] == service.digest(w.trained.specification)
    assert access.parameters["reuse_adjudication"] == original["reuse_adjudication"]
    assert access.parameters["reuse_adjudication_sha256"] == service.digest(original["reuse_adjudication"])
    url = f"/api/jobs/{job.pk}/"

    def read(status, reason):
        with CaptureQueriesContext(connection) as queries:
            receipt = w.clients["developer"].get(url)
        assert all('"execution_jobs_nativeprotectedinput"."payload"' not in row["sql"] for row in queries)
        assert receipt.status_code == 200, receipt.content
        body = receipt.json()
        assert body["result"] == original and body["result_sha256"] == job.result_sha256
        assert body["assessment_applicability"] == {
            "status": status, "confirmation_usable": status == "current", "reason_code": reason,
            "assessment_sha256": job.specification["assessment_sha256"],
        }

    read("current", "first_prospective_assessment_completed")
    with patch.object(assessment, "ASSESSMENT_POLICY", {**assessment.ASSESSMENT_POLICY, "version": "changed"}):
        read("invalidated", "native_assessment_policy_changed")
    HoldoutAccess.objects.filter(pk=access.pk).update(parameters={**access.parameters, "reuse_adjudication_sha256": "0" * 64})
    read("invalidated", "job_assessment_receipt_changed")
    HoldoutAccess.objects.filter(pk=access.pk).update(parameters=access.parameters)
    approval = NativeAdoptionEvent.objects.get(pk=original["approval_event_id"])
    changed = {**approval.payload, "rationale": "Changed despite retaining the same approval identifier."}
    NativeAdoptionEvent.objects.filter(pk=approval.pk).update(payload=changed, payload_sha256=service.digest(changed))
    read("invalidated", "native_assessment_plan_changed")
    NativeAdoptionEvent.objects.filter(pk=approval.pk).update(payload=approval.payload, payload_sha256=approval.payload_sha256)
    revoke = post(w.clients["reviewer"], f"/api/native-adoptions/{w.adoption['id']}/", {
        "request_id": str(uuid.uuid4()), "expected_revision": 1,
        "proposal_sha256": w.adoption["proposal_sha256"], "action": "revoke", "rationale": "Withdraw this approval.",
    })
    assert revoke.status_code == 200, revoke.content
    read("invalidated", "native_adoption_not_approved")
    access.refresh_from_db()
    assert access.evidence_status == "confirmatory"


def test_changed_candidate_and_reordered_outcomes_have_distinct_exploratory_evidence(prospective):  # noqa: F811
    w = prospective
    response, _, protected_id = seal(w, w.outcomes)
    assert response.status_code == 200, response.content
    first = _assess(w, protected_id)
    assert first.result["confirmatory"] is True

    options = copy.deepcopy(w.trained.specification["training"]["options"])
    options["features"] = ["x"]
    path = w.path.with_name("candidate-two.csv")
    path.write_bytes(w.path.read_bytes())
    relative = str(path.relative_to(w.root))
    dataset = Declaration.objects.create(file=relative, name=path.name, original_name=path.name)
    projects.bind_dataset(dataset, w.project.pk)
    w.file_id = dataset.pk
    body, _ = admission(w, options)
    identifier = queue(w, body)
    service.execute(identifier)
    w.trained = NativeJob.objects.get(pk=identifier)
    assert w.trained.state == "succeeded", w.trained.reason_code
    w.adoption = approve(w, proposal(w))
    response, _, protected_id = seal(w, w.outcomes.iloc[::-1].drop(columns="z"))
    assert response.status_code == 200, response.content
    second = _assess(w, protected_id)
    receipt = second.result
    assert not receipt["confirmatory"] and receipt["evidence_status"] == "exploratory"
    assert receipt["confirmation_reason"] == "prior_overlapping_project_access"
    assert receipt["assessment_sha256"] != first.result["assessment_sha256"]
    assert receipt["candidate_export_sha256"] != first.result["candidate_export_sha256"]
    assert receipt["input_sha256"] != first.result["input_sha256"]
    reuse, = receipt["reuse_adjudication"]["records"]
    assert reuse["access_id"] == first.result["outcome_access_id"]
    assert reuse["actor"]["id"] == w.users["reviewer"].pk
    assert reuse["relation"] == "overlapping_project"
    assert HoldoutAccess.objects.filter(evidence_status="confirmatory").count() == 1
