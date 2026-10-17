"""Private startup needs effective DML rights, beyond current physical schema."""

from contextlib import contextmanager
from importlib import import_module, util
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction, OperationalError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]
RIGHTS = ("SELECT", "INSERT", "UPDATE", "DELETE")


@pytest.fixture
def permission_database(settings, monkeypatch):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    settings.DECLARAI_JOBS_ENABLED = True
    monkeypatch.setattr(preflight, "check_metadata_write_mode", lambda: None)
    # Actual RLS behavior is independently exercised by row-security tests.
    monkeypatch.setattr(preflight, "check_schema_row_security", lambda: None)
    transport = MagicMock(vendor="postgresql")
    transport.alias = connection.alias
    transport.introspection = connection.introspection
    calls = [0]

    def cursor():
        calls[0] += 1
        if calls[0] == 1:
            return MagicMock(__enter__=lambda _: MagicMock(fetchone=lambda: (True,)),
                             __exit__=lambda *args: False)
        return connection.cursor()

    transport.cursor.side_effect = cursor
    monkeypatch.setattr(preflight, "connection", transport)
    monkeypatch.setattr(preflight, "MigrationExecutor", lambda _: MigrationExecutor(connection))
    broker = MagicMock()
    monkeypatch.setattr("backend.celery.app.connection_for_write", lambda: broker)
    missing = {}
    if connection.vendor == "sqlite":
        # SQLite has no PostgreSQL privileges. This is an explicit catalog-response
        # reference, never a product fallback. P85 tests physical-schema behavior.
        monkeypatch.setattr(preflight, "check_schema", lambda: None)
        if util.find_spec("execution_jobs.schema_privileges") is not None:
            schema = import_module("execution_jobs.schema_privileges")

            @contextmanager
            def catalog():
                rows = []

                def execute(sql, parameters):
                    tables = set(connection.introspection.table_names())
                    rows.extend((t, *(missing.get(t) != r for r in RIGHTS)) for t in parameters[0] if t in tables)
                yield SimpleNamespace(execute=execute, fetchall=lambda: rows)

            monkeypatch.setattr(schema, "connection", SimpleNamespace(cursor=catalog))
    else:
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
            assert cursor.fetchone() == (False,), "Permission qualification requires a non-superuser test owner"
    return broker.__enter__.return_value, missing


@contextmanager
def withheld_permission(reference, table, right):
    if connection.vendor == "sqlite":
        reference[table] = right
        try:
            yield
        finally:
            reference.clear()
    else:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"REVOKE {right} ON public.{connection.ops.quote_name(table)} FROM CURRENT_USER")
                cursor.execute("SELECT has_table_privilege(current_user, %s, %s)", ["public." + table, right])
                assert cursor.fetchone() == (False,)
            try:
                yield
            finally:
                transaction.set_rollback(True)


def run_preflight(command):
    if command:
        output = StringIO()
        call_command("check_job_runtime", stdout=output)
        return output.getvalue()
    return preflight.check_runtime()


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("table", ["execution_jobs_nativejob", "execution_jobs_jobevent", "auth_user_groups"])
@pytest.mark.parametrize("right", RIGHTS)
def test_each_required_operation_is_checked_before_broker(permission_database, command, table, right):
    broker, reference = permission_database
    before = set(MigrationRecorder(connection).applied_migrations())
    assert table in connection.introspection.table_names()
    with withheld_permission(reference, table, right):
        expected = CommandError if command else preflight.RuntimeUnavailable
        with pytest.raises(expected, match="^job_schema_privileges_invalid$"):
            run_preflight(command)
        broker.ensure_connection.assert_not_called()
        assert before == set(MigrationRecorder(connection).applied_migrations())


@pytest.mark.parametrize("command", [False, True])
def test_current_effective_permissions_allow_startup_without_grants(permission_database, command):
    broker, _ = permission_database
    before = set(MigrationRecorder(connection).applied_migrations())
    assert "current" in str(run_preflight(command))
    broker.ensure_connection.assert_called_once_with(max_retries=0)
    assert before == set(MigrationRecorder(connection).applied_migrations())


@pytest.mark.parametrize("command", [False, True])
def test_privilege_catalog_error_is_a_redacted_storage_failure(permission_database, monkeypatch, command):
    broker, _ = permission_database

    def unavailable():
        raise OperationalError("postgresql://private:secret@private-host/privileges")

    monkeypatch.setattr(preflight, "check_schema_privileges", unavailable, raising=False)
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_storage_unavailable$"):
        run_preflight(command)
    broker.ensure_connection.assert_not_called()


@pytest.mark.parametrize("command", [False, True])
def test_relation_lost_between_presence_and_permissions_cannot_pass(permission_database, monkeypatch, command):
    broker, _ = permission_database
    original = preflight.check_schema
    table = connection.ops.quote_name("execution_jobs_jobevent")
    backup = connection.ops.quote_name("privilege_fixture_event")

    def change_after_presence():
        original()
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {table} RENAME TO {backup}")

    monkeypatch.setattr(preflight, "check_schema", change_after_presence)
    with transaction.atomic():
        try:
            expected = CommandError if command else preflight.RuntimeUnavailable
            with pytest.raises(expected, match="^job_schema_privileges_invalid$"):
                run_preflight(command)
            broker.ensure_connection.assert_not_called()
        finally:
            transaction.set_rollback(True)
