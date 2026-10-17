"""Catalog access and table permissions do not establish a writable session."""

from contextlib import contextmanager
from importlib import import_module, util
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction, DatabaseError, OperationalError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]
MODES = {"current_only": ("on", "off"), "default_only": ("off", "on"), "both": ("on", "on")}


@pytest.fixture
def write_mode_database(settings, monkeypatch):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    settings.DECLARAI_JOBS_ENABLED = True
    transport = MagicMock(vendor="postgresql")
    transport.alias = connection.alias
    transport.introspection = connection.introspection
    calls, executors = [0], []

    def cursor():
        calls[0] += 1
        if calls[0] == 1:
            return MagicMock(__enter__=lambda _: MagicMock(fetchone=lambda: (True,)),
                             __exit__=lambda *args: False)
        return connection.cursor()

    def executor(_):
        executors.append(True)
        return MigrationExecutor(connection)

    transport.cursor.side_effect = cursor
    monkeypatch.setattr(preflight, "connection", transport)
    monkeypatch.setattr(preflight, "MigrationExecutor", executor)
    broker = MagicMock()
    monkeypatch.setattr("backend.celery.app.connection_for_write", lambda: broker)
    state = {"row": ("off", "off")}
    if connection.vendor == "sqlite":
        # Explicit response references only: SQLite has no PostgreSQL GUCs.
        # Product checks remain PostgreSQL-only; preceding phases are separate.
        monkeypatch.setattr(preflight, "check_schema", lambda: None)
        monkeypatch.setattr(preflight, "check_schema_privileges", lambda: None)
        monkeypatch.setattr(preflight, "check_schema_row_security", lambda: None)
        if util.find_spec("execution_jobs.metadata_write_mode") is not None:
            metadata = import_module("execution_jobs.metadata_write_mode")

            @contextmanager
            def catalog():
                yield SimpleNamespace(execute=lambda *args: None, fetchone=lambda: state["row"])

            monkeypatch.setattr(metadata, "connection", SimpleNamespace(cursor=catalog))
    else:
        with connection.cursor() as actual:
            actual.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
            assert actual.fetchone() == (False,), "Write-mode qualification requires an ordinary test owner"
    return broker.__enter__.return_value, state, executors


@contextmanager
def read_only_mode(reference, mode):
    if connection.vendor == "sqlite":
        reference["row"] = MODES[mode]
        try:
            yield
        finally:
            reference["row"] = ("off", "off")
    elif mode == "both":
        with connection.cursor() as cursor:
            cursor.execute("SET default_transaction_read_only=on")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET default_transaction_read_only=off")
    else:
        with transaction.atomic():
            with connection.cursor() as cursor:
                if mode == "current_only":
                    cursor.execute("SET TRANSACTION READ ONLY")
                else:
                    cursor.execute("SELECT 1")  # Begin a writable transaction first.
                    cursor.execute("SET default_transaction_read_only=on")
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
@pytest.mark.parametrize("mode", MODES)
def test_read_only_current_or_default_mode_blocks_before_history_and_broker(write_mode_database, command, mode):
    broker, reference, executors = write_mode_database
    before = set(MigrationRecorder(connection).applied_migrations())
    with read_only_mode(reference, mode):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('transaction_read_only'),current_setting('default_transaction_read_only')")
                assert cursor.fetchone() == MODES[mode]
            if mode == "default_only":
                # The active transaction can still write; the session default
                # applies after commit. The owned transaction below rolls back.
                Group.objects.create(name="owned-default-mode-fixture")
                assert Group.objects.filter(name="owned-default-mode-fixture").exists()
            else:
                with pytest.raises(DatabaseError) as exc:
                    with transaction.atomic():
                        Group.objects.create(name="owned-read-only-refused")
                assert exc.value.__cause__.sqlstate == "25006"
        expected = CommandError if command else preflight.RuntimeUnavailable
        with pytest.raises(expected, match="^job_metadata_read_only$"):
            run_preflight(command)
        assert executors == []
        broker.ensure_connection.assert_not_called()
        assert before == set(MigrationRecorder(connection).applied_migrations())
    if connection.vendor == "postgresql":
        assert not Group.objects.filter(name="owned-default-mode-fixture").exists()


@pytest.mark.parametrize("command", [False, True])
def test_normal_write_modes_allow_existing_startup_receipt(write_mode_database, command):
    broker, _, executors = write_mode_database
    assert "current" in str(run_preflight(command))
    assert executors == [True]
    broker.ensure_connection.assert_called_once_with(max_retries=0)


@pytest.mark.parametrize("command", [False, True])
def test_write_mode_query_error_is_a_redacted_storage_failure(write_mode_database, monkeypatch, command):
    broker, _, executors = write_mode_database

    def unavailable():
        raise OperationalError("postgresql://private:secret@private-host/write-mode")

    monkeypatch.setattr(preflight, "check_metadata_write_mode", unavailable, raising=False)
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_storage_unavailable$"):
        run_preflight(command)
    assert executors == []
    broker.ensure_connection.assert_not_called()


@contextmanager
def shadow_settings_function():
    if connection.vendor != "postgresql":
        # SQLite has no PostgreSQL function namespaces; the caller still
        # exercises its explicit read-only response reference.
        yield
    else:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("CREATE FUNCTION public.current_setting(text) RETURNS text LANGUAGE sql IMMUTABLE AS $$ SELECT 'off'::text $$")
                cursor.execute("SET LOCAL search_path=public,pg_catalog")
            try:
                yield
            finally:
                transaction.set_rollback(True)


@pytest.mark.parametrize("command", [False, True])
def test_builtin_setting_lookup_cannot_be_shadowed(write_mode_database, command):
    broker, reference, executors = write_mode_database
    with shadow_settings_function(), read_only_mode(reference, "default_only"):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('default_transaction_read_only'),pg_catalog.current_setting('default_transaction_read_only')")
                assert cursor.fetchone() == ("off", "on")
        expected = CommandError if command else preflight.RuntimeUnavailable
        with pytest.raises(expected, match="^job_metadata_read_only$"):
            run_preflight(command)
        assert executors == []
        broker.ensure_connection.assert_not_called()
