#!/usr/bin/env python3
"""Synthetic broker trust checks inside exclusively owned private fixtures."""

CODE = r'''
import json,os,socket,sys
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
from backend.celery import app
from execution_jobs.broker_transport import Transport,SelectedCAConnection,captured_tls
from execution_jobs.config import load_job_config
from kombu import Connection,Producer,Queue
import redis
phase,token=sys.argv[1:]
assert len(token)==32 and all(c in '0123456789abcdef' for c in token)
queue='declarai-broker-qualification-'+token
config=load_job_config('private')
def open_broker():
    connection=app.connection_for_write()
    assert connection.get_transport_cls() is Transport
    connection.ensure_connection(max_retries=0)
    channel=connection.default_channel
    for asynchronous in (False,True):
        params=channel._connparams(asynchronous=asynchronous)
        assert issubclass(params['connection_class'],SelectedCAConnection)
        assert params['ssl_ca_data']==config['CELERY_BROKER_USE_SSL']['ssl_ca_data']
    assert channel.client.info('persistence')['aof_enabled']==1
    return connection
with open_broker() as connection:
    bound=Queue(queue,durable=False,auto_delete=False)(connection)
    bound.declare()
    if phase in ('api','dispatcher'):
        Producer(connection).publish({'owned':token,'stage':phase},exchange='',routing_key=queue,serializer='json',retry=False)
        print(json.dumps({phase+'_selected_ca_publish':'passed','producer_and_async_consumer_class':'passed'}))
    elif phase in ('worker','check'):
        try:
            message=bound.get(no_ack=False)
            assert message is not None and message.payload=={'owned':token,'stage':'api' if phase=='worker' else 'dispatcher'}
            message.ack()
            if phase=='worker':
                print(json.dumps({'worker_selected_ca_consume':'passed','producer_and_async_consumer_class':'passed'}))
            else:
                failures={}
                def denied(label,overrides,reason=None):
                    options={'hostname':config['CELERY_BROKER_URL'],'transport':config['CELERY_BROKER_TRANSPORT'],
                             'ssl':config['CELERY_BROKER_USE_SSL'],'connect_timeout':2,
                             'transport_options':{'socket_timeout':2,'socket_connect_timeout':2}}
                    options.update(overrides)
                    with Connection(**options) as other:
                        try:other.ensure_connection(max_retries=0)
                        except Exception as error:
                            if reason is not None:assert reason in str(error)
                            failures[label]='rejected'
                        else:raise AssertionError(label+'_unexpectedly_connected')
                base='rediss://:{}@job-broker:6379/1'
                denied('unauthenticated',{'hostname':'rediss://job-broker:6379/1'},'Authentication')
                denied('wrong_password',{'hostname':base.format('wrong-synthetic-password')},'invalid username-password')
                from urllib.parse import urlsplit
                cache_password=urlsplit(Path('/installation/cache-url').read_text().strip()).password
                denied('cache_credential',{'hostname':base.format(cache_password)},'invalid username-password')
                wrong=captured_tls('/installation/cache-ca.crt')
                denied('wrong_ca',{'ssl':wrong},'CERTIFICATE_VERIFY_FAILED')
                denied('wrong_hostname',{'hostname':config['CELERY_BROKER_URL'].replace('@job-broker:', '@'+socket.gethostbyname('job-broker')+':')},'CERTIFICATE_VERIFY_FAILED')
                before=os.environ.get('SSL_CERT_FILE')
                try:
                    os.environ['SSL_CERT_FILE']='/installation/job-ca.crt'
                    # Positive control: the ambient anchor really is usable by
                    # the preceding library implementation in this owned fixture.
                    control=redis.Redis.from_url(config['CELERY_BROKER_URL'],ssl_ca_certs='/installation/cache-ca.crt',ssl_cert_reqs='required',ssl_check_hostname=True,socket_timeout=2,socket_connect_timeout=2)
                    try:assert control.ping() is True
                    finally:control.close()
                    denied('ambient_trust_cannot_override_selected_ca',{'ssl':wrong},'CERTIFICATE_VERIFY_FAILED')
                finally:
                    if before is None:os.environ.pop('SSL_CERT_FILE',None)
                    else:os.environ['SSL_CERT_FILE']=before
                plain=redis.Redis(host='job-broker',port=6379,socket_timeout=2,socket_connect_timeout=2)
                try:
                    try:plain.ping()
                    except redis.exceptions.ConnectionError:failures['plaintext']='rejected'
                    else:raise AssertionError('plaintext_unexpectedly_connected')
                finally:plain.close()
                print(json.dumps({'dispatcher_payload_acknowledged':'passed','denials':failures,'ambient_anchor_positive_control':'passed','aof_retained':'passed'}))
        finally:
            if phase=='check':bound.delete()
    else:raise AssertionError('unsupported_phase')
'''


def qualify(value, adopted, command):
    import json
    import os
    import re
    import sys
    import uuid
    from pathlib import Path
    import private_dependency_start as startup

    root = Path(value["request"]["root"])
    if (sys.platform != "linux" or os.geteuid() != 0 or root.name != "installation"
            or root.parent.parent != Path("/srv")
            or not re.fullmatch(r"declarai-p37-[0-9a-f]{32}", root.parent.name)):
        raise startup.checker.planner.PlanError("broker_tls_fixture_scope_required")
    token = uuid.uuid4().hex
    results = {}
    for phase, role in [("api", "api"), ("worker", "worker"), ("dispatcher", "dispatcher"), ("check", "api")]:
        results[phase] = json.loads(command([
            "exec", adopted["services"][role]["container_id"], "python", "-I", "-c", CODE, phase, token,
        ]))
    return results
