"""Sealed PostgreSQL foreign-key metadata must match local and target declarations."""

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from access_control.models import Project, ProjectMembership
from execution_jobs import preflight, schema_presence
from tests.unit.test_private_schema_presence import physical_database  # noqa: F401
from tests.unit.test_private_schema_unique_fields import reference_denial

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]
TABLE = "access_control_projectmembership"
FOREIGN_KEYS = [('access_control_mcpdatasetgrant', 'actor_id'), ('access_control_mcpdatasetgrant', 'dataset_id'), ('access_control_mcpaccessevent', 'actor_id'), ('access_control_mcpaccessevent', 'grant_id'), ('access_control_assistantactionapproval', 'actor_id'), ('access_control_sessionauthority', 'user_id'), ('access_control_authenticationevent', 'actor_id'), ('access_control_projectartifact', 'dataset_id'), ('access_control_projectartifact', 'project_id'), ('access_control_projectauthorityevent', 'actor_id'), ('access_control_projectauthorityevent', 'project_id'), ('access_control_projectdataset', 'dataset_id'), ('access_control_projectdataset', 'project_id'), ('access_control_projectpipeline', 'pipeline_id'), ('access_control_projectpipeline', 'project_id'), ('access_control_projectmembership', 'actor_id'), ('access_control_projectmembership', 'project_id'), ('django_admin_log', 'content_type_id'), ('django_admin_log', 'user_id'), ('auth_permission', 'content_type_id'), ('auth_group_permissions', 'group_id'), ('auth_group_permissions', 'permission_id'), ('auth_user_groups', 'user_id'), ('auth_user_groups', 'group_id'), ('auth_user_user_permissions', 'user_id'), ('auth_user_user_permissions', 'permission_id'), ('declaration_datadictionary', 'data_file_id'), ('deployment_packagereview', 'dataset_id'), ('deployment_packagereview', 'project_id'), ('deployment_packagereviewevent', 'actor_id'), ('deployment_packagereviewevent', 'review_id'), ('deployment_packagereviewevent', 'evidence_job_id'), ('execution_jobs_nativejob', 'actor_id'), ('execution_jobs_nativejob', 'dataset_id'), ('execution_jobs_nativejob', 'project_id'), ('execution_jobs_nativejob', 'source_dataset_id'), ('execution_jobs_jobevent', 'job_id'), ('modeling_holdoutaccess', 'actor_id')]
SUBSTITUTES = ["wrong_local", "wrong_target", "wrong_target_column", "wrong_schema", "compound",
               "not_valid", "not_deferrable", "initially_immediate", "match_full", "delete_cascade",
               "update_cascade", "delete_restrict", "delete_set_null", "delete_set_default",
               "catalog_shadow", "operator_forgery"]


def run(command):
    return call_command("check_job_runtime") if command else preflight.check_runtime()


def seed():
    actor = User.objects.create(username="foreign-user", password="retained-password")
    project = Project.objects.create(name="foreign-project")
    row = ProjectMembership.objects.create(project=project, actor=actor, role="developer", active=True)
    return actor, project, row, set(MigrationRecorder(connection).applied_migrations())


def preserved(actor, project, row, history):
    assert User.objects.get(pk=actor.pk).password == "retained-password"
    found = ProjectMembership.objects.get(project=project, actor=actor)
    assert found.pk == row.pk and found.role == "developer" and found.active is True
    assert set(MigrationRecorder(connection).applied_migrations()) == history


def key(cursor, table=TABLE, column="actor_id"):
    cursor.execute("SELECT k.conname FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_attribute a ON a.attrelid OPERATOR(pg_catalog.=) k.conrelid WHERE k.conrelid OPERATOR(pg_catalog.=) %s::pg_catalog.regclass AND a.attname OPERATOR(pg_catalog.=) %s::pg_catalog.name AND k.contype OPERATOR(pg_catalog.=) 'f'::pg_catalog.\"char\" AND k.conkey OPERATOR(pg_catalog.=) ARRAY[a.attnum]::pg_catalog.int2[]", ["public." + table, column])
    keys = cursor.fetchall()
    assert len(keys) == 1
    return keys[0][0]


def drop(cursor, table=TABLE, column="actor_id"):
    name = key(cursor, table, column)
    q = connection.ops.quote_name
    cursor.execute(f"ALTER TABLE public.{q(table)} DROP CONSTRAINT {q(name)}")
    return name


def denied(broker, command):
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_schema_invalid$"):
        run(command)
    broker.ensure_connection.assert_not_called()


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("table,column", FOREIGN_KEYS)
def test_each_declared_foreign_key_is_required(physical_database, monkeypatch, command, table, column):
    actor, project, row, history = seed()
    if connection.vendor == "sqlite":
        reference_denial(monkeypatch, table, column)
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                drop(cursor, table, column)
        try:
            denied(physical_database, command)
        finally:
            transaction.set_rollback(True)
    preserved(actor, project, row, history)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("case", SUBSTITUTES)
def test_foreign_key_substitutes_do_not_satisfy_declaration(physical_database, monkeypatch, command, case):
    actor, project, row, history = seed()
    Group.objects.create(pk=actor.pk, name="foreign-target")
    if connection.vendor == "sqlite":
        reference_denial(monkeypatch, TABLE, "actor_id")
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                if case == "catalog_shadow":
                    for catalog in ["pg_constraint", "pg_class", "pg_namespace", "pg_attribute"]:
                        fields = "attrelid,attname,attnum,atttypid,atttypmod,attnotnull,attgenerated,attidentity,attisdropped" if catalog == "pg_attribute" else "*"
                        cursor.execute(f"CREATE TEMP TABLE {catalog} AS SELECT {fields} FROM pg_catalog.{catalog}")
                drop(cursor)
                local, target, mode = "actor_id", "public.auth_user(id)", "DEFERRABLE INITIALLY DEFERRED"
                if case in {"wrong_local", "compound"}:
                    cursor.execute("ALTER TABLE public.auth_user ADD COLUMN foreign_fixture_extra int UNIQUE")
                    cursor.execute("UPDATE public.auth_user SET foreign_fixture_extra=%s WHERE id=%s", [row.pk, actor.pk])
                    if case == "wrong_local":
                        local, target = "id", "public.auth_user(foreign_fixture_extra)"
                    else:
                        cursor.execute("ALTER TABLE public.auth_user ADD UNIQUE (id,foreign_fixture_extra)")
                        local, target = "actor_id,id", "public.auth_user(id,foreign_fixture_extra)"
                elif case in {"wrong_target", "operator_forgery"}:
                    target = "public.auth_group(id)"
                elif case == "wrong_target_column":
                    cursor.execute("ALTER TABLE public.auth_user ADD COLUMN foreign_fixture_extra int UNIQUE")
                    cursor.execute("UPDATE public.auth_user SET foreign_fixture_extra=id")
                    target = "public.auth_user(foreign_fixture_extra)"
                elif case == "wrong_schema":
                    cursor.execute("CREATE SCHEMA foreign_fixture_schema")
                    cursor.execute("CREATE TABLE foreign_fixture_schema.auth_user(id int PRIMARY KEY)")
                    cursor.execute("INSERT INTO foreign_fixture_schema.auth_user VALUES (%s)", [actor.pk])
                    target = "foreign_fixture_schema.auth_user(id)"
                elif case == "not_valid":
                    mode += " NOT VALID"
                elif case == "not_deferrable":
                    mode = "NOT DEFERRABLE"
                elif case == "initially_immediate":
                    mode = "DEFERRABLE INITIALLY IMMEDIATE"
                elif case == "match_full":
                    mode = "MATCH FULL " + mode
                elif case.startswith("delete_"):
                    mode = "ON DELETE " + case.removeprefix("delete_").replace("_", " ").upper() + " " + mode
                elif case == "update_cascade":
                    mode = "ON UPDATE CASCADE " + mode
                if case != "catalog_shadow":
                    cursor.execute(f"ALTER TABLE public.{TABLE} ADD CONSTRAINT foreign_fixture_key FOREIGN KEY ({local}) REFERENCES {target} {mode}")
                if case == "catalog_shadow":
                    cursor.execute("SET LOCAL search_path=pg_temp,public,pg_catalog")
                elif case == "operator_forgery":
                    cursor.execute("CREATE FUNCTION public.foreign_fixture_oid(pg_catalog.oid,pg_catalog.oid) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true'")
                    cursor.execute("CREATE OPERATOR public.= (LEFTARG=pg_catalog.oid, RIGHTARG=pg_catalog.oid, FUNCTION=public.foreign_fixture_oid)")
                    cursor.execute("SET LOCAL search_path=public,pg_catalog")
        try:
            denied(physical_database, command)
        finally:
            transaction.set_rollback(True)
    preserved(actor, project, row, history)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("variant", ["genuine", "renamed", "recreated", "extra_fk"])
def test_genuine_foreign_keys_preserve_ordinary_writes(physical_database, command, variant):
    actor, project, row, history = seed()
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                if variant == "renamed":
                    cursor.execute(f"ALTER TABLE public.{TABLE} RENAME CONSTRAINT {connection.ops.quote_name(key(cursor))} TO foreign_fixture_renamed")
                elif variant == "recreated":
                    drop(cursor)
                    cursor.execute(f"ALTER TABLE public.{TABLE} ADD CONSTRAINT foreign_fixture_recreated FOREIGN KEY (actor_id) REFERENCES public.auth_user(id) DEFERRABLE INITIALLY DEFERRED")
                elif variant == "extra_fk":
                    cursor.execute(f"ALTER TABLE public.{TABLE} ADD COLUMN foreign_fixture_extra int REFERENCES public.auth_user(id)")
        run(command)
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        other_actor = User.objects.create(username="foreign-other", password="ordinary")
        other_project = Project.objects.create(name="foreign-other")
        one = ProjectMembership.objects.create(project=project, actor=other_actor, role="reviewer")
        two = ProjectMembership.objects.create(project=other_project, actor=actor, role="developer")
        assert ProjectMembership.objects.get(pk=one.pk).actor.pk == other_actor.pk
        assert ProjectMembership.objects.get(pk=two.pk).actor.pk == actor.pk
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectMembership.objects.create(project=project, actor=actor, role="reviewer")
        transaction.set_rollback(True)
    preserved(actor, project, row, history)


@pytest.mark.parametrize("command", [False, True])
def test_genuine_initially_deferred_fk_rejects_orphan_at_commit(physical_database, command):
    actor, project, row, history = seed()
    run(command)
    physical_database.ensure_connection.assert_called_once_with(max_retries=0)
    missing = 2147483000
    assert not User.objects.filter(pk=missing).exists()
    inserted = False
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            orphan = ProjectMembership.objects.create(project=project, actor_id=missing, role="reviewer")
            inserted = True
            assert ProjectMembership.objects.filter(pk=orphan.pk).exists()
    assert inserted and not ProjectMembership.objects.filter(actor_id=missing).exists()
    preserved(actor, project, row, history)


@pytest.mark.parametrize("command", [False, True])
def test_nullable_fk_keeps_default_null_behavior(physical_database, monkeypatch, command):
    actor, project, row, history = seed()

    def nullable_state(database):
        assert database is None
        loader = MigrationLoader(None)
        state = loader.project_state()
        field = state.models[("access_control", "projectmembership")].fields["actor"].clone()
        field.null = True
        state.models[("access_control", "projectmembership")].fields["actor"] = field
        loader.project_state = lambda: state
        return loader

    monkeypatch.setattr(schema_presence, "MigrationLoader", nullable_state)
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(f"ALTER TABLE public.{TABLE} ALTER COLUMN actor_id DROP NOT NULL")
            run(command)
            ProjectMembership.objects.create(project=project, actor=None, role="reviewer")
            assert ProjectMembership.objects.filter(project=project, actor__isnull=True).count() == 1
        else:
            run(command)  # SQLite is an ordinary-schema reference, not PostgreSQL NULL/DDL emulation.
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        transaction.set_rollback(True)
    preserved(actor, project, row, history)


@pytest.mark.parametrize("command", [False, True])
def test_unqualified_unconstrained_fk_declaration_fails_closed(physical_database, monkeypatch, command):
    actor, project, row, history = seed()

    def changed_state(database):
        assert database is None
        loader = MigrationLoader(None)
        state = loader.project_state()
        field = state.models[("access_control", "projectmembership")].fields["actor"].clone()
        field.db_constraint = False
        state.models[("access_control", "projectmembership")].fields["actor"] = field
        loader.project_state = lambda: state
        return loader

    monkeypatch.setattr(schema_presence, "MigrationLoader", changed_state)
    denied(physical_database, command)
    preserved(actor, project, row, history)
