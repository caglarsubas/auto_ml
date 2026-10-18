"""Required metadata columns retain their sealed local-field nullability."""

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
    "nullable_password": ("auth_user", "password", "DROP NOT NULL"),
    "nullable_authority": ("auth_user", "is_superuser", "DROP NOT NULL"),
    "nullable_job_state": ("execution_jobs_nativejob", "state", "DROP NOT NULL"),
    "nullable_event_detail": ("execution_jobs_jobevent", "detail", "DROP NOT NULL"),
    "required_last_login": ("auth_user", "last_login", "SET NOT NULL"),
    "required_lease": ("execution_jobs_nativejob", "lease_token", "SET NOT NULL"),
    "required_actor": ("execution_jobs_nativejob", "actor_id", "SET NOT NULL"),
    "required_source": ("execution_jobs_nativejob", "source_dataset_id", "SET NOT NULL"),
}


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("case", CASES)
def test_changed_nullability_blocks_before_broker(physical_database, monkeypatch, command, case):
    seed = User.objects.create(username="u", password="retained-password", is_superuser=False)
    history = set(MigrationRecorder(connection).applied_migrations())
    table, column, action = CASES[case]
    if connection.vendor == "sqlite":
        # Explicit denial references only; SQLite does not emulate the native
        # catalog nullability check or PostgreSQL ALTER COLUMN behavior.
        @contextmanager
        def catalog():
            rows = [(t, "r", not (t == table and c == column), c)
                    for t, columns in schema_presence.required_schema().items() for c in columns]
            yield SimpleNamespace(execute=lambda *args: None, fetchall=lambda: rows)

        monkeypatch.setattr(schema_presence, "connection", SimpleNamespace(cursor=catalog))
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                if case == "required_last_login":
                    cursor.execute("UPDATE public.auth_user SET last_login=CURRENT_TIMESTAMP WHERE id=%s", [seed.pk])
                cursor.execute(f'ALTER TABLE public."{table}" ALTER COLUMN "{column}" {action}')
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
    assert restored.last_login is None
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("extra", [False, True])
def test_declared_nullability_and_extra_columns_remain_supported(physical_database, command, extra):
    history = set(MigrationRecorder(connection).applied_migrations())
    with transaction.atomic():
        if extra:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE execution_jobs_nativejob ADD COLUMN nullability_fixture_extra text NOT NULL DEFAULT 'fixture'")
                cursor.execute("ALTER TABLE execution_jobs_nativejob ADD COLUMN nullability_fixture_optional text")
        result = call_command("check_job_runtime") if command else preflight.check_runtime()
        if not command:
            assert result["migrations"] == "current"
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        transaction.set_rollback(True)
    assert set(MigrationRecorder(connection).applied_migrations()) == history
