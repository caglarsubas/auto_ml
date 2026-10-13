#!/usr/bin/env python3
"""Actual adopted Django roles retain the private PostgreSQL TLS contract."""

CODE = r'''
import json,os,socket,sys
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
# Conflicting ambient defaults must not alter explicit connection parameters.
os.environ.update(PGGSSENCMODE='require',PGSSLMODE='disable',PGSSLMINPROTOCOLVERSION='TLSv1',PGSSLROOTCERT='/installation/cache-ca.crt')
os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
import django
django.setup()
import psycopg
from django.db import connections
db=connections['default']
try:
    with db.cursor() as cursor:
        cursor.execute('SELECT current_database(),current_user,s.ssl,s.version,r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolbypassrls FROM pg_roles r JOIN pg_stat_ssl s ON s.pid=pg_backend_pid() WHERE r.rolname=current_user')
        row=cursor.fetchone()
        assert row[:3]==(os.environ['DECLARAI_DB_NAME'],os.environ['DECLARAI_DB_USER'],True)
        assert row[3] in ('TLSv1.2','TLSv1.3') and all(x is False for x in row[4:])
    # ConnectionInfo.get_parameters omits values equal to driver defaults.
    # PQconninfo retains the effective options; never serialize this mapping.
    parameters={option.keyword.decode():option.val.decode() for option in db.connection.pgconn.info if option.val is not None}
    assert parameters['sslmode']=='verify-full' and parameters['gssencmode']=='disable'
    assert parameters['ssl_min_protocol_version']=='TLSv1.2'
    assert parameters['sslrootcert']==os.environ['DECLARAI_DB_SSLROOTCERT']
    params=db.get_connection_params();params['connect_timeout']=2
    denials={}
    for fault,changes,reason in (
        ('wrong_ca',{'sslrootcert':'/installation/cache-ca.crt'},'certificate verify failed'),
        ('wrong_hostname',{'host':'mismatch.private.test','hostaddr':socket.gethostbyname(os.environ['DECLARAI_DB_HOST'])},'does not match host name'),
    ):
        try:
            with psycopg.connect(**{**params,**changes}):pass
        except psycopg.OperationalError as error:
            assert reason in str(error)
            denials[fault]='rejected'
        else:raise AssertionError('private_postgres_tls_negative_control_accepted')
    print(json.dumps({'django_authenticated_tls':'passed','ordinary_database_role':'passed','explicit_tls_despite_ambient_defaults':'passed','tls_version':row[3],'denials':denials,'private_values_emitted':False}))
finally:db.close()
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
        raise startup.checker.planner.PlanError("private_postgres_tls_fixture_scope_required")
    return {role: json.loads(command([
        "exec", adopted["services"][role]["container_id"], "python", "-I", "-c", CODE,
    ])) for role in ("api", "worker", "dispatcher")}
