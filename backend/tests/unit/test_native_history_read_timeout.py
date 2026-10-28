"""Bound history SQL without acquiring execution authority or the queue lock."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.db import DatabaseError, connection, transaction
from django.http import QueryDict
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from access_control import projects
from execution_jobs import history, service
from execution_jobs.models import JobEvent, NativeJob, QueueLock
from modeling.models import HoldoutAccess
from tests.unit.test_native_handoff_history_counter import world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def bounded():
    return getattr(history, "_bounded_read", nullcontext)()


def milliseconds():
    with connection.cursor() as cursor:
        cursor.execute("SELECT setting::bigint FROM pg_settings WHERE name = 'statement_timeout'")
        return cursor.fetchone()[0]


def configure(value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", [f"{value}ms"])


def snapshot():
    return [list(model.objects.order_by("pk").values()) for model in [NativeJob, JobEvent, HoldoutAccess, QueueLock]]


@pytest.mark.parametrize("previous,configured,expected", [("0", 0, "5000ms"), ("17s", 17000, "5000ms"),
                                                          ("2s", 2000, "2000ms"), ("1ms", 1, "1ms")])
def test_postgresql_scope_limits_each_statement_and_restores_exact_caller_setting(monkeypatch, previous, configured, expected):
    events, cursor = [], MagicMock()
    cursor.fetchone.return_value = (previous, configured)
    cursor.execute.side_effect = lambda sql, params=None: events.append((sql, params))
    fake = SimpleNamespace(vendor="postgresql", cursor=MagicMock())
    fake.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(history, "connection", fake, raising=False)
    with bounded():
        events.append(("body", None))
    assert events == [
        ("SELECT current_setting('statement_timeout'), setting::bigint FROM pg_settings WHERE name = 'statement_timeout'", None),
        ("SELECT set_config('statement_timeout', %s, true)", [expected]),
        ("body", None),
        ("SELECT set_config('statement_timeout', %s, true)", [previous]),
    ]


@pytest.mark.parametrize("initial", [0, 17000, 2000, 1000])
def test_all_actual_history_queries_use_limit_without_queue_lock_or_metadata_writes(world, monkeypatch, initial):  # noqa: F811
    postgres = connection.vendor == "postgresql"
    observed, before = [], snapshot()
    monkeypatch.setattr(service, "locked", lambda: pytest.fail("history took execution lock"))

    def inspect(execute, sql, params, many, context):
        if sql.startswith("SELECT") and '"execution_jobs_nativejob"' in sql:
            observed.append(milliseconds() if postgres else "sqlite")
        return execute(sql, params, many, context)

    original = milliseconds() if postgres else None
    with transaction.atomic():
        if postgres:
            configure(initial)
        with connection.execute_wrapper(inspect), CaptureQueriesContext(connection) as queries:
            value = history.read(world.actor, world.job.dataset_id, QueryDict())
        assert observed and set(observed) == {min(initial or 5000, 5000) if postgres else "sqlite"}
        if postgres:
            assert milliseconds() == initial
        else:
            assert not any("set_config" in q["sql"] or "pg_settings" in q["sql"] for q in queries)
        assert not any(q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries)
        assert value["read_only"] and value["queue"]["states"]["queued"] == 1
        assert [j["id"] for j in value["jobs"]] == [str(world.job.pk)]
    if postgres:
        assert milliseconds() == original
    assert snapshot() == before


@pytest.mark.parametrize("outcome", ["normal", "python_error", "database_error", "rollback"])
def test_settings_and_savepoint_restore_on_every_exit(outcome):
    postgres = connection.vendor == "postgresql"
    original = milliseconds() if postgres else None
    with transaction.atomic():
        if postgres:
            configure(17000)
        try:
            with bounded():
                if postgres:
                    assert milliseconds() == 5000
                QueueLock.objects.create(pk=3)
                if outcome == "python_error":
                    raise ValueError("fixture rollback")
                if outcome == "database_error":
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT * FROM declarai_intentionally_absent_history_fixture")
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


def test_nested_scopes_restore_enclosing_limit():
    postgres = connection.vendor == "postgresql"
    with transaction.atomic():
        if postgres:
            configure(17000)
        with bounded():
            if postgres:
                assert milliseconds() == 5000
            with bounded():
                if postgres:
                    assert milliseconds() == 5000
            if postgres:
                assert milliseconds() == 5000
        if postgres:
            assert milliseconds() == 17000


def test_actual_postgresql_cancels_unlimited_statement_and_recovers_savepoint():
    if connection.vendor != "postgresql":
        with bounded():
            assert not connection.needs_rollback
        return
    with transaction.atomic():
        configure(0)
        with pytest.raises(DatabaseError) as caught:
            with bounded(), connection.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(6)")
        cause = caught.value.__cause__
        assert getattr(cause, "sqlstate", getattr(cause, "pgcode", None)) == "57014"
        assert milliseconds() == 0 and not connection.needs_rollback
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("query", ["counts", "page"])
def test_actual_query_cancellation_is_private_uncached_and_connection_reusable(world, monkeypatch, method, query):  # noqa: F811
    postgres, active, injected = connection.vendor == "postgresql", False, []
    before, actual = snapshot(), history.read

    def read(*args, **kwargs):
        nonlocal active
        active = True
        try:
            return actual(*args, **kwargs)
        finally:
            active = False

    monkeypatch.setattr(history, "read", read)

    def slow(execute, sql, params, many, context):
        if active and sql.startswith("SELECT") and '"execution_jobs_nativejob"' in sql and (("COUNT(" in sql) == (query == "counts")):
            injected.append(True)
            if postgres:
                execute("SELECT pg_sleep(1)", None, False, context)
            else:
                raise DatabaseError("private driver details must remain private")
        return execute(sql, params, many, context)

    client = APIClient()
    client.force_authenticate(user=world.actor)
    with transaction.atomic():
        if postgres:
            configure(100)
        with connection.execute_wrapper(slow):
            response = getattr(client, method)(f"/api/jobs/datasets/{world.job.dataset_id}/history/")
        assert injected == [True]
        assert response.status_code == 503 and response["Cache-Control"] == "no-store"
        assert response.content == b"" if method == "head" else response.json() == {"error_code": "job_storage_unavailable"}
        if postgres:
            assert milliseconds() == 100
        assert not connection.needs_rollback and snapshot() == before


@pytest.mark.parametrize("invalid", ["outsider", "parameters", "cursor"])
def test_authority_and_request_guards_still_precede_job_storage(world, monkeypatch, invalid):  # noqa: F811
    monkeypatch.setattr(NativeJob.objects, "filter", lambda *a, **k: pytest.fail("job query before validation"))
    actor = world.outsider if invalid == "outsider" else world.actor
    params = QueryDict("offset=1" if invalid == "parameters" else "cursor=invalid")
    expected = projects.ProjectDenied if invalid == "outsider" else ValueError
    with pytest.raises(expected):
        history.read(actor, world.job.dataset_id, params)
