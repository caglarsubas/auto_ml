"""Storage preparation failures cannot strand admitted searches as running."""
import copy
import json
import threading
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from modeling.search_admission import update_search_progress
from modeling.search_worker import launch_search_worker
from tests.unit.test_search_worker_launch import worker_api as worker_api

pytestmark = pytest.mark.unit


class InlineThread:
    def __init__(self, target):
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def inline_api(worker_api, monkeypatch):
    monkeypatch.setattr(threading, "Thread", InlineThread)
    return worker_api


@pytest.mark.parametrize("error_type", [PermissionError, OSError, FileExistsError])
def test_directory_failure_is_terminal_correlated_and_preserves_prior_evidence(inline_api, monkeypatch, caplog, capsys, error_type):
    from modeling import views

    registry, submit, progress, path, prior, search = inline_api
    original = views.os.makedirs

    def prepare(directory, *args, **kwargs):
        if Path(directory) == path.parent:
            raise error_type("STORAGE_SETUP_SECRET")
        return original(directory, *args, **kwargs)

    monkeypatch.setattr(views.os, "makedirs", prepare)
    response = submit()
    assert response.status_code == 200 and response.data["status"] == "started"
    current = progress().data
    assert current["status"] == "error" and registry[1]["status"] == "error"
    assert current["failure"]["stage"] == "worker_storage_setup"
    assert current["failure"]["exception_type"] == error_type.__name__
    assert current["operation_id"] == current["failure"]["operation_id"] == response.data["operation_id"]
    assert current["failure"]["execution_id"] == "source-run"
    assert path.read_bytes() == prior and sorted(path.parent.iterdir()) == [path]
    assert current.get("storage_failure") is None
    search.assert_not_called()
    output = capsys.readouterr()
    assert "STORAGE_SETUP_SECRET" not in caplog.text + output.out + output.err + json.dumps(current) + json.dumps(response.data)


def test_real_blocking_file_is_preserved_and_does_not_leave_a_running_owner(inline_api):
    registry, submit, progress, path, _, search = inline_api
    path.unlink()
    path.parent.rmdir()
    path.parent.write_bytes(b"owned-blocking-file")
    response = submit()
    assert response.status_code == 200
    assert progress().data["failure"]["exception_type"] == "FileExistsError"
    assert progress().data["failure"]["stage"] == "worker_storage_setup"
    assert registry[1]["status"] == "error" and path.parent.read_bytes() == b"owned-blocking-file"
    search.assert_not_called()


def test_recovered_storage_allows_a_fresh_retry_with_the_same_capacity_limit(inline_api, monkeypatch):
    from modeling import views

    registry, submit, _, path, prior, search = inline_api
    peer_name = "HYPERPARAM_PROGRESS" if registry is views.SFS_PROGRESS else "SFS_PROGRESS"
    peer = {2: {"status": "running", "operation_id": str(uuid.uuid4())}}
    monkeypatch.setattr(views, peer_name, peer)
    original = views.os.makedirs

    def failed(directory, *args, **kwargs):
        if Path(directory) == path.parent:
            raise PermissionError("temporary storage failure")
        return original(directory, *args, **kwargs)

    monkeypatch.setattr(views.os, "makedirs", failed)
    first = submit()
    assert first.status_code == 200 and registry[1]["status"] == "error"
    monkeypatch.setattr(views.os, "makedirs", original)

    class PendingThread:
        def __init__(self, target):
            pass

        def start(self):
            pass

    monkeypatch.setattr(threading, "Thread", PendingThread)
    second = submit()
    assert second.status_code == 200 and second.data["status"] == "started"
    assert second.data["operation_id"] != first.data["operation_id"]
    assert registry[1]["operation_id"] == second.data["operation_id"] and registry[1]["status"] == "running"
    assert peer[2]["status"] == "running" and path.read_bytes() == prior
    search.assert_not_called()


@pytest.mark.parametrize("ownership", ["current", "replace", "retoken", "remove"])
def test_preparation_failure_cannot_change_a_different_operation(ownership, caplog):
    operation = str(uuid.uuid4())
    owner = {"operation_id": operation, "status": "running"}
    registry, snapshots = {1: owner}, []
    work = Mock()

    def prepare():
        if ownership == "replace":
            registry[1] = {"operation_id": str(uuid.uuid4()), "status": "running"}
        elif ownership == "retoken":
            owner["operation_id"] = str(uuid.uuid4())
        elif ownership == "remove":
            registry.pop(1)
        snapshots.append(copy.deepcopy(registry))
        raise PermissionError("PREPARATION_SECRET")

    result = launch_search_worker(registry, 1, work, {"operation_id": operation},
                                  prepare=prepare, thread_factory=InlineThread)
    assert result is None
    work.assert_not_called()
    if ownership == "current":
        assert owner["status"] == "error" and owner["failure"]["stage"] == "worker_storage_setup"
        assert owner["failure"]["operation_id"] == operation
    else:
        assert registry == snapshots[0]
    assert "PREPARATION_SECRET" not in caplog.text + json.dumps(registry)


@pytest.mark.parametrize("mode", ["inline", "thread"])
def test_successful_preparation_precedes_work_in_the_same_execution_thread(mode):
    operation = str(uuid.uuid4())
    owner = {"operation_id": operation, "status": "running"}
    registry, events, threads = {1: owner}, [], []

    def prepare():
        events.append(("prepare", threading.get_ident()))

    def work():
        assert events and events[0][0] == "prepare"
        events.append(("work", threading.get_ident()))
        assert update_search_progress(registry, 1, owner, operation, {"status": "completed"})

    def factory(target):
        thread = InlineThread(target) if mode == "inline" else threading.Thread(target=target)
        threads.append(thread)
        return thread

    assert launch_search_worker(registry, 1, work, {"operation_id": operation}, prepare=prepare, thread_factory=factory) is None
    if mode == "thread":
        threads[0].join(5)
        assert not threads[0].is_alive()
        assert events[0][1] != threading.get_ident()
    assert [name for name, _ in events] == ["prepare", "work"]
    assert events[0][1] == events[1][1] and owner["status"] == "completed"


def test_real_worker_cleans_up_after_preparation_failure_and_retains_both_diagnostics(monkeypatch, caplog):
    from modeling import search_worker

    operation = str(uuid.uuid4())
    owner = {"operation_id": operation, "status": "running"}
    registry, events, threads = {1: owner}, [], []
    work = Mock()

    def setup():
        events.append(("setup", threading.get_ident()))

    def prepare():
        events.append(("prepare", threading.get_ident()))
        raise PermissionError("PREPARATION_SECRET")

    def cleanup():
        events.append(("cleanup", threading.get_ident()))
        raise RuntimeError("CLEANUP_SECRET")

    def factory(target):
        thread = threading.Thread(target=target)
        threads.append(thread)
        return thread

    monkeypatch.setattr(search_worker, "close_old_connections", setup)
    monkeypatch.setattr(search_worker.connections, "close_all", cleanup)
    assert launch_search_worker(registry, 1, work, {"operation_id": operation}, prepare=prepare, thread_factory=factory) is None
    threads[0].join(5)
    assert not threads[0].is_alive()
    assert [name for name, _ in events] == ["setup", "prepare", "cleanup"]
    assert len({thread for _, thread in events}) == 1 and events[0][1] != threading.get_ident()
    assert owner["status"] == "error" and owner["failure"]["stage"] == "worker_storage_setup"
    assert owner["cleanup_failure"]["stage"] == "worker_cleanup"
    assert owner["failure"]["operation_id"] == owner["cleanup_failure"]["operation_id"] == operation
    work.assert_not_called()
    assert "PREPARATION_SECRET" not in caplog.text + json.dumps(owner)
    assert "CLEANUP_SECRET" not in caplog.text + json.dumps(owner)
