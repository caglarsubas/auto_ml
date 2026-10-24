"""Standalone operator reads respect database policy and version their evidence."""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext

from execution_jobs import operator_triage
from execution_jobs.models import NativeJob, QueueLock
from tests.unit.test_native_job_pagination import listing  # noqa: F401
from tests.unit.test_native_operator_triage import snapshot  # noqa: F401
from tests.unit.test_private_queue_evidence import module as evidence, sample

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
V1, V2 = "native_queue_operator_snapshot_v1", "native_queue_operator_snapshot_v2"
SETTING = "SELECT current_setting('statement_timeout'), setting::bigint FROM pg_settings WHERE name = 'statement_timeout'"


def actual_settings():
    with connection.cursor() as cursor:
        cursor.execute("SELECT setting::bigint, current_setting('transaction_read_only'), "
                       "current_setting('transaction_isolation') FROM pg_settings WHERE name = 'statement_timeout'")
        return cursor.fetchone()


@contextmanager
def policy(monkeypatch, initial):
    if connection.vendor == "postgresql":
        original = actual_settings()
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('statement_timeout', %s, false)", [f"{initial}ms"])
        try:
            yield actual_settings
            assert actual_settings() == (initial, original[1], original[2])
            assert not connection.in_atomic_block and not connection.needs_rollback
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('statement_timeout', %s, false)", [f"{original[0]}ms"])
        assert actual_settings() == original
        return
    # Development compatibility only: control statements are modeled while
    # real ORM reads/transactions still run. Native cases prove PostgreSQL
    # settings, cancellation, read-only enforcement and restoration.
    import django.db
    state = SimpleNamespace(applied=initial, last=None)

    class ControlCursor:
        def execute(self, sql, params=None):
            state.last = sql
            if sql == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY":
                assert params is None
            elif sql == SETTING:
                assert params is None
            elif sql == "SET LOCAL statement_timeout = '5000ms'":
                assert params is None
                state.applied = 5000
            elif sql == "SELECT set_config('statement_timeout', %s, true)":
                assert params == [f"{min(initial or 5000, 5000)}ms"]
                state.applied = int(params[0][:-2])
            else:
                pytest.fail("unexpected operator control statement")

        def fetchone(self):
            assert state.last == SETTING
            return f"{initial}ms", initial

    class ControlConnection:
        vendor = "postgresql"

        @property
        def in_atomic_block(self):
            return connection.in_atomic_block

        @contextmanager
        def cursor(self):
            yield ControlCursor()

    with monkeypatch.context() as patch:
        patch.setattr(django.db, "connection", ControlConnection())
        yield lambda: (state.applied, None, None)


@pytest.mark.parametrize("initial", [0, 17000, 5000, 2000, 1000])
def test_effective_budget_is_reported_applies_to_every_metadata_read_and_restores_policy(listing, monkeypatch, initial):  # noqa: F811
    before = list(NativeJob.objects.order_by("pk").values())
    observed = []
    with policy(monkeypatch, initial) as settings:
        def inspect(execute, sql, params, many, context):
            if sql.startswith("SELECT") and '"execution_jobs_nativejob"' in sql:
                observed.append(settings())
            return execute(sql, params, many, context)

        with connection.execute_wrapper(inspect):
            value = operator_triage.read_snapshot()
        expected = min(initial or 5000, 5000)
        assert observed and {row[0] for row in observed} == {expected}
        if connection.vendor == "postgresql":
            assert all(row[1:] == ("on", "repeatable read") for row in observed)
        assert value["schema"] == V2 and value["statement_timeout_ms"] == expected
        assert value["read_only_transaction"] and value["repeatable_read"]
        assert value["live_service_health"] == "not_tested" and not value["recovery_authorized"]
        evidence.queue(value)
    assert list(NativeJob.objects.order_by("pk").values()) == before


@pytest.mark.parametrize("fault", ["python", "database", "slow", "write"])
def test_failure_cancellation_and_read_only_refusal_restore_caller_policy_and_rows(listing, monkeypatch, fault):  # noqa: F811
    before = list(NativeJob.objects.order_by("pk").values())
    observed = []
    with policy(monkeypatch, 1000) as settings:
        def fail(execute, sql, params, many, context):
            if sql.startswith("SELECT") and '"execution_jobs_nativejob"' in sql:
                observed.append(settings())
                if fault == "python":
                    raise ValueError("private-p145-fixture")
                if connection.vendor == "postgresql":
                    query = {"database": "SELECT * FROM declarai_intentionally_absent_operator_fixture",
                             "slow": "SELECT pg_sleep(6)",
                             "write": "INSERT INTO execution_jobs_queuelock (id) VALUES (12345)"}[fault]
                    return execute(query, None, False, context)
                raise DatabaseError("development-control-fixture")
            return execute(sql, params, many, context)

        with connection.execute_wrapper(fail), pytest.raises(ValueError if fault == "python" else DatabaseError) as caught:
            operator_triage.read_snapshot()
        assert observed and {row[0] for row in observed} == {1000}
        if connection.vendor == "postgresql" and fault != "python":
            cause = caught.value.__cause__
            assert getattr(cause, "sqlstate", getattr(cause, "pgcode", None)) == {
                "database": "42P01", "slow": "57014", "write": "25006"}[fault]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    assert not QueueLock.objects.filter(pk=12345).exists()
    assert list(NativeJob.objects.order_by("pk").values()) == before


@contextmanager
def manual_transaction():
    assert transaction.get_autocommit()
    transaction.set_autocommit(False)
    try:
        yield
    finally:
        connection.rollback()
        transaction.set_autocommit(True)


@pytest.mark.parametrize("mode", ["atomic_clean", "atomic_queried", "manual_clean", "manual_queried"])
def test_existing_transactions_are_refused_before_sql_without_changing_their_behavior(listing, snapshot, monkeypatch, mode):  # noqa: F811
    before = list(NativeJob.objects.order_by("pk").values())
    monkeypatch.setattr(NativeJob.objects, "alias", lambda *a, **k: pytest.fail("nested observation queried jobs"))
    with (transaction.atomic() if mode.startswith("atomic") else manual_transaction()):
        if mode.endswith("queried"):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                assert cursor.fetchone() == (1,)
        with CaptureQueriesContext(connection) as queries:
            with pytest.raises(ValueError, match="operator_top_level_transaction_required"):
                snapshot()
        assert not list(queries)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    assert list(NativeJob.objects.order_by("pk").values()) == before


@pytest.mark.parametrize("budget", [1, 1000, 4999, 5000])
def test_v2_evidence_accepts_bounded_effective_timeouts(budget):
    value = sample()["queue"]
    value.update(schema=V2, statement_timeout_ms=budget)
    evidence.queue(value)


def test_legacy_v1_evidence_remains_accepted_without_rewriting_it():
    value = sample()["queue"]
    before = json.dumps(value, sort_keys=True)
    evidence.queue(value)
    assert value["schema"] == V1 and json.dumps(value, sort_keys=True) == before


@pytest.mark.parametrize("budget", [0, 1, 4999, 5001, True, 5000.0, "5000", None])
def test_legacy_v1_timeout_contract_remains_strict(budget):
    value = sample()["queue"]
    value["statement_timeout_ms"] = budget
    with pytest.raises(ValueError, match="queue_evidence_invalid"):
        evidence.queue(value)


@pytest.mark.parametrize("budget", [0, -1, 5001, True, 1.5, "1000", None])
def test_v2_evidence_rejects_unbounded_or_untyped_timeouts(budget):
    value = sample()["queue"]
    value.update(schema=V2, statement_timeout_ms=budget)
    with pytest.raises(ValueError, match="queue_evidence_invalid"):
        evidence.queue(value)


@pytest.mark.parametrize("schema", ["native_queue_operator_snapshot_v3", None, [], {}, 17])
def test_unknown_future_evidence_schema_is_refused(schema):
    value = sample()["queue"]
    value["schema"] = schema
    with pytest.raises(ValueError, match="queue_evidence_invalid"):
        evidence.queue(value)


def test_v2_safe_unavailable_evidence_is_accepted():
    evidence.queue(dict(schema=V2, status="unavailable", reason="queue_metadata_unavailable"))


@pytest.mark.parametrize("schema", [V1, V2])
@pytest.mark.parametrize("status", ["observed", "unavailable"])
def test_fixed_probe_transport_accepts_legacy_and_current_versions_without_authority_changes(monkeypatch, schema, status):
    module = evidence.triage
    value = dict(schema=schema, status=status)
    def run(args, **kwargs):
        assert args == [*module.resources.PREFIX, "exec", "--user", "10001:10001", "a" * 64,
                        "python", "-m", "execution_jobs.operator_triage"]
        assert kwargs["timeout"] == 20 and kwargs["stderr"] == module.subprocess.DEVNULL
        kwargs["stdout"].write(json.dumps(value).encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.probe(dict(container_id="a" * 64, attention_required=False)) == value


@pytest.mark.parametrize("schema", ["native_queue_operator_snapshot_v3", None, [], {}, 17])
def test_fixed_probe_transport_still_refuses_unknown_future_versions(monkeypatch, schema):
    module = evidence.triage
    def run(args, **kwargs):
        kwargs["stdout"].write(json.dumps(dict(schema=schema, status="observed")).encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(module.checker.planner.PlanError, match="probe_output_invalid"):
        module.probe(dict(container_id="a" * 64, attention_required=False))
