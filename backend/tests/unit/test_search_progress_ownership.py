"""Late callbacks, stop flags and failure diagnostics retain their operation owner."""
import copy
import json
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from modeling.search_admission import claim_search

pytestmark = pytest.mark.unit


@pytest.fixture(params=["sfs", "hyperparam"])
def search_api(request, monkeypatch, _use_tmp_media, settings, db):
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
    monkeypatch.setattr(views, "load_development_data", lambda *args: saved)
    sfs = request.param == "sfs"
    registry = views.SFS_PROGRESS if sfs else views.HYPERPARAM_PROGRESS
    start = views.SFSStartView if sfs else views.HyperparamStartView
    status = views.SFSStatusView if sfs else views.HyperparamStatusView
    path = root / ("sfs_results/1_sfs_results.json" if sfs else "hyperparam_results/1_hyperparam.json")
    path.parent.mkdir()
    path.write_bytes(b'{"status":"completed","operation_id":"preceding"}')
    pending, searches = [], []
    result = {"status": "completed", "forward": [], "backward": [],
              "selected_params": {"n_estimators": 5}, "features": ["x"]}

    def search(**kwargs):
        searches.append(kwargs)
        return copy.deepcopy(result)

    monkeypatch.setattr(views, "run_sfs_with_progress" if sfs else "run_hyperparam_search_with_progress", search)
    adapter = Mock(fit_receipt={})
    monkeypatch.setattr("modeling.tuning_evidence.fit_for_tuning", lambda *args, **kwargs: adapter)
    monkeypatch.setattr(views, "publish_candidate", Mock(return_value={
        "model": {"model_path": "candidate/model"}, "execution_id": "candidate", "adoption_status": "candidate"}))

    class QueuedThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            pending.append(self.target)

    monkeypatch.setattr(views.threading, "Thread", QueuedThread)
    registry.pop(1, None)
    factory = APIRequestFactory()

    def submit():
        return start.as_view()(factory.post("/start/", {"file_id": "1", "cv_folds": 4}, format="json"))

    def progress():
        return status.as_view()(factory.get("/status/1/"), file_id=1)

    yield {"registry": registry, "submit": submit, "progress": progress, "pending": pending,
           "searches": searches, "result": result, "path": path, "sfs": sfs, "views": views}
    registry.pop(1, None)


@pytest.mark.parametrize("terminal", ["completed", "stopped", "error"])
def test_late_callback_cannot_revive_terminal_state_or_rewrite_current_evidence(search_api, terminal):
    case = search_api
    case["result"]["status"] = terminal
    response = case["submit"]()
    assert response.status_code == 200
    case["pending"][0]()
    owner = case["registry"][1]
    assert owner["status"] == terminal
    before, current = copy.deepcopy(owner), case["path"].read_bytes()
    case["searches"][0]["status_callback"]({"status": "running", "progress": 0.5,
        "operation_id": str(uuid.uuid4()), "completed_steps": [
            {"direction": "forward", "step": 1, "selected_features": ["x"]}]})
    assert owner == before and case["path"].read_bytes() == current
    assert case["progress"]().data["status"] == terminal


def test_late_callback_cannot_modify_a_later_legitimately_claimed_operation(search_api):
    case = search_api
    case["submit"]()
    case["pending"][0]()
    original = case["registry"][1]
    before, current = copy.deepcopy(original), case["path"].read_bytes()
    newer = {"status": "running", "operation_id": str(uuid.uuid4()), "stop_requested": True, "sentinel": "newer"}
    assert claim_search(case["registry"], 1, newer)
    case["searches"][0]["status_callback"]({"status": "running", "message": "old callback", "completed_steps": [
        {"direction": "forward", "step": 1, "selected_features": ["x"]}]})
    assert case["registry"][1] == newer and original == before
    assert case["path"].read_bytes() == current
    assert case["searches"][0]["stop_flag"] is original


@pytest.mark.parametrize("status", [None, "pending", "unavailable", "completed", "error"])
def test_callback_identity_is_pinned_and_live_owner_stays_running(search_api, monkeypatch, status):
    case = search_api
    callbacks = []

    def search(**kwargs):
        callbacks.append(kwargs)
        before = copy.deepcopy(case["registry"][1])
        kwargs["status_callback"]({"status": status, "operation_id": "foreign-callback", "progress": 0.25})
        owner = case["registry"][1]
        assert owner["operation_id"] == before["operation_id"]
        assert owner["status"] == "running" and owner["progress"] == 0.25
        assert case["submit"]().status_code == 409
        return copy.deepcopy(case["result"])

    monkeypatch.setattr(case["views"], "run_sfs_with_progress" if case["sfs"] else "run_hyperparam_search_with_progress", search)
    case["submit"]()
    case["pending"][0]()
    assert callbacks and case["registry"][1]["status"] == "completed"


@pytest.mark.parametrize("change", ["replace", "retoken", "remove"])
def test_stale_running_callback_does_not_touch_reassigned_progress_or_checkpoint(search_api, monkeypatch, change):
    case = search_api
    accepted = case["submit"]()
    owner = case["registry"][1]
    checkpoint = case["path"].read_bytes()

    def search(**kwargs):
        newer = {"status": "running", "operation_id": str(uuid.uuid4()), "sentinel": "newer"}
        if change == "replace":
            case["registry"][1] = newer
        elif change == "retoken":
            owner.clear()
            owner.update(newer)
        else:
            case["registry"].pop(1)
        before = copy.deepcopy(case["registry"])
        kwargs["status_callback"]({"status": "running", "message": "old callback", "completed_steps": [
            {"direction": "forward", "step": 1, "selected_features": ["x"]}]})
        assert case["registry"] == before and case["path"].read_bytes() == checkpoint
        raise ValueError("Old worker cannot update the replacement owner")

    monkeypatch.setattr(case["views"], "run_sfs_with_progress" if case["sfs"] else "run_hyperparam_search_with_progress", search)
    case["pending"][0]()
    if change != "remove":
        assert case["registry"][1]["status"] == "running"
        assert case["registry"][1]["operation_id"] != accepted.data["operation_id"]
        assert "failure" not in case["registry"][1] and "storage_failure" not in case["registry"][1]
    else:
        assert 1 not in case["registry"]


def test_deferred_worker_receives_its_own_stop_flag_and_cannot_write_new_progress(search_api, monkeypatch):
    case = search_api
    case["submit"]()
    original = case["registry"][1]
    original["stop_requested"] = True
    newer = {"status": "running", "operation_id": str(uuid.uuid4()), "stop_requested": False}
    case["registry"][1] = newer
    observed = []

    def search(**kwargs):
        observed.append(kwargs["stop_flag"])
        assert kwargs["stop_flag"] is original and kwargs["stop_flag"]["stop_requested"] is True
        raise ValueError("Stopped old owner")

    monkeypatch.setattr(case["views"], "run_sfs_with_progress" if case["sfs"] else "run_hyperparam_search_with_progress", search)
    case["pending"][0]()
    assert observed == [original] and case["registry"][1] == newer


def test_failure_is_fully_diagnosed_before_a_new_request_can_claim(search_api, monkeypatch):
    from modeling import async_failures

    case = search_api
    actual, attempts = async_failures.record_failure, []

    def diagnostic(error, stage, context):
        attempts.append(case["submit"]())
        return actual(error, stage, context)

    def fail(**kwargs):
        raise ValueError("Synthetic search failure")

    monkeypatch.setattr(async_failures, "record_failure", diagnostic)
    monkeypatch.setattr(case["views"], "run_sfs_with_progress" if case["sfs"] else "run_hyperparam_search_with_progress", fail)
    accepted = case["submit"]()
    case["pending"][0]()
    assert len(attempts) == 1 and attempts[0].status_code == 409
    progress = case["progress"]().data
    assert progress["status"] == "error"
    assert progress["operation_id"] == progress["failure"]["operation_id"] == accepted.data["operation_id"]
    persisted = json.loads(case["path"].read_bytes())
    if case["sfs"]:
        assert persisted["operation_id"] == "preceding"
    else:
        assert persisted["operation_id"] == persisted["failure"]["operation_id"] == accepted.data["operation_id"]
