"""Schema-state evidence must come from trusted catalogs, operators and aggregates."""

from unittest.mock import MagicMock

import pytest
from django.apps import apps
from django.contrib.auth.models import Group
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder

from tests.unit.test_private_schema_namespace_prefix import schema_state  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


def shadow_class(cursor, hidden):
    from psycopg import sql

    cursor.execute(sql.SQL("CREATE TEMP VIEW pg_class AS SELECT * FROM pg_catalog.pg_class WHERE relname OPERATOR(pg_catalog.<>) {}::pg_catalog.name").format(sql.Literal(hidden)))
    # Keep the substitute's dependency class IDs coherent with its regclass
    # identity. The genuine catalog remains unchanged and independently visible.
    cursor.execute("""CREATE TEMP VIEW pg_depend AS SELECT
        CASE WHEN classid OPERATOR(pg_catalog.=) 'pg_catalog.pg_class'::pg_catalog.regclass::pg_catalog.oid
        THEN 'pg_temp.pg_class'::pg_catalog.regclass::pg_catalog.oid ELSE classid END AS classid,
        objid,objsubid,refclassid,refobjid,refobjsubid,deptype FROM pg_catalog.pg_depend""")


def substitute(cursor, case):
    if case == "table":
        cursor.execute("CREATE TABLE public.foreign_retained (value text)")
        cursor.execute("INSERT INTO public.foreign_retained VALUES ('owned-row')")
        shadow_class(cursor, "foreign_retained")
    elif case in {"sequence", "dependency"}:
        cursor.execute("CREATE SEQUENCE public.unapproved_state_seq")
        if case == "sequence":
            shadow_class(cursor, "unapproved_state_seq")
        else:
            cursor.execute("""CREATE TEMP VIEW pg_depend AS SELECT * FROM pg_catalog.pg_depend UNION ALL SELECT
                'pg_catalog.pg_class'::pg_catalog.regclass::pg_catalog.oid,
                'public.unapproved_state_seq'::pg_catalog.regclass::pg_catalog.oid,0,
                'pg_catalog.pg_class'::pg_catalog.regclass::pg_catalog.oid,
                'public.auth_group'::pg_catalog.regclass::pg_catalog.oid,0,'a'::pg_catalog."char"
                """)
        cursor.execute("""SELECT pg_catalog.count(*) FROM pg_catalog.pg_depend
            WHERE classid OPERATOR(pg_catalog.=) 'pg_catalog.pg_class'::pg_catalog.regclass::pg_catalog.oid
            AND objid OPERATOR(pg_catalog.=) 'public.unapproved_state_seq'::pg_catalog.regclass::pg_catalog.oid
            AND deptype OPERATOR(pg_catalog.=) ANY(ARRAY['a','i']::pg_catalog."char"[])""")
        assert cursor.fetchone() == (0,), "Owned sequence must actually lack a table ownership dependency"
    elif case == "extension_reference":
        cursor.execute("CREATE TEMP VIEW pg_extension AS SELECT 'not_installed'::pg_catalog.name AS extname")
    elif case == "event_reference":
        cursor.execute("CREATE TEMP VIEW pg_event_trigger AS SELECT 'not_installed'::pg_catalog.name AS evtname")
    elif case == "function":
        cursor.execute("CREATE FUNCTION public.unapproved_state_function() RETURNS integer LANGUAGE sql AS $$ SELECT 12 $$")
        cursor.execute("CREATE TEMP VIEW pg_proc AS SELECT * FROM pg_catalog.pg_proc WHERE proname OPERATOR(pg_catalog.<>) 'unapproved_state_function'::pg_catalog.name")
    elif case == "aggregate":
        cursor.execute("CREATE FUNCTION public.state_count_step(bigint) RETURNS bigint LANGUAGE sql AS $$ SELECT 0::bigint $$")
        cursor.execute("CREATE AGGREGATE public.count(*) (SFUNC=public.state_count_step,STYPE=bigint,INITCOND='0')")
        cursor.execute("SET LOCAL search_path=public,pg_catalog")
    elif case == "join_operator":
        cursor.execute("""CREATE FUNCTION public.state_oid_equal(oid,oid) RETURNS boolean LANGUAGE sql AS $$
            SELECT CASE WHEN pg_catalog.strpos(pg_catalog.current_query(),'pg_proc') > 0 THEN false
            ELSE $1 OPERATOR(pg_catalog.=) $2 END $$""")
        cursor.execute("CREATE OPERATOR public.= (PROCEDURE=public.state_oid_equal,LEFTARG=pg_catalog.oid,RIGHTARG=pg_catalog.oid)")
        cursor.execute("SET LOCAL search_path=public,pg_catalog")
    else:
        cursor.execute("CREATE TEMP TABLE healthy_state_fixture (value text)")


@pytest.mark.parametrize("case", ["table", "sequence", "dependency", "function", "aggregate", "join_operator", "extension_reference", "event_reference", "healthy"])
def test_state_catalog_substitutions_cannot_hide_unsupported_objects(schema_state, case):
    seed = Group.objects.create(name="owned-state-catalog-fixture")
    history = set(MigrationRecorder(connection).applied_migrations())
    positive = case in {"extension_reference", "event_reference", "healthy"}
    expected = "current" if positive else ("partial_or_foreign" if case == "table" else "foreign")
    if connection.vendor != "postgresql":
        # Explicit genuine-state response references only; no PostgreSQL catalog
        # or substitution semantics are emulated on SQLite.
        database = MagicMock()
        cursor = database.cursor.return_value.__enter__.return_value
        if case in {"function", "aggregate", "join_operator"}:
            cursor.fetchall.side_effect = [[], []]
            cursor.fetchone.return_value = (1,)
        else:
            wanted = {"django_migrations"} | {m._meta.db_table for m in apps.get_models(include_auto_created=True)
                                             if m._meta.managed and not m._meta.proxy}
            relations = [("public", name, "r", "fixture") for name in wanted]
            if not positive:
                relations.append(("public", "extra", "r" if case == "table" else "S", "fixture"))
            cursor.fetchall.side_effect = [[], [], relations, [] if positive or case == "table" else [("extra", None)]]
            cursor.fetchone.return_value = (0,)
        assert schema_state(database, "fixture") == expected
    else:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                user = cursor.fetchone()[0]
                substitute(cursor, case)
            assert schema_state(connection, user) == expected
            assert set(MigrationRecorder(connection).applied_migrations()) == history
            if case == "table":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT value FROM public.foreign_retained")
                    assert cursor.fetchall() == [("owned-row",)]
            transaction.set_rollback(True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.to_regclass('public.foreign_retained'),pg_catalog.to_regclass('public.unapproved_state_seq')")
            assert cursor.fetchone() == (None, None)
    assert set(MigrationRecorder(connection).applied_migrations()) == history
    assert Group.objects.get(pk=seed.pk).name == "owned-state-catalog-fixture"
