"""Real frozen legacy execution; fixed native state never loads in the parent."""

import copy
import json
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.utils import timezone

from execution_jobs import legacy_execution as legacy, service
from execution_jobs.models import NativeJob
from tests.unit import test_durable_training_search as native_fixtures

world = native_fixtures.world
post = native_fixtures.post

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def options(w):
    return {
        "file_id": w.file_id,
        "processed_file": str(w.path.relative_to(w.root)),
        "algorithm": "xgboost",
        "excluded_variables": ["entity", "date", "end"],
        "business_understanding": copy.deepcopy(w.options["business_understanding"]),
    }


def launch(w, operation, data):
    response = post(
        w.clients["developer"],
        f"/api/jobs/datasets/{w.file_id}/legacy-input/",
        {"operation": operation, "options": data},
    )
    assert response.status_code == 200, response.content
    preview = response.json()
    body = {
        **data,
        "execution_request": {k: preview[k] for k in ["plan_sha256", "inputs_sha256"]}
        | {"request_id": str(uuid.uuid4())},
    }
    path = (
        "/api/modeling/start/"
        if operation == "training"
        else "/api/modeling/" + ("sfs" if operation == "sfs" else "hyperparam") + "/start/"
    )
    queued = post(w.clients["developer"], path, body)
    assert queued.status_code == 202, queued.content
    return queued.json()["native_job_id"], body, path


def test_legacy_training_uses_immutable_native_candidate_before_any_selection(world):
    w = world
    identifier, body, path = launch(w, "training", options(w))
    replay = post(w.clients["developer"], path, body)
    assert replay.status_code == 200 and replay.json()["native_job_id"] == identifier
    with (
        patch("pickle.load", side_effect=AssertionError("Parent read fitted state")),
        patch("joblib.load", side_effect=AssertionError("Parent read fitted state")),
    ):
        service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "succeeded", list(job.events.values("event_type", "detail"))
    assert job.result["payload"]["model"]["task"] == "classification"
    assert job.result["files_sha256"] and job.result["files"]
    assert not (w.root / "modeling" / f"{w.file_id}_status.json").exists()
    assert not (w.root / "execution_runs").exists()
    result = w.clients["developer"].get(f"/api/modeling/status/{w.file_id}/").json()
    assert result["status"] == "ok" and result["immutable_candidate"] is True
    assert result["model_adopted"] is False
    assert result["review_approved"] is result["production_use_approved"] is False
    before = job.result_sha256
    service.execute(identifier)
    job.refresh_from_db()
    assert job.result_sha256 == before and job.attempts == 1
    (w.root / "legacy-test-source.json").write_text(json.dumps({"id": identifier}))


def test_mutation_after_preview_rejects_before_queueing(world):
    w = world
    data = options(w)
    preview = legacy.preview(w.users["developer"], w.file_id, "training", data)
    w.path.write_text(w.path.read_text() + "1,2,1,2020-01-01,2020-01-02,bad\n")
    with pytest.raises(service.JobConflict, match="plan_changed"):
        service.submit(
            w.users["developer"],
            w.file_id,
            {
                "kind": legacy.KIND,
                "operation": "training",
                "options": data,
                "plan_sha256": preview["plan_sha256"],
                "inputs_sha256": preview["inputs_sha256"],
                "request_id": str(uuid.uuid4()),
            },
        )
    assert not NativeJob.objects.exists()


@pytest.mark.parametrize("role", ["reviewer", "admin", "outsider", "anonymous"])
def test_legacy_launch_cannot_bypass_project_role(world, role):
    w = world
    response = post(
        w.clients[role],
        f"/api/jobs/datasets/{w.file_id}/legacy-input/",
        {"operation": "training", "options": options(w)},
    )
    assert response.status_code in (403, 404)
    assert not NativeJob.objects.exists()


def test_unreviewed_legacy_launch_never_starts_local_thread(world):
    with patch("modeling.views.threading.Thread", side_effect=AssertionError("Process-local launch")):
        response = world.clients["developer"].post(
            "/api/modeling/start/",
            json.dumps(options(world)),
            content_type="application/json",
            HTTP_X_DECLARAI_EXECUTION_PROTOCOL="native-reviewed-v1",
        )
    assert response.status_code == 409 and response.json()["error_code"] == "job_legacy_preview_required"
    assert not NativeJob.objects.exists()


def test_sfs_and_hpo_use_the_exact_native_source_and_keep_results_unselected(world):
    w = world
    identifier, _, _ = launch(w, "training", options(w))
    service.execute(identifier)
    trained = NativeJob.objects.get(pk=identifier)
    assert trained.state == "succeeded"
    source = {
        "file_id": w.file_id,
        "source_job_id": identifier,
        "source_result_sha256": trained.result_sha256,
        "execution_id": trained.result["payload"]["execution_id"],
        "cv_folds": 2,
        "n_jobs": 1,
    }
    for operation, extra in [
        ("sfs", {"methods": ["backward"], "stopping_criteria": {"min_features": 1}, "top_k": 1}),
        (
            "hpo",
            {
                "param_space": {"max_depth": {"type": "int", "min": 1, "max": 2, "enabled": True}},
                "fixed_params": {"n_estimators": 8},
                "n_iter": 2,
                "search_method": "random",
                "validation_curve_points": 2,
            },
        ),
    ]:
        projection = w.root / "modeling" / f"{w.file_id}_status.json"
        prior = projection.read_bytes() if projection.exists() else None
        job_id, _, _ = launch(w, operation, {**source, **extra})
        service.execute(job_id)
        job = NativeJob.objects.get(pk=job_id)
        assert job.state == "succeeded", list(job.events.values("event_type", "detail"))
        assert job.result["source"]["job_id"] == identifier and job.result["legacy_projection_updated"] is False
        assert (projection.read_bytes() if projection.exists() else None) == prior
        chosen = w.clients["developer"].get(f"/api/jobs/{job_id}/legacy-selection/")
        assert chosen.status_code == 200, chosen.content
        preview = chosen.json()
        assert preview["candidates"]
        candidate = preview["candidates"][-1]["execution_id"]
        request = {
            "request_id": str(uuid.uuid4()),
            "result_sha256": job.result_sha256,
            "execution_id": candidate,
            "expected_projection_sha256": preview["expected_projection_sha256"],
        }
        picked = post(w.clients["developer"], f"/api/jobs/{job_id}/legacy-selection/", request)
        assert picked.status_code == 200, picked.content
        assert picked.json()["currently_selected"] is True
        before = (w.root / "modeling" / f"{w.file_id}_status.json").read_bytes()
        replay = post(w.clients["developer"], f"/api/jobs/{job_id}/legacy-selection/", request)
        assert replay.status_code == 200 and replay.json()["replayed"] is True
        assert (w.root / "modeling" / f"{w.file_id}_status.json").read_bytes() == before
        job.refresh_from_db()
        assert job.result_sha256 == picked.json()["result_sha256"]


def test_worker_loss_requeues_with_new_lease_and_old_attempt_cannot_publish(world):
    w = world
    identifier, _, _ = launch(w, "training", options(w))
    job, old_token = service.claim(identifier)
    assert job.attempts == 1 and job.lease_until - timezone.now() < timedelta(seconds=181)
    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1))
    service.reconcile()
    job.refresh_from_db()
    assert job.state == "queued" and job.result is None
    # Recompute in a fresh child; retries have distinct scratch directories.
    service.execute(identifier)
    job.refresh_from_db()
    assert job.state == "succeeded" and job.attempts == 2
    original = job.result_sha256
    service.finish(identifier, old_token, "succeeded", result={"forged": True})
    job.refresh_from_db()
    assert job.result_sha256 == original and "forged" not in job.result


def test_shared_capacity_queued_cancel_and_request_reuse(world):
    w = world
    identifiers = [launch(w, "training", options(w))[0] for _ in range(3)]
    assert service.claim(identifiers[0]) and service.claim(identifiers[1])
    assert service.claim(identifiers[2]) is None
    reply = service.cancel(w.users["developer"], identifiers[2], {"action": "cancel"})
    assert reply["state"] == "cancelled" and reply["attempts"] == 0
    service.execute(identifiers[2])
    assert NativeJob.objects.get(pk=identifiers[2]).state == "cancelled"
    identifier, body, path = launch(w, "training", options(w))
    body["algorithm"] = "lightgbm"
    reused = post(w.clients["developer"], path, body)
    assert reused.status_code == 409 and reused.json()["error_code"] == "job_legacy_request_reused"
    assert NativeJob.objects.get(pk=identifier).attempts == 0


@pytest.mark.parametrize("fault", ["snapshot", "authority", "runtime", "malformed"])
def test_changed_queued_authority_or_inputs_never_fits_or_adopts(world, fault):
    from access_control.models import ProjectMembership

    w = world
    identifier, _, _ = launch(w, "training", options(w))
    job = NativeJob.objects.get(pk=identifier)
    if fault == "snapshot":
        frozen = legacy.job_root(identifier) / "inputs" / next(iter(job.specification["legacy"]["inputs"]))
        frozen.chmod(0o600)
        frozen.write_bytes(b"tampered")
    elif fault == "authority":
        ProjectMembership.objects.filter(project=w.project, actor=w.users["developer"]).update(role="reviewer")
    else:
        spec = copy.deepcopy(job.specification)
        if fault == "runtime":
            spec["runtime"]["native_child"]["expert_code"] = True
        else:
            spec["legacy"] = {"not": "a plan"}
        NativeJob.objects.filter(pk=identifier).update(specification=spec)
    service.execute(identifier)
    job.refresh_from_db()
    assert job.state == "blocked" and job.result is None
    assert not (w.root / "modeling" / f"{w.file_id}_status.json").exists()
    if fault in {"authority", "runtime", "malformed"}:
        assert job.attempts == 0


def test_live_cancellation_stops_real_child_and_keeps_durable_diagnostics(world, monkeypatch):
    from execution_jobs import legacy_process

    w = world
    identifier, _, _ = launch(w, "training", options(w))
    original = legacy_process.event
    children = []

    def cancel_after_child_binding(job_id, token, kind, detail):
        accepted = original(job_id, token, kind, detail)
        if kind == "legacy_child_started":
            children.append(detail)
            service.cancel(w.users["developer"], identifier, {"action": "cancel"})
        return accepted

    monkeypatch.setattr(legacy_process, "event", cancel_after_child_binding)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert children and job.state == "cancelled" and job.result is None
    assert not (w.root / "modeling" / f"{w.file_id}_status.json").exists()
    assert w.clients["reviewer"].get(f"/api/jobs/{identifier}/").json()["state"] == "cancelled"
    assert w.clients["outsider"].get(f"/api/jobs/{identifier}/").status_code in (403, 404)


def test_child_failure_is_correlatable_without_exception_values_or_rows(world):
    w = world
    data = options(w)
    # Semantically invalid target fails in the original scientific contract.
    data["business_understanding"]["target_contract"]["target_column"] = "secret-row-value-not-a-column"
    identifier, _, _ = launch(w, "training", data)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "blocked" and job.reason_code == "job_legacy_native_execution_failed"
    detail = job.events.get(event_type="legacy_failure").detail
    failure = detail["failure"]
    assert failure["trace_frames"] and failure["exception_type"] == "PredictionContractError"
    assert failure["operation_id"] == identifier
    assert "secret-row-value" not in json.dumps(detail)
    response = w.clients["developer"].get(f"/api/modeling/status/{w.file_id}/", {"job_id": identifier}).json()
    assert response["job_status"] == "error" and response["failure"] == failure


def test_selection_stale_pointer_tamper_and_lost_ack_are_fenced(world, monkeypatch):
    from execution_jobs import legacy_selection as selection

    w = world
    identifier, _, _ = launch(w, "training", options(w))
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    endpoint = f"/api/jobs/{identifier}/legacy-selection/"
    proposal = w.clients["developer"].get(endpoint).json()
    body = {
        "request_id": str(uuid.uuid4()),
        "result_sha256": job.result_sha256,
        "execution_id": proposal["candidates"][0]["execution_id"],
        "expected_projection_sha256": None,
    }
    for role in ("reviewer", "admin", "outsider", "anonymous"):
        assert post(w.clients[role], endpoint, body).status_code in (403, 404)
    original_record = service.record

    def lost_ack(row, kind, **kwargs):
        if kind == "legacy_selection_completed":
            raise OSError("lost database acknowledgement after pointer publication")
        return original_record(row, kind, **kwargs)

    with monkeypatch.context() as local:
        local.setattr(service, "record", lost_ack)
        with pytest.raises(OSError):
            selection.select(w.users["developer"], identifier, body)
    # Filesystem publication survived the rolled-back second DB transaction.
    published = (w.root / "modeling" / f"{w.file_id}_status.json").read_bytes()
    retry = selection.select(w.users["developer"], identifier, body)
    assert retry["currently_selected"] and not retry["replayed"]
    assert (w.root / "modeling" / f"{w.file_id}_status.json").read_bytes() == published
    stale = {**body, "request_id": str(uuid.uuid4())}
    assert post(w.clients["developer"], endpoint, stale).json()["error_code"] == "job_legacy_selection_base_changed"
    member = legacy.output_root(job) / f"execution_runs/{body['execution_id']}/modeling_status.json"
    member.chmod(0o600)
    member.write_bytes(b"tampered")
    assert w.clients["developer"].get(endpoint).json()["error_code"] == "job_legacy_selection_artifact_changed"
    job.refresh_from_db()
    assert job.result_sha256 == body["result_sha256"]


@pytest.mark.parametrize("name", ["../escape", "/tmp/out", "a/../out", "a//out", "a\\out", ".private/a", "a\x00b"])
def test_frozen_member_paths_reject_ambiguous_or_unsafe_names(name):
    with pytest.raises(service.JobConflict, match="path_invalid"):
        legacy.relative(name)


def test_assistant_execution_is_server_queued_and_exact_approval_goes_stale(world):
    from tests.unit.test_assistant_approvals import session
    from access_control.models import AssistantActionApproval

    w = world
    from django.contrib.auth import get_user_model

    actor, csrf_client = session(get_user_model(), "legacy-assistant")
    from access_control.models import ProjectMembership

    ProjectMembership.objects.create(project=w.project, actor=actor, role="developer")
    request = {"file_id": w.file_id, "action_type": "start_modeling", "payload": options(w), "source": "panel"}
    proposal = csrf_client.post("/api/ai-assistant/prepare-action/", request, format="json")
    assert proposal.status_code == 200, proposal.content
    envelope = proposal.json()
    selector = {key: envelope[key] for key in ("approval_id", "proposal_sha256")}
    assert envelope["budget"]["native_execution"]["seconds"] == 120
    assert csrf_client.post("/api/ai-assistant/approve-action/", selector, format="json").status_code == 200
    dispatched = csrf_client.post("/api/ai-assistant/execute-action/", {**request, **selector}, format="json")
    assert dispatched.status_code == 200, dispatched.content
    result = dispatched.json()
    assert result["native_job_started"] is True
    assert NativeJob.objects.get(pk=result["native_job_id"]).state == "queued"
    duplicate = csrf_client.post("/api/ai-assistant/execute-action/", {**request, **selector}, format="json")
    assert duplicate.status_code == 200 and duplicate.json()["native_job_id"] == result["native_job_id"]
    assert NativeJob.objects.count() == 1
    second = csrf_client.post("/api/ai-assistant/prepare-action/", request, format="json")
    assert second.status_code == 200, second.content
    binding = {key: second.json()[key] for key in selector}
    w.path.write_text(w.path.read_text().replace("good", "changed"))
    stale = csrf_client.post("/api/ai-assistant/approve-action/", binding, format="json")
    assert stale.status_code == 409
    assert AssistantActionApproval.objects.get(pk=binding["approval_id"]).state == "stale"
    assert NativeJob.objects.count() == 1


def test_cancelled_sfs_resumes_only_an_exact_recorded_checkpoint(world, monkeypatch):
    from execution_jobs import legacy_process

    w = world
    trained_id, _, _ = launch(w, "training", options(w))
    service.execute(trained_id)
    trained = NativeJob.objects.get(pk=trained_id)
    source = {
        "file_id": w.file_id,
        "source_job_id": trained_id,
        "source_result_sha256": trained.result_sha256,
        "execution_id": trained.result["payload"]["execution_id"],
        "cv_folds": 2,
        "n_jobs": 1,
        "methods": ["forward"],
        "top_k": 1,
    }
    identifier, _, _ = launch(w, "sfs", source)
    original = legacy_process.event

    def stopped(job_id, token, kind, detail):
        accepted = original(job_id, token, kind, detail)
        if kind == "legacy_child_started":
            service.cancel(w.users["developer"], identifier, {"action": "cancel"})
        return accepted

    with monkeypatch.context() as local:
        local.setattr(legacy_process, "event", stopped)
        service.execute(identifier)
    cancelled = NativeJob.objects.get(pk=identifier)
    assert cancelled.state == "cancelled"
    checkpoint = cancelled.events.get(event_type="legacy_checkpoint").detail
    assert checkpoint["source"]["job_id"] == trained_id
    with pytest.raises(service.JobConflict, match="checkpoint_required"):
        legacy.preview(w.users["developer"], w.file_id, "sfs", {**source, "resume": True})
    resume = {**source, "resume": True, "checkpoint_job_id": identifier, "checkpoint_sha256": checkpoint["sha256"]}
    resumed_id, _, _ = launch(w, "sfs", resume)
    service.execute(resumed_id)
    resumed = NativeJob.objects.get(pk=resumed_id)
    assert resumed.state == "succeeded", list(resumed.events.values("event_type", "detail"))
    assert resumed.specification["legacy"]["checkpoint"] == {"job_id": identifier, "sha256": checkpoint["sha256"]}
    assert resumed.result["source"]["result_sha256"] == trained.result_sha256
    assert cancelled.result is None
    with pytest.raises(service.JobConflict, match="checkpoint_changed"):
        legacy.preview(w.users["developer"], w.file_id, "sfs", {**resume, "checkpoint_sha256": "f" * 64})


def test_v1_http_contract_uses_durable_worker_and_preserves_versioned_search_evidence(world, monkeypatch):
    from execution_jobs import legacy_compatibility as compatibility

    w = world
    observed = []

    def worker_then_observe(actor, identifier):
        row = NativeJob.objects.get(pk=identifier)
        assert row.state == "queued" and row.result is None
        observed.append(identifier)
        service.execute(identifier)
        return service.read(actor, identifier)

    monkeypatch.setattr(compatibility, "wait", worker_then_observe)
    with patch("modeling.views.threading.Thread", side_effect=AssertionError("API started a numerical thread")):
        response = post(w.clients["developer"], "/api/modeling/start/", options(w))
    assert response.status_code == 200, response.content
    trained = response.json()
    assert len(observed) == 1 and trained["native_job_id"] == observed[0]
    assert trained["selected_for_development"] is True
    assert (w.root / "execution_runs" / trained["execution_id"] / "manifest.json").is_file()
    sfs = post(
        w.clients["developer"],
        "/api/modeling/sfs/start/",
        {
            "file_id": w.file_id,
            "execution_id": trained["execution_id"],
            "methods": ["forward"],
            "initial_features": ["x"],
            "top_k": 1,
            "cv_folds": 2,
            "stopping_criteria": {"min_features": 1, "max_features": 1},
        },
    )
    assert sfs.status_code == 200 and sfs.json()["status"] == "started", sfs.content
    service.execute(sfs.json()["native_job_id"])
    status = w.clients["developer"].get(f"/api/modeling/sfs/status/{w.file_id}/")
    assert status.status_code == 200 and status.json()["status"] == "completed", status.content
    search = NativeJob.objects.get(pk=sfs.json()["native_job_id"])
    new_execution = search.result["payload"]["forward_execution_id"]
    assert (w.root / "execution_runs" / new_execution / "manifest.json").is_file()
    history = w.clients["developer"].get(f"/api/modeling/sfs/{w.file_id}/history/")
    assert history.status_code == 200, history.content
    assert list((w.root / "modeling" / f"{w.file_id}_runs").glob("sfs_run_*.json"))
    resume = post(
        w.clients["developer"],
        "/api/modeling/sfs/start/",
        {
            "file_id": w.file_id,
            "execution_id": trained["execution_id"],
            "resume": True,
            "cv_folds": 3,
        },
    )
    assert resume.status_code == 409 and "Start a fresh search" in resume.json()["error"]
    # Search completion does not replace the selected initial training model.
    selected = w.clients["developer"].get(f"/api/modeling/status/{w.file_id}/").json()
    assert selected["execution_id"] == trained["execution_id"]


@pytest.mark.parametrize("invalid", [None, True, 123, [], {}, "not-a-job"])
def test_malformed_source_identifiers_fail_before_any_worker_or_state_read(world, invalid):
    response = post(
        world.clients["developer"],
        f"/api/jobs/datasets/{world.file_id}/legacy-input/",
        {
            "operation": "hpo",
            "options": {
                "file_id": world.file_id,
                "source_job_id": invalid,
                "source_result_sha256": "a" * 64,
                "execution_id": str(uuid.uuid4()),
            },
        },
    )
    assert response.status_code == 409, response.content
    assert response.json()["error_code"] == "job_legacy_source_job_required"
    assert not NativeJob.objects.exists()
