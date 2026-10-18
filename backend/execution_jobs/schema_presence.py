"""Read-only presence and storage-type checks for sealed private PostgreSQL.

Migration records alone do not establish that required physical relations still
exist with their declared base storage types. Type modifiers, constraints and
complete schema/restore equivalence remain outside this check.
"""

import json

from django.apps import apps
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder


class SchemaMismatch(Exception):
    pass


STORAGE_TYPES = {
    "AutoField": "int4", "IntegerField": "int4", "PositiveIntegerField": "int4",
    "BigAutoField": "int8", "BigIntegerField": "int8", "PositiveBigIntegerField": "int8",
    "SmallAutoField": "int2", "SmallIntegerField": "int2", "PositiveSmallIntegerField": "int2",
    "BooleanField": "bool", "CharField": "varchar", "FileField": "varchar",
    "TextField": "text", "DateTimeField": "timestamptz", "UUIDField": "uuid", "JSONField": "jsonb",
}


def required_storage_types():
    # Use the sealed migration graph's final storage declarations. Runtime
    # auto-created auth through-model IDs can differ from their historical DDL.
    # Loading the graph with no connection executes no migrations or data reads.
    loader = MigrationLoader(None)
    if loader.replacements:
        raise SchemaMismatch
    models = [m for m in loader.project_state().apps.get_models(include_auto_created=True)
              if m._meta.managed and not m._meta.proxy]
    models.append(MigrationRecorder.Migration)
    expected = {}
    for model in models:
        expected[model._meta.db_table] = {}
        for field in model._meta.local_concrete_fields:
            target = field.target_field if field.is_relation else field
            try:
                expected[model._meta.db_table][field.column] = STORAGE_TYPES[target.get_internal_type()]
            except KeyError:
                raise SchemaMismatch from None
    required = required_schema()
    if any(not columns <= expected.get(table, {}).keys() for table, columns in required.items()):
        raise SchemaMismatch
    return {table: {column: expected[table][column] for column in columns} for table, columns in required.items()}


def required_schema():
    models = [m for m in apps.get_models(include_auto_created=True) if m._meta.managed and not m._meta.proxy]
    models.append(MigrationRecorder.Migration)
    return {m._meta.db_table: {f.column for f in m._meta.local_concrete_fields} for m in models}


def check_schema():
    required = required_schema()
    with connection.cursor() as cursor:
        # Catalog-only evidence: visible ordinary public relations and exact
        # pg_catalog storage OIDs. A same-named domain or array is not the sealed
        # plain type. Extra columns retain the existing permissive policy.
        # Bind every catalog/operator/type so namespaces cannot forge evidence.
        cursor.execute("""
            WITH required_relations AS (
                SELECT c.relname,c.relkind,c.oid
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid OPERATOR(pg_catalog.=) c.relnamespace
                WHERE n.nspname OPERATOR(pg_catalog.=) 'public'::pg_catalog.name
                    AND c.relname OPERATOR(pg_catalog.=) ANY(%s::pg_catalog.name[])
            ), profile AS (SELECT %s::pg_catalog.jsonb AS types)
            SELECT c.relname, c.relkind,
                pg_catalog.pg_table_is_visible(c.oid)
                    AND (wanted.name IS NULL OR a.atttypid OPERATOR(pg_catalog.=) t.oid), a.attname
            FROM required_relations c CROSS JOIN profile p
            LEFT JOIN pg_catalog.pg_attribute a
                ON a.attrelid OPERATOR(pg_catalog.=) c.oid
                AND a.attnum OPERATOR(pg_catalog.>) 0 AND NOT a.attisdropped
            LEFT JOIN LATERAL (
                SELECT ((p.types OPERATOR(pg_catalog.->) c.relname::pg_catalog.text)
                    OPERATOR(pg_catalog.->>) a.attname::pg_catalog.text)::pg_catalog.name AS name
            ) wanted ON true
            LEFT JOIN pg_catalog.pg_type t
                ON t.typnamespace OPERATOR(pg_catalog.=) 'pg_catalog'::pg_catalog.regnamespace::pg_catalog.oid
                    AND t.typname OPERATOR(pg_catalog.=) wanted.name
        """, [list(required), json.dumps(required_storage_types())])
        present = {}
        for table, kind, compatible, column in cursor.fetchall():
            if kind != "r" or compatible is not True:
                raise SchemaMismatch
            present.setdefault(table, set()).add(column)
    if any(not columns <= present.get(table, set()) for table, columns in required.items()):
        raise SchemaMismatch
