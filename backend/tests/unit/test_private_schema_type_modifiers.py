"""Declared varchar lengths and timestamp modifiers remain sealed metadata state."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight, schema_presence
from tests.unit.test_private_schema_presence import physical_database  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]

CASES = {
    "short_username": ("auth_user", "username", "pg_catalog.varchar(1)"),
    "wider_username": ("auth_user", "username", "pg_catalog.varchar(255)"),
    "unbounded_email": ("auth_user", "email", "pg_catalog.varchar"),
    "short_digest": ("execution_jobs_nativejob", "result_sha256", "pg_catalog.varchar(1)"),
    "wider_digest": ("execution_jobs_nativejob", "result_sha256", "pg_catalog.varchar(128)"),
    "seconds_timestamp": ("django_session", "expire_date", "timestamp(0) with time zone"),
    "milliseconds_timestamp": ("django_session", "expire_date", "timestamp(3) with time zone"),
    "explicit_full_precision": ("django_session", "expire_date", "timestamp(6) with time zone"),
}


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("case", CASES)
def test_changed_modifier_blocks_before_broker(physical_database, monkeypatch, command, case):
    seed = User.objects.create(username="u", password="retained-password", is_superuser=False)
    history = set(MigrationRecorder(connection).applied_migrations())
    table, column, datatype = CASES[case]
    if connection.vendor == "sqlite":
        # Explicit modifier-denial references only. SQLite does not emulate
        # PostgreSQL varchar/timestamp modifiers or storage coercions.
        @contextmanager
        def catalog():
            rows = [(t, "r", not (t == table and c == column), c)
                    for t, columns in schema_presence.required_schema().items() for c in columns]
            yield SimpleNamespace(execute=lambda *args: None, fetchall=lambda: rows)

        monkeypatch.setattr(schema_presence, "connection", SimpleNamespace(cursor=catalog))
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(f'ALTER TABLE public."{table}" ALTER COLUMN "{column}" TYPE {datatype} USING "{column}"::{datatype}')
                cursor.execute("SELECT username FROM public.auth_user WHERE id=%s", [seed.pk])
                assert cursor.fetchone() == ("u",)
        try:
            expected = CommandError if command else preflight.RuntimeUnavailable
            with pytest.raises(expected, match="^job_schema_invalid$"):
                if command:
                    call_command("check_job_runtime")
                else:
                    preflight.check_runtime()
            physical_database.ensure_connection.assert_not_called()
            assert set(MigrationRecorder(connection).applied_migrations()) == history
        finally:
            transaction.set_rollback(True)
    restored = User.objects.get(pk=seed.pk)
    assert restored.username == "u" and restored.password == "retained-password" and restored.is_superuser is False
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("extra", [False, True])
def test_declared_modifiers_and_extra_columns_remain_supported(physical_database, command, extra):
    history = set(MigrationRecorder(connection).applied_migrations())
    with transaction.atomic():
        if extra:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE execution_jobs_nativejob ADD COLUMN modifier_fixture_extra varchar(1)")
        result = call_command("check_job_runtime") if command else preflight.check_runtime()
        if not command:
            assert result["migrations"] == "current"
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        transaction.set_rollback(True)
    assert set(MigrationRecorder(connection).applied_migrations()) == history
