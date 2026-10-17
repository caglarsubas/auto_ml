"""The initial private metadata profile requires unfiltered managed tables."""

from django.db import connection
from execution_jobs.schema_presence import required_schema


class SchemaRowSecurityMismatch(Exception):
    pass


def check_schema_row_security():
    required = set(required_schema())
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid OPERATOR(pg_catalog.=) c.relnamespace
            WHERE n.nspname OPERATOR(pg_catalog.=) 'public'::pg_catalog.name
                AND c.relname OPERATOR(pg_catalog.=) ANY(%s::pg_catalog.name[])
        """, [sorted(required)])
        present = set()
        for table, enabled, forced in cursor.fetchall():
            if enabled is not False or forced is not False:
                raise SchemaRowSecurityMismatch
            present.add(table)
    if present != required:
        raise SchemaRowSecurityMismatch
