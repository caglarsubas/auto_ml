"""Required effective table permissions for the current private owner profile."""

from django.db import connection
from execution_jobs.schema_presence import required_schema


class SchemaPrivilegesMismatch(Exception):
    pass


def check_schema_privileges():
    required = set(required_schema())
    with connection.cursor() as cursor:
        # Separate predicates require every operation, rather than any one of a
        # comma-separated privilege list. No grants or model-row reads occur.
        cursor.execute("""
            SELECT c.relname,
                pg_catalog.has_table_privilege(c.oid, 'SELECT'),
                pg_catalog.has_table_privilege(c.oid, 'INSERT'),
                pg_catalog.has_table_privilege(c.oid, 'UPDATE'),
                pg_catalog.has_table_privilege(c.oid, 'DELETE')
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s::text[])
        """, [sorted(required)])
        present = set()
        for table, *rights in cursor.fetchall():
            if len(rights) != 4 or any(right is not True for right in rights):
                raise SchemaPrivilegesMismatch
            present.add(table)
    if present != required:
        raise SchemaPrivilegesMismatch
