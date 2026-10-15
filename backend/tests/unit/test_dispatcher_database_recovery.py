"""Standalone outbox cycles reconnect instead of retaining broken DB sessions."""
import io
import signal
from itertools import count
from types import SimpleNamespace

import pytest
from django.core.management.base import CommandError
from django.db import DatabaseError, InterfaceError, OperationalError, connection, connections

from execution_jobs import service
from execution_jobs.management.commands import dispatch_jobs
from execution_jobs.models import QueueLock

pytestmark = pytest.mark.unit


def controller(monkeypatch):
    handlers = {}
    monkeypatch.setattr(dispatch_jobs, "signal", SimpleNamespace(
        SIGTERM=signal.SIGTERM, SIGINT=signal.SIGINT,
        signal=lambda signum, handler: handlers.setdefault(signum, handler)))
    ticks = count(step=10)
    monkeypatch.setattr(dispatch_jobs, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    output, errors = io.StringIO(), io.StringIO()
    return dispatch_jobs.Command(stdout=output, stderr=errors), handlers, output, errors


@pytest.mark.parametrize("outcome", ["healthy", "database", "policy", "unexpected"])
def test_once_releases_connections_on_every_exit(monkeypatch, outcome):
    command, _, output, errors = controller(monkeypatch)
    calls = []
    failures = {"database": DatabaseError("private-db-sentinel"),
                "policy": service.JobConflict("job_service_disabled"),
                "unexpected": RuntimeError("unexpected-sentinel")}

    def dispatch(**kwargs):
        calls.append("dispatch")
        if outcome in failures:
            raise failures[outcome]
        return {"delivered": 0, "broker_unavailable": 0}

    monkeypatch.setattr(dispatch_jobs, "close_old_connections", lambda: calls.append("cleanup"), raising=False)
    monkeypatch.setattr(dispatch_jobs, "dispatch_once", dispatch)
    if outcome == "healthy":
        command.handle(once=True)
    else:
        expected = RuntimeError if outcome == "unexpected" else CommandError
        with pytest.raises(expected) as caught:
            command.handle(once=True)
        if outcome == "database":
            assert str(caught.value) == "job_storage_unavailable"
    assert calls == ["cleanup", "dispatch", "cleanup"]
    assert "private-db-sentinel" not in output.getvalue() + errors.getvalue()


@pytest.mark.parametrize("failure", [OperationalError, InterfaceError])
def test_continuous_storage_failure_cleans_before_the_next_cycle(monkeypatch, failure):
    command, handlers, output, errors = controller(monkeypatch)
    calls, cycles = [], []

    def dispatch(**kwargs):
        calls.append("dispatch")
        cycles.append(1)
        if len(cycles) == 1:
            raise failure("private-db-sentinel")
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        return {"delivered": 0, "broker_unavailable": 0}

    monkeypatch.setattr(dispatch_jobs, "close_old_connections", lambda: calls.append("cleanup"), raising=False)
    monkeypatch.setattr(dispatch_jobs, "dispatch_once", dispatch)
    command.handle(once=False)
    assert calls == ["cleanup", "dispatch", "cleanup"] * 2
    assert errors.getvalue().strip() == "job_storage_unavailable; retrying"
    assert "private-db-sentinel" not in output.getvalue() + errors.getvalue()


@pytest.mark.parametrize("failure", [service.JobConflict("job_service_disabled"), RuntimeError("unexpected")])
def test_continuous_fatal_failure_still_retires_connections(monkeypatch, failure):
    command, _, _, _ = controller(monkeypatch)
    calls = []

    def dispatch(**kwargs):
        raise failure

    monkeypatch.setattr(dispatch_jobs, "close_old_connections", lambda: calls.append("cleanup"), raising=False)
    monkeypatch.setattr(dispatch_jobs, "dispatch_once", dispatch)
    with pytest.raises(CommandError if isinstance(failure, service.JobConflict) else RuntimeError):
        command.handle(once=False)
    assert calls == ["cleanup", "cleanup"]


@pytest.mark.parametrize("health_checks", [False, True])
@pytest.mark.django_db(transaction=True)
def test_actual_terminated_postgresql_session_recovers_without_restarting_dispatcher(monkeypatch, health_checks):
    command, handlers, output, errors = controller(monkeypatch)
    monkeypatch.setitem(connection.settings_dict, "CONN_MAX_AGE", None)
    monkeypatch.setitem(connection.settings_dict, "CONN_HEALTH_CHECKS", health_checks)
    connection.close()
    attempts, sessions = [], []
    killer = connections["default"].copy(alias="dispatcher-termination-fixture")

    def dispatch(**kwargs):
        attempts.append(1)
        assert len(attempts) <= 2, "dispatcher retained its unusable database session"
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                sessions.append(cursor.fetchone()[0])
            if len(attempts) == 1:
                # Terminate this test's own session only; never a server/service.
                with killer.cursor() as cursor:
                    cursor.execute("SELECT pg_terminate_backend(%s)", [sessions[0]])
                    assert cursor.fetchone() == (True,)
                # Observe a driver failure outside an atomic block, whose
                # rollback handler would otherwise close the broken session.
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
        elif len(attempts) == 1:
            # SQLite has no server session to terminate. Keep the development
            # reference and redaction behavior exercised without a new skip.
            raise OperationalError("private-db-sentinel")
        due = service.reconcile()
        assert due == [] and QueueLock.objects.filter(pk=1).exists()
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        return {"delivered": 0, "broker_unavailable": 0}

    monkeypatch.setattr(dispatch_jobs, "dispatch_once", dispatch)
    try:
        command.handle(once=False)
        assert len(attempts) == 2
        if connection.vendor == "postgresql":
            assert len(sessions) == 2 and sessions[0] != sessions[1]
        assert errors.getvalue().strip() == "job_storage_unavailable; retrying"
        assert "private-db-sentinel" not in output.getvalue() + errors.getvalue()
    finally:
        killer.close()
        connection.close()


@pytest.mark.django_db(transaction=True)
def test_obsolete_connection_is_retired_before_first_cycle(monkeypatch):
    command, _, _, _ = controller(monkeypatch)
    monkeypatch.setitem(connection.settings_dict, "CONN_MAX_AGE", 0)
    connection.ensure_connection()
    previous = connection.connection
    connection.close_at = -1
    observed = []

    def dispatch(**kwargs):
        observed.append(connection.connection)
        assert service.reconcile() == []
        return {"delivered": 0, "broker_unavailable": 0}

    monkeypatch.setattr(dispatch_jobs, "dispatch_once", dispatch)
    command.handle(once=True)
    if connection.vendor == "postgresql":
        assert observed == [None]
        assert connection.connection is not previous
    else:
        # Django deliberately retains its in-memory SQLite test database when
        # close() is requested. The real queue read still succeeds.
        assert len(observed) == 1 and QueueLock.objects.filter(pk=1).exists()
