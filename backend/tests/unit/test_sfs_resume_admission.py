"""Resume is refused before work when evidence is inconsistent or ambiguous."""

import copy
import json
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

from modeling.sfs_objective import prepare_search, json_record
from modeling.sfs_resume import restore_sfs_resume
from tests.unit.test_sfs_objective import data, run

pytestmark = pytest.mark.unit


@pytest.fixture
def operation(monkeypatch, _use_tmp_media, settings):
    from rest_framework.test import APIRequestFactory
    from modeling import views

    X, y, V, z, context = data()
    saved = {"X_train": X, "y_train": y, "X_valid": V, "y_valid": z,
             "task": "regression", "algorithm": "xgboost", "validation_context": context,
             "prediction_contract": context["prediction_contract"], "execution_id": "source-run"}
    root = Path(settings.MEDIA_ROOT)
    (root / "train_data").mkdir()
    (root / "train_data/1_train_data.pkl").touch()
    path = root / "sfs_results/1_sfs_results.json"
    path.parent.mkdir()
    _, _, objective, _, basis = prepare_search(X, y, V, z, "regression", "xgboost", context, {}, 4, 3,
                                               ["forward"], execution_id="source-run", n_jobs=1)
    step = {"step": 1, "direction": "forward", "selected_features": ["x"], "search_basis_sha256": basis["sha256"]}
    record = {"status": "stopped", "resume_basis": basis, "selection_objective": objective,
              "forward": [step], "backward": [], "baselines": {}}
    monkeypatch.setattr(views, "load_development_data", lambda *args: saved)
    start = Mock()

    class NoWorkThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            start()

    monkeypatch.setattr(views.threading, "Thread", NoWorkThread)
    views.SFS_PROGRESS.pop(1, None)
    views.HYPERPARAM_PROGRESS.pop(1, None)
    yield views, APIRequestFactory(), path, record, basis, start
    views.SFS_PROGRESS.pop(1, None)
    views.HYPERPARAM_PROGRESS.pop(1, None)


@pytest.mark.parametrize("fault", [
    "root_list", "root_null", "malformed", "duplicate_status", "nonfinite", "failed_with_resume", "completed_with_resume",
    "nested_list", "nested_foreign_basis", "nested_missing_basis", "direction_dict", "step_scalar",
    "step_gap", "step_boolean", "wrong_direction", "foreign_step_basis", "feature_scalar", "foreign_feature",
    "duplicate_feature", "contradictory_features", "contradictory_completed_steps", "baseline_list",
    "metrics_without_steps", "invalid_active_key", "ambiguous_forward", "nested_steps_dict",
    "forward_multi_add", "forward_reordered",
])
def test_invalid_resume_never_starts_work_or_rewrites_evidence(operation, fault):
    views, factory, path, original, basis, start = operation
    record = copy.deepcopy(original)
    state = {"resume_basis": basis, "forward_results": record["forward"], "completed_steps": record["forward"],
             "forward_selected_features": ["x"], "baselines": {}}
    content = None
    if fault == "root_list":
        content = "[]"
    elif fault == "root_null":
        content = "null"
    elif fault == "malformed":
        content = "{"
    elif fault == "duplicate_status":
        content = json.dumps(record)[:-1] + ',"status":"stopped"}'
    elif fault == "nonfinite":
        content = json.dumps(record)[:-1] + ',"invalid":NaN}'
    elif fault in {"failed_with_resume", "completed_with_resume"}:
        record.update(status="error" if fault == "failed_with_resume" else "completed", resume_state=state)
    elif fault == "nested_list":
        record["resume_state"] = [state]
    elif fault == "nested_foreign_basis":
        record["resume_state"] = {**state, "resume_basis": {**basis, "execution_id": "foreign"}}
    elif fault == "nested_missing_basis":
        record["resume_state"] = {key: value for key, value in state.items() if key != "resume_basis"}
    elif fault == "direction_dict":
        record["forward"] = {}
    elif fault == "step_scalar":
        record["forward"] = [None]
    elif fault in {"step_gap", "step_boolean", "wrong_direction", "foreign_step_basis", "feature_scalar", "foreign_feature", "duplicate_feature"}:
        changes = {"step_gap": {"step": 2}, "step_boolean": {"step": True}, "wrong_direction": {"direction": "backward"},
                   "foreign_step_basis": {"search_basis_sha256": "foreign"}, "feature_scalar": {"selected_features": "x"},
                   "foreign_feature": {"selected_features": ["foreign"]}, "duplicate_feature": {"selected_features": ["x", "x"]}}
        record["forward"][0].update(changes[fault])
    elif fault == "contradictory_features":
        record["resume_state"] = {**state, "forward_selected_features": ["noise"]}
    elif fault == "contradictory_completed_steps":
        record["resume_state"] = {**state, "completed_steps": []}
    elif fault == "baseline_list":
        record["baselines"] = []
    elif fault == "metrics_without_steps":
        record["resume_state"] = {"resume_basis": basis, "completed_steps": [], "forward_previous_metrics": {"rmse": .1}}
    elif fault == "invalid_active_key":
        record["resume_direction_keys"] = {"forward": "backward"}
    elif fault == "ambiguous_forward":
        record["forward_from_backward"] = record["forward"]
    elif fault == "nested_steps_dict":
        record["resume_state"] = {**state, "forward_results": {}}
    elif fault == "forward_multi_add":
        record["forward"][0]["selected_features"] = ["x", "noise"]
    elif fault == "forward_reordered":
        record["forward"].append({**record["forward"][0], "step": 2, "selected_features": ["noise", "x"]})
    path.write_text(content if content is not None else json.dumps(record))
    before = path.read_bytes()
    response = views.SFSStartView.as_view()(factory.post("/sfs/start/", {"file_id": 1, "resume": True, "cv_folds": 4}, format="json"))
    assert response.status_code == 409 and response.data["status"] == "resume_blocked"
    assert "error" in response.data
    start.assert_not_called()
    assert 1 not in views.SFS_PROGRESS and path.read_bytes() == before


@pytest.mark.parametrize("status", ["running", "interrupted", "stopped"])
def test_valid_simple_checkpoint_is_admitted_with_bound_features(operation, status):
    views, factory, path, record, basis, start = operation
    record["status"] = status
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    restored = restore_sfs_resume(path, basis)
    assert restored["resume_basis"] == basis and restored["forward_selected_features"] == ["x"]
    assert restored["completed_steps"] == record["forward"]
    response = views.SFSStartView.as_view()(factory.post("/sfs/start/", {"file_id": 1, "resume": True, "cv_folds": 4}, format="json"))
    assert response.status_code == 200 and response.data["operation_id"]
    start.assert_called_once()
    assert views.SFS_PROGRESS[1]["completed_steps"] == record["forward"]
    assert path.read_bytes() == before


def test_explicit_active_direction_avoids_reusing_an_older_forward_branch(operation):
    _, _, path, record, basis, _ = operation
    historical = {**record["forward"][0], "search_basis_sha256": "historical", "selected_features": ["noise"]}
    record.update(forward=[historical], forward_from_backward=record["forward"],
                  resume_direction_keys={"forward": "forward_from_backward"})
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    resumed = restore_sfs_resume(path, basis)
    assert resumed["forward_selected_features"] == ["x"]
    assert resumed["completed_steps"][0]["search_basis_sha256"] == basis["sha256"]
    assert path.read_bytes() == before


def test_native_stop_in_a_later_direction_retains_prior_direction_feature_state(tmp_path):
    flag = {}

    def stop_after_first(info):
        if info["completed_steps"]:
            flag["stop_requested"] = True

    parts = data()
    options = {"methods": ["backward", "forward"], "stopping_criteria": {"min_features": 1, "max_features": 2}}
    stopped = run(parts, stop_flag=flag, status_callback=stop_after_first, **options)
    assert stopped["status"] == "stopped"
    assert stopped["backward"] and not stopped["resume_state"].get("backward_current_features")
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(json_record(stopped)))
    restored = restore_sfs_resume(path, stopped["resume_basis"])
    assert restored["backward_current_features"] == stopped["backward"][-1]["selected_features"]
    resumed = run(parts, resume_state=restored, **options)
    uninterrupted = run(parts, **options)
    assert resumed["status"] == uninterrupted["status"] == "completed"
    assert resumed["backward_remaining_features"] == uninterrupted["backward_remaining_features"]
    assert resumed["backward"] == uninterrupted["backward"]
    assert resumed["forward"][-1]["selected_features"] == uninterrupted["forward"][-1]["selected_features"]


@pytest.mark.parametrize("operation_name", ["sfs", "hyperparam"])
def test_numeric_string_and_integer_start_share_the_same_inflight_owner(operation, operation_name):
    views, factory, _, _, _, start = operation
    view = views.SFSStartView if operation_name == "sfs" else views.HyperparamStartView
    registry = views.SFS_PROGRESS if operation_name == "sfs" else views.HYPERPARAM_PROGRESS
    first = view.as_view()(factory.post("/search/start/", {"file_id": "1", "cv_folds": 4}, format="json"))
    assert first.status_code == 200 and first.data["file_id"] == 1
    assert registry[1]["operation_id"] == first.data["operation_id"] and "1" not in registry
    second = view.as_view()(factory.post("/search/start/", {"file_id": 1, "cv_folds": 4}, format="json"))
    assert second.status_code == 409 and second.data["status"] == "already_running"
    start.assert_called_once()
    assert registry[1]["operation_id"] == first.data["operation_id"]


def test_simultaneous_validated_registration_accepts_one_owner():
    from modeling.search_admission import claim_search

    registry = {}
    barrier = threading.Barrier(2)
    outcomes = []

    def claim(identifier):
        barrier.wait(5)
        outcomes.append((identifier, claim_search(registry, 1, {"status": "running", "operation_id": identifier})))

    # threading.Thread is real here; the operation fixture is intentionally absent.
    threads = [threading.Thread(target=claim, args=(name,)) for name in ("one", "two")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert not any(thread.is_alive() for thread in threads)
    accepted = [identifier for identifier, success in outcomes if success]
    assert len(accepted) == 1 and registry[1]["operation_id"] == accepted[0]
