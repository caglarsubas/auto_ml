#!/usr/bin/env python3
"""Synthetic cache checks inside this qualification's fresh API and worker."""

CODE = r'''
import json,os,socket,sys,uuid
from pathlib import Path
from urllib.parse import unquote,urlsplit
sys.path.insert(0,'/app/backend')
import redis
from ai_assistant.cache_connection import connection_options
from ai_assistant import cache
from ai_assistant.rag.embeddings import _get_redis as embedding_redis
phase,token=sys.argv[1:]
assert len(token)==32 and all(c in '0123456789abcdef' for c in token)
url,options=connection_options()
client=cache._get_redis();assert client is not None and client.ping() is True
# The embedding layer must use the same factory rather than another endpoint.
assert embedding_redis() is client
artifact='qualification-'+token
if phase=='write':
    assert cache.cache_put(0,artifact,{'owned':token,'stage':'api'},ttl=60)
    print(json.dumps({'api_authenticated_tls_write':'passed'}))
elif phase=='worker':
    assert cache.cache_get(0,artifact)=={'owned':token,'stage':'api'}
    assert cache.cache_put(0,artifact,{'owned':token,'stage':'worker'},ttl=60)
    print(json.dumps({'worker_authenticated_tls_read_write':'passed'}))
elif phase=='check':
    try:
        assert cache.cache_get(0,artifact)=={'owned':token,'stage':'worker'}
        password=unquote(urlsplit(url).password)
        failures={}
        def denied(label,kwargs,expected,reason=None):
            test=redis.Redis(socket_connect_timeout=2,socket_timeout=2,**kwargs)
            try:
                test.ping()
            except expected as error:
                if reason is not None:assert reason in str(error)
                failures[label]='rejected'
            else:raise AssertionError(label+'_unexpectedly_connected')
            finally:test.close()
        base={'host':'cache','port':6379,'ssl':True,**options}
        denied('unauthenticated',base,redis.exceptions.AuthenticationError)
        denied('wrong_password',{**base,'password':'wrong-synthetic-password'},redis.exceptions.AuthenticationError)
        broker=unquote(urlsplit(Path('/installation/job-broker-url').read_text().strip()).password)
        denied('broker_credential',{**base,'password':broker},redis.exceptions.AuthenticationError)
        denied('plaintext',{'host':'cache','port':6379,'password':password},redis.exceptions.ConnectionError)
        denied('wrong_ca',{**base,'password':password,'ssl_ca_data':Path('/installation/postgres-ca.crt').read_text()},redis.exceptions.ConnectionError,'CERTIFICATE_VERIFY_FAILED')
        denied('wrong_hostname',{**base,'password':password,'host':socket.gethostbyname('cache')},redis.exceptions.ConnectionError,'CERTIFICATE_VERIFY_FAILED')
        assert client.info('persistence')['aof_enabled']==0
        assert client.info('memory')['maxmemory']==96*1024**2
        print(json.dumps({'api_worker_parity':'passed','denials':failures,'reconstructible_limits':'passed'}))
    finally:assert cache.cache_delete(0,artifact)
else:raise AssertionError('unknown_qualification_phase')
'''


def qualify(value, adopted, command):
    """Only a caller's fresh owned services, not an operator installation."""
    import uuid

    token = uuid.uuid4().hex
    results = {}
    for phase, role in [("write", "api"), ("worker", "worker"), ("check", "api")]:
        output = command(["exec", adopted["services"][role]["container_id"], "python", "-I", "-c", CODE, phase, token])
        import json

        results[phase] = json.loads(output)
    return results
