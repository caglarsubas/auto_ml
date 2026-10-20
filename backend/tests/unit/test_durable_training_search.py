"""Real native training/search through durable request, lease and result fences."""

import copy
import json
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from django.test import Client
from django.utils import timezone

from access_control import projects
from access_control.models import Project, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs import service, training_search as training
from execution_jobs.models import JobEvent, NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_governed_foundation import declaration

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def post(client, url, body):
    return client.post(url, json.dumps(body), content_type="application/json")


@pytest.fixture
def world(_use_tmp_media, settings, django_user_model):
    settings.DECLARAI_JOBS_ENABLED = True
    ProjectPolicy.objects.create()
    project = Project.objects.create(name="Durable training fixture")
    relative = "data_files/durable-development.csv"
    path = Path(settings.MEDIA_ROOT) / relative
    frame = pd.DataFrame(
        {
            "x": np.linspace(-3, 3, 120),
            "z": [1.0, np.nan, 3.0] * 40,
            "entity": np.repeat(np.arange(30), 4),
            "date": pd.date_range("2020-01-01", periods=120).astype(str),
            "end": pd.date_range("2020-01-02", periods=120).astype(str),
            "outcome": ["good", "bad"] * 60,
        }
    )
    frame.to_csv(path, index=False)
    dataset = Declaration.objects.create(name="Development only", original_name="development.csv", file=relative)
    projects.bind_dataset(dataset, project.pk)
    users, clients = {}, {}
    for role in ["developer", "reviewer", "admin", "outsider"]:
        actor = django_user_model.objects.create(username="training-" + role)
        if role != "outsider":
            ProjectMembership.objects.create(project=project, actor=actor, role=role)
        client = Client()
        client.force_login(actor)
        users[role], clients[role] = actor, client
    clients["anonymous"] = Client()
    options = {
        "data_role": "development_only",
        "business_understanding": declaration(),
        "features": ["x", "z"],
        "validation": {"strategy": "random", "n_splits": 3},
    }
    return SimpleNamespace(
        file_id=dataset.pk,
        project=project,
        users=users,
        clients=clients,
        path=path,
        frame=frame,
        options=options,
        root=Path(settings.MEDIA_ROOT),
    )


def admission(w, options=None):
    options = options or w.options
    result = post(w.clients["developer"], f"/api/jobs/datasets/{w.file_id}/training-input/", options)
    assert result.status_code == 200, result.content
    preview = result.json()
    return {
        **options,
        "kind": training.KIND,
        "request_id": str(uuid.uuid4()),
        "input_sha256": preview["input_sha256"],
        "training_sha256": preview["training_sha256"],
    }, preview


def queue(w, body):
    result = post(w.clients["developer"], f"/api/jobs/datasets/{w.file_id}/", body)
    assert result.status_code == 202, result.content
    return result.json()["id"]


@pytest.mark.parametrize("task,positive", [("classification", "bad"), ("classification", "good"), ("regression", None)])
def test_real_training_search_and_refit_survive_process_local_state_loss(world, task, positive):
    w = world
    options = copy.deepcopy(w.options)
    options["business_understanding"] = declaration(task, positive)
    if task == "regression":
        w.frame["outcome"] = [10.0, 20.0] * 60  # Cardinality cannot choose the task.
        w.frame.to_csv(w.path, index=False)
    body, preview = admission(w, options)
    identifier = queue(w, body)
    replay = post(w.clients["developer"], f"/api/jobs/datasets/{w.file_id}/", body)
    assert replay.status_code == 200 and replay.json()["replayed"]
    with (
        patch("pickle.load", side_effect=AssertionError("untrusted state loaded")),
        patch("joblib.load", side_effect=AssertionError("state loaded")),
    ):
        service.execute(identifier)
        service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "succeeded" and job.attempts == 1 and job.result_sha256 == service.digest(job.result)
    assert job.specification["training"]["profile"] == {
        "kind": training.KIND,
        "runtime": preview["runtime"],
        "limits": preview["budget"],
    }
    result = w.clients["reviewer"].get(f"/api/jobs/{identifier}/").json()["result"]
    assert result["prediction_contract"]["task"] == task
    assert result["prediction_contract"]["positive_class"] == positive
    assert result["training_sha256"] == preview["training_sha256"]
    assert len(result["candidates"]) == 2 and all(len(c["folds"]) == 3 for c in result["candidates"])
    assert result["model_format"] == "xgboost_json" and json.loads(result["model_json"])["learner"]
    assert result["refit_receipt"]["train"]["n_rows"] == 120
    for candidate in result["candidates"]:
        for fold in candidate["folds"]:
            provenance = fold["preprocessing"]
            expected = w.frame.loc[provenance["train_rows"], "z"].mean()
            assert provenance["impute_means"]["z"] == pytest.approx(expected)
            assert not set(provenance["train_rows"]) & set(provenance["valid_rows"])
            assert fold["fit_receipt"]["early_stopping_rounds"] == 0
    assert all(
        result[key] is False
        for key in [
            "final_holdout_accessed",
            "legacy_projection_updated",
            "model_adopted",
            "review_approved",
            "production_use_approved",
        ]
    )
    assert not (w.root / "modeling").exists() and not (w.root / "execution_runs").exists()
    assert list(job.events.values_list("event_type", flat=True)) == ["submitted", "started", "succeeded"]
    listing = w.clients["developer"].get(f"/api/jobs/datasets/{w.file_id}/").json()["jobs"]
    assert listing[0]["kind"] == training.KIND and listing[0]["bundle_id"] is None


@pytest.mark.parametrize("strategy", ["group", "oot"])
def test_declared_entity_time_and_outcome_windows_govern_actual_folds(world, strategy):
    w = world
    options = copy.deepcopy(w.options)
    options["validation"] = {"strategy": strategy, "n_splits": 3, "group_column": "entity"}
    if strategy == "oot":
        options["validation"].update(date_column="date", label_end_column="end")
    body, preview = admission(w, options)
    identifier = queue(w, body)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "succeeded", job.reason_code
    for fold in preview["folds"]:
        train, valid = w.frame.loc[fold["train_rows"]], w.frame.loc[fold["valid_rows"]]
        assert not set(train.entity) & set(valid.entity)
        if strategy == "oot":
            assert train.end.max() < valid.date.min()


@pytest.mark.parametrize("role", ["reviewer", "admin", "outsider", "anonymous"])
def test_training_admission_and_preview_require_current_developer(world, role):
    w = world
    body, _ = admission(w)
    assert post(w.clients[role], f"/api/jobs/datasets/{w.file_id}/training-input/", w.options).status_code == 403
    assert post(w.clients[role], f"/api/jobs/datasets/{w.file_id}/", body).status_code == 403
    assert not NativeJob.objects.exists()


@pytest.mark.parametrize(
    "fault",
    [
        "role",
        "features",
        "folds",
        "strategy",
        "group",
        "date",
        "business",
        "target",
        "metric",
        "costs",
        "forbidden",
        "categorical",
        "labels",
        "wide",
        "rows",
    ],
)
def test_unsupported_or_contradictory_training_profiles_never_queue(world, fault):
    w = world
    options = copy.deepcopy(w.options)
    if fault == "role":
        options["data_role"] = "final_holdout"
    elif fault == "features":
        options["features"] = ["x", "outcome"]
    elif fault == "folds":
        options["validation"]["n_splits"] = True
    elif fault == "strategy":
        options["validation"]["strategy"] = "auto"
    elif fault == "group":
        options["validation"] = {"strategy": "group", "n_splits": 3}
    elif fault == "date":
        options["validation"] = {"strategy": "oot", "n_splits": 3, "date_column": "missing"}
    elif fault == "business":
        options["business_understanding"]["target_contract"] = "invalid"
    elif fault == "target":
        options["business_understanding"]["target_contract"]["positive_class"] = "missing"
    elif fault == "metric":
        options["business_understanding"]["success_criteria"]["primary_metric"] = "rmse"
    elif fault == "costs":
        options["business_understanding"]["success_criteria"]["cost_matrix"] = "invalid"
    elif fault == "forbidden":
        options["business_understanding"]["forbidden_features"] = ["x"]
    elif fault == "categorical":
        options["features"] = ["date"]
    elif fault == "labels":
        w.frame.loc[0, "outcome"] = None
        w.frame.to_csv(w.path, index=False)
    elif fault == "wide":
        options["features"] = ["x"] * 33
    else:
        w.frame.iloc[:20].to_csv(w.path, index=False)
    response = post(w.clients["developer"], f"/api/jobs/datasets/{w.file_id}/training-input/", options)
    assert response.status_code in {400, 409}, response.content
    assert not NativeJob.objects.exists()


@pytest.mark.parametrize("field", ["input_sha256", "training_sha256"])
def test_stale_preview_requires_a_new_review_before_admission(world, field):
    body, _ = admission(world)
    body[field] = "0" * 64
    response = post(world.clients["developer"], f"/api/jobs/datasets/{world.file_id}/", body)
    assert response.status_code == 409 and not NativeJob.objects.exists()


def test_changed_input_or_runtime_cannot_execute_under_old_approval(world):
    body, _ = admission(world)
    identifier = queue(world, body)
    world.path.write_text(world.path.read_text().replace("-3.0", "-2.99"))
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "blocked" and job.result is None


def test_runtime_and_authority_changes_are_rechecked_before_claim(world):
    body, _ = admission(world)
    first = queue(world, body)
    job = NativeJob.objects.get(pk=first)
    job.specification["runtime"]["python"] = "different"
    job.save()
    service.execute(first)
    assert NativeJob.objects.get(pk=first).reason_code == "job_runtime_changed"
    body["request_id"] = str(uuid.uuid4())
    second = queue(world, body)
    projects.change_member(world.project, world.users["developer"], "reviewer")
    service.execute(second)
    assert NativeJob.objects.get(pk=second).state == "blocked"


def test_expired_attempt_can_recompute_but_cannot_double_publish(world):
    body, _ = admission(world)
    identifier = queue(world, body)
    job, stale = service.claim(identifier)
    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1))
    service.reconcile()
    service.execute(identifier)
    completed = NativeJob.objects.get(pk=identifier)
    assert completed.state == "succeeded" and completed.attempts == 2
    receipt = completed.result_sha256
    service.finish(identifier, stale, "succeeded", result={"invalid": True})
    assert NativeJob.objects.get(pk=identifier).result_sha256 == receipt
    assert JobEvent.objects.filter(job_id=identifier, event_type="succeeded").count() == 1


def test_active_cancellation_discards_the_model_before_publication(world, monkeypatch):
    from modeling.booster_adapters import XGBoostAdapter

    body, _ = admission(world)
    identifier = queue(world, body)
    original = XGBoostAdapter.train

    def cancelled(*args, **kwargs):
        result = original(*args, **kwargs)
        service.cancel(world.users["developer"], identifier, {"action": "cancel"})
        return result

    monkeypatch.setattr(XGBoostAdapter, "train", cancelled)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "cancelled" and job.result is None and not job.result_sha256


def test_request_id_cannot_be_rebound_to_other_training_fields(world):
    body, _ = admission(world)
    queue(world, body)
    body["features"] = ["x"]
    response = post(world.clients["developer"], f"/api/jobs/datasets/{world.file_id}/", body)
    assert response.status_code == 409 and NativeJob.objects.count() == 1


@pytest.mark.parametrize("change", ["budget", "runtime"])
def test_preview_pins_execution_profile_before_queue_admission(world, monkeypatch, change):
    body, preview = admission(world)
    assert preview["budget"]["seconds"] == 120 and preview["budget"]["max_input_bytes"] == 5 * 1024**2
    assert preview["runtime"] == service.runtime(training.KIND)
    if change == "budget":
        monkeypatch.setitem(training.BUDGET, "boost_rounds", 17)
    else:
        original = service.runtime
        monkeypatch.setattr(service, "runtime", lambda kind: {**original(kind), "python": "changed"})
    response = post(world.clients["developer"], f"/api/jobs/datasets/{world.file_id}/", body)
    assert response.status_code == 409
    assert response.json()["error_code"] == "job_training_input_or_plan_changed"
    assert not NativeJob.objects.exists()


def test_preview_and_submission_require_csrf(world):
    client = Client(enforce_csrf_checks=True)
    client.force_login(world.users["developer"])
    body, _ = admission(world)
    assert post(client, f"/api/jobs/datasets/{world.file_id}/training-input/", world.options).status_code == 403
    assert post(client, f"/api/jobs/datasets/{world.file_id}/", body).status_code == 403


@pytest.mark.parametrize("existing", ["split", "model", "assessment", "same_source_assessment"])
@pytest.mark.parametrize("boundary", ["preview", "execute"])
def test_existing_final_partition_history_cannot_be_relabelled_development_only(world, existing, boundary):
    import hashlib

    if boundary == "execute":
        body, _ = admission(world)
        identifier = queue(world, body)
    if existing in {"split", "model"}:
        relative = (
            f"splits/{world.file_id}_split.json" if existing == "split" else f"modeling/{world.file_id}_status.json"
        )
        path = world.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("invalid metadata must not be opened or trusted")
    else:
        HoldoutAccess.objects.create(
            file_id=world.file_id if existing == "assessment" else world.file_id + 1000,
            dataset_sha256=hashlib.sha256(world.path.read_bytes()).hexdigest(),
        )
    if boundary == "preview":
        response = post(
            world.clients["developer"], f"/api/jobs/datasets/{world.file_id}/training-input/", world.options
        )
        assert response.status_code == 409
        assert response.json()["error_code"] == "job_training_requires_fresh_development_input"
        assert not NativeJob.objects.exists()
    else:
        service.execute(identifier)
        job = NativeJob.objects.get(pk=identifier)
        assert job.state == "blocked" and job.result is None
        assert job.reason_code == "job_training_requires_fresh_development_input"
