#!/usr/bin/env python3
"""Selected PostgreSQL CA preflight in the owned sealed API."""

CODE = r'''
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
from backend.runtime_config import private_postgres_tls_options
from django.core.exceptions import ImproperlyConfigured
results={}
with tempfile.TemporaryDirectory(prefix='private-tls-capture-') as temporary:
    for route,name in [('postgres_ca','DECLARAI_DB_SSLROOTCERT')]:
        data=Path(os.environ[name]).read_bytes()
        path=Path(temporary)/route
        def capture():
            return private_postgres_tls_options(path)
        path.write_bytes(data)
        for mode in (0o400,0o600,0o444,0o644):path.chmod(mode);assert capture()
        checked={'stable_selected_input':'passed','public_ca_modes':'passed'}
        alias=Path(temporary)/'alias'
        for fault in ('symlink','hardlink','shared_write','malformed'):
            path.chmod(0o600);path.write_bytes(data);path.chmod(0o400)
            selected=path
            if fault=='symlink':alias.symlink_to(path);selected=alias
            elif fault=='hardlink':os.link(path,alias)
            elif fault=='shared_write':path.chmod(0o666)
            else:path.chmod(0o600);path.write_text('malformed certificate');path.chmod(0o400)
            try:
                try:private_postgres_tls_options(selected)
                except ImproperlyConfigured as error:
                    assert str(error).startswith('DECLARAI_DB_SSLROOTCERT:')
                    checked[fault]='rejected'
                else:raise AssertionError('unsafe_postgres_ca_accepted')
            finally:
                if alias.is_symlink() or alias.exists():alias.unlink()
        path.chmod(0o600);path.write_bytes(data);path.chmod(0o400)
        for fault in ('bytes','mode','link'):
            path.chmod(0o600);path.write_bytes(data);path.chmod(0o400)
            stamp=path.stat();actual_fstat=os.fstat;actual_fdopen=os.fdopen
            alias=Path(temporary)/'alias'
            class CoarseTimes:
                st_mtime_ns,st_ctime_ns=stamp.st_mtime_ns,stamp.st_ctime_ns
                def __init__(self,current):self.current=current
                def __getattr__(self,key):return getattr(self.current,key)
            def fstat(fd):
                current=actual_fstat(fd)
                return CoarseTimes(current) if (current.st_dev,current.st_ino)==(stamp.st_dev,stamp.st_ino) else current
            class ChangingRead:
                def __init__(self,stream):self.stream=stream;self.changed=False
                def __enter__(self):return self
                def __exit__(self,*args):self.stream.close()
                def fileno(self):return self.stream.fileno()
                def seek(self,offset):return self.stream.seek(offset)
                def read(self,limit):
                    value=self.stream.read(limit);current=actual_fstat(self.fileno())
                    if not self.changed and (current.st_dev,current.st_ino)==(stamp.st_dev,stamp.st_ino):
                        self.changed=True
                        if fault=='bytes':path.chmod(0o600);path.write_bytes(b'X'+value[1:]);path.chmod(0o400)
                        elif fault=='mode':path.chmod(0o666)
                        else:os.link(path,alias)
                    return value
            try:
                with patch('os.fstat',side_effect=fstat),patch('os.fdopen',side_effect=lambda *a,**k:ChangingRead(actual_fdopen(*a,**k))):
                    try:capture()
                    except ImproperlyConfigured as error:
                        assert str(error).startswith('DECLARAI_DB_SSLROOTCERT:')
                        checked[fault]='rejected'
                    else:raise AssertionError('unstable_tls_input_accepted')
            finally:
                if alias.exists():alias.unlink()
                path.chmod(0o400)
        assert Path(os.environ[name]).read_bytes()==data
        results[route]=checked
print(json.dumps({'actual_sealed_postgres_ca_preflight':results,'installed_inputs_modified':False,'private_values_emitted':False}))
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
        raise startup.checker.planner.PlanError("private_postgres_ca_fixture_scope_required")
    return json.loads(command([
        "exec", adopted["services"]["api"]["container_id"], "python", "-I", "-c", CODE,
    ]))
