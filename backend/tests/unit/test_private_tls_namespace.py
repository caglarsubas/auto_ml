"""Private TLS attestation must describe the actual metadata backend."""

from contextlib import contextmanager
from io import StringIO
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from execution_jobs import preflight

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


@contextmanager
def plaintext_shadow(monkeypatch, shadow):
    if connection.vendor != "postgresql":
        # Explicit TLS denial response reference only; SQLite has no PostgreSQL
        # TLS session view, backend PID or function/operator namespace behavior.
        database = MagicMock(vendor="postgresql")
        database.cursor.return_value.__enter__.return_value.fetchone.return_value = (False,)
        monkeypatch.setattr(preflight, "connection", database)
        yield
        return
    # This copy targets only pytest's owned database, even when the default
    # fixture uses TLS. It never changes the default connection or its settings.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_catalog.pg_backend_pid(),ssl FROM pg_catalog.pg_stat_ssl WHERE pid OPERATOR(pg_catalog.=) pg_catalog.pg_backend_pid()")
        original_backend = cursor.fetchone()
    original_options = dict(connection.settings_dict["OPTIONS"])
    plaintext = connection.copy(alias=connection.alias)
    assert plaintext.settings_dict["OPTIONS"] is not connection.settings_dict["OPTIONS"]
    plaintext.settings_dict["OPTIONS"]["sslmode"] = "disable"
    try:
        plaintext.ensure_connection()
        with plaintext.connection.transaction(force_rollback=True):
            with plaintext.cursor() as cursor:
                if shadow == "combined":
                    cursor.execute("CREATE FUNCTION public.pg_backend_pid() RETURNS integer LANGUAGE sql AS $$ SELECT 424242 $$")
                    cursor.execute("CREATE VIEW public.pg_stat_ssl AS SELECT 424242 AS pid,true AS ssl")
                elif shadow == "public":
                    cursor.execute("CREATE VIEW public.pg_stat_ssl AS SELECT pg_catalog.pg_backend_pid() AS pid,true AS ssl")
                elif shadow == "temporary":
                    cursor.execute("CREATE TEMP VIEW pg_stat_ssl AS SELECT pg_catalog.pg_backend_pid() AS pid,true AS ssl")
                else:
                    cursor.execute("""CREATE FUNCTION public.tls_pid_equal(integer,integer) RETURNS boolean
                        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'untrusted-tls-operator'; END $$""")
                    cursor.execute("""CREATE OPERATOR public.= (PROCEDURE=public.tls_pid_equal,
                        LEFTARG=pg_catalog.int4, RIGHTARG=pg_catalog.int4)""")
                cursor.execute("SET LOCAL search_path=public,pg_catalog")
                cursor.execute("SELECT ssl FROM pg_catalog.pg_stat_ssl WHERE pid OPERATOR(pg_catalog.=) pg_catalog.pg_backend_pid()")
                assert cursor.fetchone() == (False,), "Owned test connection must actually be plaintext"
                if shadow != "operator":
                    cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
                    assert cursor.fetchone() == (True,)
            monkeypatch.setattr(preflight, "connection", plaintext)
            yield
    finally:
        plaintext.close()
        assert connection.settings_dict["OPTIONS"] == original_options
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_catalog.pg_backend_pid(),ssl FROM pg_catalog.pg_stat_ssl WHERE pid OPERATOR(pg_catalog.=) pg_catalog.pg_backend_pid()")
        assert cursor.fetchone() == original_backend
        cursor.execute("SELECT pg_catalog.to_regclass('public.pg_stat_ssl') IS NULL")
        assert cursor.fetchone() == (True,)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("shadow", ["public", "temporary", "combined", "operator"])
def test_plaintext_namespace_substitutes_cannot_claim_verified_tls(settings, monkeypatch, command, shadow):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    settings.DECLARAI_JOBS_ENABLED = True
    executor = MagicMock()
    executor.return_value.migration_plan.return_value = []
    monkeypatch.setattr(preflight, "MigrationExecutor", executor)
    phases = []
    for name in ("check_metadata_write_mode", "check_schema", "check_schema_privileges", "check_schema_row_security"):
        check = MagicMock()
        phases.append(check)
        monkeypatch.setattr(preflight, name, check)
    broker = MagicMock()
    monkeypatch.setattr("backend.celery.app.connection_for_write", broker)
    with plaintext_shadow(monkeypatch, shadow):
        expected = CommandError if command else preflight.RuntimeUnavailable
        with pytest.raises(expected, match="^job_metadata_tls_required$"):
            if command:
                call_command("check_job_runtime", stdout=StringIO())
            else:
                preflight.check_runtime()
        executor.assert_not_called()
        broker.assert_not_called()
        for phase in phases:
            phase.assert_not_called()
