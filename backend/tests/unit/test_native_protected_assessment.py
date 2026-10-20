"""Real protected native assessment, independent adoption, custody and fencing."""

import copy
import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from access_control.models import ProjectMembership
from deployment import native_candidate
from execution_jobs import native_assessment as assessment, service
from execution_jobs.models import NativeAdoption, NativeAdoptionEvent, NativeJob, NativeProtectedInput
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import admission, post, queue, world  # noqa: F401
from tests.unit.test_governed_foundation import declaration

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def candidate(world):  # noqa: F811
    body, _ = admission(world)
    identifier = queue(world, body)
    service.execute(identifier)
    world.trained = NativeJob.objects.get(pk=identifier)
    assert world.trained.state == "succeeded"
    return world


def proposal(w):
    body = {
        "request_id": str(uuid.uuid4()),
        "training_result_sha256": w.trained.result_sha256,
        "rationale": "Freeze this exact development candidate before any protected input.",
    }
    response = post(w.clients["developer"], f"/api/jobs/{w.trained.pk}/adoptions/", body)
    assert response.status_code == 201, response.content
    replay = post(w.clients["developer"], f"/api/jobs/{w.trained.pk}/adoptions/", body)
    assert replay.status_code == 200 and replay.json()["replayed"]
    return response.json()


def approve(w, p):
    body = {
        "request_id": str(uuid.uuid4()),
        "expected_revision": p["revision"],
        "proposal_sha256": p["proposal_sha256"],
        "action": "approve",
        "rationale": "Independent inspection accepts this candidate only for protected assessment.",
    }
    response = post(w.clients["reviewer"], f"/api/native-adoptions/{p['id']}/", body)
    assert response.status_code == 200, response.content
    assert post(w.clients["reviewer"], f"/api/native-adoptions/{p['id']}/", body).json()["replayed"]
    return response.json()


def seal(w, p, frame=None, request_id=None):
    if frame is None:
        frame = pd.DataFrame(
            {"x": np.linspace(10, 14, 60), "z": [np.nan, 2.0, 4.0] * 20, "outcome": ["bad", "good"] * 30}
        )
    raw = frame.to_csv(index=False).encode()
    body = {
        "request_id": request_id or str(uuid.uuid4()),
        "proposal_sha256": p["proposal_sha256"],
        "rationale": "Independent reviewer attests population, disjoint identity and complete label maturity.",
        "assessment_as_of": "2026-10-21T00:00:00+00:00",
        "population_and_maturity_attested": "true",
        "file": SimpleUploadedFile("protected.csv", raw, content_type="text/csv"),
    }
    response = w.clients["reviewer"].post(f"/api/native-adoptions/{p['id']}/protected-inputs/", body)
    assert response.status_code == 200, response.content
    sealed = response.json()["protected_inputs"][-1]
    return sealed, raw, body


def queued(w, sealed):
    response = post(w.clients["reviewer"], f"/api/native-protected-inputs/{sealed['id']}/preview/", {})
    assert response.status_code == 200, response.content
    p = response.json()
    body = {
        "request_id": str(uuid.uuid4()),
        "kind": assessment.KIND,
        "protected_input_id": sealed["id"],
        "assessment_sha256": p["assessment_sha256"],
    }
    response = post(w.clients["reviewer"], f"/api/jobs/datasets/{w.file_id}/", body)
    assert response.status_code == 202, response.content
    assert post(w.clients["reviewer"], f"/api/jobs/datasets/{w.file_id}/", body).json()["replayed"]
    return response.json()["id"]


@pytest.mark.parametrize("task,positive", [("classification", "bad"), ("classification", "good"), ("regression", None)])
def test_actual_reviewed_adoption_protected_assessment_and_common_access_history(world, task, positive):  # noqa: F811
    w = world
    options = copy.deepcopy(w.options)
    options["business_understanding"] = declaration(task, positive)
    if task == "regression":
        w.frame["outcome"] = [10.0, 20.0] * 60
        w.frame.to_csv(w.path, index=False)
    body, _ = admission(w, options)
    identifier = queue(w, body)
    service.execute(identifier)
    w.trained = NativeJob.objects.get(pk=identifier)
    p = approve(w, proposal(w))
    assert p["state"] == "accepted" and p["usable"] and not p["production_use_approved"]
    held = pd.DataFrame(
        {
            "z": [np.nan, 1.0, 8.0] * 20,
            "x": np.linspace(9, 13, 60),
            "outcome": [10.0, 20.0] * 30 if task == "regression" else ["bad", "good"] * 30,
        }
    )
    sealed, raw, _ = seal(w, p, held)
    assert not HoldoutAccess.objects.exists()
    identifier = queued(w, sealed)
    spec = NativeJob.objects.get(pk=identifier).specification
    assert "payload" not in json.dumps(spec) and "outcome" not in spec
    original = assessment.training_search.parsed_frame

    def logged_before_parse(data):
        if data == raw:
            assert HoldoutAccess.objects.filter(parameters__job_id=identifier, attempt_state="started").exists()
        return original(data)

    with (
        patch.object(assessment.training_search, "parsed_frame", side_effect=logged_before_parse),
        patch("pickle.load", side_effect=AssertionError("pickle")),
    ):
        service.execute(identifier)
        service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "succeeded" and job.attempts == 1, job.reason_code
    assert job.result["prediction_contract"]["positive_class"] == positive
    assert job.result["candidate_adopted_for_assessment"] and job.result["final_holdout_accessed"]
    assert not job.result["confirmatory"] and job.result["evidence_status"] == "exploratory"
    assert not job.result["review_approved"] and not job.result["production_use_approved"]
    assert job.result["n_assessed"] == 60 and job.result["prior_related_accesses"] == 0
    assert set(job.result).isdisjoint({"scores", "labels", "model_json", "payload"})
    assert HoldoutAccess.objects.get().attempt_state == "completed"
    w.trained.refresh_from_db()
    assert not w.trained.result["model_adopted"] and not w.trained.result["final_holdout_accessed"]
    second = queued(w, sealed)
    service.execute(second)
    assert NativeJob.objects.get(pk=second).result["prior_related_accesses"] == 1
    assert HoldoutAccess.objects.count() == 2
    assert not (w.root / "modeling").exists() and not (w.root / "execution_runs").exists()
    # Authorized developers receive only aggregate evidence and metadata, never sealed labels.
    returned = w.clients["developer"].get(f"/api/native-adoptions/{p['id']}/").json()
    assert all(set(item) == {"id", "specification", "specification_sha256"} for item in returned["protected_inputs"])
    assert raw.decode() not in json.dumps(returned)
    assert w.clients["developer"].get(f"/api/jobs/{identifier}/").status_code == 200


@pytest.mark.parametrize("role", ["reviewer", "admin", "outsider", "anonymous"])
def test_proposal_requires_developer(candidate, role):
    w = candidate
    response = post(
        w.clients[role],
        f"/api/jobs/{w.trained.pk}/adoptions/",
        {"request_id": str(uuid.uuid4()), "training_result_sha256": w.trained.result_sha256, "rationale": "freeze"},
    )
    assert response.status_code == 403 and not NativeAdoption.objects.exists()


@pytest.mark.parametrize("role", ["developer", "admin", "outsider", "anonymous"])
def test_review_and_sealed_input_require_reviewer(candidate, role):
    w = candidate
    p = proposal(w)
    response = post(
        w.clients[role],
        f"/api/native-adoptions/{p['id']}/",
        {
            "request_id": str(uuid.uuid4()),
            "proposal_sha256": p["proposal_sha256"],
            "expected_revision": 0,
            "action": "approve",
            "rationale": "review",
        },
    )
    assert response.status_code == 403
    p = approve(w, p)
    sealed, _, _ = seal(w, p)
    assert post(w.clients[role], f"/api/native-protected-inputs/{sealed['id']}/preview/", {}).status_code == 403
    assert not HoldoutAccess.objects.exists()


def test_role_change_does_not_allow_self_review(candidate):
    w = candidate
    p = proposal(w)
    membership = ProjectMembership.objects.get(actor=w.users["developer"], project=w.project)
    membership.role = "reviewer"
    membership.save()
    response = post(
        w.clients["developer"],
        f"/api/native-adoptions/{p['id']}/",
        {
            "request_id": str(uuid.uuid4()),
            "proposal_sha256": p["proposal_sha256"],
            "expected_revision": 0,
            "action": "approve",
            "rationale": "self review forbidden",
        },
    )
    assert response.status_code == 409 and not NativeAdoptionEvent.objects.exists()


@pytest.mark.parametrize(
    "fault",
    [
        "proposal",
        "decision",
        "source",
        "model",
        "reviewer",
        "proposer",
        "revoked",
        "protected_spec",
        "protected_payload",
        "cancel",
        "runtime",
    ],
)
def test_stale_or_tampered_scope_never_publishes(candidate, fault):
    w = candidate
    p = approve(w, proposal(w))
    sealed, _, _ = seal(w, p)
    identifier = queued(w, sealed)
    if fault == "proposal":
        adoption = NativeAdoption.objects.get(pk=p["id"])
        adoption.proposal["rationale"] = "tampered"
        adoption.save()
    elif fault == "decision":
        event = NativeAdoptionEvent.objects.get(adoption_id=p["id"])
        event.payload["rationale"] = "tampered"
        event.save()
    elif fault == "source":
        w.path.write_text("changed\n")
    elif fault == "model":
        NativeJob.objects.filter(pk=w.trained.pk).update(result={"tampered": True})
    elif fault in {"reviewer", "proposer"}:
        ProjectMembership.objects.filter(
            actor=w.users["reviewer" if fault == "reviewer" else "developer"], project=w.project
        ).update(active=False)
    elif fault == "revoked":
        response = post(
            w.clients["reviewer"],
            f"/api/native-adoptions/{p['id']}/",
            {
                "request_id": str(uuid.uuid4()),
                "proposal_sha256": p["proposal_sha256"],
                "expected_revision": 1,
                "action": "revoke",
                "rationale": "withdraw scope",
            },
        )
        assert response.status_code == 200
    elif fault == "protected_spec":
        record = NativeProtectedInput.objects.get(pk=sealed["id"])
        record.specification["rows"] = 99
        record.save()
    elif fault == "protected_payload":
        NativeProtectedInput.objects.filter(pk=sealed["id"]).update(payload=b"tampered\n")
    elif fault == "cancel":
        service.cancel(w.users["reviewer"], identifier, {"action": "cancel"})
    else:
        job = NativeJob.objects.get(pk=identifier)
        job.specification["runtime"]["python"] = "different"
        job.save()
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state in {"blocked", "cancelled"} and job.result is None and job.result_sha256 == ""
    assert HoldoutAccess.objects.count() == (1 if fault == "protected_payload" else 0)


@pytest.mark.parametrize("fault", ["missing", "unknown", "single_class"])
def test_failed_outcome_interpretation_is_access_accounted(candidate, fault):
    w = candidate
    p = approve(w, proposal(w))
    frame = pd.DataFrame({"x": np.linspace(10, 15, 60), "z": [1.0] * 60, "outcome": ["bad", "good"] * 30})
    if fault == "missing":
        frame.loc[0, "outcome"] = None
    elif fault == "unknown":
        frame.loc[0, "outcome"] = "other"
    else:
        frame["outcome"] = "bad"
    sealed, _, _ = seal(w, p, frame)
    identifier = queued(w, sealed)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "blocked" and job.result is None
    assert HoldoutAccess.objects.get().attempt_state == "failed"


@pytest.mark.parametrize("strategy,fault", [("group", False), ("group", True), ("oot", False), ("oot", True)])
def test_actual_entity_time_and_outcome_window_protocol(world, strategy, fault):  # noqa: F811
    w = world
    options = copy.deepcopy(w.options)
    options["validation"] = {"strategy": strategy, "n_splits": 2, "group_column": "entity"}
    if strategy == "oot":
        options["validation"].update(date_column="date", label_end_column="end")
    body, _ = admission(w, options)
    identifier = queue(w, body)
    service.execute(identifier)
    w.trained = NativeJob.objects.get(pk=identifier)
    p = approve(w, proposal(w))
    frame = pd.DataFrame(
        {
            "x": np.linspace(9, 12, 60),
            "z": [2.0] * 60,
            "entity": np.arange(60) + (0 if fault and strategy == "group" else 1000),
            "outcome": ["good", "bad"] * 30,
        }
    )
    if strategy == "oot":
        frame["date"] = pd.date_range("2020-01-01" if fault else "2021-01-01", periods=60).astype(str)
        frame["end"] = pd.date_range("2020-01-02" if fault else "2021-01-02", periods=60).astype(str)
    sealed, _, _ = seal(w, p, frame)
    identifier = queued(w, sealed)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == ("blocked" if fault else "succeeded"), job.reason_code
    assert HoldoutAccess.objects.count() == 1


def test_lost_lease_and_late_revocation_cannot_publish_after_label_access(candidate):
    w = candidate
    p = approve(w, proposal(w))
    sealed, _, _ = seal(w, p)
    identifier = queued(w, sealed)
    job, token = service.claim(identifier)
    result = assessment.assess(job, lambda: None)
    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1))
    service.finish(identifier, token, "succeeded", result=result)
    assert NativeJob.objects.get(pk=identifier).result is None
    service.reconcile()
    job, token = service.claim(identifier)
    response = post(
        w.clients["reviewer"],
        f"/api/native-adoptions/{p['id']}/",
        {
            "request_id": str(uuid.uuid4()),
            "proposal_sha256": p["proposal_sha256"],
            "expected_revision": 1,
            "action": "revoke",
            "rationale": "stop before publication",
        },
    )
    assert response.status_code == 200
    service.finish(identifier, token, "succeeded", result=result)
    job.refresh_from_db()
    assert job.state == "blocked" and job.result is None and HoldoutAccess.objects.count() == 1


def test_sealed_bytes_never_enter_generic_dataset_or_export_routes(candidate):
    w = candidate
    p = approve(w, proposal(w))
    sealed, raw, body = seal(w, p)
    from declaration.models import Declaration

    assert Declaration.objects.count() == 1 and bytes(NativeProtectedInput.objects.get(pk=sealed["id"]).payload) == raw
    body["file"] = SimpleUploadedFile("protected.csv", raw, content_type="text/csv")
    assert w.clients["reviewer"].post(f"/api/native-adoptions/{p['id']}/protected-inputs/", body).json()["replayed"]
    assert w.clients["developer"].get(f"/api/native-protected-inputs/{sealed['id']}/").status_code in {403, 404}
    assert not HoldoutAccess.objects.exists()


def test_interrupted_access_is_retained_and_recovery_records_reuse(candidate):
    w = candidate
    p = approve(w, proposal(w))
    sealed, _, _ = seal(w, p)
    identifier = queued(w, sealed)
    with patch.object(
        assessment.training_search, "parsed_frame", side_effect=RuntimeError("fixture crash after reservation")
    ):
        with pytest.raises(RuntimeError):
            service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "running" and job.result is None
    assert HoldoutAccess.objects.get().attempt_state == "failed"
    stale = job.lease_token
    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1))
    service.reconcile()
    service.execute(identifier)
    job.refresh_from_db()
    assert job.state == "succeeded" and job.attempts == 2 and job.result["prior_related_accesses"] == 1
    assert HoldoutAccess.objects.count() == 2
    service.finish(identifier, stale, "succeeded", result={"stale": True})
    assert NativeJob.objects.get(pk=identifier).result_sha256 == job.result_sha256


def test_controller_never_loads_native_model_or_sealed_payload_for_preview(candidate):
    w = candidate
    with patch("xgboost.Booster", side_effect=AssertionError("model loaded in controller")):
        p = approve(w, proposal(w))
        sealed, _, _ = seal(w, p)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            identifier = queued(w, sealed)
        assert not HoldoutAccess.objects.exists()
        assert all('"execution_jobs_nativeprotectedinput"."payload"' not in q["sql"] for q in queries)
    service.execute(identifier)
    assert NativeJob.objects.get(pk=identifier).state == "succeeded"


def test_sealed_payload_has_explicit_writable_nonnullable_private_storage_contract():
    from execution_jobs.schema_presence import required_storage_contract

    assert required_storage_contract()["execution_jobs_nativeprotectedinput"]["payload"] == {
        "type": "bytea",
        "modifier": -1,
        "not_null": True,
        "primary_key": False,
        "unique_field": False,
        "unique_groups": [],
        "foreign_key": None,
        "identity": "",
    }
