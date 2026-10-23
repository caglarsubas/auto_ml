"""Scoped handoff SQL limits, real PostgreSQL cancellation and safe API errors."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from access_control import projects
from access_control.models import ProjectMembership
from execution_jobs import operational_handoff as handoff, service
from execution_jobs.models import JobEvent, NativeJob, QueueLock
from modeling.models import HoldoutAccess
from tests.unit.test_native_handoff_history_counter import world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def bounded():
    # Permit the exact pre-fix source to run the new regression assertions.
    return getattr(handoff, "_bounded_read", service.locked)()


def milliseconds():
    with connection.cursor() as cursor:
        cursor.execute("SELECT setting::bigint FROM pg_settings WHERE name = 'statement_timeout'")
        return cursor.fetchone()[0]


def configure(value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", [f"{value}ms"])


def state():
    return (list(NativeJob.objects.values()), list(JobEvent.objects.values()), list(HoldoutAccess.objects.values()))


@pytest.mark.parametrize("previous,configured,expected", [("0", 0, "5000ms"), ("17s", 17000, "5000ms"),
                                                          ("2s", 2000, "2000ms"), ("1ms", 1, "1ms")])
def test_postgresql_contract_applies_before_queue_lock_and_restores_after_it(monkeypatch, previous, configured, expected):
    events, cursor = [], MagicMock()
    cursor.fetchone.return_value = (previous, configured)
    cursor.execute.side_effect = lambda sql, params=None: events.append((sql, params))
    fake = SimpleNamespace(vendor="postgresql", cursor=MagicMock())
    fake.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def lock():
        events.append(("lock", None))
        yield
        events.append(("unlock", None))

    monkeypatch.setattr(handoff, "connection", fake)
    monkeypatch.setattr(service, "locked", lock)
    with bounded():
        events.append(("body", None))
    assert events == [
        ("SELECT current_setting('statement_timeout'), setting::bigint FROM pg_settings WHERE name = 'statement_timeout'", None),
        ("SELECT set_config('statement_timeout', %s, true)", [expected]),
        ("lock", None), ("body", None), ("unlock", None),
        ("SELECT set_config('statement_timeout', %s, true)", [previous]),
    ]


@pytest.mark.parametrize("initial", [0, 17000, 2000, 1000])
def test_actual_handoff_uses_effective_limit_then_restores_outer_setting(world, initial):  # noqa: F811
    postgres = connection.vendor == "postgresql"
    original = milliseconds() if postgres else None
    observed = []

    def inspect(execute, sql, params, many, context):
        if sql.startswith("SELECT") and '"execution_jobs_nativejob"' in sql:
            observed.append(milliseconds() if postgres else "sqlite")
        return execute(sql, params, many, context)

    before = state()
    with transaction.atomic():
        if postgres:
            configure(initial)
        with connection.execute_wrapper(inspect), CaptureQueriesContext(connection) as queries:
            receipt = handoff.read(world.actor, world.job.pk, "0")
        assert observed and set(observed) == {min(initial or 5000, 5000) if postgres else "sqlite"}
        if postgres:
            assert milliseconds() == initial
        else:
            assert not any("set_config" in q["sql"] or "pg_settings" in q["sql"] for q in queries)
        assert receipt["read_only"] and receipt["revision"] == 0
    if postgres:
        assert milliseconds() == original
    assert state() == before


@pytest.mark.parametrize("outcome", ["normal", "python_error", "database_error", "rollback"])
def test_normal_failure_and_rollback_restore_settings_and_atomicity(outcome):
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
                        cursor.execute("SELECT * FROM declarai_intentionally_absent_handoff_fixture")
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


def test_nested_postgresql_scopes_restore_enclosing_limit():
    if connection.vendor != "postgresql":
        # The development file lock is deliberately not recursive.
        for _ in range(2):
            with bounded():
                assert QueueLock.objects.filter(pk=1).exists()
        return
    original = milliseconds()
    with transaction.atomic():
        configure(17000)
        with bounded():
            assert milliseconds() == 5000
            with bounded():
                assert milliseconds() == 5000
            assert milliseconds() == 5000
        assert milliseconds() == 17000
    assert milliseconds() == original


def test_actual_postgresql_cancels_slow_access_query_and_releases_queue_lock(world):  # noqa: F811
    before = state()
    if connection.vendor != "postgresql":
        with bounded():
            assert QueueLock.objects.filter(pk=1).exists()
        assert state() == before
        return
    original = milliseconds()

    def slow(execute, sql, params, many, context):
        if sql.startswith("SELECT") and '"modeling_holdoutaccess"' in sql:
            execute("SELECT pg_sleep(6)", None, False, context)
        return execute(sql, params, many, context)

    with transaction.atomic():
        configure(0)
        with connection.execute_wrapper(slow), pytest.raises(DatabaseError) as caught:
            handoff.read(world.actor, world.job.pk, "0")
        cause = caught.value.__cause__
        assert getattr(cause, "sqlstate", getattr(cause, "pgcode", None)) == "57014"
        assert milliseconds() == 0 and not connection.needs_rollback
        with service.locked():
            assert QueueLock.objects.filter(pk=1).exists()
    assert milliseconds() == original and state() == before


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("table", ["execution_jobs_nativejob", "modeling_holdoutaccess"])
def test_query_cancellation_has_safe_uncached_http_failure(world, monkeypatch, method, table):  # noqa: F811
    before = state()
    postgres = connection.vendor == "postgresql"
    active = False
    actual = handoff.read

    def read(*args, **kwargs):
        nonlocal active
        active = True
        try:
            return actual(*args, **kwargs)
        finally:
            active = False

    monkeypatch.setattr(handoff, "read", read)

    def unavailable(execute, sql, params, many, context):
        if active and sql.startswith("SELECT") and f'"{table}"' in sql:
            if postgres:
                execute("SELECT pg_sleep(1)", None, False, context)
            else:
                raise DatabaseError("private driver details must not leak")
        return execute(sql, params, many, context)

    client = APIClient()
    client.force_authenticate(user=world.actor)
    with transaction.atomic():
        if postgres:
            configure(100)
        with connection.execute_wrapper(unavailable):
            response = getattr(client, method)(f"/api/jobs/{world.job.pk}/operational-handoff/", {"revision": "0"})
        assert response.status_code == 503 and response["Cache-Control"] == "no-store"
        assert response.content == b"" if method == "head" else response.json() == {"error_code": "job_storage_unavailable"}
        if postgres:
            assert milliseconds() == 100
        assert not connection.needs_rollback and state() == before


@pytest.mark.parametrize("denial", ["outsider", "revoked", "stale", "event_gap"])
def test_earlier_authority_revision_and_history_guards_still_precede_access_queries(world, monkeypatch, denial):  # noqa: F811
    if denial == "revoked":
        ProjectMembership.objects.filter(actor=world.actor).update(active=False)
    if denial == "event_gap":
        NativeJob.objects.filter(pk=world.job.pk).update(revision=1)
    before = state()
    monkeypatch.setattr(HoldoutAccess.objects, "filter", lambda *a, **k: pytest.fail("access before guard"))
    actor = world.outsider if denial == "outsider" else world.actor
    expected = projects.ProjectDenied if denial in {"outsider", "revoked"} else service.JobConflict
    code = "job_handoff_stale" if denial == "stale" else "job_event_history_invalid" if denial == "event_gap" else "project_access_denied"
    with pytest.raises(expected) as caught:
        handoff.read(actor, world.job.pk, "1" if denial in {"stale", "event_gap"} else "0")
    assert caught.value.code == code
    assert state() == before


@pytest.mark.parametrize("count", [0, 1, 8, 32])
def test_full_receipt_and_repeatable_digest_remain_read_only(world, count):  # noqa: F811
    NativeJob.objects.filter(pk=world.job.pk).update(revision=count)
    JobEvent.objects.bulk_create([JobEvent(job=world.job, revision=n, event_type="fixture_receipt") for n in range(1, count + 1)])
    before = state()
    receipt = handoff.read(world.actor, world.job.pk, str(count))
    assert handoff.read(world.actor, world.job.pk, str(count), receipt["sha256"]) == receipt
    assert [e["revision"] for e in receipt["events"]] == list(range(1, count + 1))
    assert receipt["sha256"] == service.digest({k: v for k, v in receipt.items() if k != "sha256"})
    assert receipt["read_only"] and not any(receipt[k] for k in ["recovery_authorized", "review_approved", "production_use_approved"])
    assert state() == before
