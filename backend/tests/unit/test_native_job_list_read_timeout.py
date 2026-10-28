"""The legacy native directory shares bounded metadata SQL and safe failures."""

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
    return f"/api/jobs/datasets/{world.job.dataset_id}/"


def test_count_page_and_final_scope_check_share_existing_bound_without_execution_lock(world, monkeypatch):  # noqa: F811
    before, entered, queries, checked, mutations = snapshot(), [], [], [], []
    active = False
    original, recheck = history._bounded_read, service.projects.recheck

    @contextmanager
    def bound():
        nonlocal active
        entered.append(True)
        with original():
            active = True
            try:
                yield
            finally:
                active = False

    def inspect(execute, sql, params, many, context):
        if sql.startswith("SELECT") and '"execution_jobs_nativejob"' in sql:
            queries.append(("count" if "COUNT(" in sql else "page", active))
        if sql.lstrip().startswith(("INSERT", "UPDATE", "DELETE")):
            mutations.append((sql.split()[0], '"access_control_projectauthorityevent"' in sql, active))
        return execute(sql, params, many, context)

    def check(*args, **kwargs):
        checked.append(active)
        return recheck(*args, **kwargs)

    monkeypatch.setattr(history, "_bounded_read", bound)
    monkeypatch.setattr(service.projects, "recheck", check)
    monkeypatch.setattr(service, "locked", lambda: pytest.fail("directory acquired execution lock"))
    monkeypatch.setattr(NativeJob, "from_db", lambda *a, **k: pytest.fail("directory loaded full job state"))
    with connection.execute_wrapper(inspect):
        response = client_for(world.actor).get(url(world))
    assert response.status_code == 200, response.content
    assert entered == [True] and queries == [("count", True), ("page", True)]
    assert True in checked
    # The HTTP authority boundary must reserve and complete its audit record.
    # Neither audit operation belongs inside the metadata query transaction.
    assert mutations == [("INSERT", True, False), ("UPDATE", True, False)]
    assert snapshot() == before


@pytest.mark.parametrize("initial", [0, 17000, 2000, 1000])
def test_actual_directory_obeys_effective_postgresql_limit_and_restores_caller(world, initial):  # noqa: F811
    postgres, observed, before = connection.vendor == "postgresql", [], snapshot()
    original = milliseconds() if postgres else None

    def inspect(execute, sql, params, many, context):
        if sql.startswith("SELECT") and '"execution_jobs_nativejob"' in sql:
            observed.append(milliseconds() if postgres else "sqlite")
        return execute(sql, params, many, context)

    with transaction.atomic():
        if postgres:
            configure(initial)
        with connection.execute_wrapper(inspect), CaptureQueriesContext(connection) as queries:
            response = client_for(world.actor).get(url(world))
        assert response.status_code == 200, response.content
        assert observed and set(observed) == {min(initial or 5000, 5000) if postgres else "sqlite"}
        assert response.json()["total"] == 1 and response.json()["next_offset"] is None
        assert [j["id"] for j in response.json()["jobs"]] == [str(world.job.pk)]
        if postgres:
            assert milliseconds() == initial
        else:
            assert not any("set_config" in q["sql"] or "pg_settings" in q["sql"] for q in queries)
    if postgres:
        assert milliseconds() == original
    assert snapshot() == before


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("query", ["count", "page"])
def test_actual_count_and_page_cancellation_returns_private_uncached_failure_without_poisoning_connection(world, method, query):  # noqa: F811
    postgres, injected, before = connection.vendor == "postgresql", [], snapshot()

    def slow(execute, sql, params, many, context):
        if sql.startswith("SELECT") and '"execution_jobs_nativejob"' in sql and (("COUNT(" in sql) == (query == "count")):
            injected.append(True)
            if postgres:
                execute("SELECT pg_sleep(1)", None, False, context)
            else:
                raise DatabaseError("private SQL and connection details must remain private")
        return execute(sql, params, many, context)

    with transaction.atomic():
        if postgres:
            configure(100)
        with connection.execute_wrapper(slow):
            response = getattr(client_for(world.actor), method)(url(world))
        assert injected == [True] and response.status_code == 503
        assert response["Cache-Control"] == "no-store"
        assert response.content == b"" if method == "head" else response.json() == {"error_code": "job_storage_unavailable"}
        if postgres:
            assert milliseconds() == 100
        assert not connection.needs_rollback and snapshot() == before


def test_actual_default_ceiling_cancels_previously_unlimited_count(world):  # noqa: F811
    before = snapshot()
    if connection.vendor != "postgresql":
        response = client_for(world.actor).get(url(world))
        assert response.status_code == 200 and snapshot() == before
        return
    injected = []

    def slow(execute, sql, params, many, context):
        if sql.startswith("SELECT") and '"execution_jobs_nativejob"' in sql and "COUNT(" in sql:
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


@pytest.mark.parametrize("denial", ["outsider", "malformed_offset", "oversized_offset"])
def test_initial_authority_and_offset_guards_precede_bound_or_job_queries(world, monkeypatch, denial):  # noqa: F811
    monkeypatch.setattr(history, "_bounded_read", lambda: pytest.fail("bound before initial guard"))
    monkeypatch.setattr(NativeJob.objects, "filter", lambda *a, **k: pytest.fail("job query before initial guard"))
    actor = world.outsider if denial == "outsider" else world.actor
    response = client_for(actor).get(url(world), {"offset": "no" if denial == "malformed_offset" else str(2**63)})
    assert response.status_code == (403 if denial == "outsider" else 400)


def test_bound_configuration_outage_withholds_directory_and_private_details(world, monkeypatch):  # noqa: F811
    before = snapshot()

    @contextmanager
    def unavailable():
        raise DatabaseError("private timeout SQL and driver details")
        yield

    monkeypatch.setattr(history, "_bounded_read", unavailable)
    response = client_for(world.actor).get(url(world))
    assert response.status_code == 503 and response.json() == {"error_code": "job_storage_unavailable"}
    assert response["Cache-Control"] == "no-store" and snapshot() == before


def test_repeated_directory_reads_restore_enclosing_history_bound(world):  # noqa: F811
    postgres, before = connection.vendor == "postgresql", snapshot()
    with transaction.atomic():
        if postgres:
            configure(17000)
        with history._bounded_read():
            for _ in range(2):
                response = client_for(world.actor).get(url(world))
                assert response.status_code == 200 and response.json()["total"] == 1
                if postgres:
                    assert milliseconds() == 5000
        if postgres:
            assert milliseconds() == 17000
    assert snapshot() == before
