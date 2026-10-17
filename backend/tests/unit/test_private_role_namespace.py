"""Caller-controlled namespaces cannot conceal elevated PostgreSQL authority."""

from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction

from execution_jobs import preflight
from tests.unit.test_service_role_preflight import launcher  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


@contextmanager
def shadow_role_namespace(monkeypatch, shadow):
    if connection.vendor != "postgresql":
        # Explicit denial response reference only. SQLite does not implement
        # PostgreSQL role catalogs, search paths or membership functions.
        database = MagicMock(vendor="postgresql")
        database.cursor.return_value.__enter__.return_value.fetchone.return_value = (False,) * 5 + (True,)
        monkeypatch.setattr(preflight, "connection", database)
        yield
        return
    with transaction.atomic():
        with connection.cursor() as cursor:
            if shadow in ("catalog", "combined"):
                cursor.execute("""CREATE VIEW public.pg_roles AS SELECT oid,rolname,
                    false AS rolsuper,false AS rolcreatedb,false AS rolcreaterole,
                    false AS rolreplication,false AS rolbypassrls FROM pg_catalog.pg_roles""")
                cursor.execute("GRANT SELECT ON public.pg_roles TO PUBLIC")
            if shadow in ("function", "combined"):
                cursor.execute("""CREATE FUNCTION public.pg_has_role(name,oid,text)
                    RETURNS boolean LANGUAGE sql IMMUTABLE AS $$ SELECT false $$""")
                cursor.execute("SET LOCAL ROLE pg_database_owner")
            cursor.execute("SET LOCAL search_path=public,pg_catalog")
            cursor.execute("SELECT rolcreatedb FROM pg_catalog.pg_roles WHERE rolname=session_user")
            assert cursor.fetchone() == (True,), "Owned fixture must exercise actual elevated session authority"
            if shadow in ("catalog", "combined"):
                cursor.execute("SELECT rolcreatedb FROM pg_roles WHERE rolname=session_user")
                assert cursor.fetchone() == (False,)
            if shadow in ("function", "combined"):
                cursor.execute("""SELECT current_user<>session_user,
                    pg_has_role(session_user,(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=session_user),'MEMBER'),
                    pg_catalog.pg_has_role(session_user,(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=session_user),'MEMBER')""")
                assert cursor.fetchone() == (True, False, True)
            if shadow == "operator":
                cursor.execute("""CREATE FUNCTION public.role_equal(name,name) RETURNS boolean
                    LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'untrusted-role-operator'; END $$""")
                cursor.execute("""CREATE OPERATOR public.= (PROCEDURE=public.role_equal,
                    LEFTARG=pg_catalog.name, RIGHTARG=pg_catalog.name)""")
                cursor.execute("SELECT pg_catalog.to_regoperator('public.=(name,name)') IS NOT NULL")
                assert cursor.fetchone() == (True,)
        try:
            yield
        finally:
            transaction.set_rollback(True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user=session_user,pg_catalog.to_regclass('public.pg_roles') IS NULL")
        assert cursor.fetchone() == (True, True)


@pytest.mark.parametrize("entrypoint", ["direct", "management", "api", "worker", "dispatcher", "preflight"])
@pytest.mark.parametrize("shadow", ["catalog", "function", "combined", "operator"])
def test_role_shadowing_cannot_allow_elevated_service_execution(launcher, monkeypatch, entrypoint, shadow):
    from execution_jobs.management.commands import check_job_runtime

    service, executions = launcher
    transport = MagicMock(return_value={"test_transport_seam": True})
    monkeypatch.setattr(check_job_runtime, "check_runtime", transport)

    def management(args, **kwargs):
        try:
            call_command("check_job_runtime", *args[3:], stdout=StringIO())
        except CommandError as error:
            assert str(error) == "job_application_role_elevated"
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(service.subprocess, "run", management)
    with shadow_role_namespace(monkeypatch, shadow):
        if entrypoint == "direct":
            with pytest.raises(preflight.RuntimeUnavailable, match="^job_application_role_elevated$"):
                preflight.check_application_role()
        elif entrypoint == "management":
            with pytest.raises(CommandError, match="^job_application_role_elevated$"):
                call_command("check_job_runtime", "--require-application-role", stdout=StringIO())
        else:
            with pytest.raises(service.ManifestError, match="^private_service_preflight_failed$"):
                service.launch([entrypoint])
        # Management keeps its existing transport/schema-before-role order.
        assert transport.call_count == (0 if entrypoint == "direct" else 1)
        assert not executions
