"""Untrusted catalog operators cannot substitute physical schema evidence."""

from io import StringIO
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]
CASES = {
    "attribute_join": ("check_schema", preflight.SchemaMismatch, "job_schema_invalid"),
    "namespace": ("check_schema", preflight.SchemaMismatch, "job_schema_invalid"),
    "after_presence": ("check_schema_privileges", preflight.SchemaPrivilegesMismatch, "job_schema_privileges_invalid"),
    "after_privileges": ("check_schema_row_security", preflight.SchemaRowSecurityMismatch, "job_schema_row_security_invalid"),
}


def alias_schema():
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE public.auth_group RENAME TO catalog_fixture_original")
        cursor.execute("CREATE SCHEMA catalog_fixture")
        cursor.execute("CREATE TABLE catalog_fixture.auth_group (LIKE public.catalog_fixture_original INCLUDING ALL)")
        cursor.execute("""CREATE FUNCTION public.catalog_name_equal(name,name) RETURNS boolean LANGUAGE sql AS $$
            SELECT $1 OPERATOR(pg_catalog.=) $2 OR ($1 OPERATOR(pg_catalog.=) 'catalog_fixture'::pg_catalog.name
                AND $2 OPERATOR(pg_catalog.=) 'public'::pg_catalog.name) $$""")
        cursor.execute("CREATE OPERATOR public.= (PROCEDURE=public.catalog_name_equal,LEFTARG=pg_catalog.name,RIGHTARG=pg_catalog.name)")
        cursor.execute("SET LOCAL search_path=catalog_fixture,public,pg_catalog")
        cursor.execute("SELECT pg_catalog.to_regclass('public.auth_group') IS NULL")
        assert cursor.fetchone() == (True,)


@pytest.fixture
def catalog_database(settings, monkeypatch):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    settings.DECLARAI_JOBS_ENABLED = True
    transport = MagicMock(vendor="postgresql")
    transport.alias = connection.alias
    transport.introspection = connection.introspection
    calls = [0]

    def cursor():
        calls[0] += 1
        if calls[0] == 1:
            return MagicMock(__enter__=lambda _: MagicMock(fetchone=lambda: (True,)), __exit__=lambda *args: False)
        return connection.cursor()

    transport.cursor.side_effect = cursor
    monkeypatch.setattr(preflight, "connection", transport)
    monkeypatch.setattr(preflight, "MigrationExecutor", lambda _: MigrationExecutor(connection))
    broker = MagicMock()
    monkeypatch.setattr("backend.celery.app.connection_for_write", lambda: broker)
    if connection.vendor == "sqlite":
        # Explicit denial references only. SQLite has no PostgreSQL catalog,
        # operator namespace or managed-public-schema semantics.
        monkeypatch.setattr(preflight, "check_metadata_write_mode", lambda: None)
        for name in ("check_schema", "check_schema_privileges", "check_schema_row_security"):
            monkeypatch.setattr(preflight, name, lambda: None)
    return broker.__enter__.return_value


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("case", CASES)
def test_catalog_substitutions_cannot_hide_lost_public_schema(catalog_database, monkeypatch, command, case):
    phase, mismatch, reason = CASES[case]
    seed = Group.objects.create(name="owned-catalog-fixture")
    history = set(MigrationRecorder(connection).applied_migrations())
    with transaction.atomic():
        if connection.vendor == "sqlite":
            def denied():
                raise mismatch
            monkeypatch.setattr(preflight, phase, denied)
        elif case == "attribute_join":
            with connection.cursor() as cursor:
                cursor.execute("SELECT 'public.auth_group'::pg_catalog.regclass::pg_catalog.oid,'public.auth_permission'::pg_catalog.regclass::pg_catalog.oid")
                target, donor = cursor.fetchone()
                cursor.execute("ALTER TABLE public.auth_group DROP COLUMN name")
                cursor.execute(f"""CREATE FUNCTION public.catalog_oid_equal(oid,oid) RETURNS boolean LANGUAGE sql AS $$
                    SELECT $1 OPERATOR(pg_catalog.=) $2 OR ($1 OPERATOR(pg_catalog.=) {donor}::pg_catalog.oid
                        AND $2 OPERATOR(pg_catalog.=) {target}::pg_catalog.oid) $$""")
                cursor.execute("CREATE OPERATOR public.= (PROCEDURE=public.catalog_oid_equal,LEFTARG=pg_catalog.oid,RIGHTARG=pg_catalog.oid)")
                cursor.execute("SET LOCAL search_path=public,pg_catalog")
            with pytest.raises(DatabaseError) as error:
                with transaction.atomic():
                    Group.objects.get(pk=seed.pk)
            assert error.value.__cause__.sqlstate == "42703"
        elif case == "namespace":
            alias_schema()
        else:
            prior_name = "check_schema" if case == "after_presence" else "check_schema_privileges"
            prior = getattr(preflight, prior_name)

            def change_after_validation():
                prior()
                alias_schema()

            monkeypatch.setattr(preflight, prior_name, change_after_validation)
        try:
            expected = CommandError if command else preflight.RuntimeUnavailable
            with pytest.raises(expected, match="^" + reason + "$"):
                if command:
                    call_command("check_job_runtime", stdout=StringIO())
                else:
                    preflight.check_runtime()
            catalog_database.ensure_connection.assert_not_called()
            assert set(MigrationRecorder(connection).applied_migrations()) == history
        finally:
            transaction.set_rollback(True)
    assert Group.objects.get(pk=seed.pk).name == "owned-catalog-fixture"
