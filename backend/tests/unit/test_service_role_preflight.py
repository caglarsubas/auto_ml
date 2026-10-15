"""Every fixed/private native launch rechecks database authority before exec."""
import importlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

pytestmark = pytest.mark.unit
SCRIPTS = Path(__file__).resolve().parents[3] / 'scripts'
ROLES = ['api', 'worker', 'dispatcher', 'preflight']


class Launched(BaseException):
    pass


@pytest.fixture
def launcher(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    service = importlib.import_module('private_service')
    monkeypatch.setenv('DECLARAI_RUNTIME_PROFILE', 'private')
    monkeypatch.setenv('DJANGO_TRUST_PROXY_TLS', 'true')
    for name in ('GUNICORN_CMD_ARGS', 'FORWARDED_ALLOW_IPS', 'PYTHONPATH', 'PYTHONHOME',
                 'PROMETA_SKILLS_DIR', 'DJANGO_SETTINGS_MODULE'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(service.os, 'geteuid', lambda: 10001)
    monkeypatch.setattr(service.os, 'getegid', lambda: 10001)
    monkeypatch.setattr(service.os, 'chdir', lambda *a: None)
    monkeypatch.setattr(service, 'verify', lambda *a: None)
    monkeypatch.setattr(service, 'Path', lambda *a: SimpleNamespace(
        lstat=lambda: SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=10001)))
    executions = []

    def execute(*args):
        executions.append(args)
        raise Launched

    monkeypatch.setattr(service.os, 'execv', execute)
    return service, executions


@pytest.mark.parametrize('role', ROLES)
@pytest.mark.parametrize('allowed', [False, True])
def test_fixed_roles_require_authority_on_every_launch(launcher, monkeypatch, capsys, role, allowed):
    service, executions = launcher
    checks = []

    def preflight(args, **kwargs):
        checks.append(args)
        # Model a successful transport/schema check followed by denied DB
        # authority. Without the flag, the old launcher incorrectly continues.
        denied = not allowed and '--require-application-role' in args
        return SimpleNamespace(returncode=1 if denied else 0)

    monkeypatch.setattr(service.subprocess, 'run', preflight)
    if not allowed:
        with pytest.raises(service.ManifestError, match='^private_service_preflight_failed$'):
            service.launch([role])
        assert not executions
    elif role == 'preflight':
        service.launch([role])
        assert not executions and capsys.readouterr().out.strip() == 'private_service_preflight_passed'
    else:
        with pytest.raises(Launched):
            service.launch([role])
        assert len(executions) == 1
        command = executions[0][1]
        if role == 'api':
            assert command[-1] == 'backend.wsgi:application' and 'gunicorn' in command
        else:
            assert command == ['sh', str(service.ROOT / 'docker/private-job-entrypoint.sh'), role]
    assert len(checks) == 1 and checks[0][-2:] == ['check_job_runtime', '--require-application-role']


@pytest.mark.parametrize('role', ['worker', 'dispatcher'])
@pytest.mark.parametrize('allowed', [False, True])
def test_actual_shell_entrypoint_checks_authority_before_native_exec(tmp_path, role, allowed):
    log = tmp_path / 'calls.jsonl'
    code = r"""
import json,os,sys
from pathlib import Path
with Path(os.environ['ROLE_PROBE_LOG']).open('a') as out:out.write(json.dumps(sys.argv[1:])+'\n')
if sys.argv[1:3]==['manage.py','check_job_runtime'] and '--require-application-role' in sys.argv and os.environ['ROLE_PROBE_ALLOWED']=='no':
    raise SystemExit(1)
"""
    result = subprocess.run(['/bin/sh', str(SCRIPTS.parent / 'docker/private-job-entrypoint.sh'), role],
                            env={**os.environ, 'PATH':str(Path(__file__).resolve().parents[1] / 'fixtures/role_launch'),
                                 'ROLE_PROBE_PYTHON':sys.executable, 'ROLE_PROBE_CODE':code, 'DECLARAI_RUNTIME_PROFILE':'private',
                                 'ROLE_PROBE_LOG':str(log), 'ROLE_PROBE_ALLOWED':'yes' if allowed else 'no'},
                            capture_output=True, text=True, timeout=5)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert result.returncode == (0 if allowed else 1)
    assert calls[0] == ['manage.py', 'check_job_runtime', '--require-application-role']
    assert len(calls) == (2 if allowed else 1)
    if allowed:
        if role == 'worker':
            assert calls[1] == ['-m', 'celery', '-A', 'backend.celery:app', 'worker', '--pool=prefork',
                                '--concurrency=2', '--without-gossip', '--without-mingle', '--without-heartbeat',
                                '--loglevel=WARNING']
        else:
            assert calls[1] == ['manage.py', 'dispatch_jobs']


@pytest.mark.parametrize('role', ROLES)
@pytest.mark.django_db(transaction=True)
def test_actual_postgresql_elevated_test_role_blocks_every_fixed_launch(launcher, monkeypatch, role):
    from execution_jobs.management.commands import check_job_runtime
    from execution_jobs import preflight

    service, executions = launcher
    monkeypatch.setattr(check_job_runtime, 'check_runtime', lambda: {'test_transport_seam':True})
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT rolsuper OR rolcreatedb FROM pg_roles WHERE rolname=current_user')
            assert cursor.fetchone() == (True,)
        role_check = preflight.check_application_role
    else:
        def role_check():
            raise preflight.RuntimeUnavailable('job_application_role_elevated')
    checked = []

    def query():
        checked.append(1)
        return role_check()

    monkeypatch.setattr(check_job_runtime, 'check_application_role', query)

    def management(args, **kwargs):
        try:
            call_command('check_job_runtime', *args[3:], stdout=io.StringIO())
        except CommandError as error:
            assert str(error) == 'job_application_role_elevated'
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(service.subprocess, 'run', management)
    with pytest.raises(service.ManifestError, match='^private_service_preflight_failed$'):
        service.launch([role])
    assert checked == [1] and not executions
