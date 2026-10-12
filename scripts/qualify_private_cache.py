#!/usr/bin/env python3
"""Synthetic cache checks inside this qualification's fresh API and worker."""

CODE = r'''
import json,os,socket,sys,uuid
from pathlib import Path
from urllib.parse import unquote,urlsplit
sys.path.insert(0,'/app/backend')
import redis
from ai_assistant.cache_connection import connection_options,create_client
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
        # Even a trusted ambient/system anchor must not override selected trust.
        before=os.environ.get('SSL_CERT_FILE')
        try:
            os.environ['SSL_CERT_FILE']='/installation/cache-ca.crt'
            alternate=create_client({**os.environ,'DECLARAI_CACHE_CA_FILE':'/installation/postgres-ca.crt'})
            try:alternate.ping()
            except redis.exceptions.ConnectionError as error:
                assert 'CERTIFICATE_VERIFY_FAILED' in str(error)
                failures['ambient_trust_cannot_override_selected_ca']='rejected'
            else:raise AssertionError('ambient_trust_bypassed_selected_ca')
            finally:alternate.close()
        finally:
            if before is None:os.environ.pop('SSL_CERT_FILE',None)
            else:os.environ['SSL_CERT_FILE']=before
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


RECOVERY_CODE = r"""
import json,sys,time,uuid
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
from ai_assistant import cache
import redis
attempts=0
original=cache.create_client
def counted(*args,**kwargs):
    global attempts
    attempts+=1
    return original(*args,**kwargs)
cache.create_client=counted
print('cache_recovery_ready',flush=True)
assert input()=='cache_stopped'
assert cache._get_redis() is None
assert cache._get_redis() is None and attempts==1
print('cache_recovery_unavailable',flush=True)
assert input()=='cache_restarted'
remaining=max(0,cache._redis_retry_after-time.monotonic())
assert remaining<=cache.CACHE_RETRY_SECONDS==5
if remaining:time.sleep(remaining+0.01)
client=cache._get_redis();assert client is not None and attempts==2
assert cache._get_redis() is client and attempts==2
key='declarai-cache-recovery:'+uuid.uuid4().hex
try:
    client.setex(key,60,'bounded-recovery');assert client.get(key)=='bounded-recovery'
finally:client.delete(key)
print(json.dumps({'same_process_reconnection':'passed','cooldown_single_attempt':'passed','authenticated_tls_read_write':'passed'}),flush=True)
"""


def recovery(value, adopted, dependency, parent, command):
    """Fresh owned fixture only. Never expose this as an operator recovery API."""
    import json
    import os
    import re
    import selectors
    import subprocess
    import sys
    from pathlib import Path
    import private_dependency_start as startup

    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or parent.parent != Path("/srv")
        or not re.fullmatch(r"declarai-p37-[0-9a-f]{32}", parent.name)
        or value["request"]["root"] != str(parent / "installation")
    ):
        raise startup.checker.planner.PlanError("cache_recovery_fixture_scope_required")
    expected = dependency["plan_manifest_sha256"]
    _, spec, initial, _, _, directory = startup.prepared(parent / "plan", expected)
    os.close(directory)
    cache_id = dependency["services"]["cache"]["container_id"]
    receipt = (parent / "installation/dependencies/started.json").read_bytes()
    startup.validate(
        startup.resources.inspect("container", cache_id),
        "cache",
        spec,
        startup.labels(value, initial),
        startup.resources.inspect("image", value["images"]["redis"]),
        startup.names(value)["cache"],
        active=True,
    )

    # A helper inherits only the already validated application container's
    # ordinary authority; no new host mount, network or privileged role.
    def exchange(code, ready, unavailable):
        process = subprocess.Popen(
            [
                *startup.resources.PREFIX,
                "exec",
                "-i",
                adopted["services"]["api"]["container_id"],
                "python",
                "-I",
                "-c",
                code,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def marker(wanted):
            with selectors.DefaultSelector() as selected:
                selected.register(process.stdout, selectors.EVENT_READ)
                if not selected.select(20):
                    raise startup.checker.planner.PlanError("cache_recovery_fixture_handshake_failed")
                if process.stdout.readline().strip() != wanted:
                    raise startup.checker.planner.PlanError("cache_recovery_fixture_handshake_failed")

        try:
            marker(ready)
            startup.validate(
                startup.resources.inspect("container", cache_id),
                "cache",
                spec,
                startup.labels(value, initial),
                startup.resources.inspect("image", value["images"]["redis"]),
                startup.names(value)["cache"],
                active=True,
            )
            command(["container", "stop", "--time", "10", cache_id])
            process.stdin.write(b"cache_stopped\n")
            process.stdin.flush()
            marker(unavailable)
            command(["container", "start", cache_id])
            restarted = startup.start(parent / "plan", expected)
            if {r: v["container_id"] for r, v in restarted["services"].items()} != {
                r: v["container_id"] for r, v in dependency["services"].items()
            } or (parent / "installation/dependencies/started.json").read_bytes() != receipt:
                raise startup.checker.planner.PlanError("cache_recovery_fixture_changed_identity_or_history")
            process.stdin.write(b"cache_restarted\n")
            process.stdin.flush()
            output, errors = process.communicate(timeout=20)
            if process.returncode:
                raise startup.checker.planner.PlanError("cache_recovery_fixture_client_failed")
            result = json.loads(output)
            result["same_dependency_ids_and_receipt"] = "passed"
            return result
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)

    return {
        "cold": exchange(RECOVERY_CODE, b"cache_recovery_ready", b"cache_recovery_unavailable"),
        "warm": exchange(WARM_CODE, b"warm_cache_ready", b"warm_cache_unavailable"),
    }


WARM_CODE = r"""
import json,sys,uuid
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
from ai_assistant import cache
client=cache._get_redis();assert client is not None and client.ping() is True
artifact='warm-recovery-'+uuid.uuid4().hex
assert cache.cache_put(0,artifact,{'state':'before_restart'},ttl=60)
print('warm_cache_ready',flush=True)
assert input()=='cache_stopped'
assert cache.cache_get(0,artifact) is None
assert cache._get_redis() is client
print('warm_cache_unavailable',flush=True)
assert input()=='cache_restarted'
try:
    assert cache._get_redis() is client
    assert cache.cache_get(0,artifact) is None
    assert cache.cache_put(0,artifact,{'state':'after_restart'},ttl=60)
    assert cache.cache_get(0,artifact)=={'state':'after_restart'}
finally:assert cache.cache_delete(0,artifact)
print(json.dumps({'warm_same_client_pool_reconnect':'passed','lost_cache_is_miss':'passed','authenticated_tls_read_write':'passed'}),flush=True)
"""
