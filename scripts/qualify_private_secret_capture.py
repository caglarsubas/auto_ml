#!/usr/bin/env python3
"""Exercise private secret loading in the owned fixture's sealed API."""

CODE = r'''
import json,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
from backend.runtime_config import _secret,load_runtime
from execution_jobs.config import load_job_config
from django.core.exceptions import ImproperlyConfigured
checked={}
with tempfile.TemporaryDirectory(prefix='private-secret-qualification-') as temporary:
    for name in ('DJANGO_SECRET_KEY','DECLARAI_DB_PASSWORD','DECLARAI_JOB_BROKER_URL'):
        captured=_secret(os.environ,name,private=True)
        path=Path(temporary)/name
        path.write_text(captured+'\n');path.chmod(0o400)
        env={**os.environ,name+'_FILE':str(path)};env.pop(name,None)
        def configure():
            return load_job_config('private',env) if name=='DECLARAI_JOB_BROKER_URL' else load_runtime(Path('/app/backend'),'unused-development-key',env)
        assert configure()
        results={'protected_delivery':'passed'}
        for fault in ('shared_read','hardlink'):
            alias=Path(temporary)/'alias'
            if fault=='shared_read':path.chmod(0o644)
            else:os.link(path,alias)
            try:
                try:configure()
                except ImproperlyConfigured as error:
                    assert captured not in str(error) and str(path) not in str(error)
                    results[fault]='rejected'
                else:raise AssertionError('unsafe_private_secret_accepted')
            finally:
                if alias.exists():alias.unlink()
                path.chmod(0o400)
        checked[name]=results
print(json.dumps({'actual_sealed_private_configuration':checked,'installed_delivery_modified':False,'private_values_emitted':False}))
'''


def qualify(value, adopted, command):
    import json
    import os
    import re
    import sys
    from pathlib import Path
    import private_dependency_start as startup

    root = Path(value["request"]["root"])
    if (sys.platform != "linux" or os.geteuid() != 0 or root.name != "installation"
            or root.parent.parent != Path("/srv")
            or not re.fullmatch(r"declarai-p37-[0-9a-f]{32}", root.parent.name)):
        raise startup.checker.planner.PlanError("private_secret_fixture_scope_required")
    return json.loads(command([
        "exec", adopted["services"]["api"]["container_id"], "python", "-I", "-c", CODE,
    ]))
