"""Owned fixed-image Unix API smoke within the disposable PostgreSQL fixture.

No host ports/source mounts. The probe stands in for a trusted local ingress;
it does not qualify a TLS proxy, frontend, production capacity or expert code.
"""

import json
import os
import re
import secrets
import subprocess
import uuid
from pathlib import Path


class PrivateCheckFailed(RuntimeError):
    def __init__(self, diagnostic):
        super().__init__("Disposable private API check failed.")
        self.diagnostic = diagnostic


def command(argv, *, data=None, timeout=120):
    result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise PrivateCheckFailed(result.stdout + result.stderr)
    return result.stdout


PREPARE = r"""
import json,os,sys
from pathlib import Path
value=json.load(sys.stdin)
root=Path('/installation');os.chown(root,0,0)
root.chmod(0o700)
for name,text in value.items():
    file=root/name
    file.write_text(text);file.chmod(0o400);os.chown(file,10001,10001)
media=Path('/artifacts');os.chown(media,0,0);media.chmod(0o700);os.chown(media,10001,10001)
os.chown(root,10001,10001)
socket=Path('/run/declarai');os.chown(socket,0,0);socket.chmod(0o750);os.chown(socket,10001,10001)
"""

SEED = r"""
import json,os,sys,uuid
os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
import django;django.setup()
from django.conf import settings
from django.db import connection
assert settings.DECLARAI_RUNTIME_PROFILE=='private' and settings.DATABASES['default']['NAME']=='declarai_fixture'
with connection.cursor() as cursor:
    cursor.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()');assert cursor.fetchone()[0]
from django.contrib.auth import get_user_model
from access_control.projects import operator_change
value=json.load(sys.stdin)
actor=get_user_model().objects.create_user(username=value['username'],password=value['password'])
assert not actor.is_superuser and not actor.is_staff
operator_change({'operation':'create','name':'Disposable fixed API project','user':actor.username},uuid.uuid4(),'disposable-fixed-api')
"""

PROBE = r"""
import http.client,json,socket,stat,sys,time
from http.cookies import SimpleCookie
from pathlib import Path
value=json.load(sys.stdin);cookies=SimpleCookie()
class Local(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(self.timeout)
        self.sock.connect('/run/declarai/api.sock')
def request(method,path,body=None,**options):
    headers={'Host':'api.private.test','X-Forwarded-Proto':'https'}
    headers.update(options)
    if cookies:headers['Cookie']='; '.join(k+'='+m.value for k,m in cookies.items())
    if body is not None:body=json.dumps(body);headers['Content-Type']='application/json'
    connection=Local('api.private.test',timeout=10)
    try:
        connection.request(method,path,body=body,headers=headers);response=connection.getresponse()
        data=response.read();result=(response.status,dict(response.getheaders()),data)
        for name,content in response.getheaders():
            if name.lower()=='set-cookie':cookies.load(content)
        return result
    finally:connection.close()
deadline=time.monotonic()+60
while True:
    try:status,headers,data=request('GET','/api/auth/session/');break
    except (OSError,http.client.HTTPException):
        if time.monotonic()>deadline:raise
        time.sleep(0.25)
assert status==200 and not json.loads(data)['authenticated']
assert cookies['csrftoken']['secure'] and headers['Cache-Control']=='no-store'
assert request('GET','/api/projects/')[0]==403
assert request('GET','/api/auth/session/',**{'X-Forwarded-Proto':'http','X-Forwarded-Ssl':'on'})[0]==301
assert request('GET','/api/auth/session/',**{'Host':'unrelated.private.test'})[0]==400
credentials={'username':value['username'],'password':value['password']}
assert request('POST','/api/auth/login/',credentials)[0]==403
csrf=json.loads(request('GET','/api/auth/session/')[2])['csrf_token']
status,headers,data=request('POST','/api/auth/login/',credentials,**{'Origin':'https://console.private.test','X-CSRFToken':csrf})
assert status==200 and json.loads(data)['authenticated']
assert cookies['sessionid']['secure'] and cookies['sessionid']['httponly']
status,headers,data=request('GET','/api/projects/');assert status==200
assert request('GET','/media/unassigned.csv')[0]==403
csrf=json.loads(request('GET','/api/auth/session/')[2])['csrf_token']
assert request('POST','/api/auth/logout/',{},**{'Origin':'https://console.private.test','X-CSRFToken':csrf})[0]==200
assert request('GET','/api/projects/')[0]==403
mode=Path('/run/declarai/api.sock').stat().st_mode
assert stat.S_ISSOCK(mode) and stat.S_IMODE(mode)==0o770
print(json.dumps({'actual_wsgi_session_csrf':'passed','secure_cookies':'passed','canonical_proxy_header':'passed','host_allowlist':'passed','protected_projects_and_media':'passed','recorded_logout':'passed','local_socket_permissions':'passed'}))
"""


def qualify_image(image_id, network, fixture, env, reports):
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
        or env.get("DECLARAI_TEST_INSTALLATION") != "1"
        or env.get("DECLARAI_RUNTIME_PROFILE") != "private"
        or env.get("DECLARAI_DB_NAME") != "declarai_fixture"
        or not network.startswith("declarai-fixture-")
    ):
        raise RuntimeError("Requires the owning disposable private fixture.")
    token = uuid.uuid4().hex[:12]
    prefix = "declarai-fixed-api-" + token
    container, installation, sockets, artifacts = (
        prefix + "-api",
        prefix + "-installation",
        prefix + "-socket",
        prefix + "-artifacts",
    )
    volumes, containers = [], []
    values = {
        "django-key": Path(env["DJANGO_SECRET_KEY_FILE"]).read_text(),
        "app-password": Path(env["DECLARAI_DB_PASSWORD_FILE"]).read_text(),
        "server.crt": Path(env["DECLARAI_DB_SSLROOTCERT"]).read_text(),
        "job-server.crt": (fixture / "job-server.crt").read_text(),
        "job-broker-url": (fixture / "job-broker-url").read_text(),
    }
    # The owning host fixture may use loopback forwards. Fixed containers use
    # the same TLS-verified service aliases on their existing owned network.
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(values["job-broker-url"])
    values["job-broker-url"] = urlunsplit(
        (parsed.scheme, ":" + parsed.password + "@job-broker:6379", parsed.path, "", "")
    )
    private = {
        "DECLARAI_RUNTIME_PROFILE": "private",
        "DECLARAI_TEST_INSTALLATION": "1",
        "DJANGO_DEBUG": "false",
        "DJANGO_TRUST_PROXY_TLS": "true",
        "DJANGO_SECRET_KEY_FILE": "/installation/django-key",
        "DJANGO_ALLOWED_HOSTS": "api.private.test",
        "DECLARAI_ALLOWED_ORIGINS": "https://console.private.test",
        "DECLARAI_MEDIA_ROOT": "/artifacts",
        "DECLARAI_DB_ENGINE": "postgresql",
        "DECLARAI_DB_NAME": "declarai_fixture",
        "DECLARAI_DB_USER": "declarai_fixture_app",
        "DECLARAI_DB_HOST": "postgres",
        "DECLARAI_DB_PORT": "5432",
        "DECLARAI_DB_SSLMODE": "verify-full",
        "DECLARAI_DB_PASSWORD_FILE": "/installation/app-password",
        "DECLARAI_DB_SSLROOTCERT": "/installation/server.crt",
        "DECLARAI_JOB_BROKER_URL_FILE": "/installation/job-broker-url",
        "DECLARAI_JOB_BROKER_CA_FILE": "/installation/job-server.crt",
        "REDIS_URL": env["REDIS_URL"]
        if "localhost" not in env["REDIS_URL"]
        else "redis://" + network.removesuffix("net") + "redis:6379/0",
    }
    env_file = fixture / "fixed-api.env"
    env_file.write_text("".join(name + "=" + value + "\n" for name, value in private.items()))
    env_file.chmod(0o600)
    probe = {"username": "fixed-api-" + token, "password": secrets.token_urlsafe(32)}
    try:
        for volume in (installation, sockets, artifacts):
            command(["docker", "volume", "create", volume])
            volumes.append(volume)
        command(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--read-only",
                "--user",
                "0:0",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "CHOWN",
                "--security-opt",
                "no-new-privileges",
                "-v",
                installation + ":/installation",
                "-v",
                artifacts + ":/artifacts",
                "-v",
                sockets + ":/run/declarai",
                "--entrypoint",
                "python",
                image_id,
                "-c",
                PREPARE,
            ],
            data=json.dumps(values).encode(),
        )
        command(
            [
                "docker",
                "create",
                "--name",
                container,
                "--network",
                network,
                "--read-only",
                "--cpus",
                "2",
                "--memory",
                "2g",
                "--pids-limit",
                "256",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=134217728,uid=10001,gid=10001",
                "--env-file",
                str(env_file),
                "-v",
                installation + ":/installation:ro",
                "-v",
                artifacts + ":/artifacts",
                "-v",
                sockets + ":/run/declarai",
                image_id,
            ]
        )
        containers.append(container)
        command(["docker", "start", container])
        command(["docker", "exec", "-i", container, "python", "-c", SEED], data=json.dumps(probe).encode())
        output = command(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "-v",
                sockets + ":/run/declarai:ro",
                "--entrypoint",
                "python",
                image_id,
                "-c",
                PROBE,
            ],
            data=json.dumps(probe).encode(),
        )
        status = json.loads(output)
        info = json.loads(command(["docker", "inspect", container]))[0]
        assert info["Config"]["User"] == "10001:10001" and info["HostConfig"]["ReadonlyRootfs"]
        assert not info["NetworkSettings"]["Ports"] and not info["HostConfig"]["Privileged"]
        assert all(
            m["Type"] != "bind" and m["Destination"] in ("/installation", "/artifacts", "/run/declarai", "/tmp")
            for m in info["Mounts"]
        )
        assert {m["Destination"] for m in info["Mounts"]}.issuperset({"/installation", "/artifacts", "/run/declarai"})
        assert next(m for m in info["Mounts"] if m["Destination"] == "/installation")["RW"] is False
        assert set(info["HostConfig"]["Tmpfs"]) == {"/tmp"}
        status.update(
            {
                "image_id": image_id,
                "source_mounts": False,
                "public_ports": False,
                "read_only_root": True,
                "uid": 10001,
                "native_runtime_inventory": "verified_before_launch",
                "actual_tls_ingress": "not_qualified",
            }
        )
        (reports / "fixed-api.json").write_text(json.dumps(status, indent=2) + "\n")
        return status
    except BaseException as error:
        # Retain diagnostic text only after stripping every generated secret.
        redactions = [
            *values.values(),
            probe["password"],
            parsed.password,
            Path(env["DECLARAI_DB_PASSWORD_FILE"]).read_text().strip(),
            Path(env["DJANGO_SECRET_KEY_FILE"]).read_text().strip(),
        ]
        diagnostic = (
            getattr(error, "diagnostic", b"")
            + subprocess.run(["docker", "logs", container], capture_output=True, check=False).stderr
        ).decode(errors="replace")
        for value in redactions:
            if value:
                diagnostic = diagnostic.replace(value, "[REDACTED]")
        (reports / "fixed-api-failure.log").write_text(diagnostic)
        raise
    finally:
        for name in containers:
            # Failure logs stay outside release evidence; never copy installation
            # secrets, session-bearing probe state or fixture data into reports.
            subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True, check=False)
        for name in volumes:
            subprocess.run(["docker", "volume", "rm", name], capture_output=True, check=False)
        env_file.unlink(missing_ok=True)
