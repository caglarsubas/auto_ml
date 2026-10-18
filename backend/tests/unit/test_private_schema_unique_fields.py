"""Declared field uniqueness needs a genuine immediate local constraint."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight, schema_presence
from tests.unit.test_private_schema_presence import physical_database  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]

CASES = ["missing_user", "missing_group", "index_only", "wrong_column", "compound", "partial",
         "expression", "deferred", "initially_deferred", "catalog_shadow", "operator_forgery"]


def run(command):
    return call_command("check_job_runtime") if command else preflight.check_runtime()


def drop_unique(cursor, table="auth_user", column="username"):
    cursor.execute("SELECT k.conname FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_attribute a ON a.attrelid OPERATOR(pg_catalog.=) k.conrelid WHERE k.conrelid OPERATOR(pg_catalog.=) %s::pg_catalog.regclass AND a.attname OPERATOR(pg_catalog.=) %s::pg_catalog.name AND k.contype OPERATOR(pg_catalog.=) 'u'::pg_catalog.\"char\" AND k.conkey OPERATOR(pg_catalog.=) ARRAY[a.attnum]::pg_catalog.int2[]", ["public." + table, column])
    keys = cursor.fetchall()
    assert len(keys) == 1
    q = connection.ops.quote_name
    cursor.execute(f"ALTER TABLE public.{q(table)} DROP CONSTRAINT {q(keys[0][0])}")


def reference_denial(monkeypatch, table, column):
    # Explicit denial reference only; SQLite does not emulate native constraint,
    # index, NULL-mode, namespace or operator semantics.
    @contextmanager
    def catalog():
        rows = [(t, "r", (t, c) != (table, column), c)
                for t, columns in schema_presence.required_schema().items() for c in columns]
        yield SimpleNamespace(execute=lambda *args: None, fetchall=lambda: rows)

    monkeypatch.setattr(schema_presence, "connection", SimpleNamespace(cursor=catalog))


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("case", CASES)
def test_unique_field_mismatch_blocks_before_broker(physical_database, monkeypatch, command, case):
    seed = User.objects.create(username="u", password="retained-password")
    group = Group.objects.create(name="g")
    history = set(MigrationRecorder(connection).applied_migrations())
    table, column = ("auth_group", "name") if case == "missing_group" else ("auth_user", "username")
    if connection.vendor == "sqlite":
        reference_denial(monkeypatch, table, column)
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                if case == "catalog_shadow":
                    cursor.execute("CREATE TEMP TABLE pg_constraint AS SELECT * FROM pg_catalog.pg_constraint")
                    cursor.execute("CREATE TEMP TABLE pg_index AS SELECT * FROM pg_catalog.pg_index")
                drop_unique(cursor, table, column)
                if case == "index_only":
                    cursor.execute("CREATE UNIQUE INDEX unique_fixture_index ON public.auth_user (username)")
                elif case in {"wrong_column", "operator_forgery"}:
                    cursor.execute("ALTER TABLE public.auth_user ADD UNIQUE (email)")
                elif case == "compound":
                    cursor.execute("ALTER TABLE public.auth_user ADD UNIQUE (username,id)")
                elif case == "partial":
                    cursor.execute("CREATE UNIQUE INDEX unique_fixture_partial ON public.auth_user (username) WHERE is_active")
                elif case == "expression":
                    cursor.execute("CREATE UNIQUE INDEX unique_fixture_expression ON public.auth_user (lower(username))")
                elif case in {"deferred", "initially_deferred"}:
                    mode = "DEFERRED" if case == "initially_deferred" else "IMMEDIATE"
                    cursor.execute(f"ALTER TABLE public.auth_user ADD UNIQUE (username) DEFERRABLE INITIALLY {mode}")
                if case == "catalog_shadow":
                    cursor.execute("SET LOCAL search_path=pg_temp,public,pg_catalog")
                elif case == "operator_forgery":
                    cursor.execute("CREATE FUNCTION public.unique_fixture_any_key(pg_catalog.int2[],pg_catalog.int2[]) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true'")
                    cursor.execute("CREATE OPERATOR public.= (LEFTARG=pg_catalog.int2[], RIGHTARG=pg_catalog.int2[], FUNCTION=public.unique_fixture_any_key)")
                    cursor.execute("SET LOCAL search_path=public,pg_catalog")
                cursor.execute("SELECT username,password FROM public.auth_user WHERE id=%s", [seed.pk])
                assert cursor.fetchone() == ("u", "retained-password")
        try:
            expected = CommandError if command else preflight.RuntimeUnavailable
            with pytest.raises(expected, match="^job_schema_invalid$"):
                run(command)
            physical_database.ensure_connection.assert_not_called()
            assert set(MigrationRecorder(connection).applied_migrations()) == history
        finally:
            transaction.set_rollback(True)
    assert User.objects.get(username="u").pk == seed.pk
    assert User.objects.get(pk=seed.pk).password == "retained-password"
    assert Group.objects.get(name="g").pk == group.pk
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("variant", ["genuine", "renamed", "included", "nonnull_not_distinct", "extra_unique"])
def test_genuine_unique_fields_and_writes_remain_supported(physical_database, command, variant):
    seed = User.objects.create(username="u", password="retained-password")
    history = set(MigrationRecorder(connection).applied_migrations())
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                if variant == "renamed":
                    cursor.execute("ALTER TABLE public.auth_user RENAME CONSTRAINT auth_user_username_key TO unique_fixture_renamed")
                elif variant == "included":
                    drop_unique(cursor)
                    cursor.execute("CREATE UNIQUE INDEX unique_fixture_covering ON public.auth_user (username) INCLUDE (email)")
                    cursor.execute("ALTER TABLE public.auth_user ADD CONSTRAINT unique_fixture_custom UNIQUE USING INDEX unique_fixture_covering")
                elif variant == "nonnull_not_distinct":
                    drop_unique(cursor)
                    cursor.execute("ALTER TABLE public.auth_user ADD UNIQUE NULLS NOT DISTINCT (username)")
                elif variant == "extra_unique":
                    cursor.execute("ALTER TABLE public.auth_user ADD COLUMN unique_fixture_extra int UNIQUE")
                cursor.execute("SELECT i.indnkeyatts,i.indnatts FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_index i ON i.indexrelid OPERATOR(pg_catalog.=) k.conindid JOIN pg_catalog.pg_attribute a ON a.attrelid OPERATOR(pg_catalog.=) k.conrelid AND a.attname OPERATOR(pg_catalog.=) 'username'::pg_catalog.name WHERE k.conrelid OPERATOR(pg_catalog.=) 'public.auth_user'::pg_catalog.regclass AND k.contype OPERATOR(pg_catalog.=) 'u'::pg_catalog.\"char\" AND k.conkey OPERATOR(pg_catalog.=) ARRAY[a.attnum]::pg_catalog.int2[]")
                assert cursor.fetchone() == (1, 2 if variant == "included" else 1)
        elif variant == "extra_unique":
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE auth_user ADD COLUMN unique_fixture_extra int")
        result = run(command)
        if not command:
            assert result["migrations"] == "current"
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        other = User.objects.create(username="unique-control", password="supported", email=seed.email)
        assert other.pk != seed.pk and User.objects.filter(email=seed.email).count() == 2
        # Ordinary local foreign keys must not inherit their target's uniqueness.
        first, second = Group.objects.create(name="first"), Group.objects.create(name="second")
        seed.groups.add(first, second)
        assert seed.groups.count() == 2
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create(username="u", password="duplicate")
        with pytest.raises(IntegrityError), transaction.atomic():
            Group.objects.create(name="first")
        transaction.set_rollback(True)
    assert User.objects.get(username="u").pk == seed.pk
    assert User.objects.get(pk=seed.pk).password == "retained-password"
    assert not User.objects.filter(username="unique-control").exists()
    assert not Group.objects.exists()
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("not_distinct", [False, True])
def test_nullable_unique_declaration_preserves_default_null_semantics(physical_database, monkeypatch, command, not_distinct):
    history = set(MigrationRecorder(connection).applied_migrations())

    def nullable_state(database):
        assert database is None
        loader = MigrationLoader(None)
        state = loader.project_state()
        # ModelState clones field dictionaries shallowly. Clone the field too,
        # so the migration module's declarations survive this fixture unchanged.
        field = state.models[("auth", "group")].fields["name"].clone()
        field.null = True
        state.models[("auth", "group")].fields["name"] = field
        loader.project_state = lambda: state
        return loader

    # An actual complete migration state with an explicitly changed declaration,
    # not an emulation of PostgreSQL index semantics or a production migration.
    monkeypatch.setattr(schema_presence, "MigrationLoader", nullable_state)
    if connection.vendor == "sqlite" and not_distinct:
        reference_denial(monkeypatch, "auth_group", "name")
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE public.auth_group ALTER COLUMN name DROP NOT NULL")
                if not_distinct:
                    drop_unique(cursor, "auth_group", "name")
                    cursor.execute("ALTER TABLE public.auth_group ADD UNIQUE NULLS NOT DISTINCT (name)")
        try:
            if not_distinct:
                expected = CommandError if command else preflight.RuntimeUnavailable
                with pytest.raises(expected, match="^job_schema_invalid$"):
                    run(command)
                physical_database.ensure_connection.assert_not_called()
            else:
                run(command)
                physical_database.ensure_connection.assert_called_once_with(max_retries=0)
                if connection.vendor == "postgresql":
                    Group.objects.create(name=None)
                    Group.objects.create(name=None)
                    assert Group.objects.filter(name__isnull=True).count() == 2
                # SQLite supplies an ordinary-write reference, not nullable DDL.
                Group.objects.create(name="ordinary-unique")
                with pytest.raises(IntegrityError), transaction.atomic():
                    Group.objects.create(name="ordinary-unique")
            assert set(MigrationRecorder(connection).applied_migrations()) == history
        finally:
            transaction.set_rollback(True)
    assert not Group.objects.exists()
    assert set(MigrationRecorder(connection).applied_migrations()) == history
