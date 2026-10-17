"""Initializer authority observations must come from PostgreSQL built-ins."""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import Group
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def schema_authority(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    source = importlib.import_module("private_schema_init").SCHEMA_CODE
    blocks = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.With)]
    result = {}
    for key, marker, size in [("role", "pg_roles", 3), ("owner", "pg_encoding_to_char", 2)]:
        statements = [block.body[i:i + size] for block in blocks for i, node in enumerate(block.body)
                      if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                      and node.value.args and isinstance(node.value.args[0], ast.Constant)
                      and marker in str(node.value.args[0].value)]
        assert len(statements) == 1 and isinstance(statements[0][-1], ast.Assert)
        # Execute actual production SQL, fetch and policy assertion together.
        # Surrounding runtime/manifest, transport and publication are separate.
        result[key] = compile(ast.Module(body=statements[0], type_ignores=[]), "<actual-schema-" + key + ">", "exec")
    return result


def substitute_role(cursor, case):
    if case in {"role_view", "member_view", "member_operator", "combined"}:
        cursor.execute("""CREATE VIEW public.pg_roles AS SELECT oid,rolname,true AS rolcanlogin,
            false AS rolsuper,false AS rolcreatedb,false AS rolcreaterole,false AS rolreplication,false AS rolbypassrls
            FROM pg_catalog.pg_roles WHERE rolname OPERATOR(pg_catalog.=) current_user""")
    if case == "role_operator":
        cursor.execute("""CREATE FUNCTION public.schema_name_equal(name,name) RETURNS boolean LANGUAGE sql AS $$
            SELECT $1 OPERATOR(pg_catalog.=) 'pg_database_owner'::pg_catalog.name
            AND $2 OPERATOR(pg_catalog.=) current_user $$""")
        cursor.execute("CREATE OPERATOR public.= (PROCEDURE=public.schema_name_equal,LEFTARG=pg_catalog.name,RIGHTARG=pg_catalog.name)")
    elif case == "member_view":
        cursor.execute("CREATE VIEW public.pg_auth_members AS SELECT oid AS member FROM pg_catalog.pg_roles WHERE rolname OPERATOR(pg_catalog.=) current_user")
    elif case == "member_operator":
        cursor.execute("CREATE FUNCTION public.schema_oid_equal(oid,oid) RETURNS boolean LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'untrusted-schema-membership'; END $$")
        cursor.execute("CREATE OPERATOR public.= (PROCEDURE=public.schema_oid_equal,LEFTARG=pg_catalog.oid,RIGHTARG=pg_catalog.oid)")
    if case == "combined":
        cursor.execute("CREATE FUNCTION public.pg_backend_pid() RETURNS integer LANGUAGE sql AS $$ SELECT 424242 $$")
        cursor.execute("CREATE VIEW public.pg_stat_ssl AS SELECT 424242 AS pid,true AS ssl")
    elif case is not None:
        cursor.execute("CREATE " + ("TEMP" if case == "temporary" else "") + " VIEW "
                       + ("pg_stat_ssl" if case == "temporary" else "public.pg_stat_ssl")
                       + " AS SELECT pg_catalog.pg_backend_pid() AS pid,true AS ssl")
    cursor.execute("SET LOCAL search_path=public,pg_catalog")


@pytest.mark.parametrize("case", [None, "role_view", "role_operator", "member_view", "member_operator", "public", "temporary", "combined"])
def test_schema_role_tls_observations_ignore_substitutes(schema_authority, case):
    seed = Group.objects.create(name="owned-schema-authority-fixture")
    history = set(MigrationRecorder(connection).applied_migrations())
    if connection.vendor != "postgresql":
        # Explicit unsafe-response reference only; no PostgreSQL namespace,
        # role, membership or TLS semantics are emulated on SQLite.
        expected = ("owned", "fixture", False, True, False, True, False, False, False, False)
        cursor = MagicMock()
        cursor.fetchone.return_value = expected
        scope = {"c": cursor, "os": SimpleNamespace(environ={"DECLARAI_DB_NAME": "owned", "DECLARAI_DB_USER": "fixture"})}
        with pytest.raises(AssertionError):
            exec(schema_authority["role"], scope)
        assert scope["row"] == expected
    else:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.pg_backend_pid(),ssl FROM pg_catalog.pg_stat_ssl WHERE pid OPERATOR(pg_catalog.=) pg_catalog.pg_backend_pid()")
            original_backend = cursor.fetchone()
        options = dict(connection.settings_dict["OPTIONS"])
        plaintext = connection.copy(alias=connection.alias)
        assert plaintext.settings_dict["OPTIONS"] is not connection.settings_dict["OPTIONS"]
        plaintext.settings_dict["OPTIONS"]["sslmode"] = "disable"
        try:
            plaintext.ensure_connection()
            with plaintext.connection.transaction(force_rollback=True):
                with plaintext.cursor() as cursor:
                    cursor.execute("SELECT pg_catalog.current_database(),current_user")
                    database, user = cursor.fetchone()
                    expected = (database, user, False, True, False, True, False, False, False, False)
                    substitute_role(cursor, case)
                    scope = {"c": cursor, "os": SimpleNamespace(environ={"DECLARAI_DB_NAME": database, "DECLARAI_DB_USER": user})}
                    with pytest.raises(AssertionError):
                        exec(schema_authority["role"], scope)
                    assert scope["row"] == expected
        finally:
            plaintext.close()
            assert connection.settings_dict["OPTIONS"] == options
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.pg_backend_pid(),ssl FROM pg_catalog.pg_stat_ssl WHERE pid OPERATOR(pg_catalog.=) pg_catalog.pg_backend_pid()")
            assert cursor.fetchone() == original_backend
            cursor.execute("SELECT pg_catalog.to_regclass('public.pg_roles'),pg_catalog.to_regclass('public.pg_auth_members'),pg_catalog.to_regclass('public.pg_stat_ssl')")
            assert cursor.fetchone() == (None, None, None)
    assert set(MigrationRecorder(connection).applied_migrations()) == history
    assert Group.objects.get(pk=seed.pk).name == "owned-schema-authority-fixture"


@pytest.mark.parametrize("case", [None, "public", "temporary", "owner_function", "encoding_function", "name_operator"])
def test_schema_owner_encoding_observations_ignore_substitutes(schema_authority, case):
    seed = Group.objects.create(name="owned-schema-owner-fixture")
    history = set(MigrationRecorder(connection).applied_migrations())
    if connection.vendor != "postgresql":
        # Genuine owned/UTF8 response reference only, not catalog emulation.
        cursor = MagicMock()
        cursor.fetchone.return_value = (True,)
        exec(schema_authority["owner"], {"c": cursor})
    else:
        with transaction.atomic():
            with connection.cursor() as cursor:
                if case in {"public", "temporary"}:
                    cursor.execute("CREATE " + ("TEMP" if case == "temporary" else "") + " VIEW "
                                   + ("pg_database" if case == "temporary" else "public.pg_database")
                                   + " AS SELECT datname,0::pg_catalog.oid AS datdba,encoding FROM pg_catalog.pg_database")
                elif case == "owner_function":
                    cursor.execute("CREATE FUNCTION public.pg_get_userbyid(oid) RETURNS name LANGUAGE sql AS $$ SELECT 'not_the_owner'::pg_catalog.name $$")
                elif case == "encoding_function":
                    cursor.execute("CREATE FUNCTION public.pg_encoding_to_char(integer) RETURNS name LANGUAGE sql AS $$ SELECT 'LATIN1'::pg_catalog.name $$")
                elif case == "name_operator":
                    cursor.execute("CREATE FUNCTION public.schema_owner_equal(name,name) RETURNS boolean LANGUAGE sql AS $$ SELECT false $$")
                    cursor.execute("CREATE OPERATOR public.= (PROCEDURE=public.schema_owner_equal,LEFTARG=pg_catalog.name,RIGHTARG=pg_catalog.name)")
                cursor.execute("SET LOCAL search_path=public,pg_catalog")
                exec(schema_authority["owner"], {"c": cursor})
            transaction.set_rollback(True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.to_regclass('public.pg_database')")
            assert cursor.fetchone() == (None,)
    assert set(MigrationRecorder(connection).applied_migrations()) == history
    assert Group.objects.get(pk=seed.pk).name == "owned-schema-owner-fixture"
