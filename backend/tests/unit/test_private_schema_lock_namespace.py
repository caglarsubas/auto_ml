"""Initializer exclusion must use the real PostgreSQL advisory lock."""

import ast
import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError, connection, transaction
from django.db.migrations.recorder import MigrationRecorder

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def schema_lock(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    source = importlib.import_module("private_schema_init").SCHEMA_CODE
    blocks = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.With)
              and any(isinstance(item.context_expr, ast.Call)
                      and isinstance(item.context_expr.func, ast.Attribute)
                      and item.context_expr.func.attr == "cursor" for item in n.items)]
    statements = [(block.body[i], block.body[i + 1]) for block in blocks
                  for i, node in enumerate(block.body[:-1]) if isinstance(node, ast.Expr)
                  and isinstance(node.value, ast.Call) and node.value.args
                  and isinstance(node.value.args[0], ast.Constant)
                  and "pg_try_advisory_lock" in str(node.value.args[0].value)]
    assert len(statements) == 1 and isinstance(statements[0][1], ast.Assert)
    # Compile the actual production statement and its acceptance assertion.
    # Role/TLS, graph/state/migration and controller publication are separate.
    return compile(ast.Module(body=list(statements[0]), type_ignores=[]), "<actual-schema-lock>", "exec")


@pytest.mark.parametrize("held", [False, True], ids=["free", "held"])
@pytest.mark.parametrize("substitute", [None, "accept", "deny", "error", "side_effect"])
def test_schema_lock_ignores_caller_functions(schema_lock, held, substitute):
    seed = Group.objects.create(name="owned-schema-lock-fixture")
    history = set(MigrationRecorder(connection).applied_migrations())
    if connection.vendor != "postgresql":
        # Explicit real-lock response reference only; SQLite has no PostgreSQL
        # session advisory locks, namespace resolution or competing session.
        cursor = MagicMock()
        cursor.fetchone.return_value = (not held,)
        if held:
            with pytest.raises(AssertionError):
                exec(schema_lock, {"c": cursor})
        else:
            exec(schema_lock, {"c": cursor})
    else:
        contender = connection.copy(alias=connection.alias)
        try:
            with transaction.atomic():
                with connection.cursor() as cursor, contender.cursor() as other:
                    cursor.execute("CREATE TABLE public.schema_lock_effects (value text)")
                    if substitute is not None:
                        body = {"accept": "RETURN true;", "deny": "RETURN false;",
                                "error": "RAISE EXCEPTION 'untrusted-schema-lock';",
                                "side_effect": "INSERT INTO public.schema_lock_effects VALUES ('called'); RETURN pg_catalog.pg_try_advisory_lock($1,$2);"}[substitute]
                        cursor.execute("CREATE FUNCTION public.pg_try_advisory_lock(integer,integer) RETURNS boolean LANGUAGE plpgsql AS $$ BEGIN " + body + " END $$")
                    cursor.execute("SET LOCAL search_path=public,pg_catalog")
                    if held:
                        other.execute("SELECT pg_catalog.pg_try_advisory_lock(1584948041,42)")
                        assert other.fetchone() == (True,), "Contender must own the genuine lock"
                    accepted = True
                    try:
                        with transaction.atomic():
                            exec(schema_lock, {"c": cursor})
                    except (AssertionError, DatabaseError):
                        accepted = False
                    assert accepted is not held, "Production acceptance must match actual lock availability"
                    cursor.execute("""SELECT pg_catalog.count(*) FROM pg_catalog.pg_locks
                        WHERE locktype OPERATOR(pg_catalog.=) 'advisory'::pg_catalog.text
                        AND pid OPERATOR(pg_catalog.=) pg_catalog.pg_backend_pid()
                        AND classid OPERATOR(pg_catalog.=) 1584948041::pg_catalog.oid
                        AND objid OPERATOR(pg_catalog.=) 42::pg_catalog.oid
                        AND objsubid OPERATOR(pg_catalog.=) 2::pg_catalog.int2 AND granted""")
                    assert cursor.fetchone() == (0 if held else 1,), "Actual session lock must support the receipt"
                    cursor.execute("SELECT value FROM public.schema_lock_effects")
                    assert cursor.fetchall() == [], "Caller-defined lock functions must never execute"
                transaction.set_rollback(True)
        finally:
            contender.close()
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_catalog.pg_advisory_unlock_all()")
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.to_regclass('public.schema_lock_effects')")
            assert cursor.fetchone() == (None,)
    assert set(MigrationRecorder(connection).applied_migrations()) == history
    assert Group.objects.get(pk=seed.pk).name == "owned-schema-lock-fixture"
