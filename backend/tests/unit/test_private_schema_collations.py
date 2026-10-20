"""Column comparisons must retain the sealed database-default collation."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight, schema_presence
from tests.unit.test_private_schema_presence import physical_database  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


def run(command):
    return call_command("check_job_runtime") if command else preflight.check_runtime()


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("table,column,datatype", [
    ("access_control_project", "name", "varchar(200)"),
    ("django_session", "session_data", "text"),
])
def test_changed_column_collation_blocks_before_broker(physical_database, monkeypatch, command, table, column, datatype):
    history = set(MigrationRecorder(connection).applied_migrations())
    if connection.vendor == "sqlite":
        # Denial adapter only; real PostgreSQL DDL and changed ORM comparisons
        # are independently exercised by the owned physical qualifier.
        @contextmanager
        def catalog():
            rows = [(t, "r", not (t == table and c == column), c)
                    for t, columns in schema_presence.required_schema().items() for c in columns]
            yield SimpleNamespace(execute=lambda *args: None, fetchall=lambda: rows)

        monkeypatch.setattr(schema_presence, "connection", SimpleNamespace(cursor=catalog))
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(f'ALTER TABLE public."{table}" ALTER COLUMN "{column}" TYPE pg_catalog.{datatype} COLLATE pg_catalog."C"')
        try:
            expected = CommandError if command else preflight.RuntimeUnavailable
            with pytest.raises(expected, match="^job_schema_invalid$"):
                run(command)
            physical_database.ensure_connection.assert_not_called()
            assert set(MigrationRecorder(connection).applied_migrations()) == history
        finally:
            transaction.set_rollback(True)
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("declaration", ["varchar", "text", "explicit_default", "foreign_target"])
def test_unsupported_sealed_collation_blocks_before_broker(physical_database, monkeypatch, command, declaration):
    history = set(MigrationRecorder(connection).applied_migrations())

    def collated_state(database):
        assert database is None
        loader = MigrationLoader(None)
        state = loader.project_state()
        # Migration states can share Field instances with cached migrations.
        # Clone before changing this fixture so later admissions stay pristine.
        for key, name in [("sessions", "session"), ("access_control", "project"), ("auth", "user")]:
            model = state.models[(key, name)]
            model.fields = {field_name: field.clone() for field_name, field in model.fields.items()}
        if declaration == "text":
            state.models[("sessions", "session")].fields["session_data"].db_collation = "C"
        elif declaration == "foreign_target":
            state.models[("auth", "user")].fields["username"].db_collation = "C"
            state.models[("access_control", "projectmembership")].fields["actor"] = models.ForeignKey(
                "auth.User", to_field="username", on_delete=models.CASCADE,
            )
        else:
            state.models[("access_control", "project")].fields["name"].db_collation = "default" if declaration == "explicit_default" else "C"
        loader.project_state = lambda: state
        return loader

    monkeypatch.setattr(schema_presence, "MigrationLoader", collated_state)
    with pytest.raises(schema_presence.SchemaMismatch):
        schema_presence.required_storage_contract()
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_schema_invalid$"):
        run(command)
    physical_database.ensure_connection.assert_not_called()
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("extra", [False, True])
def test_default_collation_and_extra_columns_remain_supported(physical_database, command, extra):
    history = set(MigrationRecorder(connection).applied_migrations())
    with transaction.atomic():
        if extra:
            with connection.cursor() as cursor:
                cursor.execute('ALTER TABLE access_control_project ADD COLUMN collation_fixture_extra text COLLATE "C"'
                               if connection.vendor == "postgresql" else
                               'ALTER TABLE access_control_project ADD COLUMN collation_fixture_extra text')
        result = run(command)
        if not command:
            assert result["migrations"] == "current"
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        transaction.set_rollback(True)
    assert set(MigrationRecorder(connection).applied_migrations()) == history
