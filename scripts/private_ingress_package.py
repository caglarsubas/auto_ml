#!/usr/bin/env python3
"""Build a fixed private TLS ingress from an exact trusted local NGINX image.

Build runs online only when the operator separately acquires dependencies.
Runtime has no templates, supplied commands or network dependency resolution.
"""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.30.5"
HEADERS = (
    "Accept", "Accept-Language", "Authorization", "Cache-Control", "Content-Type",
    "Cookie", "Origin", "Referer", "X-CSRFToken", "Range",
    "If-None-Match", "If-Modified-Since", "If-Range",
)


class IngressError(RuntimeError):
    pass


def authority(value):
    if not isinstance(value, str) or len(value) > 253:
        raise IngressError("private_ingress_authority_invalid")
    host, separator, raw_port = value.partition(":")
    labels = host.split(".")
    if len(labels) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels):
        raise IngressError("private_ingress_authority_invalid")
    if separator and (not re.fullmatch(r"[1-9][0-9]{0,4}", raw_port) or not 1 <= int(raw_port) <= 65535):
        raise IngressError("private_ingress_authority_invalid")
    return host, int(raw_port) if separator else 443


def configuration(public_authority, body_mib=50):
    host, port = authority(public_authority)
    if type(body_mib) is not int or not 1 <= body_mib <= 64:
        raise IngressError("private_ingress_body_limit_invalid")
    canonical = host if port == 443 else f"{host}:{port}"
    host_pattern = host.replace(".", r"\.") + (r"(?::443)?" if port == 443 else f":{port}")
    forwarded = "\n".join(
        f"            proxy_set_header {name} $http_{name.lower().replace('-', '_')};" for name in HEADERS
    )
    proxy = f"""
            proxy_pass http://unix:/run/declarai/api.sock;
            proxy_http_version 1.1;
            proxy_pass_request_headers off;
            proxy_set_header Host {canonical};
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header Connection "";
{forwarded}
            proxy_request_buffering on;
            proxy_buffering on;
            proxy_max_temp_file_size 0;
            proxy_buffer_size 16k;
            proxy_buffers 8 16k;
            proxy_connect_timeout 5s;
            proxy_send_timeout 120s;
            proxy_read_timeout 120s;
            proxy_next_upstream off;
            proxy_cache off;
            proxy_ignore_headers X-Accel-Buffering X-Accel-Redirect;
            proxy_hide_header Strict-Transport-Security;
            proxy_hide_header X-Content-Type-Options;
            proxy_hide_header X-Accel-Redirect;
"""
    return f"""# Fixed private API ingress; generated from validated installation authority.
worker_processes 1;
pid /tmp/nginx.pid;
error_log /dev/stderr crit;
events {{ worker_connections 128; }}
http {{
    access_log off;
    server_tokens off;
    client_body_temp_path /tmp/client;
    proxy_temp_path /tmp/proxy;
    fastcgi_temp_path /tmp/fastcgi;
    uwsgi_temp_path /tmp/uwsgi;
    scgi_temp_path /tmp/scgi;
    client_max_body_size {body_mib}m;
    client_body_buffer_size 64k;
    client_header_timeout 15s;
    client_body_timeout 30s;
    send_timeout 30s;
    keepalive_timeout 15s;
    keepalive_requests 100;
    reset_timedout_connection on;
    underscores_in_headers off;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_tickets off;
    ssl_session_cache off;
    map $http_host $accepted_host {{ default 0; ~^{host_pattern}$ 1; }}
    server {{
        listen 8443 ssl default_server;
        ssl_reject_handshake on;
        return 421;
    }}
    server {{
        listen 8443 ssl;
        server_name {host};
        ssl_certificate /installation/tls.crt;
        ssl_certificate_key /installation/tls.key;
        if ($accepted_host = 0) {{ return 421; }}
        if ($ssl_server_name != {host}) {{ return 421; }}
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options nosniff always;
        location /api/ {{
{proxy}        }}
        # Never map protected media to a filesystem alias or X-Accel redirect.
        location /media/ {{
{proxy}        }}
        location / {{ return 404; }}
    }}
}}
"""


def context(destination, public_authority, body_mib=50, root=ROOT):
    config = configuration(public_authority, body_mib)
    files = {"nginx.conf": config.encode()}
    for source, target in (("private-ingress.Dockerfile", "Dockerfile"), ("private-ingress-entrypoint.sh", "start-ingress.sh")):
        path = root / "docker" / source
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            raise IngressError("private_ingress_source_invalid")
        files[target] = path.read_bytes()
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise IngressError("private_ingress_destination_exists")
    destination.mkdir(parents=False, mode=0o700)
    for name, data in files.items():
        (destination / name).write_bytes(data)
    receipt = {"schema": "private_tls_ingress_v1", "nginx_version": VERSION,
               "authority": public_authority, "body_mib": body_mib,
               "source_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    (destination / "source-manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def run(argv, timeout=120):
    result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise IngressError("private_ingress_command_failed")
    return result.stdout


def build(base, tag, public_authority, body_mib=50):
    configuration(public_authority, body_mib)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", base):
        raise IngressError("private_ingress_exact_base_required")
    if not re.fullmatch(r"declarai-private-ingress:[a-z0-9][a-z0-9_.-]{0,63}", tag):
        raise IngressError("private_ingress_owned_tag_required")
    if subprocess.run(["docker", "image", "inspect", tag], capture_output=True, check=False).returncode == 0:
        raise IngressError("private_ingress_tag_exists")
    info = json.loads(run(["docker", "image", "inspect", base]))[0]
    if info["Id"] != base or info["Os"] != "linux":
        raise IngressError("private_ingress_base_identity_invalid")
    # NGINX reports its version on stderr; the shell program is a fixed literal.
    version = run(["docker", "run", "--rm", "--pull=never", "--network", "none", "--read-only", "--cap-drop", "ALL",
                   "--entrypoint", "sh", base, "-c", "nginx -v 2>&1"]).strip()
    if version != f"nginx version: nginx/{VERSION}".encode():
        raise IngressError("private_ingress_version_rejected")
    temporary = "declarai-ingress-base:" + uuid.uuid4().hex
    run(["docker", "tag", base, temporary])
    try:
        with tempfile.TemporaryDirectory(prefix="declarai-ingress-build-") as directory:
            receipt = context(Path(directory) / "context", public_authority, body_mib)
            run(["docker", "build", "--provenance=false", "--network=none", "--build-arg", "NGINX_IMAGE=" + temporary,
                 "-t", tag, str(Path(directory) / "context")], timeout=600)
    finally:
        run(["docker", "image", "rm", temporary])
    built = json.loads(run(["docker", "image", "inspect", tag]))[0]
    if built["Config"]["User"] != "10001:10001" or built["Config"]["Entrypoint"] != ["/bin/sh", "/opt/declarai/start-ingress.sh"]:
        raise IngressError("private_ingress_built_configuration_invalid")
    receipt.update(image_id=built["Id"], base_image_id=base, architecture=built["Architecture"])
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("context", "build"):
        command = sub.add_parser(name)
        command.add_argument("--authority", required=True)
        command.add_argument("--body-mib", type=int, default=50)
        if name == "context":
            command.add_argument("destination", type=Path)
        else:
            command.add_argument("--base-image", required=True)
            command.add_argument("--tag", required=True)
    args = parser.parse_args()
    try:
        receipt = (context(args.destination, args.authority, args.body_mib) if args.action == "context"
                   else build(args.base_image, args.tag, args.authority, args.body_mib))
    except (IngressError, OSError, subprocess.TimeoutExpired):
        parser.exit(1, "Private ingress preparation failed.\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
