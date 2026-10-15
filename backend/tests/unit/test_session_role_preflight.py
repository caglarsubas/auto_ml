"""SET ROLE cannot hide elevated session authority from private startup checks."""
import io
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from execution_jobs import preflight
from tests.unit.test_service_role_preflight import launcher  # noqa: F401

pytestmark = pytest.mark.unit


def role_row(monkeypatch, values):
    database = MagicMock(vendor='postgresql')
    database.cursor.return_value.__enter__.return_value.fetchone.return_value = values
    monkeypatch.setattr(preflight, 'connection', database)
    return database


def test_query_checks_active_and_session_membership_and_accepts_ordinary_result(monkeypatch):
    database = role_row(monkeypatch, (False,) * 6)
    assert preflight.check_application_role() is None
    cursor = database.cursor.return_value.__enter__.return_value
    cursor.execute.assert_called_once()
    sql = cursor.execute.call_args.args[0]
    assert "pg_has_role(current_user, privileged.oid, 'MEMBER')" in sql
    assert "pg_has_role(session_user, privileged.oid, 'MEMBER')" in sql


@pytest.mark.parametrize('entrypoint', ['direct', 'management', 'api', 'worker', 'dispatcher', 'preflight'])
@pytest.mark.django_db(transaction=True)
def test_elevated_session_cannot_hide_behind_ordinary_active_role(launcher, monkeypatch, entrypoint):
    from execution_jobs.management.commands import check_job_runtime

    service, executions = launcher
    postgres = connection.vendor == 'postgresql'
    monkeypatch.setattr(check_job_runtime, 'check_runtime', lambda: {'transport_fixture_only':True})
    try:
        if postgres:
            with connection.cursor() as cursor:
                cursor.execute('SET ROLE pg_database_owner')
                cursor.execute('''SELECT current_user<>session_user,
                    (SELECT rolsuper OR rolcreatedb FROM pg_roles WHERE rolname=current_user),
                    (SELECT rolsuper OR rolcreatedb FROM pg_roles WHERE rolname=session_user)''')
                assert cursor.fetchone() == (True, False, True)
        else:
            # SQLite has no PostgreSQL session principals. This is an explicit
            # denial seam; the complete PostgreSQL matrix executes the real query.
            role_row(monkeypatch, (False,) * 5 + (True,))

        def management(args, **kwargs):
            try:
                call_command('check_job_runtime', *args[3:], stdout=io.StringIO())
            except CommandError as error:
                assert str(error) == 'job_application_role_elevated'
                return SimpleNamespace(returncode=1)
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(service.subprocess, 'run', management)
        if entrypoint == 'direct':
            with pytest.raises(preflight.RuntimeUnavailable, match='^job_application_role_elevated$'):
                preflight.check_application_role()
        elif entrypoint == 'management':
            with pytest.raises(CommandError, match='^job_application_role_elevated$'):
                call_command('check_job_runtime', '--require-application-role', stdout=io.StringIO())
        else:
            with pytest.raises(service.ManifestError, match='^private_service_preflight_failed$'):
                service.launch([entrypoint])
        assert not executions
    finally:
        if postgres:
            with connection.cursor() as cursor:
                cursor.execute('RESET ROLE')
                cursor.execute('SELECT current_user=session_user')
                assert cursor.fetchone() == (True,)


@pytest.mark.parametrize('entrypoint', ['direct', 'management'])
@pytest.mark.django_db(transaction=True)
def test_unswitched_elevated_principal_remains_rejected(monkeypatch, entrypoint):
    from execution_jobs.management.commands import check_job_runtime

    monkeypatch.setattr(check_job_runtime, 'check_runtime', lambda: {})
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_user=session_user,(SELECT rolsuper OR rolcreatedb FROM pg_roles WHERE rolname=current_user)')
            assert cursor.fetchone() == (True, True)
    else:
        role_row(monkeypatch, (True,) + (False,) * 5)
    if entrypoint == 'direct':
        with pytest.raises(preflight.RuntimeUnavailable, match='^job_application_role_elevated$'):
            preflight.check_application_role()
    else:
        with pytest.raises(CommandError, match='^job_application_role_elevated$'):
            call_command('check_job_runtime', '--require-application-role', stdout=io.StringIO())


@pytest.mark.parametrize('boundary', ['cursor', 'query'])
def test_unavailable_authority_keeps_static_redacted_failure(monkeypatch, boundary):
    database = role_row(monkeypatch, (False,) * 6)
    error = RuntimeError('private-database-credential-sentinel')
    if boundary == 'cursor':
        database.cursor.side_effect = error
    else:
        database.cursor.return_value.__enter__.return_value.execute.side_effect = error
    with pytest.raises(preflight.RuntimeUnavailable) as caught:
        preflight.check_application_role()
    assert str(caught.value) == 'job_application_role_unavailable'
    assert 'sentinel' not in str(caught.value) and caught.value.__suppress_context__
