"""Bounded private job startup checks; never log a connection or secret."""

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class RuntimeUnavailable(Exception):
    pass


def check_application_role():
    """Initial installation profile excludes elevated application DB authority."""
    if connection.vendor != "postgresql":
        raise RuntimeUnavailable("job_private_postgresql_required")
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls,
                    EXISTS (
                        SELECT 1 FROM pg_roles privileged
                        WHERE (privileged.rolsuper OR privileged.rolcreatedb
                            OR privileged.rolcreaterole OR privileged.rolreplication
                            OR privileged.rolbypassrls OR privileged.rolname IN (
                            'pg_read_server_files', 'pg_write_server_files',
                            'pg_execute_server_program', 'pg_signal_backend',
                            'pg_read_all_data', 'pg_write_all_data'
                        )) AND pg_has_role(current_user, privileged.oid, 'MEMBER')
                    )
                FROM pg_roles WHERE rolname = current_user
            """)
            row = cursor.fetchone()
        if not row or len(row) != 6 or any(item is not False for item in row):
            raise RuntimeUnavailable("job_application_role_elevated")
    except RuntimeUnavailable:
        raise
    except Exception:
        raise RuntimeUnavailable("job_application_role_unavailable") from None


def check_runtime():
    if settings.DECLARAI_RUNTIME_PROFILE != "private" or not settings.DECLARAI_JOBS_ENABLED:
        raise RuntimeUnavailable("job_private_configuration_required")
    if connection.vendor != "postgresql":
        raise RuntimeUnavailable("job_private_postgresql_required")
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
            row = cursor.fetchone()
        if not row or row[0] is not True:
            raise RuntimeUnavailable("job_metadata_tls_required")
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise RuntimeUnavailable("job_migrations_required")
    except RuntimeUnavailable:
        raise
    except Exception:
        raise RuntimeUnavailable("job_storage_unavailable") from None
    try:
        from backend.celery import app

        # Force an actual authenticated TLS connection, without publishing a task
        # or trusting configuration/system checks as proof of connectivity.
        with app.connection_for_write() as broker:
            broker.ensure_connection(max_retries=0)
    except Exception:
        raise RuntimeUnavailable("job_broker_unavailable") from None
    return {"private_metadata_tls": "verified", "broker_connection": "verified", "migrations": "current"}
