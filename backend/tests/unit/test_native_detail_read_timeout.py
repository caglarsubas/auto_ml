"""Native receipt polling bounds job, event and final authority SQL without changing serialization."""

from contextlib import contextmanager

import pytest
from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from execution_jobs import history, service
from execution_jobs.models import JobEvent, NativeJob, QueueLock
from modeling.models import HoldoutAccess
from tests.unit.test_native_handoff_history_counter import world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def milliseconds():
    with connection.cursor() as cursor:
        cursor.execute("SELECT setting::bigint FROM pg_settings WHERE name = 'statement_timeout'")
        return cursor.fetchone()[0]


def configure(value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", [f"{value}ms"])


def snapshot():
    return [list(model.objects.order_by("pk").values()) for model in [NativeJob, JobEvent, HoldoutAccess, QueueLock]]


def client_for(actor):
    client = APIClient()
    client.force_authenticate(user=actor)
    return client


def url(world):
    return f"/api/jobs/{world.job.pk}/"


def test_receipt_and_final_authority_use_bound_and_preserve_serialized_snapshot(world, monkeypatch):  # noqa: F811
    before, observed, checked, locks, audits = snapshot(), [], [], [], []
    active = False
    original, recheck, locked = history._bounded_read, service.projects.recheck, service.locked

    @contextmanager
    def bound():
        nonlocal active
        with original():
            active = True
            try:
                yield
            finally:
                active = False

    @contextmanager
    def serialized():
        locks.append(active)
        with locked():
            yield

    def inspect(execute, sql, params, many, context):
        if sql.startswith("SELECT") and ('\"execution_jobs_nativejob\".\"result\"' in sql or '\"execution_jobs_jobevent\"' in sql):
            observed.append(active)
        if sql.lstrip().startswith(("INSERT", "UPDATE")) and '"access_control_projectauthorityevent"' in sql:
            audits.append(active)
        return execute(sql, params, many, context)

    def check(*args, **kwargs):
        checked.append(active)
        return recheck(*args, **kwargs)

    monkeypatch.setattr(history, "_bounded_read", bound)
    monkeypatch.setattr(service, "locked", serialized)
    monkeypatch.setattr(service.projects, "recheck", check)
    with connection.execute_wrapper(inspect):
        response = client_for(world.actor).get(url(world))
    assert response.status_code == 200, response.content
    assert locks == [True] and observed and all(observed)
    assert True in checked and audits == [False, False]
    assert response.json()["id"] == str(world.job.pk)
    assert snapshot() == before


@pytest.mark.parametrize("initial", [0, 17000, 2000, 1000])
def test_actual_receipt_obeys_effective_postgresql_limit_and_restores_caller(world, initial):  # noqa: F811
    postgres, observed, before = connection.vendor == "postgresql", [], snapshot()
    original = milliseconds() if postgres else None

    def inspect(execute, sql, params, many, context):
        if sql.startswith("SELECT") and '"execution_jobs_nativejob"."result"' in sql:
            observed.append(milliseconds() if postgres else "sqlite")
        return execute(sql, params, many, context)

    with transaction.atomic():
        if postgres:
            configure(initial)
        with connection.execute_wrapper(inspect), CaptureQueriesContext(connection) as queries:
            response = client_for(world.actor).get(url(world))
        assert response.status_code == 200, response.content
        assert observed and set(observed) == {min(initial or 5000, 5000) if postgres else "sqlite"}
        assert response.json()["id"] == str(world.job.pk)
        if postgres:
            assert milliseconds() == initial
        else:
            assert not any("set_config" in q["sql"] or "pg_settings" in q["sql"] for q in queries)
    if postgres:
        assert milliseconds() == original
    assert snapshot() == before


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("query", ["job", "events", "authority"])
def test_actual_receipt_cancellation_returns_private_uncached_failure_without_poisoning_connection(world, monkeypatch, method, query):  # noqa: F811
    postgres, injected, before = connection.vendor == "postgresql", [], snapshot()

    def slow(execute, sql, params, many, context):
        table = {"job": "execution_jobs_nativejob", "events": "execution_jobs_jobevent", "authority": "access_control_projectmembership"}[query]
        if sql.startswith("SELECT") and f'"{table}"' in sql and query != "authority" and (query != "job" or '"execution_jobs_nativejob"."result"' in sql):
            injected.append(True)
            if postgres:
                execute("SELECT pg_sleep(1)", None, False, context)
            else:
                raise DatabaseError("private SQL and connection details must remain private")
        return execute(sql, params, many, context)

    if query == "authority":
        original, active = service.projects.recheck, service.authorized_receipt
        inside = False
        def receipt(*args, **kwargs):
            nonlocal inside
            inside = True
            try:
                return active(*args, **kwargs)
            finally:
                inside = False
        def final(*args, **kwargs):
            if not inside:
                return original(*args, **kwargs)
            if postgres:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_sleep(1)")
            else:
                raise DatabaseError("private final authority details")
            return original(*args, **kwargs)
        monkeypatch.setattr(service.projects, "recheck", final)
        monkeypatch.setattr(service, "authorized_receipt", receipt)

    with transaction.atomic():
        if postgres:
            configure(100)
        with connection.execute_wrapper(slow):
            response = getattr(client_for(world.actor), method)(url(world))
        assert injected == ([] if query == "authority" else [True]) and response.status_code == 503
        assert response["Cache-Control"] == "no-store"
        assert response.content == b"" if method == "head" else response.json() == {"error_code": "job_storage_unavailable"}
        if postgres:
            assert milliseconds() == 100
        assert not connection.needs_rollback and snapshot() == before


def test_actual_default_ceiling_cancels_previously_unlimited_receipt(world):  # noqa: F811
    before = snapshot()
    if connection.vendor != "postgresql":
        response = client_for(world.actor).get(url(world))
        assert response.status_code == 200 and snapshot() == before
        return
    injected = []

    def slow(execute, sql, params, many, context):
        if sql.startswith("SELECT") and '"execution_jobs_nativejob"."result"' in sql:
            injected.append(True)
            execute("SELECT pg_sleep(6)", None, False, context)
        return execute(sql, params, many, context)

    with transaction.atomic():
        configure(0)
        with connection.execute_wrapper(slow):
            response = client_for(world.actor).get(url(world))
        assert injected == [True] and response.status_code == 503
        assert response.json() == {"error_code": "job_storage_unavailable"}
        assert response["Cache-Control"] == "no-store" and milliseconds() == 0
        assert not connection.needs_rollback and snapshot() == before


def test_unauthenticated_receipt_denied_before_bound(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(history, "_bounded_read", lambda: pytest.fail("bound before HTTP authentication"))
    response = APIClient().get(url(world))
    assert response.status_code in [401, 403]
    assert response["Cache-Control"] == "no-store"


def test_bound_configuration_outage_withholds_receipt_and_private_details(world, monkeypatch):  # noqa: F811
    before = snapshot()

    @contextmanager
    def unavailable():
        raise DatabaseError("private timeout SQL and driver details")
        yield

    monkeypatch.setattr(history, "_bounded_read", unavailable)
    response = client_for(world.actor).get(url(world))
    assert response.status_code == 503 and response.json() == {"error_code": "job_storage_unavailable"}
    assert response["Cache-Control"] == "no-store" and snapshot() == before


def test_repeated_receipt_reads_restore_enclosing_history_bound(world):  # noqa: F811
    postgres, before = connection.vendor == "postgresql", snapshot()
    with transaction.atomic():
        if postgres:
            configure(17000)
        with history._bounded_read():
            for _ in range(2):
                response = client_for(world.actor).get(url(world))
                assert response.status_code == 200 and response.json()["id"] == str(world.job.pk)
                if postgres:
                    assert milliseconds() == 5000
        if postgres:
            assert milliseconds() == 17000
    assert snapshot() == before
