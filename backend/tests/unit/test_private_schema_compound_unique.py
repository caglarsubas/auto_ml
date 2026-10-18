"""Sealed compound declarations require genuine immediate local uniqueness."""

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from access_control.models import Project, ProjectMembership
from execution_jobs import preflight, schema_presence
from tests.unit.test_private_schema_presence import physical_database  # noqa: F401
from tests.unit.test_private_schema_unique_fields import reference_denial

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]
TABLE = "access_control_projectmembership"
COLUMNS = ("project_id", "actor_id")
GROUPS = [
    ("access_control_mcpdatasetgrant", ("actor_id", "dataset_id")), (TABLE, COLUMNS),
    ("auth_permission", ("content_type_id", "codename")),
    ("auth_group_permissions", ("group_id", "permission_id")),
    ("auth_user_groups", ("user_id", "group_id")),
    ("auth_user_user_permissions", ("user_id", "permission_id")),
    ("django_content_type", ("app_label", "model")),
    ("declaration_datadictionary", ("data_file_id", "column_name")),
    ("deployment_packagereview", ("dataset_id", "bundle_id")),
    ("deployment_packagereviewevent", ("review_id", "revision")),
    ("execution_jobs_jobevent", ("job_id", "revision")),
]
SUBSTITUTES = ["wrong_member", "larger_group", "smaller_group", "index_only", "partial", "expression",
               "deferred", "initially_deferred", "catalog_shadow", "operator_forgery", "function_forgery"]


def run(command):
    return call_command("check_job_runtime") if command else preflight.check_runtime()


def seed():
    actor = User.objects.create(username="compound-user", password="retained-password")
    project = Project.objects.create(name="compound-project")
    row = ProjectMembership.objects.create(project=project, actor=actor, role="developer", active=True)
    return actor, project, row, set(MigrationRecorder(connection).applied_migrations())


def preserved(actor, project, row, history):
    assert User.objects.get(pk=actor.pk).password == "retained-password"
    found = ProjectMembership.objects.get(project=project, actor=actor)
    assert found.pk == row.pk and found.role == "developer" and found.active is True
    assert set(MigrationRecorder(connection).applied_migrations()) == history


def key(cursor, table=TABLE, columns=COLUMNS):
    cursor.execute("SELECT a.attname,a.attnum FROM pg_catalog.pg_attribute a WHERE a.attrelid OPERATOR(pg_catalog.=) %s::pg_catalog.regclass AND a.attname OPERATOR(pg_catalog.=) ANY(%s::pg_catalog.name[])", ["public." + table, list(columns)])
    attrs = dict(cursor.fetchall())
    assert len(attrs) == len(columns)
    cursor.execute("SELECT k.conname FROM pg_catalog.pg_constraint k WHERE k.conrelid OPERATOR(pg_catalog.=) %s::pg_catalog.regclass AND k.contype OPERATOR(pg_catalog.=) 'u'::pg_catalog.\"char\" AND ARRAY(SELECT x FROM pg_catalog.unnest(k.conkey) x ORDER BY x USING OPERATOR(pg_catalog.<)) OPERATOR(pg_catalog.=) %s::pg_catalog.int2[]", ["public." + table, sorted(attrs.values())])
    names = cursor.fetchall()
    assert len(names) == 1
    return names[0][0]


def drop(cursor, table=TABLE, columns=COLUMNS):
    name = key(cursor, table, columns)
    q = connection.ops.quote_name
    cursor.execute(f"ALTER TABLE public.{q(table)} DROP CONSTRAINT {q(name)}")
    return name


def denied(broker, command):
    expected = CommandError if command else preflight.RuntimeUnavailable
    with pytest.raises(expected, match="^job_schema_invalid$"):
        run(command)
    broker.ensure_connection.assert_not_called()


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("table,columns", GROUPS)
def test_each_declared_compound_group_is_required(physical_database, monkeypatch, command, table, columns):
    actor, project, row, history = seed()
    if connection.vendor == "sqlite":
        # Explicit denial reference; no emulation of native catalog semantics.
        reference_denial(monkeypatch, table, columns[0])
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                drop(cursor, table, columns)
        try:
            denied(physical_database, command)
            assert set(MigrationRecorder(connection).applied_migrations()) == history
        finally:
            transaction.set_rollback(True)
    preserved(actor, project, row, history)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("case", SUBSTITUTES)
def test_compound_substitutes_cannot_satisfy_declaration(physical_database, monkeypatch, command, case):
    actor, project, row, history = seed()
    if connection.vendor == "sqlite":
        reference_denial(monkeypatch, TABLE, COLUMNS[0])
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                if case == "catalog_shadow":
                    for catalog in ["pg_constraint", "pg_index", "pg_attribute"]:
                        fields = "attrelid,attname,attnum,atttypid,atttypmod,attnotnull,attgenerated,attidentity,attisdropped" if catalog == "pg_attribute" else "*"
                        cursor.execute(f"CREATE TEMP TABLE {catalog} AS SELECT {fields} FROM pg_catalog.{catalog}")
                drop(cursor)
                if case in {"wrong_member", "operator_forgery"}:
                    cursor.execute(f"ALTER TABLE public.{TABLE} ADD UNIQUE (project_id,revision)")
                elif case == "larger_group":
                    cursor.execute(f"ALTER TABLE public.{TABLE} ADD UNIQUE (project_id,actor_id,id)")
                elif case == "smaller_group":
                    cursor.execute(f"ALTER TABLE public.{TABLE} ADD UNIQUE (project_id)")
                elif case == "index_only":
                    cursor.execute(f"CREATE UNIQUE INDEX compound_fixture_index ON public.{TABLE} (project_id,actor_id)")
                elif case == "partial":
                    cursor.execute(f"CREATE UNIQUE INDEX compound_fixture_partial ON public.{TABLE} (project_id,actor_id) WHERE active")
                elif case == "expression":
                    cursor.execute(f"CREATE UNIQUE INDEX compound_fixture_expression ON public.{TABLE} (project_id,(actor_id + 0))")
                elif case in {"deferred", "initially_deferred"}:
                    mode = "DEFERRED" if case == "initially_deferred" else "IMMEDIATE"
                    cursor.execute(f"ALTER TABLE public.{TABLE} ADD UNIQUE (project_id,actor_id) DEFERRABLE INITIALLY {mode}")
                if case == "catalog_shadow":
                    cursor.execute("SET LOCAL search_path=pg_temp,public,pg_catalog")
                elif case == "operator_forgery":
                    cursor.execute("CREATE FUNCTION public.compound_fixture_any_key(pg_catalog.int2[],pg_catalog.int2[]) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true'")
                    cursor.execute("CREATE OPERATOR public.= (LEFTARG=pg_catalog.int2[], RIGHTARG=pg_catalog.int2[], FUNCTION=public.compound_fixture_any_key)")
                    cursor.execute("SET LOCAL search_path=public,pg_catalog")
                elif case == "function_forgery":
                    cursor.execute("CREATE FUNCTION public.jsonb_array_elements(pg_catalog.jsonb) RETURNS SETOF pg_catalog.jsonb LANGUAGE sql IMMUTABLE AS 'SELECT NULL::pg_catalog.jsonb WHERE false'")
                    cursor.execute("SET LOCAL search_path=public,pg_catalog")
        try:
            denied(physical_database, command)
            assert set(MigrationRecorder(connection).applied_migrations()) == history
        finally:
            transaction.set_rollback(True)
    preserved(actor, project, row, history)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("variant", ["genuine", "renamed", "reordered", "included", "nonnull_not_distinct", "extra_unique"])
def test_equivalent_compound_constraints_preserve_ordinary_writes(physical_database, command, variant):
    actor, project, row, history = seed()
    with transaction.atomic():
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                if variant == "renamed":
                    cursor.execute(f"ALTER TABLE public.{TABLE} RENAME CONSTRAINT {connection.ops.quote_name(key(cursor))} TO compound_fixture_renamed")
                elif variant in {"reordered", "included", "nonnull_not_distinct"}:
                    drop(cursor)
                    if variant == "reordered":
                        cursor.execute(f"ALTER TABLE public.{TABLE} ADD UNIQUE (actor_id,project_id)")
                    elif variant == "included":
                        cursor.execute(f"CREATE UNIQUE INDEX compound_fixture_covering ON public.{TABLE} (actor_id,project_id) INCLUDE (role)")
                        cursor.execute(f"ALTER TABLE public.{TABLE} ADD CONSTRAINT compound_fixture_custom UNIQUE USING INDEX compound_fixture_covering")
                    else:
                        cursor.execute(f"ALTER TABLE public.{TABLE} ADD UNIQUE NULLS NOT DISTINCT (project_id,actor_id)")
                elif variant == "extra_unique":
                    cursor.execute(f"ALTER TABLE public.{TABLE} ADD COLUMN compound_fixture_extra int UNIQUE")
                cursor.execute("SELECT i.indnkeyatts,i.indnatts FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_index i ON i.indexrelid OPERATOR(pg_catalog.=) k.conindid WHERE k.conrelid OPERATOR(pg_catalog.=) %s::pg_catalog.regclass AND k.conname OPERATOR(pg_catalog.=) %s::pg_catalog.name", ["public." + TABLE, key(cursor)])
                assert cursor.fetchone() == (2, 3 if variant == "included" else 2)
            elif variant == "extra_unique":
                cursor.execute(f"ALTER TABLE {TABLE} ADD COLUMN compound_fixture_extra int")
        run(command)
        physical_database.ensure_connection.assert_called_once_with(max_retries=0)
        other_actor = User.objects.create(username="compound-other", password="ordinary")
        other_project = Project.objects.create(name="compound-other")
        ProjectMembership.objects.create(project=project, actor=other_actor, role="developer")
        ProjectMembership.objects.create(project=other_project, actor=actor, role="developer")
        assert ProjectMembership.objects.filter(project=project).count() == 2
        assert ProjectMembership.objects.filter(actor=actor).count() == 2
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectMembership.objects.create(project=project, actor=actor, role="reviewer")
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create(username=actor.username)
        transaction.set_rollback(True)
    preserved(actor, project, row, history)
    assert not User.objects.filter(username="compound-other").exists()


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("not_distinct", [False, True])
def test_nullable_compound_declaration_preserves_default_null_semantics(physical_database, monkeypatch, command, not_distinct):
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
    if connection.vendor == "sqlite" and not_distinct:
        reference_denial(monkeypatch, TABLE, COLUMNS[0])
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(f"ALTER TABLE public.{TABLE} ALTER COLUMN actor_id DROP NOT NULL")
                if not_distinct:
                    drop(cursor)
                    cursor.execute(f"ALTER TABLE public.{TABLE} ADD UNIQUE NULLS NOT DISTINCT (project_id,actor_id)")
        try:
            if not_distinct:
                denied(physical_database, command)
            else:
                run(command)
                physical_database.ensure_connection.assert_called_once_with(max_retries=0)
                if connection.vendor == "postgresql":
                    ProjectMembership.objects.create(project=project, actor=None, role="developer")
                    ProjectMembership.objects.create(project=project, actor=None, role="developer")
                    assert ProjectMembership.objects.filter(project=project, actor__isnull=True).count() == 2
                with pytest.raises(IntegrityError), transaction.atomic():
                    ProjectMembership.objects.create(project=project, actor=actor, role="reviewer")
        finally:
            transaction.set_rollback(True)
    preserved(actor, project, row, history)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("form", ["condition", "expression", "deferred", "include", "opclasses", "nulls_distinct", "missing_member", "duplicate_member"])
def test_unqualified_sealed_declaration_forms_fail_closed(physical_database, monkeypatch, command, form):
    actor, project, row, history = seed()

    def changed_state(database):
        assert database is None
        loader = MigrationLoader(None)
        state = loader.project_state()
        options = state.models[("access_control", "projectmembership")].options
        if form in {"missing_member", "duplicate_member"}:
            options["unique_together"] = {("project", "missing" if form == "missing_member" else "project")}
        else:
            parameters = {"name": "compound_fixture_declaration"}
            if form == "expression":
                constraint = models.UniqueConstraint(models.F("project"), models.F("actor"), **parameters)
            else:
                parameters["fields"] = ["project", "actor"]
                parameters.update({
                    "condition": {"condition": models.Q(active=True)},
                    "deferred": {"deferrable": models.Deferrable.IMMEDIATE},
                    "include": {"include": ["role"]},
                    "opclasses": {"opclasses": ["uuid_ops", "int4_ops"]},
                    "nulls_distinct": {"nulls_distinct": False},
                }[form])
                constraint = models.UniqueConstraint(**parameters)
            options["constraints"] = [constraint]
        loader.project_state = lambda: state
        return loader

    monkeypatch.setattr(schema_presence, "MigrationLoader", changed_state)
    denied(physical_database, command)
    preserved(actor, project, row, history)
