"""Application dependency evidence must describe the actual PostgreSQL session."""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.db import connection

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def probe_authority(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    probe = importlib.import_module("private_dependency_start").PROBE
    blocks = [
        node for node in ast.walk(ast.parse(probe))
        if isinstance(node, ast.With) and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr == "cursor"
            for item in node.items
        )
    ]
    assert len(blocks) == 1
    # Execute the production SQL, fetch and assertion together. The test never
    # mirrors that policy or runs the surrounding transport/credential code.
    return compile(ast.Module(body=blocks[0].body, type_ignores=[]), "<dependency-probe-authority>", "exec")


def substitute(cursor, shadow):
    if shadow in {"role_view", "member_view", "member_operator", "public", "temporary", "combined"}:
        cursor.execute("""CREATE VIEW public.pg_roles AS SELECT oid,rolname,false AS rolsuper,
            false AS rolcreatedb,false AS rolcreaterole,false AS rolreplication,false AS rolbypassrls
            FROM pg_catalog.pg_roles WHERE rolname OPERATOR(pg_catalog.=) current_user""")
    if shadow == "role_operator":
        cursor.execute("""CREATE FUNCTION public.probe_name_equal(name,name) RETURNS boolean LANGUAGE sql AS $$
            SELECT $1 OPERATOR(pg_catalog.=) 'pg_database_owner'::pg_catalog.name
            AND $2 OPERATOR(pg_catalog.=) current_user $$""")
        cursor.execute("CREATE OPERATOR public.= (PROCEDURE=public.probe_name_equal,LEFTARG=pg_catalog.name,RIGHTARG=pg_catalog.name)")
    elif shadow == "member_view":
        # CI has no explicit membership. Fabricating one still must not alter
        # the observed row; a separate owned membership profile proves hiding.
        cursor.execute("""CREATE VIEW public.pg_auth_members AS SELECT oid AS member
            FROM pg_catalog.pg_roles WHERE rolname OPERATOR(pg_catalog.=) current_user""")
    elif shadow == "member_operator":
        cursor.execute("""CREATE FUNCTION public.probe_oid_equal(oid,oid) RETURNS boolean
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'untrusted-probe-membership'; END $$""")
        cursor.execute("CREATE OPERATOR public.= (PROCEDURE=public.probe_oid_equal,LEFTARG=pg_catalog.oid,RIGHTARG=pg_catalog.oid)")
    if shadow == "combined":
        cursor.execute("CREATE FUNCTION public.pg_backend_pid() RETURNS integer LANGUAGE sql AS $$ SELECT 424242 $$")
        cursor.execute("CREATE VIEW public.pg_stat_ssl AS SELECT 424242 AS pid,true AS ssl")
    elif shadow == "temporary":
        cursor.execute("CREATE TEMP VIEW pg_stat_ssl AS SELECT pg_catalog.pg_backend_pid() AS pid,true AS ssl")
    else:
        cursor.execute("CREATE VIEW public.pg_stat_ssl AS SELECT pg_catalog.pg_backend_pid() AS pid,true AS ssl")
    cursor.execute("SET LOCAL search_path=public,pg_catalog")


@pytest.mark.parametrize("shadow", ["role_view", "role_operator", "member_view", "member_operator", "public", "temporary", "combined"])
def test_application_probe_rejects_substituted_authority(probe_authority, shadow):
    if connection.vendor != "postgresql":
        # Explicit unsafe-authority response reference only; SQLite implements
        # none of PostgreSQL's role, membership, TLS or namespace semantics.
        cursor = MagicMock()
        expected = ("owned", "fixture", False, False, True, False, False, False, False)
        cursor.fetchone.return_value = expected
        scope = {"cursor": cursor, "os": SimpleNamespace(environ={"DEPENDENCY_DATABASE": "owned", "DEPENDENCY_USER": "fixture"})}
        with pytest.raises(AssertionError):
            exec(probe_authority, scope)
        assert scope["row"] == expected
        return
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
                cursor.execute("SELECT pg_catalog.current_database(),current_user")
                database, user = cursor.fetchone()
                # The owned native fixture is CREATEDB, otherwise non-elevated,
                # with no explicit membership. This copy is actually plaintext.
                expected = (database, user, False, False, True, False, False, False, False)
                substitute(cursor, shadow)
                scope = {"cursor": cursor, "os": SimpleNamespace(environ={"DEPENDENCY_DATABASE": database, "DEPENDENCY_USER": user})}
                with pytest.raises(AssertionError):
                    exec(probe_authority, scope)
                assert scope["row"] == expected
    finally:
        plaintext.close()
        assert connection.settings_dict["OPTIONS"] == original_options
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_catalog.pg_backend_pid(),ssl FROM pg_catalog.pg_stat_ssl WHERE pid OPERATOR(pg_catalog.=) pg_catalog.pg_backend_pid()")
        assert cursor.fetchone() == original_backend
        cursor.execute("SELECT pg_catalog.to_regclass('public.pg_roles'),pg_catalog.to_regclass('public.pg_auth_members'),pg_catalog.to_regclass('public.pg_stat_ssl')")
        assert cursor.fetchone() == (None, None, None)
