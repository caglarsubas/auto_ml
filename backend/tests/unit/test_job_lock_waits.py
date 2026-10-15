"""Native metadata lock waits are bounded without leaking caller settings."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from django.db import DatabaseError, connection, connections, transaction

from execution_jobs import service
from execution_jobs.models import QueueLock

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


def milliseconds(name="lock_timeout"):
    with connection.cursor() as cursor:
        cursor.execute("SELECT setting::bigint FROM pg_settings WHERE name = %s", [name])
        return cursor.fetchone()[0]


def local_timeout(value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('lock_timeout', %s, true)", [f"{value}ms"])


@pytest.mark.parametrize("previous,configured,expected", [("0", 0, "5000ms"), ("17s", 17000, "5000ms"),
                                                          ("2s", 2000, "2000ms"), ("1ms", 1, "1ms")])
def test_postgresql_contract_bounds_before_bootstrap_and_restores_after_body(monkeypatch, previous, configured, expected):
    cursor, manager, events = MagicMock(), Mock(), []
    cursor.fetchone.return_value = (previous, configured)
    cursor.execute.side_effect = lambda sql, params=None: events.append((sql, params))
    manager.get_or_create.side_effect = lambda **kwargs: events.append(("bootstrap", kwargs))
    manager.select_for_update.return_value.get.side_effect = lambda **kwargs: events.append(("row_lock", kwargs))
    fake = SimpleNamespace(vendor="postgresql", cursor=MagicMock())
    fake.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(service, "connection", fake)
    monkeypatch.setattr(service, "QueueLock", SimpleNamespace(objects=manager))
    with service.locked():
        events.append(("body", None))
    assert events == [
        ("SELECT current_setting('lock_timeout'), setting::bigint FROM pg_settings WHERE name = 'lock_timeout'", None),
        ("SELECT set_config('lock_timeout', %s, true)", [expected]),
        ("bootstrap", {"pk": 1}), ("row_lock", {"pk": 1}), ("body", None),
        ("SELECT set_config('lock_timeout', %s, true)", [previous]),
    ]


@pytest.mark.parametrize("initial", [0, 17000, 2000, 1])
def test_effective_server_limit_and_outer_transaction_restoration(initial):
    if connection.vendor != "postgresql":
        with transaction.atomic(), service.locked():
            assert QueueLock.objects.filter(pk=1).exists()
        return
    original, statement = milliseconds(), milliseconds("statement_timeout")
    with transaction.atomic():
        local_timeout(initial)
        with service.locked():
            assert milliseconds() == min(initial or 5000, 5000)
            assert milliseconds("statement_timeout") == statement
        assert milliseconds() == initial
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    assert milliseconds() == original and milliseconds("statement_timeout") == statement


@pytest.mark.parametrize("outcome", ["normal", "python_error", "database_error", "rollback"])
def test_success_error_and_explicit_rollback_preserve_caller_state(outcome):
    postgres = connection.vendor == "postgresql"
    original = milliseconds() if postgres else None
    with transaction.atomic():
        if postgres:
            local_timeout(17000)
        try:
            with service.locked():
                QueueLock.objects.create(pk=3)
                if outcome == "python_error":
                    raise ValueError("test rollback")
                if outcome == "database_error":
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT * FROM declarai_intentionally_absent_lock_fixture")
                if outcome == "rollback":
                    transaction.set_rollback(True)
        except (ValueError, DatabaseError):
            assert outcome in {"python_error", "database_error"}
        assert QueueLock.objects.filter(pk=3).exists() is (outcome == "normal")
        if postgres:
            assert milliseconds() == 17000
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    if postgres:
        assert milliseconds() == original


def test_nested_scopes_restore_the_enclosing_limit():
    if connection.vendor != "postgresql":
        # SQLite's file lock is intentionally not recursively acquired.
        for _ in range(2):
            with service.locked():
                assert QueueLock.objects.filter(pk=1).exists()
        return
    original = milliseconds()
    with transaction.atomic():
        local_timeout(17000)
        with service.locked():
            assert milliseconds() == 5000
            with service.locked():
                assert milliseconds() == 5000
            assert milliseconds() == 5000
        assert milliseconds() == 17000
    assert milliseconds() == original


@pytest.mark.parametrize("phase", ["existing_row", "bootstrap", "body_row"])
def test_actual_postgresql_contention_times_out_without_partial_metadata(phase):
    if connection.vendor != "postgresql":
        with service.locked():
            assert QueueLock.objects.get(pk=1).pk == 1
        return
    if phase != "bootstrap":
        QueueLock.objects.create(pk=1)
    if phase == "body_row":
        QueueLock.objects.create(pk=2)
    ready, release = threading.Event(), threading.Event()
    failures = []

    def holder():
        try:
            with transaction.atomic():
                if phase == "bootstrap":
                    QueueLock.objects.create(pk=1)
                else:
                    QueueLock.objects.select_for_update().get(pk=2 if phase == "body_row" else 1)
                ready.set()
                assert release.wait(20)
        except BaseException as error:
            failures.append(error)
            ready.set()
        finally:
            connections.close_all()

    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert ready.wait(5) and not failures
        started = time.monotonic()
        with pytest.raises(DatabaseError) as caught:
            with service.locked():
                QueueLock.objects.create(pk=3)
                if phase == "body_row":
                    QueueLock.objects.select_for_update().get(pk=2)
        elapsed = time.monotonic() - started
        cause = caught.value.__cause__
        assert getattr(cause, "sqlstate", getattr(cause, "pgcode", None)) == "55P03"
        assert 4 <= elapsed < 15 and not release.is_set()
        assert not QueueLock.objects.filter(pk=3).exists()
        assert not connection.needs_rollback
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not failures
    with service.locked():
        QueueLock.objects.create(pk=3)
    assert QueueLock.objects.filter(pk=3).exists()


def test_development_sqlite_retains_its_existing_file_lock_and_atomicity():
    with service.locked():
        assert QueueLock.objects.filter(pk=1).count() == 1
    with pytest.raises(ValueError):
        with service.locked():
            QueueLock.objects.create(pk=2)
            raise ValueError("rollback")
    assert not QueueLock.objects.filter(pk=2).exists()
