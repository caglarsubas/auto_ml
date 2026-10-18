"""Required writable metadata cannot silently become generated expressions."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight, schema_presence
from tests.unit.test_private_schema_presence import physical_database  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]

CASES = {
    "password": ("auth_user", "password", "varchar(128)", "'generated'::pg_catalog.varchar(128)", True),
    "authority": ("auth_user", "is_superuser", "bool", "false", True),
    "attempts": ("execution_jobs_nativejob", "attempts", "int2", "0::pg_catalog.int2", True),
    "result": ("execution_jobs_nativejob", "result", "jsonb", "NULL::pg_catalog.jsonb", False),
    "finished": ("execution_jobs_nativejob", "finished_at", "timestamptz", "NULL::pg_catalog.timestamptz", False),
    "session": ("django_session", "session_data", "text", "''::pg_catalog.text", True),
}


def run(command):
    return call_command("check_job_runtime") if command else preflight.check_runtime()


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("case", CASES)
def test_generated_required_column_blocks_before_broker(physical_database, monkeypatch, command, case):
    seed = User.objects.create(username="u", password="retained-password", is_superuser=False)
    history = set(MigrationRecorder(connection).applied_migrations())
    table, column, datatype, expression, not_null = CASES[case]
    if connection.vendor == "sqlite":
        # Explicit denial references only; no native generated-column or
        # PostgreSQL catalog behavior is inferred from this adapter.
        @contextmanager
        def catalog():
            rows = [(t, "r", not (t == table and c == column), c)
                    for t, columns in schema_presence.required_schema().items() for c in columns]
            yield SimpleNamespace(execute=lambda *args: None, fetchall=lambda: rows)

        monkeypatch.setattr(schema_presence, "connection", SimpleNamespace(cursor=catalog))
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(f'ALTER TABLE public."{table}" RENAME COLUMN "{column}" TO generated_fixture_original')
                cursor.execute(f'ALTER TABLE public."{table}" ADD COLUMN "{column}" pg_catalog.{datatype} GENERATED ALWAYS AS ({expression}) STORED' + (" NOT NULL" if not_null else ""))
                if case == "password":
                    cursor.execute("SELECT generated_fixture_original FROM public.auth_user WHERE id=%s", [seed.pk])
                    assert cursor.fetchone() == ("retained-password",)
        try:
            expected = CommandError if command else preflight.RuntimeUnavailable
            with pytest.raises(expected, match="^job_schema_invalid$"):
                run(command)
            physical_database.ensure_connection.assert_not_called()
            assert set(MigrationRecorder(connection).applied_migrations()) == history
        finally:
            transaction.set_rollback(True)
    restored = User.objects.get(pk=seed.pk)
    assert restored.username == "u" and restored.password == "retained-password" and restored.is_superuser is False
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("persisted", [False, True])
def test_unsupported_sealed_generation_blocks_before_broker(physical_database, monkeypatch, command, persisted):
    history = set(MigrationRecorder(connection).applied_migrations())

    def generated_state(database):
        assert database is None
        loader = MigrationLoader(None)
        state = loader.project_state()
        # GeneratedField reports its output's ordinary internal type. A full
        # real migration state keeps all other declarations and required names.
        state.models[("execution_jobs", "jobevent")].fields["detail"] = models.GeneratedField(
            expression=models.Value(None, output_field=models.JSONField()),
            output_field=models.JSONField(), db_persist=persisted,
        )
        loader.project_state = lambda: state
        return loader

    monkeypatch.setattr(schema_presence, "MigrationLoader", generated_state)
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_schema_invalid$"):
        run(command)
    physical_database.ensure_connection.assert_not_called()
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("extra", [False, True])
def test_identity_keys_and_extra_columns_remain_supported(physical_database, command, extra):
    seed = User.objects.create(username="u", password="retained-password", is_superuser=False)
    history = set(MigrationRecorder(connection).applied_migrations())
    with transaction.atomic():
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                cursor.execute("SELECT a.attidentity,a.attgenerated FROM pg_catalog.pg_attribute a WHERE a.attrelid OPERATOR(pg_catalog.=) 'public.auth_user'::pg_catalog.regclass AND a.attname OPERATOR(pg_catalog.=) 'id'::pg_catalog.name")
                identity, generated = cursor.fetchone()
                assert identity in {"a", "d"} and generated == ""
                if extra:
                    cursor.execute("ALTER TABLE public.auth_user ADD COLUMN generated_fixture_optional text GENERATED ALWAYS AS (NULL::pg_catalog.text) STORED")
                    cursor.execute("ALTER TABLE public.auth_user ADD COLUMN generated_fixture_required text GENERATED ALWAYS AS ('fixture'::pg_catalog.text) STORED NOT NULL")
            elif extra:
                cursor.execute("ALTER TABLE auth_user ADD COLUMN generated_fixture_optional text")
                cursor.execute("ALTER TABLE auth_user ADD COLUMN generated_fixture_required text NOT NULL DEFAULT 'fixture'")
        result = run(command)
        if not command:
            assert result["migrations"] == "current"
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        created = User.objects.create(username="identity-control", password="supported")
        assert created.pk is not None
        assert User.objects.filter(pk=seed.pk).update(password="temporary-password") == 1
        transaction.set_rollback(True)
    assert User.objects.get(pk=seed.pk).password == "retained-password"
    assert not User.objects.filter(username="identity-control").exists()
    assert set(MigrationRecorder(connection).applied_migrations()) == history
