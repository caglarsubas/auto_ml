"""Failed launches cannot leave false owners or release possibly active workers."""
import json
import threading
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from modeling.search_admission import claim_search
from modeling.search_worker import launch_search_worker

pytestmark = pytest.mark.unit


@pytest.fixture(params=["sfs", "hyperparam"])
def worker_api(request, monkeypatch, _use_tmp_media, settings):
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
    prior = b'{"status":"completed","operation_id":"older"}'
    path.write_bytes(prior)
    search = Mock(side_effect=AssertionError("Launch failure must not execute work"))
    monkeypatch.setattr(views, "run_sfs_with_progress" if sfs else "run_hyperparam_search_with_progress", search)
    registry.pop(1, None)
    factory = APIRequestFactory()

    def submit():
        return start.as_view()(factory.post("/start/", {"file_id": "1", "cv_folds": 4}, format="json"))

    def progress():
        return status.as_view()(factory.get("/status/1/"), file_id=1)

    yield registry, submit, progress, path, prior, search
    registry.pop(1, None)


@pytest.mark.parametrize("stage", ["construction", "daemon", "start"])
def test_known_launch_failure_is_attributable_and_allows_a_fresh_retry(worker_api, monkeypatch, caplog, capsys, stage):
    registry, submit, progress, path, prior, search = worker_api

    class FailedThread:
        ident = None

        def __init__(self, target):
            if stage == "construction":
                raise RuntimeError("WORKER_LAUNCH_SECRET")

        @property
        def daemon(self):
            return True

        @daemon.setter
        def daemon(self, value):
            if stage == "daemon":
                raise RuntimeError("WORKER_LAUNCH_SECRET")

        def start(self):
            raise RuntimeError("WORKER_LAUNCH_SECRET")

    monkeypatch.setattr(threading, "Thread", FailedThread)
    response = submit()
    assert response.status_code == 503 and response.data["error_code"] == "search_worker_start_failed"
    assert response.data["status"] == "error" and progress().data["status"] == "error"
    assert response.data["failure"] == registry[1]["failure"]
    assert response.data["failure"]["stage"] == "worker_start"
    assert response.data["failure"]["operation_id"] == response.data["operation_id"]
    assert response.data["failure"]["execution_id"] == "source-run"
    assert registry[1]["operation_id"] == response.data["operation_id"] and "1" not in registry
    assert path.read_bytes() == prior
    search.assert_not_called()
    output = capsys.readouterr()
    assert "WORKER_LAUNCH_SECRET" not in caplog.text + output.out + output.err + json.dumps(response.data)

    class AcceptedThread:
        def __init__(self, target):
            pass

        def start(self):
            pass

    monkeypatch.setattr(threading, "Thread", AcceptedThread)
    retry = submit()
    assert retry.status_code == 200 and retry.data["status"] == "started"
    assert retry.data["operation_id"] != response.data["operation_id"]
    assert registry[1]["operation_id"] == retry.data["operation_id"] and registry[1]["status"] == "running"


@pytest.mark.parametrize("change", ["replace", "retoken"])
def test_stale_launch_failure_cannot_change_a_different_owner(worker_api, monkeypatch, change):
    registry, submit, _, path, prior, search = worker_api
    replacement = {"status": "running", "operation_id": str(uuid.uuid4()), "sentinel": "newer"}

    class FailedThread:
        def __init__(self, target):
            if change == "replace":
                registry[1] = replacement
            else:
                registry[1].clear()
                registry[1].update(replacement)
            raise RuntimeError("Old launch failed")

    monkeypatch.setattr(threading, "Thread", FailedThread)
    response = submit()
    assert response.status_code == 503 and response.data["error_code"] == "search_worker_start_uncertain"
    assert response.data["operation_id"] != replacement["operation_id"]
    assert registry[1] == replacement and path.read_bytes() == prior
    search.assert_not_called()


@pytest.mark.parametrize("introspection_fails", [False, True])
def test_uncertain_launch_retains_owner_and_blocks_duplicate_work(worker_api, monkeypatch, introspection_fails):
    registry, submit, progress, path, prior, search = worker_api

    class UncertainThread:
        def __init__(self, target):
            pass

        @property
        def ident(self):
            if introspection_fails:
                raise RuntimeError("Thread introspection unavailable")
            return 123

        def start(self):
            raise RuntimeError("Launch acknowledgement unavailable")

    monkeypatch.setattr(threading, "Thread", UncertainThread)
    response = submit()
    assert response.status_code == 503 and response.data["status"] == "unavailable"
    assert response.data["error_code"] == "search_worker_start_uncertain"
    assert progress().data["status"] == "running"
    assert registry[1]["launch_failure"] == response.data["failure"]
    assert registry[1].get("failure") is None
    assert submit().status_code == 409 and path.read_bytes() == prior
    search.assert_not_called()


@pytest.mark.parametrize("terminal", ["completed", "error"])
def test_a_worker_that_finished_before_launch_exception_keeps_its_terminal_state(terminal):
    operation = str(uuid.uuid4())
    owner = {"operation_id": operation, "status": "running"}
    registry = {1: owner}

    class FinishedThenRaised:
        def __init__(self, target):
            self.target = target

        def start(self):
            self.target()
            raise RuntimeError("Launch acknowledgement failed after completion")

    response = launch_search_worker(registry, 1, lambda: owner.update(status=terminal),
                                    {"operation_id": operation}, thread_factory=FinishedThenRaised)
    assert response["error_code"] == "search_worker_start_uncertain"
    assert owner["status"] == terminal and "failure" not in owner
    assert owner["launch_failure"]["stage"] == "worker_start"


def test_real_started_worker_is_not_released_when_launch_acknowledgement_raises():
    operation = str(uuid.uuid4())
    owner = {"operation_id": operation, "status": "running"}
    registry = {1: owner}
    entered, release = threading.Event(), threading.Event()
    threads = []

    def target():
        entered.set()
        assert release.wait(5)
        owner["status"] = "completed"

    class StartedThenRaised:
        def __init__(self, target):
            self.actual = threading.Thread(target=target)
            threads.append(self.actual)

        @property
        def daemon(self):
            return self.actual.daemon

        @daemon.setter
        def daemon(self, value):
            self.actual.daemon = value

        @property
        def ident(self):
            return self.actual.ident

        def start(self):
            self.actual.start()
            assert entered.wait(5)
            raise RuntimeError("Acknowledgement failed after native worker start")

    try:
        response = launch_search_worker(registry, 1, target, {"operation_id": operation},
                                        thread_factory=StartedThenRaised)
        assert response["error_code"] == "search_worker_start_uncertain"
        assert threads[0].is_alive() and owner["status"] == "running"
        assert not claim_search(registry, 1, {"operation_id": str(uuid.uuid4()), "status": "running"})
    finally:
        release.set()
        for thread in threads:
            thread.join(5)
    assert not threads[0].is_alive() and owner["status"] == "completed"


@pytest.mark.parametrize("state", [None, "foreign", "completed"])
def test_launch_requires_its_current_running_claim(state):
    operation = str(uuid.uuid4())
    owner = {"operation_id": str(uuid.uuid4()) if state == "foreign" else operation,
             "status": "completed" if state == "completed" else "running"}
    registry = {} if state is None else {1: owner}
    factory, work = Mock(), Mock()
    response = launch_search_worker(registry, 1, work, {"operation_id": operation}, thread_factory=factory)
    assert response["status"] == "unavailable"
    factory.assert_not_called()
    work.assert_not_called()
    if state is not None:
        assert owner["status"] == ("completed" if state == "completed" else "running")
