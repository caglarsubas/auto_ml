#!/usr/bin/env python3
"""Prepare fresh, bound dependency storage and delivered TLS credentials.

Linux root only. Never generate credentials, touch an existing dependency root,
contact Docker, initialize a database, run migrations or start a service.
"""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import unquote_to_bytes, urlsplit

import private_installation_resources as resources

checker = resources.checker
initializer = resources.initializer
DELIVERY = {"postgres": ["server.crt", "server.key", "owner-password"], "job-broker": ["server.crt", "server.key"], "cache": ["server.crt", "server.key"]}
IDENTITY = {"postgres": (70, 70), "job-broker": (999, 1000), "cache": (999, 1000)}


def profile(value, expected, identifier):
    root = value["request"]["root"] + "/dependencies"
    result = {
        "schema": "private_dependency_profile_v3",
        "plan_manifest_sha256": expected,
        "initialization_id": identifier,
        "installation_id": value["request"]["installation_id"],
        "root": root,
        "private_network": value["prerequisites"]["networks"][0]["name"],
        "database": value["request"]["database"],
        "services": {
            role: {
                "image_id": value["images"]["postgres" if role == "postgres" else "redis"],
                "uid": uid,
                "gid": gid,
                "config": root + "/" + role + "/config",
                "data": root + "/" + role + "/data" if role != "cache" else None,
                "public_ports": False,
                "read_only_root": True,
                "capabilities": [],
                "no_new_privileges": True,
            }
            for role, (uid, gid) in IDENTITY.items()
        },
        "supported_image_accounts": "postgres_70_70_and_redis_999_1000_verified_before_start",
        "installation_qualified": False,
        "release_qualified": False,
        "expert_isolation_qualified": False,
    }
    for role, service in result["services"].items():
        uid, gid = IDENTITY[role]
        postgres = role == "postgres"
        service.update(
            entrypoint=["docker-entrypoint.sh"],
            command=[
                "postgres",
                "-c",
                "ssl=on",
                "-c",
                "ssl_min_protocol_version=TLSv1.2",
                "-c",
                "ssl_cert_file=/installation/server.crt",
                "-c",
                "ssl_key_file=/installation/server.key",
                "-c",
                "hba_file=/installation/pg_hba.conf",
                "-c",
                "password_encryption=scram-sha-256",
                "-c",
                "log_min_error_statement=panic",
                "-c",
                "log_statement=none",
                "-c",
                "log_error_verbosity=terse",
                "-c",
                "listen_addresses=*",
            ]
            if postgres
            else ["redis-server", "/installation/redis.conf"],
            environment={
                "PGDATA": "/var/lib/postgresql/data",
                "POSTGRES_USER": "postgres",
                "POSTGRES_DB": "postgres",
                "POSTGRES_PASSWORD_FILE": "/installation/owner-password",
                "POSTGRES_INITDB_ARGS": "--auth-local=peer --auth-host=scram-sha-256",
            }
            if postgres
            else {},
            cpus=2 if postgres else 1,
            memory_bytes=2 * 1024**3 if postgres else 512 * 1024**2 if role == "job-broker" else 128 * 1024**2,
            pids=128 if postgres else 64,
            restart={"Name": "on-failure", "MaximumRetryCount": 3},
            stop_timeout=60,
            tmpfs={"/tmp": f"rw,noexec,nosuid,size=16777216,uid={uid},gid={gid},mode=700"},
            mounts=[{"source": service["config"], "target": "/installation", "read_only": True}],
            configuration_recipe="private_dependency_configuration_v2",
        )
        if postgres:
            service["tmpfs"]["/var/run/postgresql"] = "rw,noexec,nosuid,size=16777216,uid=70,gid=70,mode=700"
        if role == "cache":
            service["tmpfs"]["/data"] = "rw,noexec,nosuid,size=67108864,uid=999,gid=1000,mode=700"
        else:
            service["mounts"].append(
                {
                    "source": service["data"],
                    "target": "/var/lib/postgresql/data" if postgres else "/data",
                    "read_only": False,
                }
            )
    return result


def capture(path, groups, root_identity=(10001, 10001, 0o700)):
    if not path.is_absolute() or ".." in path.parts:
        raise checker.planner.PlanError("dependency_delivery_path_invalid")
    root = checker.open_directory(path)
    result = {}
    try:
        info = os.fstat(root)
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != root_identity:
            raise checker.planner.PlanError("dependency_delivery_identity_invalid")
        checker.no_directory_acl(root)
        if set(os.listdir(root)) != set(groups):
            raise checker.planner.PlanError("dependency_delivery_members_invalid")
        for group, members in groups.items():
            fd = os.open(group, initializer.DIRECTORY_FLAGS, dir_fd=root)
            try:
                initializer.check_directory(fd)
                if set(os.listdir(fd)) != set(members):
                    raise checker.planner.PlanError("dependency_delivery_members_invalid")
                for name in members:
                    source = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=fd)
                    with os.fdopen(source, "rb") as stream:
                        before = os.fstat(stream.fileno())
                        budget = 65536 if name.endswith((".crt", ".key")) else 4096
                        if (
                            not stat.S_ISREG(before.st_mode)
                            or before.st_nlink != 1
                            or (before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode)) != (10001, 10001, 0o400)
                            or not 0 < before.st_size <= budget
                        ):
                            raise checker.planner.PlanError("dependency_delivery_file_invalid")
                        checker.no_directory_acl(stream.fileno())
                        data = stream.read(budget + 1)
                        stream.seek(0)
                        repeated = stream.read(budget + 1)
                        after = os.fstat(stream.fileno())
                        fields = ("st_dev", "st_ino", "st_size", "st_mode", "st_uid", "st_gid", "st_nlink", "st_mtime_ns", "st_ctime_ns")
                        if data != repeated or len(data) != before.st_size or any(getattr(before, key) != getattr(after, key) for key in fields):
                            raise checker.planner.PlanError("dependency_delivery_file_changed")
                        checker.no_directory_acl(stream.fileno())
                        result[group + "/" + name] = data
            finally:
                os.close(fd)
    finally:
        os.close(root)
    return result


def password(data, *, strip_file_newlines=True):
    try:
        value = data.decode("utf-8")
        if strip_file_newlines:
            value = value.rstrip("\r\n")
        if len(value) < 32 or len(set(value)) < 5 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError
    except (UnicodeError, ValueError):
        raise checker.planner.PlanError("dependency_password_invalid") from None
    return value


def broker_password(data, host="job-broker", database=None):
    try:
        url = data.decode("utf-8").rstrip("\r\n")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "rediss"
            or parsed.hostname != host
            or parsed.port != 6379
            or parsed.username not in (None, "")
            or not parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"/" + str(n) for n in range(16)}
            or (database is not None and parsed.path != "/" + str(database))
            or any(c.isspace() for c in url)
        ):
            raise ValueError
        if resources.re.search(r"%(?![a-fA-F0-9]{2})", parsed.password):
            raise ValueError
        return password(unquote_to_bytes(parsed.password), strip_file_newlines=False)
    except (UnicodeError, ValueError):
        raise checker.planner.PlanError("dependency_" + ("cache" if host == "cache" else "broker") + "_url_invalid") from None


def configurations(value, app):
    db = value["request"]["database"]
    password(app["app/app-password"])
    secret = broker_password(app["app/job-broker-url"]).replace("\\", "\\\\").replace('"', '\\"')
    cache_secret = broker_password(app["app/cache-url"], "cache", 0)
    if cache_secret == broker_password(app["app/job-broker-url"]):
        raise checker.planner.PlanError("dependency_cache_broker_credentials_must_differ")
    cache_secret = cache_secret.replace("\\", "\\\\").replace('"', '\\"')
    hba = (
        "local all postgres peer\nlocal all all reject\n"
        + 'hostssl "'
        + db["name"]
        + '" "'
        + db["user"]
        + '" 0.0.0.0/0 scram-sha-256\n'
        + "host all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n"
    )
    common = 'bind 0.0.0.0\nrename-command CONFIG ""\nrename-command DEBUG ""\nrename-command MODULE ""\n'
    broker = (
        common
        + "protected-mode yes\n"
        + (
            "port 0\ntls-port 6379\ntls-cert-file /installation/server.crt\n"
            "tls-key-file /installation/server.key\ntls-ca-cert-file /installation/server-ca.crt\n"
            'tls-protocols "TLSv1.2 TLSv1.3"\ntls-auth-clients no\ndatabases 16\n'
            'dir /data\nappendonly yes\nappendfsync everysec\nsave ""\n'
            'maxmemory 384mb\nmaxmemory-policy noeviction\nrequirepass "' + secret + '"\n'
        )
    )
    cache = (
        common
        + 'protected-mode yes\nport 0\ntls-port 6379\n'
        + 'tls-cert-file /installation/server.crt\ntls-key-file /installation/server.key\n'
        + 'tls-ca-cert-file /installation/server-ca.crt\ntls-protocols "TLSv1.2 TLSv1.3"\ntls-auth-clients no\n'
        + 'databases 1\ndir /data\nappendonly no\nsave ""\nmaxmemory 96mb\nmaxmemory-policy allkeys-lru\n'
        + 'requirepass "' + cache_secret + '"\n'
    )
    return {
        "postgres/pg_hba.conf": hba.encode(),
        "job-broker/redis.conf": broker.encode(),
        "cache/redis.conf": cache.encode(),
    }


def certificates(delivered, app):
    with tempfile.TemporaryDirectory(prefix="declarai-dependency-tls-") as temporary:
        parent = Path(temporary)
        for role, ca in [("postgres", "postgres-ca.crt"), ("job-broker", "job-ca.crt"), ("cache", "cache-ca.crt")]:
            paths = {name: parent / name for name in ["server.crt", "server.key", "ca.crt"]}
            for name, path in paths.items():
                path.write_bytes(app["app/" + ca] if name == "ca.crt" else delivered[role + "/" + name])
                path.chmod(0o600)

            def openssl(args):
                try:
                    result = subprocess.run(
                        ["/usr/bin/openssl", *args],
                        capture_output=True,
                        timeout=15,
                        check=False,
                        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                        cwd=parent,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    raise checker.planner.PlanError("dependency_certificate_validation_unavailable") from None
                if result.returncode or len(result.stdout) > 65536:
                    raise checker.planner.PlanError("dependency_certificate_invalid")
                return result.stdout

            openssl(
                [
                    "verify",
                    "-no-CApath",
                    "-no-CAstore",
                    "-CAfile",
                    str(paths["ca.crt"]),
                    "-untrusted",
                    str(paths["server.crt"]),
                    "-purpose",
                    "sslserver",
                    "-verify_hostname",
                    role,
                    str(paths["server.crt"]),
                ]
            )
            public = openssl(["x509", "-in", str(paths["server.crt"]), "-pubkey", "-noout"])
            if public != openssl(["pkey", "-in", str(paths["server.key"]), "-passin", "pass:", "-pubout"]):
                raise checker.planner.PlanError("dependency_certificate_key_mismatch")


def initialize(plan, expected, source):
    value = checker.verify(plan, expected)
    if value["manifest"]["schema"] != checker.planner.PLAN_SCHEMA:
        raise checker.planner.PlanError("dependency_v3_plan_required")
    if sys.platform != "linux" or os.geteuid() != 0:
        raise checker.planner.PlanError("dependency_linux_root_required")
    initialized = resources.initialization(value)
    if initialized["plan_manifest_sha256"] != expected:
        raise checker.planner.PlanError("dependency_initialization_plan_mismatch")
    checker.check_paths(plan, expected)
    root = initializer.trusted_directory(Path(value["request"]["root"]))
    stage = ".declarai-dependencies-" + uuid.uuid4().hex
    staged = False
    try:
        initializer.absent(root, "dependencies")  # Before any secret capture.
        app = capture(
            Path(value["request"]["root"]) / "secrets", value["prerequisites"]["secret_files"], (0, 10001, 0o750)
        )
        delivered = capture(source, DELIVERY)
        password(delivered["postgres/owner-password"])
        configs = configurations(value, app)
        certificates(delivered, app)
        spec = profile(value, expected, initialized["initialization_id"])
        digest = hashlib.sha256(checker.planner.encoded(spec)).hexdigest()
        receipt = {
            "schema": "private_dependency_initialization_v1",
            "plan_manifest_sha256": expected,
            "initialization_id": initialized["initialization_id"],
            "dependency_initialization_id": stage.removeprefix(".declarai-dependencies-"),
            "dependency_profile_sha256": digest,
            "delivered_files": 7,
            "certificate_chain_hostname_and_key": "verified_at_initialization",
            "secret_values_or_hashes_emitted": False,
            "dependency_filesystem_initialized": True,
            "dependencies_started": False,
            "database_initialized": False,
            "migrations_applied": False,
            "installation_qualified": False,
            "release_qualified": False,
            "expert_isolation_qualified": False,
            "encrypted_storage_verified": False,
        }
        os.mkdir(stage, mode=0o700, dir_fd=root)
        staged = True
        fd = os.open(stage, initializer.DIRECTORY_FLAGS, dir_fd=root)
        try:
            os.fchown(fd, 0, 0)
            os.fchmod(fd, 0o700)
            for role, (uid, gid) in IDENTITY.items():
                child = initializer.directory(fd, role, 0, gid, 0o750)
                try:
                    config = initializer.directory(child, "config", 0, gid, 0o750)
                    try:
                        files = {
                            name.split("/", 1)[1]: data
                            for name, data in {**delivered, **configs}.items()
                            if name.startswith(role + "/")
                        }
                        if role in ("job-broker", "cache"):
                            files["server-ca.crt"] = app["app/job-ca.crt" if role == "job-broker" else "app/cache-ca.crt"]
                        for name, data in files.items():
                            initializer.write_file(config, name, data, 0, gid, 0o440)
                        os.fsync(config)
                    finally:
                        os.close(config)
                    if role != "cache":
                        data = initializer.directory(child, "data", uid, gid, 0o700)
                        os.fsync(data)
                        os.close(data)
                    os.fsync(child)
                finally:
                    os.close(child)
            initializer.write_file(fd, "profile.json", checker.planner.encoded(spec), 0, 0, 0o600)
            initializer.write_file(fd, "initialization.json", checker.planner.encoded(receipt), 0, 0, 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)
        initializer.rename_noreplace(root, stage, "dependencies")
        staged = False
        os.fsync(root)
        return receipt
    finally:
        try:
            if staged:
                initializer.remove_stage(root, stage)
        finally:
            os.close(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--delivery", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(initialize(args.plan, args.expected_plan_sha256, args.delivery)))


if __name__ == "__main__":
    try:
        main()
    except (checker.planner.PlanError, OSError, ValueError, UnicodeError) as error:
        print(
            str(error) if isinstance(error, checker.planner.PlanError) else "dependency_init_io_failed", file=sys.stderr
        )
        sys.exit(1)
