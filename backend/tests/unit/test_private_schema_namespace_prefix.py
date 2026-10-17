"""Only PostgreSQL's literal reserved schema prefix may bypass foreign-state checks."""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.apps import apps
from django.contrib.auth.models import Group
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def schema_state(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    source = importlib.import_module("private_schema_init").SCHEMA_CODE
    functions = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == "state"]
    assert len(functions) == 1
    code = compile(ast.Module(body=functions, type_ignores=[]), "<actual-schema-state>", "exec")

    def evaluate(database, user):
        executor = MigrationExecutor(connection)
        scope = {"connection": database, "loader": executor.loader, "executor": executor, "apps": apps,
                 "os": SimpleNamespace(environ={"DECLARAI_DB_USER": user})}
        exec(code, scope)
        return scope["state"]()

    return evaluate


@pytest.mark.parametrize("namespace", ["pgx_archive", "pgarchive", "pg-archive", "pg9", "pgø_archive", "pg", "PgX_archive", "ordinary_archive", None])
def test_foreign_schema_names_never_inherit_reserved_prefix_status(schema_state, namespace):
    seed = Group.objects.create(name="owned-prefix-fixture")
    history = set(MigrationRecorder(connection).applied_migrations())
    expected = "current" if namespace is None else "foreign"
    if connection.vendor != "postgresql":
        # Explicit state-response references only. SQLite has no PostgreSQL
        # namespaces or reserved-prefix/catalog semantics; do not emulate LIKE.
        database = MagicMock()
        cursor = database.cursor.return_value.__enter__.return_value
        if namespace is not None:
            cursor.fetchall.return_value = [(namespace,)]
        else:
            wanted = {"django_migrations"} | {m._meta.db_table for m in apps.get_models(include_auto_created=True)
                                             if m._meta.managed and not m._meta.proxy}
            cursor.fetchall.side_effect = [[], [], [("public", name, "r", "fixture") for name in wanted], []]
            cursor.fetchone.return_value = (0,)
        assert schema_state(database, "fixture") == expected
    else:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                user = cursor.fetchone()[0]
                if namespace is None:
                    # PostgreSQL creates genuine pg_temp/pg_toast_temp schemas.
                    # These and the default system schemas must remain accepted.
                    cursor.execute("CREATE TEMP TABLE prefix_fixture (value text)")
                else:
                    quoted = connection.ops.quote_name(namespace)
                    cursor.execute("CREATE SCHEMA " + quoted)
                    cursor.execute("CREATE TABLE " + quoted + ".retained (value text)")
                    cursor.execute("INSERT INTO " + quoted + ".retained VALUES ('owned-row')")
            assert schema_state(connection, user) == expected
            assert set(MigrationRecorder(connection).applied_migrations()) == history
            if namespace is not None:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT value FROM " + quoted + ".retained")
                    assert cursor.fetchall() == [("owned-row",)]
            transaction.set_rollback(True)
        if namespace is not None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_catalog.to_regnamespace(%s)", [namespace])
                assert cursor.fetchone() == (None,)
    assert set(MigrationRecorder(connection).applied_migrations()) == history
    assert Group.objects.get(pk=seed.pk).name == "owned-prefix-fixture"
