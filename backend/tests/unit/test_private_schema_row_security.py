"""A fixed private metadata profile must not silently filter its own rows."""

from contextlib import contextmanager
from importlib import import_module, util
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction, OperationalError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]
MODES = {"enabled": (True, False), "enabled_forced": (True, True), "force_only": (False, True)}


@pytest.fixture
def row_security_database(settings, monkeypatch):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    settings.DECLARAI_JOBS_ENABLED = True
    # The independent write-mode phase has its own actual PostgreSQL tests.
    monkeypatch.setattr(preflight, "check_metadata_write_mode", lambda: None)
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
    states = {}
    if connection.vendor == "sqlite":
        # SQLite has no RLS. These are explicit catalog-response references;
        # independent presence/permission tests cover the preceding phases.
        monkeypatch.setattr(preflight, "check_schema", lambda: None)
        monkeypatch.setattr(preflight, "check_schema_privileges", lambda: None)
        if util.find_spec("execution_jobs.schema_row_security") is not None:
            schema = import_module("execution_jobs.schema_row_security")

            @contextmanager
            def catalog():
                rows = []

                def execute(sql, parameters):
                    tables = set(connection.introspection.table_names())
                    rows.extend((t, *states.get(t, (False, False))) for t in parameters[0] if t in tables)
                yield SimpleNamespace(execute=execute, fetchall=lambda: rows)

            monkeypatch.setattr(schema, "connection", SimpleNamespace(cursor=catalog))
    else:
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
            assert cursor.fetchone() == (False, False), "RLS qualification requires an ordinary test owner"
    return broker.__enter__.return_value, states


@contextmanager
def changed_row_security(reference, table, mode):
    if connection.vendor == "sqlite":
        reference[table] = MODES[mode]
        try:
            yield
        finally:
            reference.clear()
    else:
        enabled, forced = MODES[mode]
        with transaction.atomic():
            with connection.cursor() as cursor:
                name = connection.ops.quote_name(table)
                if enabled:
                    cursor.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
                if forced:
                    cursor.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
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
@pytest.mark.parametrize("table", ["execution_jobs_nativejob", "execution_jobs_jobevent", "auth_group", "auth_user_groups"])
@pytest.mark.parametrize("mode", MODES)
def test_unsupported_metadata_row_security_blocks_before_broker(row_security_database, command, table, mode):
    broker, reference = row_security_database
    before = set(MigrationRecorder(connection).applied_migrations())
    prove_hidden_rows = connection.vendor == "postgresql" and table == "auth_group" and mode == "enabled_forced"
    if prove_hidden_rows:
        Group.objects.create(name="owned-row-security-fixture")
        assert Group.objects.count() == 1
    with changed_row_security(reference, table, mode):
        if prove_hidden_rows:
            assert Group.objects.count() == 0
        expected = CommandError if command else preflight.RuntimeUnavailable
        with pytest.raises(expected, match="^job_schema_row_security_invalid$"):
            run_preflight(command)
        broker.ensure_connection.assert_not_called()
        assert before == set(MigrationRecorder(connection).applied_migrations())
    if prove_hidden_rows:
        assert Group.objects.count() == 1


@pytest.mark.parametrize("command", [False, True])
def test_unfiltered_metadata_profile_allows_startup_without_policy_changes(row_security_database, command):
    broker, _ = row_security_database
    before = set(MigrationRecorder(connection).applied_migrations())
    assert "current" in str(run_preflight(command))
    broker.ensure_connection.assert_called_once_with(max_retries=0)
    assert before == set(MigrationRecorder(connection).applied_migrations())


@pytest.mark.parametrize("command", [False, True])
def test_row_security_catalog_error_is_a_redacted_storage_failure(row_security_database, monkeypatch, command):
    broker, _ = row_security_database

    def unavailable():
        raise OperationalError("postgresql://private:secret@private-host/row-security")

    monkeypatch.setattr(preflight, "check_schema_row_security", unavailable, raising=False)
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_storage_unavailable$"):
        run_preflight(command)
    broker.ensure_connection.assert_not_called()


@pytest.mark.parametrize("command", [False, True])
def test_relation_lost_before_row_security_check_cannot_pass(row_security_database, monkeypatch, command):
    broker, _ = row_security_database
    original = preflight.check_schema_privileges
    table = connection.ops.quote_name("execution_jobs_jobevent")
    backup = connection.ops.quote_name("row_security_fixture_event")

    def change_after_permissions():
        original()
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {table} RENAME TO {backup}")

    monkeypatch.setattr(preflight, "check_schema_privileges", change_after_permissions)
    with transaction.atomic():
        try:
            expected = CommandError if command else preflight.RuntimeUnavailable
            with pytest.raises(expected, match="^job_schema_row_security_invalid$"):
                run_preflight(command)
            broker.ensure_connection.assert_not_called()
        finally:
            transaction.set_rollback(True)
