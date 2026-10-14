"""Tuning reports actual failures and never invents saved completion."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def recorded(_use_tmp_media, settings):
    from modeling.views import HYPERPARAM_PROGRESS

    HYPERPARAM_PROGRESS.clear()
    path = Path(settings.MEDIA_ROOT) / "hyperparam_results/41_hyperparam.json"
    path.parent.mkdir()
    yield path
    HYPERPARAM_PROGRESS.clear()


def readers():
    from rest_framework.test import APIRequestFactory
    from modeling.views import HyperparamStatusView, HyperparamResultsView

    factory = APIRequestFactory()
    return (HyperparamStatusView.as_view()(factory.get("/hp/status/41/"), file_id=41),
            HyperparamResultsView.as_view()(factory.get("/hp/results/41/"), file_id=41))


def test_saved_failure_retains_exact_diagnostic_and_operation(recorded):
    failure = {"operation": "hyperparameter_tuning", "operation_id": "operation-41",
               "stage": "candidate_publication", "exception_type": "OperationalError"}
    recorded.write_text(json.dumps({"status": "error", "error": "candidate failed", "failure": failure,
                                    "operation_id": "operation-41", "duration_seconds": 2.4, "trials": []}))
    before = recorded.read_bytes()
    progress, results = readers()
    assert progress.status_code == results.status_code == 200
    for payload in (progress.data, results.data):
        assert payload["status"] == "error" and payload["failure"] == failure
        assert payload["operation_id"] == "operation-41" and payload["duration_seconds"] == 2.4
        assert payload["error"] == "candidate failed"
    assert results.data["hyperparam_completed"] is False and progress.data["progress"] == 0
    assert recorded.read_bytes() == before


@pytest.mark.parametrize("content", [
    "{", "[]", "null", "{}", '{"status":"unknown"}', '{"status":null}',
    '{"status":"completed","error":"failed"}',
    '{"status":"completed","failure":{"stage":"search"}}',
    '{"status":"error","status":"completed"}',
    '{"status":"completed","trials":NaN}',
    '{"status":"completed","trials":{}}',
    '{"status":"completed","validation_curves":{}}',
])
def test_invalid_saved_tuning_is_unavailable_and_bytes_are_preserved(recorded, content):
    recorded.write_text(content)
    before = recorded.read_bytes()
    for response in readers():
        assert response.status_code == 503
        assert response.data["status"] == "unavailable"
        assert response.data["hyperparam_completed"] is False and response.data["progress"] == 0
        assert response.data["error_code"].startswith("hyperparam_record_")
    assert recorded.read_bytes() == before


@pytest.mark.parametrize("state", ["completed", "running", "stopped", "interrupted"])
def test_valid_state_preserves_record_and_no_local_owner_is_interrupted(recorded, state):
    recorded.write_text(json.dumps({"status": state, "trials": [], "operation_id": "old-operation"}))
    progress, results = readers()
    assert progress.status_code == results.status_code == 200
    assert progress.data["status"] == ("interrupted" if state == "running" else state)
    assert results.data["status"] == state
    assert progress.data["progress"] == int(state == "completed")
    assert results.data["hyperparam_completed"] is (state == "completed")


def test_live_tuning_keeps_precedence_over_an_older_record(recorded):
    from modeling.views import HYPERPARAM_PROGRESS

    recorded.write_text('{"status":"completed","operation_id":"older"}')
    HYPERPARAM_PROGRESS[41] = {"status": "error", "operation_id": "current", "failure": {"stage": "final_evidence_write"}}
    progress, _ = readers()
    assert progress.data["status"] == "error" and progress.data["operation_id"] == "current"
    assert progress.data["failure"]["stage"] == "final_evidence_write"


def test_absent_tuning_keeps_not_started_and_not_found(recorded):
    progress, results = readers()
    assert progress.status_code == 200 and progress.data["status"] == "not_started"
    assert results.status_code == 404 and results.data["hyperparam_completed"] is False


def test_unreadable_tuning_has_a_safe_reason_without_a_completion_claim(recorded, monkeypatch):
    from modeling import search_state

    recorded.touch()

    def fail(*args, **kwargs):
        raise PermissionError("private storage detail")

    monkeypatch.setattr(search_state, "open", fail, raising=False)
    for response in readers():
        assert response.status_code == 503
        assert response.data["error_code"] == "hyperparam_record_unreadable"
        assert "private storage detail" not in json.dumps(response.data)


def test_swallowed_native_search_exception_keeps_correlation_without_logging_values(monkeypatch, caplog, capsys):
    from modeling import hyperparam_utils
    from tests.unit.test_tuning_evidence import run

    def fail(*args, **kwargs):
        raise RuntimeError("HPO_FAILURE_SECRET")

    monkeypatch.setattr(hyperparam_utils, "_build_guidance", fail)
    updates = []
    context = {"operation_id": "operation-41", "file_id": 41, "execution_id": "source-41"}
    result = run(n_jobs=1, status_callback=updates.append, failure_context=context)
    assert result["status"] == updates[-1]["status"] == "error"
    assert result["failure"] == updates[-1]["failure"]
    assert result["failure"]["operation"] == "hyperparameter_tuning"
    assert result["failure"]["stage"] == "search"
    assert all(result["failure"][key] == value for key, value in context.items())
    assert result["failure"]["trace_frames"][-1]["function"] == "fail"
    output = capsys.readouterr()
    assert "HPO_FAILURE_SECRET" not in caplog.text + output.out + output.err


@pytest.fixture
def api_operation(monkeypatch, _use_tmp_media, settings):
    from rest_framework.test import APIRequestFactory
    from modeling import views
    from tests.unit.test_sfs_objective import data

    X, y, V, z, context = data()
    saved = {"X_train": X, "y_train": y, "X_valid": V, "y_valid": z,
             "task": "regression", "algorithm": "xgboost", "validation_context": context,
             "prediction_contract": context["prediction_contract"], "execution_id": "source-run"}
    root = Path(settings.MEDIA_ROOT)
    (root / "train_data").mkdir()
    (root / "train_data/1_train_data.pkl").touch()
    path = root / "hyperparam_results/1_hyperparam.json"
    path.parent.mkdir()
    prior = b'{"status":"completed","operation_id":"previous","trials":[]}'
    path.write_bytes(prior)
    monkeypatch.setattr(views, "load_development_data", lambda *args: saved)
    adapter = Mock(fit_receipt={})
    monkeypatch.setattr("modeling.tuning_evidence.fit_for_tuning", lambda *args, **kwargs: adapter)
    publication = Mock(return_value={"model": {"model_path": "model"}, "execution_id": "candidate",
                                     "adoption_status": "candidate"})
    monkeypatch.setattr(views, "publish_candidate", publication)
    monkeypatch.setattr(views, "run_hyperparam_search_with_progress", lambda **kwargs: {
        "status": "completed", "selected_params": {"n_estimators": 5}, "features": ["x"]})

    class InlineThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(views.threading, "Thread", InlineThread)
    views.HYPERPARAM_PROGRESS.pop(1, None)
    yield views, APIRequestFactory(), path, prior, publication
    views.HYPERPARAM_PROGRESS.pop(1, None)


@pytest.mark.parametrize("stage", ["search", "candidate_refit", "candidate_publication", "final_evidence_write"])
def test_background_failures_are_attributable_and_do_not_claim_completion(api_operation, monkeypatch, caplog, capsys, stage):
    views, factory, path, prior, publication = api_operation

    def fail(*args, **kwargs):
        raise RuntimeError("HPO_API_FAILURE_SECRET")

    if stage == "search":
        monkeypatch.setattr(views, "run_hyperparam_search_with_progress", fail)
    elif stage == "candidate_refit":
        monkeypatch.setattr("modeling.tuning_evidence.fit_for_tuning", fail)
    elif stage == "candidate_publication":
        publication.side_effect = fail
    else:
        monkeypatch.setattr(views, "write_hyperparam_record", fail)
    response = views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    assert response.status_code == 200
    progress = views.HyperparamStatusView.as_view()(factory.get("/hp/status/1/"), file_id=1)
    assert progress.data["status"] == "error"
    assert progress.data["failure"]["stage"] == stage
    assert progress.data["failure"]["operation_id"] == response.data["operation_id"]
    assert progress.data["failure"]["operation"] == "hyperparameter_tuning"
    assert progress.data["failure"]["execution_id"] == "source-run"
    if stage == "final_evidence_write":
        assert path.read_bytes() == prior
    else:
        views.HYPERPARAM_PROGRESS.pop(1)
        recorded = views.HyperparamStatusView.as_view()(factory.get("/hp/status/1/"), file_id=1)
        assert recorded.data["status"] == "error" and recorded.data["failure"] == progress.data["failure"]
    if stage in {"search", "candidate_refit"}:
        publication.assert_not_called()
    output = capsys.readouterr()
    assert "HPO_API_FAILURE_SECRET" not in caplog.text + output.out + output.err


def test_error_record_save_failure_does_not_replace_original_search_failure(api_operation, monkeypatch):
    views, factory, path, prior, _ = api_operation

    def search(**kwargs):
        raise ValueError("search failed")

    def save(*args):
        raise OSError("storage failed")

    monkeypatch.setattr(views, "run_hyperparam_search_with_progress", search)
    monkeypatch.setattr(views, "write_hyperparam_record", save)
    response = views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    progress = views.HYPERPARAM_PROGRESS[1]
    assert response.status_code == 200 and progress["status"] == "error"
    assert progress["failure"]["stage"] == "search"
    assert progress["storage_failure"]["stage"] == "failure_evidence_write"
    assert progress["storage_failure"]["operation_id"] == progress["failure"]["operation_id"]
    assert path.read_bytes() == prior


@pytest.mark.parametrize("search_result", [{}, {"status": "running"}])
def test_missing_or_nonterminal_search_state_cannot_become_completion(api_operation, monkeypatch, search_result):
    views, factory, _, _, publication = api_operation
    monkeypatch.setattr(views, "run_hyperparam_search_with_progress", lambda **kwargs: search_result)
    response = views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    assert response.status_code == 200 and views.HYPERPARAM_PROGRESS[1]["status"] == "error"
    assert views.HYPERPARAM_PROGRESS[1]["failure"]["stage"] == "search"
    publication.assert_not_called()
