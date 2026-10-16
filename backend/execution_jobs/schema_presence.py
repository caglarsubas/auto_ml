"""Read-only presence checks for the sealed private PostgreSQL profile.

Migration records alone do not establish that required physical relations still
exist. This is deliberately not a complete schema/constraint or restore proof.
"""

from django.apps import apps
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


class SchemaMismatch(Exception):
    pass


def required_schema():
    models = [m for m in apps.get_models(include_auto_created=True) if m._meta.managed and not m._meta.proxy]
    models.append(MigrationRecorder.Migration)
    return {m._meta.db_table: {f.column for f in m._meta.local_concrete_fields} for m in models}


def check_schema():
    required = required_schema()
    with connection.cursor() as cursor:
        # Read catalogs only, without querying substituted views or model rows.
        # Public relations must be visible to the actual connection search path.
        cursor.execute("""
            SELECT c.relname, c.relkind, pg_catalog.pg_table_is_visible(c.oid), a.attname
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_catalog.pg_attribute a
                ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
            WHERE n.nspname = 'public' AND c.relname = ANY(%s::text[])
        """, [list(required)])
        present = {}
        for table, kind, visible, column in cursor.fetchall():
            if kind != "r" or visible is not True:
                raise SchemaMismatch
            present.setdefault(table, set()).add(column)
    if any(not columns <= present.get(table, set()) for table, columns in required.items()):
        raise SchemaMismatch
