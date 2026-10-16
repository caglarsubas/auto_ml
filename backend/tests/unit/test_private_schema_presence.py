"""Current migration records cannot hide lost or shadowed managed relations."""

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


@pytest.fixture
def physical_database(settings, monkeypatch):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    settings.DECLARAI_JOBS_ENABLED = True
    # Privileges are independently tested against actual PostgreSQL REVOKE.
    monkeypatch.setattr(preflight, "check_schema_privileges", lambda: None)
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
    # PostgreSQL executes the production catalog SQL. SQLite has no pg_catalog;
    # its development reference adapts actual SQLite metadata after the same DDL.
    spec = util.find_spec("execution_jobs.schema_presence")
    if connection.vendor == "sqlite" and spec is not None:
        schema = import_module("execution_jobs.schema_presence")

        @contextmanager
        def catalog():
            rows = []

            def execute(sql, parameters):
                with connection.cursor() as actual:
                    for table in parameters[0]:
                        actual.execute("SELECT type FROM sqlite_master WHERE name=%s", [table])
                        found = actual.fetchone()
                        if found is None:
                            continue
                        actual.execute("SELECT count(*) FROM sqlite_temp_master WHERE name=%s", [table])
                        visible = actual.fetchone()[0] == 0
                        fields = connection.introspection.get_table_description(actual, table)
                        rows.extend((table, "r" if found[0] == "table" else "v", visible, f.name) for f in fields)
            yield SimpleNamespace(execute=execute, fetchall=lambda: rows)

        monkeypatch.setattr(schema, "connection", SimpleNamespace(cursor=catalog))
    return broker.__enter__.return_value


def run_preflight(command):
    if command:
        output = StringIO()
        call_command("check_job_runtime", stdout=output)
        return output.getvalue()
    return preflight.check_runtime()


@contextmanager
def changed_schema(statements):
    with transaction.atomic():
        with connection.cursor() as cursor:
            for sql in statements:
                cursor.execute(sql)
        try:
            yield
        finally:
            transaction.set_rollback(True)


def blocked(broker, command):
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_schema_invalid$"):
        run_preflight(command)
    broker.ensure_connection.assert_not_called()


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("table", ["execution_jobs_nativejob", "execution_jobs_jobevent",
                                    "django_session", "auth_user_groups"])
def test_missing_managed_table_blocks_with_current_history(physical_database, command, table):
    before = set(MigrationRecorder(connection).applied_migrations())
    q = connection.ops.quote_name
    with changed_schema([f"ALTER TABLE {q(table)} RENAME TO {q('presence_fixture_table')}"]):
        blocked(physical_database, command)
        assert before == set(MigrationRecorder(connection).applied_migrations())


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("table,column", [
    ("execution_jobs_nativejob", "result_sha256"), ("execution_jobs_nativejob", "expires_at"),
    ("execution_jobs_jobevent", "detail"), ("auth_user", "password"), ("django_session", "expire_date"),
])
def test_missing_managed_column_blocks_without_data_reads(physical_database, command, table, column):
    q = connection.ops.quote_name
    with changed_schema([f"ALTER TABLE {q(table)} RENAME COLUMN {q(column)} TO {q('presence_fixture_column')}"]):
        blocked(physical_database, command)


@pytest.mark.parametrize("command", [False, True])
def test_view_cannot_substitute_for_a_managed_table(physical_database, command):
    table, backup = "execution_jobs_nativejob", "presence_fixture_table"
    q = connection.ops.quote_name
    with changed_schema([f"ALTER TABLE {q(table)} RENAME TO {q(backup)}",
                         f"CREATE VIEW {q(table)} AS SELECT * FROM {q(backup)}"]):
        blocked(physical_database, command)


@pytest.mark.parametrize("command", [False, True])
def test_shadowed_public_table_is_not_the_runtime_relation(physical_database, command):
    table = connection.ops.quote_name("execution_jobs_nativejob")
    if connection.vendor == "postgresql":
        statements = ["CREATE SCHEMA presence_fixture", "SET LOCAL search_path=presence_fixture,public",
                      f"CREATE TABLE presence_fixture.{table} (id text)"]
    else:
        statements = [f"CREATE TEMP TABLE {table} (id text)"]
    with changed_schema(statements):
        blocked(physical_database, command)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("extra_column", [False, True])
def test_current_required_columns_allow_startup_without_repair(physical_database, command, extra_column):
    before = set(MigrationRecorder(connection).applied_migrations())
    statements = ["ALTER TABLE execution_jobs_nativejob ADD COLUMN presence_fixture_extra text"] if extra_column else []
    with changed_schema(statements):
        assert "current" in str(run_preflight(command))
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        assert before == set(MigrationRecorder(connection).applied_migrations())


@pytest.mark.parametrize("command", [False, True])
def test_catalog_failure_remains_a_redacted_storage_failure(physical_database, monkeypatch, command):
    def unavailable():
        raise OperationalError("postgresql://private:secret@private-host/catalog")

    monkeypatch.setattr(preflight, "check_schema", unavailable, raising=False)
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_storage_unavailable$"):
        run_preflight(command)
    physical_database.ensure_connection.assert_not_called()
