#!/usr/bin/env python3
"""Start only exact prepared dependencies and initialize a fresh application DB.

This trusted Linux-root controller never repairs altered services, recreates
recorded containers, rotates credentials, migrates schema or approves model use.
"""

import argparse
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

import private_dependency_init as preparation

resources = preparation.resources
checker = preparation.checker
ROLES = set(preparation.IDENTITY)
LABEL = resources.LABEL


def read_file(parent, name, uid, gid, mode, limit):
    descriptor = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode)) != (uid, gid, mode)
            or not 0 < before.st_size <= limit
        ):
            raise checker.planner.PlanError("dependency_stored_file_invalid")
        checker.no_directory_acl(stream.fileno())
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(data) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise checker.planner.PlanError("dependency_stored_file_changed")
        return data


def directory(parent, name, identity):
    descriptor = os.open(name, preparation.initializer.DIRECTORY_FLAGS, dir_fd=parent)
    try:
        info = os.fstat(descriptor)
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != identity:
            raise checker.planner.PlanError("dependency_stored_directory_invalid")
        checker.no_directory_acl(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def prepared(plan, expected):
    value = checker.verify(plan, expected)
    if sys.platform != "linux" or os.geteuid() != 0:
        raise checker.planner.PlanError("dependency_v2_linux_root_required")
    checker.check_paths(plan, expected)
    return prepared_value(value, expected)


def prepared_value(value, expected):
    """Consume a verified plan value; callers must first run P35 path checks."""
    if value["manifest"]["schema"] != checker.planner.PLAN_SCHEMA or sys.platform != "linux" or os.geteuid() != 0:
        raise checker.planner.PlanError("dependency_v2_linux_root_required")
    initialized = resources.initialization(value)
    if initialized["plan_manifest_sha256"] != expected:
        raise checker.planner.PlanError("dependency_initialization_plan_mismatch")
    parent = preparation.initializer.trusted_directory(Path(value["request"]["root"]))
    try:
        root = directory(parent, "dependencies", (0, 0, 0o700))
    finally:
        os.close(parent)
    try:
        if not {"initialization.json", "profile.json", *ROLES} <= set(os.listdir(root)) or set(os.listdir(root)) - {
            "initialization.json",
            "profile.json",
            "start.lock",
            "started.json",
            *ROLES,
        }:
            raise checker.planner.PlanError("dependency_stored_members_invalid")
        receipt = checker.planner.decode(read_file(root, "initialization.json", 0, 0, 0o600, 16384))
        if not isinstance(receipt, dict):
            raise checker.planner.PlanError("dependency_stored_initialization_invalid")
        spec = preparation.profile(value, expected, initialized["initialization_id"])
        encoded = checker.planner.encoded(spec)
        digest = hashlib.sha256(encoded).hexdigest()
        if read_file(root, "profile.json", 0, 0, 0o600, 32768) != encoded:
            raise checker.planner.PlanError("dependency_stored_profile_mismatch")
        identifier = receipt.get("dependency_initialization_id")
        wanted = {
            "schema": "private_dependency_initialization_v1",
            "plan_manifest_sha256": expected,
            "initialization_id": initialized["initialization_id"],
            "dependency_initialization_id": identifier,
            "dependency_profile_sha256": digest,
            "delivered_files": 5,
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
        if (
            not isinstance(identifier, str)
            or not resources.re.fullmatch(r"[0-9a-f]{32}", identifier)
            or checker.planner.encoded(receipt) != checker.planner.encoded(wanted)
        ):
            raise checker.planner.PlanError("dependency_stored_initialization_invalid")
        app = preparation.capture(
            Path(value["request"]["root"]) / "secrets", value["prerequisites"]["secret_files"], (0, 10001, 0o750)
        )
        configs = preparation.configurations(value, app)
        delivered, data_empty = {}, {}
        for role, (uid, gid) in preparation.IDENTITY.items():
            child = directory(root, role, (0, gid, 0o750))
            try:
                if set(os.listdir(child)) != ({"config"} if role == "cache" else {"config", "data"}):
                    raise checker.planner.PlanError("dependency_stored_members_invalid")
                config = directory(child, "config", (0, gid, 0o750))
                try:
                    names = set(preparation.DELIVERY.get(role, [])) | {
                        "pg_hba.conf" if role == "postgres" else "redis.conf"
                    }
                    if role == "job-broker":
                        names.add("server-ca.crt")
                    if set(os.listdir(config)) != names:
                        raise checker.planner.PlanError("dependency_stored_members_invalid")
                    for name in names:
                        data = read_file(
                            config,
                            name,
                            0,
                            gid,
                            0o440,
                            65536 if name.endswith((".crt", ".key")) else 4096 if name == "owner-password" else 16384,
                        )
                        if name in preparation.DELIVERY.get(role, []):
                            delivered[role + "/" + name] = data
                        elif name == "server-ca.crt":
                            if data != app["app/job-ca.crt"]:
                                raise checker.planner.PlanError("dependency_current_ca_changed")
                        elif data != configs[role + "/" + name]:
                            raise checker.planner.PlanError("dependency_configuration_changed")
                finally:
                    os.close(config)
                if role != "cache":
                    data = directory(child, "data", (uid, gid, 0o700))
                    try:
                        data_empty[role] = not os.listdir(data)
                    finally:
                        os.close(data)
            finally:
                os.close(child)
        preparation.password(delivered["postgres/owner-password"])
        preparation.certificates(delivered, app)  # Current validity/trust, not the old receipt alone.
        return value, spec, receipt, app, data_empty, root
    except BaseException:
        os.close(root)
        raise


def labels(value, receipt):
    return {
        **resources.labels(value, receipt["plan_manifest_sha256"], receipt["initialization_id"]),
        LABEL + "dependency": receipt["dependency_initialization_id"],
        LABEL + "dependency-profile": receipt["dependency_profile_sha256"],
    }


def names(value):
    return {role: "declarai-" + value["request"]["installation_id"] + "-dependency-" + role for role in ROLES}


def environment(items):
    result = {}
    for item in items or []:
        if not isinstance(item, str) or "=" not in item or item.split("=", 1)[0] in result:
            raise checker.planner.PlanError("dependency_environment_invalid")
        key, value = item.split("=", 1)
        result[key] = value
    return result


def validate(info, role, spec, binding, image, name, active=False):
    service = spec["services"][role]
    config, host = info.get("Config", {}), info.get("HostConfig", {})
    wanted_env = environment(image["Config"].get("Env"))
    wanted_env.update(service["environment"])
    if (
        info.get("Image") != service["image_id"]
        or info.get("Name") != "/" + name
        or config.get("Labels") != {**(image["Config"].get("Labels") or {}), **binding, LABEL + "role": role}
    ):
        raise checker.planner.PlanError("dependency_container_identity_mismatch")
    if (
        config.get("User") != f"{service['uid']}:{service['gid']}"
        or config.get("Entrypoint") != service["entrypoint"]
        or config.get("Cmd") != service["command"]
        or config.get("WorkingDir") != image["Config"].get("WorkingDir")
        or config.get("StopTimeout") != service["stop_timeout"]
        or config.get("Healthcheck") != image["Config"].get("Healthcheck")
        or environment(config.get("Env")) != wanted_env
    ):
        raise checker.planner.PlanError("dependency_container_profile_mismatch")
    if (
        host.get("ReadonlyRootfs") is not True
        or host.get("Privileged") is not False
        or host.get("CapDrop") != ["ALL"]
        or host.get("CapAdd") not in (None, [])
        or host.get("SecurityOpt") != ["no-new-privileges:true"]
        or host.get("PidsLimit") != service["pids"]
        or host.get("NanoCpus") != service["cpus"] * 1_000_000_000
        or host.get("Memory") != service["memory_bytes"]
        or host.get("MemorySwap") != service["memory_bytes"]
        or host.get("Tmpfs") != service["tmpfs"]
        or host.get("RestartPolicy") != service["restart"]
        or host.get("Runtime") != "runc"
        or host.get("IpcMode") != "private"
        or host.get("CgroupnsMode") != "private"
        or host.get("ShmSize") != 64 * 1024**2
        or host.get("PortBindings") not in (None, {})
    ):
        raise checker.planner.PlanError("dependency_container_profile_mismatch")
    if (
        any(host.get(k) not in (None, "") for k in ["PidMode", "UTSMode", "UsernsMode"])
        or any(
            host.get(k) not in (None, [])
            for k in [
                "Devices",
                "DeviceRequests",
                "GroupAdd",
                "ExtraHosts",
                "Links",
                "Dns",
                "DnsOptions",
                "DnsSearch",
                "VolumesFrom",
            ]
        )
        or host.get("Sysctls") not in (None, {})
    ):
        raise checker.planner.PlanError("dependency_container_profile_mismatch")
    networks = info.get("NetworkSettings", {}).get("Networks", {})
    if set(networks) != {spec["private_network"]} or role not in (
        networks[spec["private_network"]].get("Aliases") or []
    ):
        raise checker.planner.PlanError("dependency_container_network_mismatch")
    ports = info.get("NetworkSettings", {}).get("Ports") or {}
    if not isinstance(ports, dict) or any(value is not None for value in ports.values()):
        raise checker.planner.PlanError("dependency_container_public_port")
    mounts = info.get("Mounts", [])
    if len(mounts) != len(service["mounts"]):
        raise checker.planner.PlanError("dependency_container_mount_mismatch")
    for wanted in service["mounts"]:
        matches = [m for m in mounts if m.get("Destination") == wanted["target"]]
        if (
            len(matches) != 1
            or matches[0].get("Type") != "bind"
            or matches[0].get("Source") != wanted["source"]
            or matches[0].get("RW") is not (not wanted["read_only"])
        ):
            raise checker.planner.PlanError("dependency_container_mount_mismatch")
    if active and (
        info.get("State", {}).get("Running") is not True
        or any(info.get("State", {}).get(k) is not False for k in ["Paused", "Restarting", "Dead"])
    ):
        raise checker.planner.PlanError("dependency_service_not_active")


def snapshot(value, spec, receipt, images, active=False):
    found = {}
    selected = names(value)
    binding = labels(value, receipt)
    for role, name in selected.items():
        listing = resources.command(["container", "ls", "--all", "--filter", "name=" + name, "--format", "{{json .}}"])
        exact = [
            checker.planner.decode(line)
            for line in listing.splitlines()
            if line and checker.planner.decode(line).get("Names") == name
        ]
        if len(exact) > 1:
            raise checker.planner.PlanError("dependency_container_identity_mismatch")
        if exact:
            info = resources.inspect("container", name)
            validate(info, role, spec, binding, images["postgres" if role == "postgres" else "redis"], name, active)
            found[role] = info
    if active and set(found) != ROLES:
        raise checker.planner.PlanError("dependency_services_missing")
    return found


def network(value, receipt, dependencies):
    import private_installation_adopt as adopter

    binding = resources.labels(value, receipt["plan_manifest_sha256"], receipt["initialization_id"])
    spec = value["prerequisites"]["networks"][0]
    info = resources.inspect("network", spec["name"])
    resources.validate_network({**info, "Containers": {}}, spec, binding)
    allowed = {c["Id"] for c in dependencies.values()}
    profile, digest, app_binding = adopter.application_profile(
        value, receipt["plan_manifest_sha256"], receipt["initialization_id"]
    )
    images = {role: resources.inspect("image", identity) for role, identity in value["images"].items()}
    app_roles = set()
    for app in adopter.project_containers(profile["name"]):
        role = app.get("Config", {}).get("Labels", {}).get("com.docker.compose.service")
        if role not in adopter.ROLES or role in app_roles:
            raise checker.planner.PlanError("dependency_unexpected_network_member")
        app_roles.add(role)
        adopter.validate_application(
            app,
            role,
            profile["services"][role],
            profile,
            digest,
            app_binding,
            images["ingress" if role == "ingress" else "api"],
        )
        allowed.add(app["Id"])
    if not isinstance(info.get("Containers"), dict) or set(info["Containers"]) - allowed:
        raise checker.planner.PlanError("dependency_unexpected_network_member")


def create_args(role, value, spec, receipt):
    service = spec["services"][role]
    args = [
        "container",
        "create",
        "--name",
        names(value)[role],
        "--pull",
        "never",
        "--network",
        spec["private_network"],
        "--network-alias",
        role,
        "--read-only",
        "--user",
        f"{service['uid']}:{service['gid']}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--cpus",
        str(service["cpus"]),
        "--memory",
        str(service["memory_bytes"]),
        "--memory-swap",
        str(service["memory_bytes"]),
        "--pids-limit",
        str(service["pids"]),
        "--restart",
        "on-failure:3",
        "--stop-timeout",
        "60",
    ]
    for key, data in {**labels(value, receipt), LABEL + "role": role}.items():
        args += ["--label", key + "=" + data]
    for key, data in service["environment"].items():
        args += ["--env", key + "=" + data]
    for path, options in service["tmpfs"].items():
        args += ["--tmpfs", path + ":" + options]
    for mount in service["mounts"]:
        args += [
            "--mount",
            "type=bind,src="
            + mount["source"]
            + ",dst="
            + mount["target"]
            + (",readonly" if mount["read_only"] else ""),
        ]
    return [*args, service["image_id"], *service["command"]]


def sql_text(value):
    return "E'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def sql_name(value):
    return '"' + value.replace('"', '""') + '"'


def owner_sql(container, sql):
    try:
        result = subprocess.run(
            [
                *resources.PREFIX,
                "exec",
                "--user",
                "70:70",
                "-i",
                container,
                "psql",
                "-X",
                "-A",
                "-t",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "postgres",
            ],
            input=sql.encode(),
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise checker.planner.PlanError("dependency_database_owner_unavailable") from None
    if result.returncode or len(result.stdout) > 16384:
        raise checker.planner.PlanError("dependency_database_owner_unavailable")
    return result.stdout.decode().strip()


def bootstrap(value, app, postgres):
    db = value["request"]["database"]
    if db["user"].startswith("pg_"):
        raise checker.planner.PlanError("dependency_application_role_reserved")
    user, database = sql_text(db["user"]), sql_text(db["name"])
    unknown = owner_sql(
        postgres,
        f"SELECT (SELECT count(*) FROM pg_roles WHERE left(rolname,3)<>'pg_' AND rolname NOT IN ('postgres', {user})) + (SELECT count(*) FROM pg_database WHERE datname NOT IN ('postgres','template0','template1',{database}));",
    )
    if unknown != "0":
        raise checker.planner.PlanError("dependency_database_foreign_catalog")
    exists = owner_sql(postgres, f"SELECT count(*) FROM pg_roles WHERE rolname={user};")
    if exists == "0":
        password = preparation.password(app["app/app-password"])
        owner_sql(
            postgres,
            "SET log_statement=none; CREATE ROLE "
            + sql_name(db["user"])
            + " LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD "
            + sql_text(password)
            + ";",
        )
    elif exists != "1":
        raise checker.planner.PlanError("dependency_database_authority_changed")
    flags = owner_sql(
        postgres,
        f"SELECT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls AND NOT EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid) FROM pg_roles r WHERE rolname={user};",
    )
    if flags != "t":
        raise checker.planner.PlanError("dependency_database_authority_changed")
    exists = owner_sql(postgres, f"SELECT count(*) FROM pg_database WHERE datname={database};")
    if exists == "0":
        owner_sql(
            postgres, "CREATE DATABASE " + sql_name(db["name"]) + " OWNER " + sql_name(db["user"]) + " ENCODING 'UTF8';"
        )
        owner_sql(postgres, "REVOKE ALL ON DATABASE " + sql_name(db["name"]) + " FROM PUBLIC;")
    elif exists != "1":
        raise checker.planner.PlanError("dependency_database_authority_changed")
    if (
        owner_sql(
            postgres,
            f"SELECT pg_get_userbyid(datdba)={user} AND pg_encoding_to_char(encoding)='UTF8' FROM pg_database WHERE datname={database};",
        )
        != "t"
    ):
        raise checker.planner.PlanError("dependency_database_authority_changed")


PROBE = r"""
import os,ssl,uuid
from pathlib import Path
import psycopg,redis
password=Path('/installation/app-password').read_text().rstrip('\r\n')
with psycopg.connect(host='postgres',port=5432,dbname=os.environ['DEPENDENCY_DATABASE'],user=os.environ['DEPENDENCY_USER'],password=password,sslmode='verify-full',sslrootcert='/installation/postgres-ca.crt',connect_timeout=5) as db:
    with db.cursor() as cursor:
        cursor.execute('SELECT current_database(),current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid) FROM pg_roles r WHERE rolname=current_user')
        row=cursor.fetchone();assert row[:3]==(os.environ['DEPENDENCY_DATABASE'],os.environ['DEPENDENCY_USER'],True) and all(x is False for x in row[3:])
url=Path('/installation/job-broker-url').read_text().rstrip('\r\n')
client=redis.Redis.from_url(url,ssl_ca_certs='/installation/job-ca.crt',ssl_cert_reqs='required',ssl_check_hostname=True,socket_connect_timeout=5,socket_timeout=5)
assert client.ping() is True and client.info('persistence')['aof_enabled']==1
key='declarai-dependency-probe:'+uuid.uuid4().hex
try:
    client.set(key,b'bounded-readiness',ex=60);assert client.get(key)==b'bounded-readiness'
finally:client.delete(key);client.close()
cache=redis.Redis(host='cache',port=6379,socket_connect_timeout=5,socket_timeout=5)
assert cache.ping() is True and cache.info('persistence')['aof_enabled']==0
cache.close();print('private_dependencies_checked')
"""


def validate_probe(info, value, spec, receipt, image):
    config, host = info.get("Config", {}), info.get("HostConfig", {})
    wanted = environment(image["Config"].get("Env"))
    wanted.update(
        DEPENDENCY_DATABASE=value["request"]["database"]["name"], DEPENDENCY_USER=value["request"]["database"]["user"]
    )
    binding = {**(image["Config"].get("Labels") or {}), **labels(value, receipt), LABEL + "role": "dependency-check"}
    paths = {
        "/installation/" + file: value["request"]["root"] + "/secrets/app/" + file
        for file in ["app-password", "postgres-ca.crt", "job-broker-url", "job-ca.crt"]
    }
    mounts = info.get("Mounts", [])
    if (
        info.get("Image") != value["images"]["api"]
        or config.get("Labels") != binding
        or config.get("User") != "10001:10001"
        or config.get("Entrypoint") != ["python"]
        or config.get("Cmd") != ["-I", "-c", PROBE]
        or config.get("WorkingDir") != image["Config"].get("WorkingDir")
        or config.get("Healthcheck") != image["Config"].get("Healthcheck")
        or environment(config.get("Env")) != wanted
    ):
        raise checker.planner.PlanError("dependency_probe_profile_invalid")
    if (
        host.get("ReadonlyRootfs") is not True
        or host.get("Privileged") is not False
        or host.get("CapDrop") != ["ALL"]
        or host.get("CapAdd") not in (None, [])
        or host.get("SecurityOpt") != ["no-new-privileges:true"]
        or host.get("PidsLimit") != 32
        or host.get("NanoCpus") != 1_000_000_000
        or host.get("Memory") != 256 * 1024**2
        or host.get("Runtime") != "runc"
        or host.get("IpcMode") != "private"
        or host.get("CgroupnsMode") != "private"
        or host.get("PortBindings") not in (None, {})
        or host.get("Tmpfs") != {"/tmp": "rw,noexec,nosuid,size=67108864,uid=10001,gid=10001,mode=700"}
    ):
        raise checker.planner.PlanError("dependency_probe_profile_invalid")
    if (
        any(host.get(k) not in (None, "") for k in ["PidMode", "UTSMode", "UsernsMode"])
        or any(
            host.get(k) not in (None, [])
            for k in [
                "Devices",
                "DeviceRequests",
                "GroupAdd",
                "ExtraHosts",
                "Links",
                "Dns",
                "DnsOptions",
                "DnsSearch",
                "VolumesFrom",
            ]
        )
        or host.get("Sysctls") not in (None, {})
    ):
        raise checker.planner.PlanError("dependency_probe_profile_invalid")
    if (
        set(info.get("NetworkSettings", {}).get("Networks", {})) != {spec["private_network"]}
        or len(mounts) != 4
        or {m.get("Destination"): m.get("Source") for m in mounts} != paths
        or any(m.get("Type") != "bind" or m.get("RW") is not False for m in mounts)
    ):
        raise checker.planner.PlanError("dependency_probe_profile_invalid")


def probe(value, spec, receipt):
    binding = {**labels(value, receipt), LABEL + "role": "dependency-check"}
    args = [
        "container",
        "create",
        "--name",
        "declarai-dependency-probe-" + uuid.uuid4().hex,
        "--pull",
        "never",
        "--network",
        spec["private_network"],
        "--read-only",
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--cpus",
        "1",
        "--memory",
        "256m",
        "--pids-limit",
        "32",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=67108864,uid=10001,gid=10001,mode=700",
        "--entrypoint",
        "python",
    ]
    for key, data in binding.items():
        args += ["--label", key + "=" + data]
    for key, data in {
        "DEPENDENCY_DATABASE": value["request"]["database"]["name"],
        "DEPENDENCY_USER": value["request"]["database"]["user"],
    }.items():
        args += ["--env", key + "=" + data]
    for file in ["app-password", "postgres-ca.crt", "job-broker-url", "job-ca.crt"]:
        args += [
            "--mount",
            "type=bind,src="
            + value["request"]["root"]
            + "/secrets/app/"
            + file
            + ",dst=/installation/"
            + file
            + ",readonly",
        ]
    identifier = None
    try:
        identifier = resources.command([*args, value["images"]["api"], "-I", "-c", PROBE]).decode().strip()
        if not resources.re.fullmatch(r"[0-9a-f]{64}", identifier):
            identifier = None
            raise checker.planner.PlanError("dependency_probe_identity_invalid")
        info = resources.inspect("container", identifier)
        validate_probe(info, value, spec, receipt, resources.inspect("image", value["images"]["api"]))
        output = resources.command(["container", "start", "--attach", identifier], allow_failure=True)
        state = resources.inspect("container", identifier)["State"]
        if (
            output.strip() != b"private_dependencies_checked"
            or state.get("Running") is not False
            or type(state.get("ExitCode")) is not int
            or state["ExitCode"] != 0
        ):
            raise checker.planner.PlanError("dependency_authenticated_readiness_failed")
    finally:
        if identifier:
            resources.command(["container", "rm", "--force", identifier])


def start_receipt(expected, receipt, final, reused):
    return {
        "schema": "private_dependency_start_v1",
        "plan_manifest_sha256": expected,
        "dependency_initialization_id": receipt["dependency_initialization_id"],
        "dependency_profile_sha256": receipt["dependency_profile_sha256"],
        "services": {
            role: {"container_id": c["Id"], "image_id": c["Image"], "reused": role in reused}
            for role, c in final.items()
        },
        "dependencies_started": True,
        "database_initialized": True,
        "application_role_elevated": False,
        "metadata_tls_and_broker_authentication": "verified",
        "broker_aof_enabled": True,
        "cache_reconstructible": True,
        "migrations_applied": False,
        "model_use_approved": False,
        "installation_qualified": False,
        "release_qualified": False,
        "production_recovery_qualified": False,
        "expert_isolation_qualified": False,
    }


def prior_receipt(prior, expected, receipt, existing):
    if (
        not isinstance(prior, dict)
        or not isinstance(prior.get("services"), dict)
        or set(prior["services"]) != ROLES
        or set(existing) != ROLES
    ):
        raise checker.planner.PlanError("dependency_recorded_identity_changed")

    reused = set()
    for role in ROLES:
        row = prior["services"][role]
        if not isinstance(row, dict) or type(row.get("reused")) is not bool:
            raise checker.planner.PlanError("dependency_recorded_identity_changed")
        if row["reused"]:
            reused.add(role)
    if checker.planner.encoded(prior) != checker.planner.encoded(start_receipt(expected, receipt, existing, reused)):
        raise checker.planner.PlanError("dependency_recorded_identity_changed")


def adoption_check(value, binding, dependencies):
    path = Path(value["request"]["root"]) / "dependencies"
    managed = any(LABEL + "dependency" in c.get("Config", {}).get("Labels", {}) for c in dependencies.values())
    if not managed and not path.exists() and not path.is_symlink():
        return  # Historical operator-managed profile remains separately scoped.
    expected = binding[LABEL + "plan"]
    _, spec, receipt, _, _, root = prepared_value(value, expected)
    try:
        images = {role: resources.inspect("image", identity) for role, identity in value["images"].items()}
        if set(dependencies) != ROLES:
            raise checker.planner.PlanError("dependency_services_missing")
        for role, info in dependencies.items():
            validate(
                info,
                role,
                spec,
                labels(value, receipt),
                images["postgres" if role == "postgres" else "redis"],
                names(value)[role],
                True,
            )
        prior = checker.planner.decode(read_file(root, "started.json", 0, 0, 0o600, 16384))
        prior_receipt(prior, expected, receipt, dependencies)
    finally:
        os.close(root)


def start(plan, expected):
    value, spec, receipt, app, empty, root = prepared(plan, expected)
    lock = None
    try:
        lock = os.open("start.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=root)
        info = os.fstat(lock)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (0, 0, 0o600)
        ):
            raise checker.planner.PlanError("dependency_lock_invalid")
        checker.no_directory_acl(lock)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise checker.planner.PlanError("dependency_operation_in_progress") from None
        resources.docker_host(value["manifest"]["architecture"])
        if resources.record(["info", "--format", "{{json .}}"]).get("DefaultRuntime") != "runc":
            raise checker.planner.PlanError("dependency_default_runtime_required")
        images = {role: resources.inspect("image", identity) for role, identity in value["images"].items()}
        if any(
            image.get("Id") != value["images"][role]
            or image.get("Architecture") != value["manifest"]["architecture"]
            or image.get("Os") != "linux"
            for role, image in images.items()
        ):
            raise checker.planner.PlanError("dependency_native_image_required")
        for role in ["postgres", "redis"]:
            image = images[role]
            if (
                image.get("Id") != value["images"][role]
                or image.get("Architecture") != value["manifest"]["architecture"]
                or image.get("Os") != "linux"
                or image["Config"].get("Entrypoint") != ["docker-entrypoint.sh"]
            ):
                raise checker.planner.PlanError("dependency_native_image_required")
            account = "postgres" if role == "postgres" else "redis"
            result = (
                resources.command(
                    [
                        "run",
                        "--rm",
                        "--pull",
                        "never",
                        "--network",
                        "none",
                        "--read-only",
                        "--user",
                        "65534:65534",
                        "--cap-drop",
                        "ALL",
                        "--security-opt",
                        "no-new-privileges",
                        "--cpus",
                        "1",
                        "--memory",
                        "128m",
                        "--pids-limit",
                        "32",
                        "--entrypoint",
                        "/bin/sh",
                        image["Id"],
                        "-c",
                        "id -u " + account + "; id -g " + account,
                    ]
                )
                .decode()
                .splitlines()
            )
            if result != (["70", "70"] if role == "postgres" else ["999", "1000"]):
                raise checker.planner.PlanError("dependency_native_account_unsupported")
        existing = snapshot(value, spec, receipt, images)
        network(value, receipt, existing)
        prior = None
        if "started.json" in os.listdir(root):
            prior = checker.planner.decode(read_file(root, "started.json", 0, 0, 0o600, 16384))
            prior_receipt(prior, expected, receipt, existing)
        for role in ROLES:
            if role not in existing and role in empty and not empty[role]:
                raise checker.planner.PlanError("dependency_new_storage_not_empty")
        selected = dict(existing)
        for role in sorted(ROLES):
            if role not in selected:
                identifier = resources.command(create_args(role, value, spec, receipt)).decode().strip()
                if not resources.re.fullmatch(r"[0-9a-f]{64}", identifier):
                    raise checker.planner.PlanError("dependency_create_response_invalid")
                info = resources.inspect("container", identifier)
                validate(
                    info,
                    role,
                    spec,
                    labels(value, receipt),
                    images["postgres" if role == "postgres" else "redis"],
                    names(value)[role],
                )
                selected[role] = info
            if selected[role]["State"].get("Paused") is True or selected[role]["State"].get("Dead") is True:
                raise checker.planner.PlanError("dependency_service_not_active")
            if selected[role]["State"].get("Running") is not True:
                resources.command(["container", "start", selected[role]["Id"]])
        deadline = time.monotonic() + 60
        while True:
            try:
                owner_sql(selected["postgres"]["Id"], "SELECT 1;")
                ready = resources.command(
                    ["exec", selected["postgres"]["Id"], "pg_isready", "-h", "127.0.0.1"], allow_failure=True
                )
                if b"accepting connections" not in ready:
                    raise checker.planner.PlanError("dependency_database_owner_unavailable")
                break
            except checker.planner.PlanError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
        bootstrap(value, app, selected["postgres"]["Id"])
        probe(value, spec, receipt)
        final = snapshot(value, spec, receipt, images, active=True)
        if any(final[role]["Id"] != selected[role]["Id"] for role in ROLES):
            raise checker.planner.PlanError("dependency_identity_changed_during_readiness")
        network(value, receipt, final)
        result = start_receipt(expected, receipt, final, existing)
        if prior is None:
            preparation.initializer.write_file(root, "started.json", checker.planner.encoded(result), 0, 0, 0o600)
            os.fsync(root)
        return result
    finally:
        if lock is not None:
            os.close(lock)
        os.close(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(start(args.plan, args.expected_plan_sha256)))


if __name__ == "__main__":
    try:
        main()
    except (checker.planner.PlanError, OSError, ValueError, UnicodeError) as error:
        print(
            str(error) if isinstance(error, checker.planner.PlanError) else "dependency_start_io_failed",
            file=sys.stderr,
        )
        sys.exit(1)
