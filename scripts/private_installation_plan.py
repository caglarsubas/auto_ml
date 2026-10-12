#!/usr/bin/env python3
"""Render a reviewable private application plan from a verified offline image set.

No Docker calls, secret reads, directory initialization or service adoption.
Database/cache/broker provisioning and migration remain operator prerequisites.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath

import private_image_set as image_set
from private_ingress_package import IngressError, authority, configuration

SCHEMA = "private_installation_request_v1"
PLAN_SCHEMA = "private_installation_plan_v3"
MAX_REQUEST = 16_384
FILES = {"request.json", "compose.json", "prerequisites.json", "image-set.json", "ingress.json"}


class PlanError(Exception):
    pass


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def read_bytes(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise PlanError("installation_input_invalid")
        data = stream.read(limit + 1)
    if not 0 < len(data) <= limit:
        raise PlanError("installation_input_budget")
    return data


def decode(data):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise PlanError("installation_duplicate_key")
            value[key] = item
        return value

    try:
        return json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        raise PlanError("installation_json_invalid") from None


def validate_request(value):
    try:
        if not isinstance(value, dict) or set(value) != {
            "schema", "installation_id", "root", "authority", "body_mib", "bind_ip", "database"
        } or value["schema"] != SCHEMA:
            raise ValueError
        name = value["installation_id"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name):
            raise ValueError
        root = value["root"]
        if not isinstance(root, str) or len(root) > 240:
            raise ValueError
        path = PurePosixPath(root)
        # Fixed child layout; no shell/Compose interpolation or path traversal.
        if not path.is_absolute() or path.as_posix() != root or len(path.parts) < 4 or any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", part) or part in {".", ".."}
            for part in path.parts[1:]
        ) or path.parts[1] in {"proc", "sys", "dev", "etc", "bin", "sbin", "usr", "boot"}:
            raise ValueError
        host, port = authority(value["authority"])
        if value["authority"] != (host if port == 443 else f"{host}:{port}"):
            raise ValueError
        if type(value["body_mib"]) is not int or not 1 <= value["body_mib"] <= 64:
            raise ValueError
        address = ipaddress.IPv4Address(value["bind_ip"])
        private = [ipaddress.ip_network(cidr) for cidr in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
        if value["bind_ip"] != str(address) or not any(address in network for network in private):
            raise ValueError
        database = value["database"]
        if not isinstance(database, dict) or set(database) != {"name", "user"} or any(
            not isinstance(item, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", item)
            for item in database.values()
        ) or database["user"] in {"postgres", "root", "admin"} or database["name"] in {"postgres", "template0", "template1"}:
            raise ValueError
    except (ValueError, TypeError, KeyError, IngressError):
        raise PlanError("installation_request_invalid") from None
    return value


def bind_ingress(request, manifest):
    files = manifest["runtime"]["files"]
    names = {name.removeprefix("/opt/declarai/frontend/") for name in files if name.startswith("/opt/declarai/frontend/")}
    config = configuration(request["authority"], request["body_mib"], names).encode()
    if hashlib.sha256(config).hexdigest() != files["/etc/nginx/nginx.conf"]:
        raise PlanError("installation_ingress_configuration_mismatch")


def mounts(root, *, socket=False):
    value = [
        {"type": "bind", "source": root + "/secrets/app", "target": "/installation", "read_only": True, "bind": {"create_host_path": False}},
        {"type": "bind", "source": root + "/artifacts", "target": "/artifacts", "bind": {"create_host_path": False}},
    ]
    if socket:
        value.append({"type": "volume", "source": "api-socket", "target": "/run/declarai", "volume": {"nocopy": True}})
    return value


def composition(request, images, cache_tls=True):
    host, port = authority(request["authority"])
    root, name = request["root"], "declarai-" + request["installation_id"]
    environment = {
        "DECLARAI_RUNTIME_PROFILE": "private", "DJANGO_DEBUG": "false", "DJANGO_TRUST_PROXY_TLS": "true",
        "DJANGO_SECRET_KEY_FILE": "/installation/django-key", "DJANGO_ALLOWED_HOSTS": host,
        "DECLARAI_ALLOWED_ORIGINS": "https://" + request["authority"], "DECLARAI_MEDIA_ROOT": "/artifacts",
        "DECLARAI_DB_ENGINE": "postgresql", "DECLARAI_DB_NAME": request["database"]["name"],
        "DECLARAI_DB_USER": request["database"]["user"], "DECLARAI_DB_HOST": "postgres", "DECLARAI_DB_PORT": "5432",
        "DECLARAI_DB_SSLMODE": "verify-full", "DECLARAI_DB_PASSWORD_FILE": "/installation/app-password",
        "DECLARAI_DB_SSLROOTCERT": "/installation/postgres-ca.crt",
        "DECLARAI_JOB_BROKER_URL_FILE": "/installation/job-broker-url", "DECLARAI_JOB_BROKER_CA_FILE": "/installation/job-ca.crt",
        "REDIS_URL": "redis://cache:6379/0", "PROMETA_DISABLE": "1", "OPENAI_API_KEY": "",
        "LLM_ENGINE_BASE_URL": "http://127.0.0.1:9/v1", "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
    }
    if cache_tls:
        environment.pop("REDIS_URL")
        environment.update(DECLARAI_CACHE_URL_FILE="/installation/cache-url", DECLARAI_CACHE_CA_FILE="/installation/cache-ca.crt")
    services = {}
    for role in ("api", "worker", "dispatcher", "ingress"):
        ingress = role == "ingress"
        service = {
            "image": images["ingress" if ingress else "api"], "pull_policy": "never", "user": "10001:10001",
            "read_only": True, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "cpus": 1 if ingress else 2, "mem_limit": "256m" if ingress else "2g", "pids_limit": 32 if ingress else 256,
            "restart": "on-failure:3", "stop_grace_period": "60s",
            "tmpfs": ["/tmp:rw,noexec,nosuid,size=" + ("268435456" if ingress else "134217728") + ",uid=10001,gid=10001,mode=700"],
            "networks": ["edge" if ingress else "private"],
        }
        if ingress:
            service["ports"] = [{"host_ip": request["bind_ip"], "published": str(port), "target": 8443, "protocol": "tcp"}]
            service["volumes"] = [
                {"type": "bind", "source": root + "/secrets/tls", "target": "/installation", "read_only": True, "bind": {"create_host_path": False}},
                {"type": "volume", "source": "api-socket", "target": "/run/declarai", "read_only": True, "volume": {"nocopy": True}},
            ]
        else:
            service.update(command=[role], environment=environment.copy(), volumes=mounts(root, socket=role == "api"))
        services[role] = service
    return {
        "name": name, "services": services,
        "networks": {key: {"external": True, "name": name + "-" + key} for key in ("private", "edge")},
        "volumes": {"api-socket": {"external": True, "name": name + "-socket"}},
    }


def prerequisites(request, images, legacy=False, cache_tls=True):
    root, name = request["root"], "declarai-" + request["installation_id"]
    return {
        "schema": "private_installation_prerequisites_v1" if legacy else ("private_installation_prerequisites_v3" if cache_tls else "private_installation_prerequisites_v2"),
        "scope": "native_application_layer_with_operator_managed_dependencies",
        "directories": [
            {"path": root + "/secrets/app", "uid": 10001, "gid": 10001, "mode": "0700", "mount": "read_only"},
            {"path": root + "/secrets/tls", "uid": 10001, "gid": 10001, "mode": "0700", "mount": "read_only"},
            {"path": root + "/artifacts", "uid": 10001, "gid": 10001, "mode": "0700", "mount": "read_write", "encrypted_storage_required": True},
        ],
        "secret_files": {"app": ["django-key", "app-password", "job-broker-url", "postgres-ca.crt", "job-ca.crt"] + (["cache-url", "cache-ca.crt"] if cache_tls else []), "tls": ["tls.crt", "tls.key"]},
        "secret_file_identity": {"uid": 10001, "gid": 10001, "mode": "0400", "regular_no_links": True},
        "networks": [{"name": name + "-" + key, "driver": "bridge", "internal": legacy or key == "private", "dedicated_installation": request["installation_id"]} for key in ("private", "edge")],
        "socket_volume": {"name": name + "-socket", "uid": 10001, "gid": 10001, "mode": "0750", "dedicated_installation": request["installation_id"]},
        "dependencies": {
            "postgres": {"image_id": images["postgres"], "alias": "postgres", "port": 5432, "tls": "verify-full", "database": request["database"], "application_superuser": False, "migrations": "approved_explicit_step"},
            "job_broker": {"image_id": images["redis"], "alias": "job-broker", "port": 6379, "tls": "required", "authentication": "required", "dedicated": True},
            "cache": {"image_id": images["redis"], "alias": "cache", "port": 6379, "network": name + "-private", "reconstructible": True, "dedicated": True, **({"tls": "verify-full", "authentication": "required", "credential_source": "cache-url", "selected_ca": "cache-ca.crt"} if cache_tls else {})},
        },
        "operator_checks": ["Certificate trust, validity, key pairing and ingress/server names", "Approved secret-manager delivery and broker URL", "Encrypted storage, capacity, backup and retention policy", "Non-superuser database grants, current migrations and attributable account/project enrollment", "Dedicated internal service networks, socket ownership and host firewall", "PostgreSQL and dedicated TLS Redis initialization and supervision", "Runtime preflight, HTTPS sign-in, task completion and recovery qualification"],
        "installation_qualified": False, "release_qualified": False, "expert_isolation_qualified": False,
    }


def render(request_path, directory, expected, destination):
    request = validate_request(decode(read_bytes(request_path, MAX_REQUEST)))
    if destination.exists() or destination.is_symlink():
        raise PlanError("installation_destination_exists")
    if not isinstance(expected, str) or not image_set.HEX.fullmatch(expected):
        raise PlanError("installation_trusted_image_set_digest_required")
    with tempfile.TemporaryDirectory(prefix="declarai-plan-images-") as temp:
        stage = Path(temp)
        image_set.snapshot(directory, stage)
        value = image_set.verify_staged(stage, expected)
        ingress = image_set.read_record(stage / "ingress/manifest.json")
        bind_ingress(request, ingress)
        images = {key: component["image_id"] for key, component in value["components"].items()}
        files = {"request.json": encoded(request), "compose.json": encoded(composition(request, images)), "prerequisites.json": encoded(prerequisites(request, images)), "image-set.json": (stage / "manifest.json").read_bytes(), "ingress.json": (stage / "ingress/manifest.json").read_bytes()}
    manifest = {
        "schema": PLAN_SCHEMA, "installation_id": request["installation_id"],
        "image_set_manifest_sha256": expected, "architecture": value["architecture"],
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "scope": "native_application_layer_with_operator_managed_dependencies", "archive_verified_at_render": True,
        "installation_qualified": False, "release_qualified": False, "expert_isolation_qualified": False,
    }
    # Validate every input before publishing any plan. A 0700 directory contains
    # only nonsecret metadata. No installation path or Docker object is touched.
    with tempfile.TemporaryDirectory(prefix="declarai-plan-output-", dir=destination.parent) as temp:
        output = Path(temp) / "plan"
        output.mkdir(mode=0o700)
        for name, data in {**files, "manifest.json": encoded(manifest)}.items():
            (output / name).write_bytes(data)
            (output / name).chmod(0o600)
        # Refuse observed existing destinations. Publish completed nonempty
        # directories atomically; concurrent successful renders cannot replace
        # each other's nonempty output. Use a trusted operator output parent.
        if destination.exists() or destination.is_symlink():
            raise PlanError("installation_destination_exists")
        output.rename(destination)
    return {"plan_manifest_sha256": hashlib.sha256(encoded(manifest)).hexdigest(), "images": images, "architecture": value["architecture"], "installation_qualified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("image_set", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--expected-image-set-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.request, args.image_set, args.expected_image_set_sha256, args.destination.absolute())))


if __name__ == "__main__":
    try:
        main()
    except (PlanError, image_set.api.PackageError, OSError, ValueError, UnicodeError) as error:
        print(str(error) if isinstance(error, (PlanError, image_set.api.PackageError)) else "installation_plan_io_failed", file=sys.stderr)
        sys.exit(1)
