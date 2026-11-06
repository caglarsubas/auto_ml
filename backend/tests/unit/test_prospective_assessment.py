"""Protected first-use assessment uses exact authority and shared outcome accounting."""

import copy
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from access_control import projects
from declaration.models import Declaration
from execution_jobs import legacy_execution, native_assessment as assessment, service
from execution_jobs.models import NativeJob, NativeProtectedInput
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import admission, post, queue, world  # noqa: F401
from tests.unit.test_native_protected_assessment import approve, proposal, queued

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def prospective(world, monkeypatch):
    options = copy.deepcopy(world.options)
    options["validation"] = {"strategy": "oot", "n_splits": 3, "group_column": "entity",
                             "date_column": "date", "label_end_column": "end"}
    body, _ = admission(world, options)
    identifier = queue(world, body)
    service.execute(identifier)
    world.trained = NativeJob.objects.get(pk=identifier)
    assert world.trained.state == "succeeded", world.trained.reason_code
    world.adoption = approve(world, proposal(world))
    start = (timezone.now() + timedelta(days=2)).date()
    dates = pd.date_range(start, periods=32)
    world.outcomes = pd.DataFrame({
        "x": range(32), "z": [1.0, 2.0] * 16, "outcome": ["good", "bad"] * 16,
        "entity": range(400, 432), "date": dates.strftime("%Y-%m-%d"),
        "end": (dates + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
    })
    world.as_of = (dates[-1] + pd.Timedelta(days=2)).tz_localize("UTC").to_pydatetime()
    # Move the assessment clock only. Authenticated session expiry stays real.
    monkeypatch.setattr(assessment, "timezone", SimpleNamespace(now=lambda: world.as_of + timedelta(hours=1)))
    return world


def seal(world, frame, *, as_of=None, opted_in=True):
    raw = frame.to_csv(index=False).encode()
    body = {
        "request_id": str(uuid.uuid4()), "proposal_sha256": world.adoption["proposal_sha256"],
        "rationale": "Synthetic temporal population in independent first-use custody.",
        "assessment_as_of": (as_of or world.as_of).isoformat(),
        "population_and_maturity_attested": "true",
        "file": SimpleUploadedFile("prospective.csv", raw),
    }
    if opted_in:
        body["prospective_first_use_attested"] = "true"
    response = world.clients["reviewer"].post(
        f"/api/native-adoptions/{world.adoption['id']}/protected-inputs/", body,
    )
    return response, raw, body["request_id"]


def test_first_use_is_published_once_and_reordered_overlap_is_exploratory(prospective, monkeypatch):
    w = prospective
    response, raw, identifier = seal(w, w.outcomes)
    assert response.status_code == 200, response.content
    sealed = next(p for p in response.json()["protected_inputs"] if p["id"] == identifier)
    assert sealed["specification"]["confirmation_protocol"]["version"] == assessment.PROSPECTIVE
    assert sealed["specification"]["confirmatory"] is False
    assert not HoldoutAccess.objects.exists()

    # Authenticated ordinary intake and both native execution boundaries fail
    # before decoding a byte-identical prospective payload as development data.
    upload = w.clients["developer"].post("/api/declaration/", {"file": SimpleUploadedFile("copy.csv", raw)})
    assert upload.status_code == 409 and upload.json()["error_code"] == "prospective_outcomes_protected"
    path = w.path.with_name("operator-copy.csv")
    path.write_bytes(raw)
    alias = Declaration.objects.create(file=str(path.relative_to(w.root)), name="operator fixture", original_name=path.name)
    projects.bind_dataset(alias, w.project.pk)
    options = w.trained.specification["training"]["options"]
    preview = post(w.clients["developer"], f"/api/jobs/datasets/{alias.pk}/training-input/", options)
    assert preview.status_code == 409 and preview.json()["error_code"] == "job_prospective_outcomes_protected"
    with pytest.raises(service.JobConflict, match="prospective_outcomes_protected"):
        legacy_execution.training_files(w.users["developer"], alias.pk, {"processed_file": alias.file.name})
    assert not HoldoutAccess.objects.exists()

    real_parse = assessment.training_search.parsed_frame

    def check_reservation(payload):
        if payload == raw:
            receipt = HoldoutAccess.objects.get(dataset_sha256=sealed["specification"]["input_sha256"])
            assert receipt.actor_id == w.users["reviewer"].pk
            assert receipt.attempt_state == "started" and receipt.evidence_status == "exploratory"
        return real_parse(payload)

    monkeypatch.setattr(assessment.training_search, "parsed_frame", check_reservation)
    job_id = queued(w, sealed)
    service.execute(job_id)
    service.execute(job_id)
    first = NativeJob.objects.get(pk=job_id)
    assert first.state == "succeeded", first.reason_code
    assert first.result["evidence_status"] == "confirmatory"
    assert first.result["confirmation_reason"] == "first_prospective_assessment_completed"
    assert first.result["confirmatory"] and not first.result["production_use_approved"]
    assert HoldoutAccess.objects.get().evidence_status == "confirmatory"
    assert not set(first.result).intersection({"labels", "payload", "scores", "model_json"})
    assert first.result["training_result_sha256"] == w.trained.result_sha256
    assert first.result["approval_event_id"] == w.adoption["events"][-1]["id"]

    response, _, other = seal(w, w.outcomes.iloc[::-1])
    assert response.status_code == 200, response.content
    second = queued(w, {"id": other})
    service.execute(second)
    result = NativeJob.objects.get(pk=second).result
    assert not result["confirmatory"] and result["confirmation_reason"] == "prior_overlapping_project_access"
    assert HoldoutAccess.objects.count() == 2
    assert HoldoutAccess.objects.filter(evidence_status="confirmatory").count() == 1


def test_confirmation_requires_pre_prediction_approval_and_maturity(prospective):
    w = prospective
    historic = w.outcomes.assign(date="2024-01-01", end="2024-01-02")
    response, _, _ = seal(w, historic)
    assert response.status_code == 409
    assert response.json()["error_code"] == "native_confirmation_candidate_not_frozen_before_prediction"
    response, _, _ = seal(w, w.outcomes, as_of=w.as_of - timedelta(days=15))
    assert response.status_code == 409 and response.json()["error_code"] == "native_confirmation_outcomes_not_mature"
    response, _, _ = seal(w, w.outcomes, as_of=w.as_of + timedelta(hours=2))
    assert response.status_code == 409 and response.json()["error_code"] == "native_confirmation_outcomes_not_mature"
    assert not NativeProtectedInput.objects.exists() and not HoldoutAccess.objects.exists()
    response, _, sealed = seal(w, historic, opted_in=False)
    assert response.status_code == 200, response.content
    assert "confirmation_protocol" not in NativeProtectedInput.objects.get(pk=sealed).specification


def test_interrupted_access_cannot_be_retried_into_confirmation(prospective, monkeypatch):
    w = prospective
    response, raw, identifier = seal(w, w.outcomes)
    assert response.status_code == 200, response.content
    first = queued(w, {"id": identifier})
    real_parse = assessment.training_search.parsed_frame

    def interrupt(payload):
        if payload == raw:
            assert HoldoutAccess.objects.get().attempt_state == "started"
            raise ValueError("fixture interrupted after reservation")
        return real_parse(payload)

    with monkeypatch.context() as mocked:
        mocked.setattr(assessment.training_search, "parsed_frame", interrupt)
        service.execute(first)
    assert NativeJob.objects.get(pk=first).result is None
    failed = HoldoutAccess.objects.get()
    assert failed.attempt_state == "failed" and failed.evidence_status == "exploratory"
    second = queued(w, {"id": identifier})
    service.execute(second)
    result = NativeJob.objects.get(pk=second).result
    assert result["confirmation_reason"] == "prior_exact_input_access" and not result["confirmatory"]
    assert not HoldoutAccess.objects.filter(evidence_status="confirmatory").exists()
