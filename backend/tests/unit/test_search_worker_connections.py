"""Real thread connection lifetime and correlated lifecycle failures."""
import copy
import threading
import uuid
from unittest.mock import Mock

import pytest
from django.db import connections

from modeling import search_worker

pytestmark = pytest.mark.unit


def launch(target, owner=None):
    operation = str(uuid.uuid4())
    owner = owner if owner is not None else {"status": "running", "operation_id": operation}
    context = {"operation": "hyperparam", "file_id": 1, "operation_id": owner["operation_id"], "execution_id": "source"}
    registry, threads = {1: owner}, []

    def factory(target):
        thread = threading.Thread(target=target)
        threads.append(thread)
        return thread

    response = search_worker.launch_search_worker(registry, 1, lambda: target(registry, owner), context,
                                                  thread_factory=factory)
    assert response is None and len(threads) == 1
    threads[0].join(5)
    assert not threads[0].is_alive()
    return registry, owner, context


@pytest.mark.parametrize("outcome", ["completed", "stopped", "error"])
def test_real_worker_closes_its_database_connection_and_preserves_caller(transactional_db, django_db_blocker, tmp_path, outcome):
    caller = connections["default"]
    with caller.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
    original, workers = caller.connection, []
    alias = "worker_proof_" + uuid.uuid4().hex
    configuration = copy.deepcopy(caller.settings_dict)
    if caller.vendor == "sqlite":
        # Django intentionally keeps in-memory test databases open. Exercise a
        # real file connection so that the same closure assertion is meaningful.
        configuration["NAME"] = str(tmp_path / "worker.sqlite3")
    connections.databases[alias] = configuration

    def work(registry, owner):
        worker = connections[alias]
        with worker.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
        workers.append((worker, worker.connection))  # Retain it beyond thread exit; GC cannot prove cleanup.
        if outcome == "error":
            raise ValueError("WORKER_EXECUTION_SECRET")
        owner["status"] = outcome

    try:
        with django_db_blocker.unblock():
            _, owner, context = launch(work)
    finally:
        connections.databases.pop(alias)
    assert len(workers) == 1 and workers[0][0] is not caller and workers[0][1] is not original
    assert workers[0][0].connection is None
    assert caller.connection is original
    with caller.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
    assert owner["status"] == outcome
    if outcome == "error":
        assert owner["failure"]["stage"] == "worker_execution"
        assert owner["failure"]["operation_id"] == context["operation_id"]
        assert "WORKER_EXECUTION_SECRET" not in str(owner)


@pytest.mark.parametrize("stage", ["worker_setup", "worker_execution", "worker_cleanup"])
@pytest.mark.parametrize("ownership", ["current", "replace", "retoken", "remove"])
def test_lifecycle_failures_are_redacted_and_cannot_change_other_owners(monkeypatch, caplog, stage, ownership):
    events, expected = [], []
    owner = {"operation_id": str(uuid.uuid4()), "status": "running", "sentinel": "original"}
    registry_ref = []

    def fault():
        registry = registry_ref[0]
        if ownership == "replace":
            registry[1] = {"operation_id": str(uuid.uuid4()), "status": "running", "sentinel": "newer"}
        elif ownership == "retoken":
            owner["operation_id"] = str(uuid.uuid4())
        elif ownership == "remove":
            registry.pop(1)
        expected.append(copy.deepcopy(registry))
        raise RuntimeError("LIFECYCLE_SECRET")

    def setup():
        events.append(("setup", threading.get_ident()))
        if stage == "worker_setup":
            fault()

    def work(registry, current):
        events.append(("work", threading.get_ident()))
        if stage == "worker_execution":
            fault()
        current["status"] = "completed"

    def cleanup():
        events.append(("cleanup", threading.get_ident()))
        if stage == "worker_cleanup":
            fault()

    monkeypatch.setattr(search_worker, "close_old_connections", setup)
    monkeypatch.setattr(search_worker.connections, "close_all", cleanup)

    class PreparedThread(threading.Thread):
        def start(self):
            registry_ref.append(registry)
            super().start()

    registry = {1: owner}
    context = {"operation": "sfs", "file_id": 1, "operation_id": owner["operation_id"], "execution_id": "source"}
    threads = []

    def factory(target):
        thread = PreparedThread(target=target)
        threads.append(thread)
        return thread

    assert search_worker.launch_search_worker(registry, 1, lambda: work(registry, owner), context,
                                             thread_factory=factory) is None
    threads[0].join(5)
    assert not threads[0].is_alive()
    assert [e[0] for e in events] == (["setup", "cleanup"] if stage == "worker_setup" else ["setup", "work", "cleanup"])
    assert all(e[1] != threading.get_ident() for e in events)
    if ownership != "current":
        assert registry == expected[0]
    elif stage == "worker_cleanup":
        assert owner["status"] == "completed" and "failure" not in owner
        assert owner["cleanup_failure"]["stage"] == stage
        assert owner["cleanup_failure"]["operation_id"] == context["operation_id"]
    else:
        assert owner["status"] == "error" and owner["failure"]["stage"] == stage
        assert owner["failure"]["operation_id"] == context["operation_id"]
    assert "LIFECYCLE_SECRET" not in str(registry) + caplog.text


def test_cleanup_failure_preserves_the_original_execution_failure(monkeypatch):
    monkeypatch.setattr(search_worker, "close_old_connections", Mock())
    monkeypatch.setattr(search_worker.connections, "close_all", Mock(side_effect=RuntimeError("cleanup secret")))

    def work(registry, owner):
        raise ValueError("execution secret")

    _, owner, context = launch(work)
    assert owner["status"] == "error" and owner["failure"]["stage"] == "worker_execution"
    assert owner["cleanup_failure"]["stage"] == "worker_cleanup"
    assert owner["failure"]["operation_id"] == owner["cleanup_failure"]["operation_id"] == context["operation_id"]
    assert "secret" not in str(owner)


def test_inline_factory_keeps_caller_connection_lifetime_and_transaction(db, monkeypatch):
    setup, cleanup = Mock(), Mock()
    monkeypatch.setattr(search_worker, "close_old_connections", setup)
    monkeypatch.setattr(search_worker.connections, "close_all", cleanup)
    caller = connections["default"]
    original = caller.connection
    operation = str(uuid.uuid4())
    owner = {"status": "running", "operation_id": operation}

    class InlineThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            self.target()

    assert search_worker.launch_search_worker({1: owner}, 1, lambda: owner.update(status="completed"),
        {"operation_id": operation}, thread_factory=InlineThread) is None
    setup.assert_not_called()
    cleanup.assert_not_called()
    assert caller.connection is original and caller.in_atomic_block and owner["status"] == "completed"
