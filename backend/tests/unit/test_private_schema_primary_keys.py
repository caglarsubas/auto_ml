"""Declared metadata keys require an immediate, valid primary-key constraint."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight, schema_presence
from execution_jobs.models import QueueLock
from tests.unit.test_private_schema_presence import physical_database  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]

MISSING = {
    "manual": "execution_jobs_queuelock",
    "auth": "auth_user",
    "through": "auth_user_groups",
    "history": "django_migrations",
    "bigint": "access_control_projectmembership",
    "uuid": "execution_jobs_nativejob",
    "text": "django_session",
    "relation": "access_control_projectdataset",
}
CASES = list(MISSING) + ["unique_only", "wrong_column", "compound", "deferred", "initially_deferred",
                        "catalog_shadow", "operator_forgery"]


def run(command):
    return call_command("check_job_runtime") if command else preflight.check_runtime()


def drop_key(cursor, table):
    cursor.execute("SELECT c.conname FROM pg_catalog.pg_constraint c WHERE c.conrelid OPERATOR(pg_catalog.=) %s::pg_catalog.regclass AND c.contype OPERATOR(pg_catalog.=) 'p'::pg_catalog.\"char\"", ["public." + table])
    keys = cursor.fetchall()
    assert len(keys) == 1
    q = connection.ops.quote_name
    # Any dependent foreign keys are fixture DDL and return on rollback. This
    # packet checks primary keys, without claiming foreign-key validation.
    cursor.execute(f'ALTER TABLE public.{q(table)} DROP CONSTRAINT {q(keys[0][0])} CASCADE')


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("case", CASES)
def test_primary_key_mismatch_blocks_before_broker(physical_database, monkeypatch, command, case):
    seed = User.objects.create(username="u", password="retained-password", is_superuser=False)
    history = set(MigrationRecorder(connection).applied_migrations())
    table = MISSING.get(case, "execution_jobs_queuelock")
    if connection.vendor == "sqlite":
        # Explicit denial references only, without native constraint, index,
        # catalog namespace or operator emulation.
        @contextmanager
        def catalog():
            rows = [(t, "r", t != table, c)
                    for t, columns in schema_presence.required_schema().items() for c in columns]
            yield SimpleNamespace(execute=lambda *args: None, fetchall=lambda: rows)

        monkeypatch.setattr(schema_presence, "connection", SimpleNamespace(cursor=catalog))
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                if case == "catalog_shadow":
                    # Preserve genuine pre-DDL catalog rows to forge a lost
                    # constraint and its old index under an unqualified lookup.
                    cursor.execute("CREATE TEMP TABLE pg_constraint AS SELECT * FROM pg_catalog.pg_constraint")
                    cursor.execute("CREATE TEMP TABLE pg_index AS SELECT * FROM pg_catalog.pg_index")
                drop_key(cursor, table)
                if case == "unique_only":
                    cursor.execute("ALTER TABLE public.execution_jobs_queuelock ADD UNIQUE (id)")
                elif case in {"wrong_column", "compound", "operator_forgery"}:
                    cursor.execute("ALTER TABLE public.execution_jobs_queuelock ADD COLUMN primary_fixture_alt int2 NOT NULL DEFAULT 1")
                    keys = "id,primary_fixture_alt" if case == "compound" else "primary_fixture_alt"
                    cursor.execute(f"ALTER TABLE public.execution_jobs_queuelock ADD PRIMARY KEY ({keys})")
                elif case in {"deferred", "initially_deferred"}:
                    mode = "DEFERRED" if case == "initially_deferred" else "IMMEDIATE"
                    cursor.execute(f"ALTER TABLE public.execution_jobs_queuelock ADD PRIMARY KEY (id) DEFERRABLE INITIALLY {mode}")
                if case == "catalog_shadow":
                    cursor.execute("SET LOCAL search_path=pg_temp,public,pg_catalog")
                elif case == "operator_forgery":
                    cursor.execute("CREATE FUNCTION public.primary_fixture_any_key(pg_catalog.int2[],pg_catalog.int2[]) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true'")
                    cursor.execute("CREATE OPERATOR public.= (LEFTARG=pg_catalog.int2[], RIGHTARG=pg_catalog.int2[], FUNCTION=public.primary_fixture_any_key)")
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
    restored = User.objects.get(pk=seed.pk)
    assert restored.username == "u" and restored.password == "retained-password" and restored.is_superuser is False
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
def test_unsupported_sealed_composite_key_blocks_before_broker(physical_database, monkeypatch, command):
    history = set(MigrationRecorder(connection).applied_migrations())

    def composite_state(database):
        assert database is None
        loader = MigrationLoader(None)
        state = loader.project_state()
        fields = state.models[("execution_jobs", "queuelock")].fields
        fields["id"] = models.PositiveSmallIntegerField(default=1)
        fields["primary_fixture_alt"] = models.PositiveSmallIntegerField(default=1)
        fields["pk"] = models.CompositePrimaryKey("id", "primary_fixture_alt")
        loader.project_state = lambda: state
        return loader

    monkeypatch.setattr(schema_presence, "MigrationLoader", composite_state)
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_schema_invalid$"):
        run(command)
    physical_database.ensure_connection.assert_not_called()
    assert set(MigrationRecorder(connection).applied_migrations()) == history


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("variant", ["genuine", "renamed", "included"])
def test_genuine_primary_keys_and_writes_remain_supported(physical_database, command, variant):
    seed = User.objects.create(username="u", password="retained-password", is_superuser=False)
    history = set(MigrationRecorder(connection).applied_migrations())
    with transaction.atomic():
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                if variant == "renamed":
                    cursor.execute("ALTER TABLE public.execution_jobs_queuelock RENAME CONSTRAINT execution_jobs_queuelock_pkey TO primary_fixture_renamed")
                elif variant == "included":
                    cursor.execute("ALTER TABLE public.execution_jobs_queuelock ADD COLUMN primary_fixture_extra int2 NOT NULL DEFAULT 1")
                    drop_key(cursor, "execution_jobs_queuelock")
                    cursor.execute("CREATE UNIQUE INDEX primary_fixture_covering ON public.execution_jobs_queuelock (id) INCLUDE (primary_fixture_extra)")
                    cursor.execute("ALTER TABLE public.execution_jobs_queuelock ADD CONSTRAINT primary_fixture_custom PRIMARY KEY USING INDEX primary_fixture_covering")
                cursor.execute("SELECT i.indnkeyatts,i.indnatts FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_index i ON i.indexrelid OPERATOR(pg_catalog.=) c.conindid WHERE c.conrelid OPERATOR(pg_catalog.=) 'public.execution_jobs_queuelock'::pg_catalog.regclass AND c.contype OPERATOR(pg_catalog.=) 'p'::pg_catalog.\"char\"")
                assert cursor.fetchone() == (1, 2 if variant == "included" else 1)
            elif variant == "included":
                cursor.execute("ALTER TABLE execution_jobs_queuelock ADD COLUMN primary_fixture_extra int NOT NULL DEFAULT 1")
        result = run(command)
        if not command:
            assert result["migrations"] == "current"
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        created = User.objects.create(username="primary-control", password="supported")
        assert created.pk is not None
        group = Group.objects.create(name="primary-control")
        seed.groups.add(group)
        assert seed.groups.filter(pk=group.pk).exists()
        QueueLock.objects.create(id=30001)
        assert QueueLock.objects.get(pk=30001).id == 30001
        with pytest.raises(IntegrityError), transaction.atomic():
            QueueLock.objects.create(id=30001)
        transaction.set_rollback(True)
    assert User.objects.get(pk=seed.pk).password == "retained-password"
    assert not User.objects.filter(username="primary-control").exists()
    assert not Group.objects.filter(name="primary-control").exists()
    assert not QueueLock.objects.filter(pk=30001).exists()
    assert set(MigrationRecorder(connection).applied_migrations()) == history
