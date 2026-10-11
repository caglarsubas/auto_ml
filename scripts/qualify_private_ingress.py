"""Real HTTPS boundary inside the explicitly disposable private API fixture."""

import json
import base64
import hashlib
import re
import subprocess
import uuid
from pathlib import Path

from qualify_private_api_image import command

PREPARE_TLS = r"""
import json,os,sys
from pathlib import Path
root=Path('/installation');root.chmod(0o700)
for name,value in json.load(sys.stdin).items():
    file=root/name;file.write_text(value);file.chmod(0o400);os.chown(file,10001,10001)
os.chown(root,10001,10001)
"""

SEED_DEVELOPER = r"""
import json,os,sys,uuid
os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
import django;django.setup()
from django.contrib.auth import get_user_model
from access_control.models import ProjectMembership
from access_control.projects import operator_change
value=json.load(sys.stdin);actor=get_user_model().objects.get(username=value['username'])
assert not actor.is_staff and not actor.is_superuser
member=ProjectMembership.objects.get(actor=actor)
operator_change({'operation':'member','project_id':str(member.project_id),'user':actor.username,'role':'developer'},uuid.uuid4(),'disposable-tls-developer')
"""

PROBE_TLS = r"""
import http.client,json,socket,ssl,sys,time
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
value=json.load(sys.stdin);cookies=SimpleCookie()
context=ssl.create_default_context(cadata=value['ca'])
class TLS(http.client.HTTPSConnection):
    def connect(self):
        self.sock=self._context.wrap_socket(socket.create_connection(('ingress',8443),timeout=self.timeout),server_hostname=self.host)
def connection(ctx=context,host='api.private.test'):
    return TLS(host,8443,timeout=5,context=ctx)
def headers(extra=None):
    result={'Host':'api.private.test:8443'}
    if cookies:result['Cookie']='; '.join(k+'='+m.value for k,m in cookies.items())
    result.update(extra or {});return result
def request(method,path,body=None,extra=None):
    conn=connection()
    try:
        if isinstance(body,dict):body=json.dumps(body).encode();extra={'Content-Type':'application/json',**(extra or {})}
        conn.request(method,path,body,headers(extra));response=conn.getresponse()
        data=response.read();result=(response.status,dict(response.getheaders()),data)
        for name,content in response.getheaders():
            if name.lower()=='set-cookie':cookies.load(content)
        return result
    finally:conn.close()
deadline=time.monotonic()+60
while True:
    try:status,returned,data=request('GET','/api/auth/session/');break
    except (OSError,http.client.HTTPException):
        if time.monotonic()>deadline:raise
        time.sleep(0.25)
assert status==200 and not json.loads(data)['authenticated']
assert cookies['csrftoken']['secure'] and returned['Cache-Control']=='no-store'
assert returned['Strict-Transport-Security']=='max-age=31536000'
assert request('GET','/api/projects/')[0]==403
spoof={'X-Forwarded-Proto':'http','X-Forwarded-Host':'evil.test','X-Forwarded-Port':'80','Forwarded':'host=evil.test;proto=http','X-Forwarded-Ssl':'off','X-Scheme':'http','X-Real-IP':'198.51.100.23','X-Forwarded-For':'198.51.100.23','X-Accel-Redirect':'/installation/tls.key'}
assert request('GET','/api/auth/session/',extra=spoof)[0]==200
for bad,expected in [('evil.test',421),('api.private.test',421),('api.private.test:9999',421),('api.private.test:8443.evil.test',400)]:
    actual=request('GET','/api/auth/session/',extra={'Host':bad})[0]
    assert actual==expected,(bad,actual,expected)
root=request('GET','/')
assert root[0]==(200 if value.get('frontend') else 404)
if value.get('frontend'):assert b'<app-root>' in root[2]
assert request('GET','/admin/')[0]==404
for ctx,host in [(ssl.create_default_context(cadata=value['wrong_ca']),'api.private.test'),(context,'evil.test')]:
    conn=connection(ctx,host)
    try:
        try:conn.connect()
        except ssl.SSLError:pass
        else:raise AssertionError('Untrusted TLS connection accepted')
    finally:conn.close()
for version in [ssl.TLSVersion.TLSv1_2,ssl.TLSVersion.TLSv1_3]:
    ctx=ssl.create_default_context(cadata=value['ca']);ctx.minimum_version=version;ctx.maximum_version=version
    conn=connection(ctx)
    try:conn.connect();assert conn.sock.version() in ('TLSv1.2','TLSv1.3')
    finally:conn.close()
credentials={'username':value['username'],'password':value['password']}
csrf=json.loads(data)['csrf_token'];csrf_headers={'Origin':'https://console.private.test','X-CSRFToken':csrf}
assert request('POST','/api/auth/login/',credentials)[0]==403
assert request('POST','/api/auth/login/',credentials,{'Origin':'https://evil.test','X-CSRFToken':csrf,**spoof})[0]==403
status,returned,data=request('POST','/api/auth/login/',credentials,csrf_headers)
assert status==200 and json.loads(data)['authenticated']
assert cookies['sessionid']['secure'] and cookies['sessionid']['httponly']
project=json.loads(request('GET','/api/projects/')[2])['projects'][0]['id']
csrf=json.loads(request('GET','/api/auth/session/')[2])['csrf_token']
csrf_headers={'Origin':'https://console.private.test','X-CSRFToken':csrf}
# A partial upload must not occupy the single synchronous API worker. A
# separate session request finishes while the buffered request is incomplete.
boundary='declarai-private-boundary'
csv=b'feature,target\n'+b'123456789,0\n'*12000
body=(f'--{boundary}\r\nContent-Disposition: form-data; name="project_id"\r\n\r\n{project}\r\n--{boundary}\r\nContent-Disposition: form-data; name="column_separator"\r\n\r\ncomma\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="private.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode()+csv+f'\r\n--{boundary}--\r\n'.encode())
upload=connection()
try:
    upload.putrequest('POST','/api/declaration/',skip_host=True)
    for name,content in headers({**csrf_headers,'Content-Type':f'multipart/form-data; boundary={boundary}','Content-Length':str(len(body))}).items():upload.putheader(name,content)
    upload.endheaders();upload.send(body[:80000]);time.sleep(0.25)
    assert request('GET','/api/auth/session/')[0]==200
    upload.send(body[80000:]);response=upload.getresponse();data=response.read()
    assert response.status==201,(response.status,data[:200])
    created=json.loads(data);assert created['project_id']==project
finally:upload.close()
path=urlsplit(created['file']).path
status,returned,data=request('GET',path)
assert status==200 and data==csv and returned['Cache-Control']=='private, no-store'
assert request('GET','/media/unassigned.csv')[0]==403
# The ingress owns upstream framing, including admitted chunked bodies.
conn=connection()
try:
    conn.request('POST','/api/declaration/',iter([body[:30000],body[30000:]]),
                 headers({**csrf_headers,'Content-Type':f'multipart/form-data; boundary={boundary}'}),encode_chunked=True)
    response=conn.getresponse();data=response.read();assert response.status==201,(response.status,data[:200])
    assert json.loads(data)['project_id']==project
finally:conn.close()
# Reject both declared and chunked oversized bodies at the edge, before the
# application receives them. No gigabyte fixture or altered application budget.
for chunked in [False,True]:
    conn=connection()
    try:
        conn.putrequest('POST','/api/declaration/',skip_host=True)
        for name,content in headers(csrf_headers).items():conn.putheader(name,content)
        conn.putheader('Transfer-Encoding','chunked') if chunked else conn.putheader('Content-Length',str(1048577))
        conn.endheaders()
        if chunked:conn.send(b'100001\r\n'+b'x'*1048577+b'\r\n0\r\n\r\n')
        response=conn.getresponse();assert response.status==413,('oversized_chunked',chunked,response.status);response.read()
    finally:conn.close()
assert request('POST','/api/auth/logout/',{},csrf_headers)[0]==200
assert request('GET',path)[0]==403 and request('GET','/api/projects/')[0]==403
print(json.dumps({'actual_https_session_csrf':'passed','secure_cookies':'passed','canonical_scheme_and_host':'passed','invalid_host_sni_ca':'blocked','tls_1_2_and_1_3':'passed','invalid_origin':'blocked','partial_upload_keeps_api_available':'passed','multipart_upload_and_protected_download':'passed','admitted_chunked_body':'passed','declared_and_chunked_body_limit':'passed','recorded_logout':'passed'}))
"""


def qualify_ingress(image_id, api_image, api_container, socket_volume, fixture, reports, probe, frontend_browser=False):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) or not socket_volume.startswith("declarai-fixed-api-"):
        raise RuntimeError("Requires the owning disposable fixed API fixture.")
    prefix = "declarai-tls-ingress-" + uuid.uuid4().hex[:12]
    network, container, volume = (prefix + suffix for suffix in ("-edge", "-server", "-certificates"))
    created_network = created_volume = created_container = False
    cert, key = fixture / "ingress.crt", fixture / "ingress.key"
    command(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=api.private.test",
             "-addext", "subjectAltName=DNS:api.private.test", "-keyout", str(key), "-out", str(cert)])
    key.chmod(0o600)
    try:
        command(["docker", "exec", "-i", api_container, "python", "-c", SEED_DEVELOPER], data=json.dumps(probe).encode())
        # Docker intentionally does not publish ports from an internal bridge.
        # Only the browser fixture uses an owned edge bridge plus a random
        # loopback binding; it still has no private-service network membership.
        command(["docker", "network", "create", *([] if frontend_browser else ["--internal"]), network]);created_network = True
        command(["docker", "volume", "create", volume]);created_volume = True
        command(["docker", "run", "--rm", "-i", "--pull=never", "--network", "none", "--read-only", "--user", "0:0",
                 "--cap-drop", "ALL", "--cap-add", "CHOWN", "--security-opt", "no-new-privileges", "-v", volume + ":/installation",
                 "--entrypoint", "python", api_image, "-c", PREPARE_TLS],
                data=json.dumps({"tls.crt": cert.read_text(), "tls.key": key.read_text()}).encode())
        ports = ["-p", "127.0.0.1::8443"] if frontend_browser else []
        command(["docker", "create", "--name", container, "--pull=never", "--network", network, "--network-alias", "ingress", *ports,
                 "--read-only", "--cpus", "1", "--memory", "256m", "--pids-limit", "32", "--cap-drop", "ALL",
                 "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,noexec,nosuid,size=268435456,uid=10001,gid=10001,mode=700",
                 "-v", volume + ":/installation:ro", "-v", socket_volume + ":/run/declarai:ro", image_id])
        created_container = True
        command(["docker", "start", container])
        output = command(["docker", "run", "--rm", "-i", "--pull=never", "--network", network, "--read-only", "--cap-drop", "ALL",
                          "--security-opt", "no-new-privileges", "--entrypoint", "python", api_image, "-c", PROBE_TLS],
                         data=json.dumps({**probe, "ca": cert.read_text(), "wrong_ca": (fixture / "wrong-ca.crt").read_text(), "frontend": frontend_browser}).encode())
        info = json.loads(command(["docker", "inspect", container]))[0]
        assert info["Config"]["User"] == "10001:10001" and info["HostConfig"]["ReadonlyRootfs"]
        assert info["Config"]["Entrypoint"] == ["/bin/sh", "/opt/declarai/start-ingress.sh"]
        assert not info["HostConfig"]["Privileged"]
        if frontend_browser:
            binding = info["NetworkSettings"]["Ports"]["8443/tcp"]
            assert len(binding) == 1 and binding[0]["HostIp"] == "127.0.0.1"
        else:
            assert not info["HostConfig"]["PortBindings"]
        assert set(info["NetworkSettings"]["Networks"]) == {network}
        # Docker exposes tmpfs separately from ordinary volume/bind mounts.
        assert {m["Destination"] for m in info["Mounts"]} == {"/installation", "/run/declarai"}
        assert all(m["Type"] == "volume" and not m["RW"] for m in info["Mounts"])
        assert set(info["HostConfig"]["Tmpfs"]) == {"/tmp"}
        assert info["HostConfig"]["Memory"] == 268435456 and info["HostConfig"]["PidsLimit"] == 32
        assert info["HostConfig"]["CapDrop"] == ["ALL"]
        status = json.loads(output)
        if frontend_browser:
            # Browser trust is restricted to this owned synthetic leaf, never
            # ignoreHTTPSErrors. The raw TLS probe still checks the CA/name.
            public = command(["openssl", "x509", "-in", str(cert), "-pubkey", "-noout"])
            der = command(["openssl", "pkey", "-pubin", "-outform", "DER"], data=public)
            pin = base64.b64encode(hashlib.sha256(der).digest()).decode()
            browser = command(["node", str(Path(__file__).with_name("qualify_private_frontend.mjs"))],
                              data=json.dumps({**probe, "port": int(binding[0]["HostPort"]), "pin": pin}).encode(), timeout=180)
            status["frontend_browser"] = json.loads(browser)
        command(["docker", "stop", container])
        for extra, expected in [([], b"private_ingress_certificate_required"),
                                (["--user", "0:0"], b"private_ingress_identity_or_command_rejected")]:
            failed = subprocess.run(["docker", "run", "--rm", "--pull=never", "--network", "none", "--read-only",
                                     "--cap-drop", "ALL", *extra, image_id], capture_output=True, check=False, timeout=30)
            assert failed.returncode != 0 and expected in failed.stderr
        failed = subprocess.run(["docker", "run", "--rm", "--pull=never", "--network", "none", "--read-only",
                                 "--cap-drop", "ALL", image_id, "unapproved-command"], capture_output=True, check=False, timeout=30)
        assert failed.returncode != 0 and b"private_ingress_identity_or_command_rejected" in failed.stderr
        command(["docker", "run", "--rm", "--pull=never", "--network", "none", "--read-only", "--cap-drop", "ALL",
                 "-v", volume + ":/installation", "--entrypoint", "python", api_image,
                 "-c", "from pathlib import Path;Path('/installation/tls.key').chmod(0o644)"])
        failed = subprocess.run(["docker", "run", "--rm", "--pull=never", "--network", "none", "--read-only",
                                 "--cap-drop", "ALL", "-v", volume + ":/installation:ro", image_id],
                                capture_output=True, check=False, timeout=30)
        assert failed.returncode != 0 and b"private_ingress_key_permissions_required" in failed.stderr
        status["missing_cert_root_command_key_permissions"] = "blocked_before_listening"
        status.update(image_id=image_id, uid=10001, read_only_root=True, shared_socket_read_only=True,
                      private_service_network_access=False, host_ports="owned_random_loopback" if frontend_browser else False,
                      frontend="baked_private_assets" if frontend_browser else "not_packaged")
        (reports / "fixed-ingress.json").write_text(json.dumps(status, indent=2) + "\n")
        return status
    except BaseException as error:
        diagnostic = getattr(error, "diagnostic", b"")
        if created_container:
            diagnostic += subprocess.run(["docker", "logs", container], capture_output=True, check=False).stderr
        text = diagnostic.decode(errors="replace")
        for secret in (key.read_text(), probe["password"]):
            text = text.replace(secret, "[REDACTED]")
        (reports / "fixed-ingress-failure.log").write_text(text)
        raise
    finally:
        if created_container:
            subprocess.run(["docker", "rm", "-f", "-v", container], capture_output=True, check=False)
        if created_volume:
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True, check=False)
        if created_network:
            subprocess.run(["docker", "network", "rm", network], capture_output=True, check=False)
        cert.unlink(missing_ok=True);key.unlink(missing_ok=True)
