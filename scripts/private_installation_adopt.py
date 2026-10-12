#!/usr/bin/env python3
"""Adopt exact private application services after bounded installation preflight.

Operator-managed TLS dependencies and current migrations are prerequisites.
This controller never generates credentials, migrates data, enrolls accounts,
recreates existing services or grants model/release/production approval.
"""

import argparse
import hashlib
import http.client
import json
import os
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import private_installation_resources as resources

checker = resources.checker
ROLES = {"api", "worker", "dispatcher", "ingress"}


def parsed_environment(values):
    if not isinstance(values, list):
        raise checker.planner.PlanError("installation_adopt_environment_invalid")
    result = {}
    for value in values:
        if not isinstance(value, str) or "=" not in value:
            raise checker.planner.PlanError("installation_adopt_environment_invalid")
        name, content = value.split("=", 1)
        if name in result:
            raise checker.planner.PlanError("installation_adopt_environment_invalid")
        result[name] = content
    return result


def application_profile(value, expected, initialization):
    profile = checker.planner.composition(value["request"], value["images"])
    digest = hashlib.sha256(checker.planner.encoded(profile)).hexdigest()
    binding = resources.labels(value, expected, initialization)
    for role, service in profile["services"].items():
        service["labels"] = {**binding, resources.LABEL + "role": role, resources.LABEL + "profile": digest}
    return profile, digest, binding


def project_containers(name):
    output = resources.command(
        ["container", "ls", "--all", "--filter", "label=com.docker.compose.project=" + name, "--format", "{{.ID}}"]
    )
    return [resources.inspect("container", identifier.decode()) for identifier in output.splitlines() if identifier]


def validate_application(info, role, service, profile, digest, binding, image):
    labels = info.get("Config", {}).get("Labels", {})
    if (
        info.get("Image") != service["image"]
        or any(
            labels.get(key) != item
            for key, item in {**binding, resources.LABEL + "role": role, resources.LABEL + "profile": digest}.items()
        )
        or labels.get("com.docker.compose.project") != profile["name"]
        or labels.get("com.docker.compose.service") != role
        or labels.get("com.docker.compose.oneoff") != "False"
    ):
        raise checker.planner.PlanError("installation_adopt_application_conflict")
    config, host = info.get("Config", {}), info.get("HostConfig", {})
    wanted_env = parsed_environment(image["Config"].get("Env") or [])
    wanted_env.update(service.get("environment", {}))
    expected_command = service.get("command", image["Config"].get("Cmd"))
    if (
        config.get("User") != "10001:10001"
        or config.get("Entrypoint") != image["Config"].get("Entrypoint")
        or config.get("Cmd") != expected_command
        or config.get("WorkingDir") != image["Config"].get("WorkingDir")
        or config.get("Healthcheck") != image["Config"].get("Healthcheck")
        or config.get("StopTimeout") != 60
        or parsed_environment(config.get("Env")) != wanted_env
        or host.get("ReadonlyRootfs") is not True
        or host.get("Privileged") is not False
        or host.get("CapDrop") != ["ALL"]
        or host.get("CapAdd") not in (None, [])
        or host.get("SecurityOpt") != ["no-new-privileges:true"]
        or host.get("PidsLimit") != service["pids_limit"]
        or host.get("NanoCpus") != service["cpus"] * 1_000_000_000
        or host.get("Memory") != (256 * 1024**2 if role == "ingress" else 2 * 1024**3)
        or host.get("PidMode") not in (None, "")
        or host.get("IpcMode") != "private"
        or host.get("UTSMode") not in (None, "")
        or host.get("UsernsMode") not in (None, "")
        or host.get("DeviceRequests") not in (None, [])
        or host.get("Devices") not in (None, [])
        or host.get("Runtime") != "runc"
        or host.get("GroupAdd") not in (None, [])
        or host.get("ExtraHosts") not in (None, [])
        or host.get("Links") not in (None, [])
        or any(host.get(key) not in (None, []) for key in ("Dns", "DnsOptions", "DnsSearch", "VolumesFrom"))
        or host.get("Sysctls") not in (None, {})
        or host.get("Tmpfs") != {"/tmp": service["tmpfs"][0].removeprefix("/tmp:")}
        or host.get("RestartPolicy") != {"Name": "on-failure", "MaximumRetryCount": 3}
    ):
        raise checker.planner.PlanError("installation_adopt_application_profile_mismatch")
    wanted_networks = {profile["networks"][n]["name"] for n in service["networks"]}
    if set(info.get("NetworkSettings", {}).get("Networks", {})) != wanted_networks:
        raise checker.planner.PlanError("installation_adopt_application_network_mismatch")
    actual_mounts = info.get("Mounts", [])
    if len(actual_mounts) != len(service["volumes"]):
        raise checker.planner.PlanError("installation_adopt_application_mount_mismatch")
    for wanted in service["volumes"]:
        matches = [m for m in actual_mounts if m.get("Destination") == wanted["target"]]
        if len(matches) != 1:
            raise checker.planner.PlanError("installation_adopt_application_mount_mismatch")
        mount = matches[0]
        source = profile["volumes"]["api-socket"]["name"] if wanted["type"] == "volume" else wanted["source"]
        if (
            mount.get("Type") != wanted["type"]
            or mount.get("Name" if wanted["type"] == "volume" else "Source") != source
            or mount.get("RW") is not (not wanted.get("read_only", False))
        ):
            raise checker.planner.PlanError("installation_adopt_application_mount_mismatch")
    ports = host.get("PortBindings") or {}
    wanted_ports = {}
    if role == "ingress":
        declared = service["ports"][0]
        wanted_ports = {"8443/tcp": [{"HostIp": declared["host_ip"], "HostPort": declared["published"]}]}
    if ports != wanted_ports:
        raise checker.planner.PlanError("installation_adopt_application_port_mismatch")
    if role == "ingress" and info.get("State", {}).get("Running") is True:
        # Docker also reports image-declared, unpublished ports as null. These
        # are not host bindings; only declarations from this exact image may
        # accompany the one required live HTTPS publication.
        actual_ports = info.get("NetworkSettings", {}).get("Ports")
        declared_ports = image["Config"].get("ExposedPorts") or {}
        if (
            not isinstance(actual_ports, dict)
            or {port: bindings for port, bindings in actual_ports.items() if bindings is not None} != wanted_ports
            or any(port not in declared_ports for port, bindings in actual_ports.items() if bindings is None)
        ):
            raise checker.planner.PlanError("installation_adopt_https_port_not_published")


def prerequisites(value, binding, applications):
    private = value["prerequisites"]["networks"][0]
    edge = value["prerequisites"]["networks"][1]
    allowed, dependency_roles = {c["Id"] for c in applications.values()}, set()
    dependencies = {}
    for spec in (private, edge):
        info = resources.inspect("network", spec["name"])
        empty = {**info, "Containers": {}}
        resources.validate_network(empty, spec, binding)
        containers = info.get("Containers")
        if not isinstance(containers, dict):
            raise checker.planner.PlanError("installation_adopt_network_members_invalid")
        for identifier in containers:
            if identifier in allowed:
                continue
            container = resources.inspect("container", identifier)
            labels = container.get("Config", {}).get("Labels", {})
            role = labels.get(resources.LABEL + "role")
            if spec is edge or role not in {"postgres", "cache", "job-broker"} or role in dependency_roles:
                raise checker.planner.PlanError("installation_adopt_unexpected_network_member")
            image = value["images"]["postgres" if role == "postgres" else "redis"]
            network = container.get("NetworkSettings", {}).get("Networks", {})
            if (
                container.get("Image") != image
                or any(labels.get(k) != v for k, v in binding.items())
                or set(network) != {private["name"]}
                or role not in (network[private["name"]].get("Aliases") or [])
                or container.get("State", {}).get("Running") is not True
                or container.get("HostConfig", {}).get("Privileged") is not False
                or container.get("HostConfig", {}).get("PortBindings") not in (None, {})
            ):
                raise checker.planner.PlanError("installation_adopt_dependency_conflict")
            dependency_roles.add(role)
            dependencies[role] = container
    if dependency_roles != {"postgres", "cache", "job-broker"}:
        raise checker.planner.PlanError("installation_adopt_dependencies_required")
    from private_dependency_start import adoption_check

    adoption_check(value, binding, dependencies)
    volume = value["prerequisites"]["socket_volume"]
    resources.validate_volume(resources.inspect("volume", volume["name"]), volume, binding)
    attached = resources.command(
        ["container", "ls", "--all", "--filter", "volume=" + volume["name"], "--format", "{{.ID}}"]
    )
    identifiers = {resources.inspect("container", n.decode())["Id"] for n in attached.splitlines() if n}
    if identifiers - allowed:
        raise checker.planner.PlanError("installation_adopt_socket_occupied")


def active_applications(profile, digest, binding, images):
    applications = {}
    for info in project_containers(profile["name"]):
        role = info.get("Config", {}).get("Labels", {}).get("com.docker.compose.service")
        if role not in ROLES or role in applications:
            raise checker.planner.PlanError("installation_adopt_application_conflict")
        validate_application(
            info,
            role,
            profile["services"][role],
            profile,
            digest,
            binding,
            images["ingress" if role == "ingress" else "api"],
        )
        state = info.get("State", {})
        if state.get("Running") is not True or any(
            state.get(key) is not False for key in ("Paused", "Restarting", "Dead")
        ):
            raise checker.planner.PlanError("installation_adopt_service_not_active")
        applications[role] = info
    if set(applications) != ROLES:
        raise checker.planner.PlanError("installation_adopt_services_missing")
    return applications


def validate_preflight(
    info, value, environment, binding, image, *, role="preflight", entrypoint=None, command=None, mount_sources=None
):
    config, host = info.get("Config", {}), info.get("HostConfig", {})
    wanted_env = parsed_environment(image["Config"].get("Env") or [])
    wanted_env.update(environment)
    mounts = info.get("Mounts", [])
    wanted_mounts = (
        mount_sources
        if mount_sources is not None
        else {
            "/installation": value["request"]["root"] + "/secrets/app",
            "/artifacts": value["request"]["root"] + "/artifacts",
        }
    )
    if (
        info.get("Image") != value["images"]["api"]
        or config.get("Labels") != {**binding, resources.LABEL + "role": role}
        or config.get("User") != "10001:10001"
        or config.get("Entrypoint") != (image["Config"].get("Entrypoint") if entrypoint is None else entrypoint)
        or config.get("WorkingDir") != image["Config"].get("WorkingDir")
        or config.get("Healthcheck") != image["Config"].get("Healthcheck")
        or config.get("Cmd") != (["preflight"] if command is None else command)
        or parsed_environment(config.get("Env")) != wanted_env
        or host.get("ReadonlyRootfs") is not True
        or host.get("Privileged") is not False
        or host.get("CapDrop") != ["ALL"]
        or host.get("CapAdd") not in (None, [])
        or host.get("SecurityOpt") != ["no-new-privileges:true"]
        or host.get("PidsLimit") != 64
        or host.get("NanoCpus") != 1_000_000_000
        or host.get("Memory") != 1024**3
        or host.get("PidMode") not in (None, "")
        or host.get("IpcMode") != "private"
        or host.get("UTSMode") not in (None, "")
        or host.get("UsernsMode") not in (None, "")
        or host.get("Devices") not in (None, [])
        or host.get("DeviceRequests") not in (None, [])
        or host.get("Runtime") != "runc"
        or host.get("GroupAdd") not in (None, [])
        or host.get("ExtraHosts") not in (None, [])
        or host.get("Links") not in (None, [])
        or any(host.get(key) not in (None, []) for key in ("Dns", "DnsOptions", "DnsSearch", "VolumesFrom"))
        or host.get("Sysctls") not in (None, {})
        or host.get("PortBindings") not in (None, {})
        or host.get("Tmpfs") != {"/tmp": "rw,noexec,nosuid,size=134217728,uid=10001,gid=10001,mode=700"}
        or set(info.get("NetworkSettings", {}).get("Networks", {})) != {value["prerequisites"]["networks"][0]["name"]}
        or len(mounts) != len(wanted_mounts)
        or {m.get("Destination"): m.get("Source") for m in mounts} != wanted_mounts
        or any(m.get("Type") != "bind" or m.get("RW") is not False for m in mounts)
    ):
        raise checker.planner.PlanError("installation_adopt_preflight_profile_mismatch")


def preflight(value, environment, binding, image):
    name = "declarai-adoption-preflight-" + uuid.uuid4().hex
    args = [
        "container",
        "create",
        "--name",
        name,
        "--pull",
        "never",
        "--network",
        value["prerequisites"]["networks"][0]["name"],
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
        "1g",
        "--pids-limit",
        "64",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=134217728,uid=10001,gid=10001,mode=700",
    ]
    for key, item in {**binding, resources.LABEL + "role": "preflight"}.items():
        args += ["--label", key + "=" + item]
    for key, item in environment.items():
        args += ["--env", key + "=" + item]
    for source, target in [
        (value["request"]["root"] + "/secrets/app", "/installation"),
        (value["request"]["root"] + "/artifacts", "/artifacts"),
    ]:
        args += ["--mount", "type=bind,src=" + source + ",dst=" + target + ",readonly"]
    created = None
    try:
        created = resources.command([*args, value["images"]["api"], "preflight"]).decode().strip()
        if not resources.re.fullmatch(r"[0-9a-f]{64}", created):
            created = None
            raise checker.planner.PlanError("installation_adopt_preflight_response_invalid")
        validate_preflight(resources.inspect("container", created), value, environment, binding, image)
        output = resources.command(["container", "start", "--attach", created], allow_failure=True)
        state = resources.inspect("container", created).get("State", {})
        if (
            state.get("Running") is not False
            or type(state.get("ExitCode")) is not int
            or state["ExitCode"] != 0
            or output.strip() != b"private_service_preflight_passed"
        ):
            raise checker.planner.PlanError("installation_adopt_preflight_failed")
    finally:
        if created:
            resources.command(["container", "rm", "--force", created])


class DeclaredHTTPS(http.client.HTTPSConnection):
    def __init__(self, address, port, host, context):
        super().__init__(host, port=port, context=context, timeout=10)
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, self.port), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def client_context(ca):
    if not ca.is_absolute() or ".." in ca.parts:
        raise checker.planner.PlanError("installation_adopt_client_ca_invalid")
    parent = resources.initializer.trusted_directory(ca.parent)
    try:
        fd = os.open(ca.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or not 0 < info.st_size <= 65536
            or info.st_uid != 0
            or info.st_mode & 0o022
            or info.st_nlink != 1
        ):
            raise checker.planner.PlanError("installation_adopt_client_ca_invalid")
        resources.checker.no_directory_acl(fd)
        data = os.read(fd, 65537)
        after = os.fstat(fd)
        if len(data) != info.st_size or (info.st_mtime_ns, info.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
            raise checker.planner.PlanError("installation_adopt_client_ca_invalid")
        context = ssl.create_default_context(cadata=data.decode("ascii"))
    except (OSError, ssl.SSLError, UnicodeError):
        raise checker.planner.PlanError("installation_adopt_client_ca_invalid") from None
    finally:
        os.close(fd)
    return context


def https_check(request, context):
    host, port = checker.planner.authority(request["authority"])
    connection = DeclaredHTTPS(request["bind_ip"], port, host, context)
    try:
        connection.request("GET", "/api/auth/session/", headers={"Host": request["authority"]})
        response = connection.getresponse()
        body = response.read(16385)
        if (
            response.status != 200
            or len(body) > 16384
            or checker.planner.decode(body).get("authenticated") is not False
        ):
            raise checker.planner.PlanError("installation_adopt_https_session_failed")
    except (OSError, ssl.SSLError, http.client.HTTPException, ValueError, AttributeError):
        raise checker.planner.PlanError("installation_adopt_https_session_failed") from None
    finally:
        connection.close()


def adoption(plan, expected, ca):
    value = checker.verify(plan, expected)
    if value["manifest"]["schema"] != checker.planner.PLAN_SCHEMA:
        raise checker.planner.PlanError("installation_adopt_v2_plan_required_render_new_root")
    if sys.platform != "linux" or os.geteuid() != 0:
        raise checker.planner.PlanError("installation_adopt_linux_root_required")
    initialized = resources.initialization(value)
    if initialized["plan_manifest_sha256"] != expected:
        raise checker.planner.PlanError("installation_adopt_initialization_plan_mismatch")
    checker.check_paths(plan, expected)
    context = client_context(ca)
    resources.docker_host(value["manifest"]["architecture"])
    if resources.record(["info", "--format", "{{json .}}"]).get("DefaultRuntime") != "runc":
        raise checker.planner.PlanError("installation_adopt_default_runtime_required")
    profile, digest, binding = application_profile(value, expected, initialized["initialization_id"])
    images = {role: resources.inspect("image", identity) for role, identity in value["images"].items()}
    for role, image in images.items():
        if (
            image.get("Id") != value["images"][role]
            or image.get("Architecture") != value["manifest"]["architecture"]
            or image.get("Os") != "linux"
        ):
            raise checker.planner.PlanError("installation_adopt_native_images_required")
    existing = {}
    for info in project_containers(profile["name"]):
        role = info.get("Config", {}).get("Labels", {}).get("com.docker.compose.service")
        if role not in ROLES or role in existing:
            raise checker.planner.PlanError("installation_adopt_application_conflict")
        validate_application(
            info,
            role,
            profile["services"][role],
            profile,
            digest,
            binding,
            images["ingress" if role == "ingress" else "api"],
        )
        existing[role] = info
    prerequisites(value, binding, existing)
    preflight(value, profile["services"]["api"]["environment"], binding, images["api"])
    # No .env files or mutable caller Compose path enter the interpreter.
    with tempfile.TemporaryDirectory(prefix="declarai-adoption-") as temporary:
        path = Path(temporary) / "compose.json"
        path.write_bytes(checker.planner.encoded(profile))
        path.chmod(0o600)
        argv = [
            *resources.PREFIX,
            "compose",
            "--env-file",
            "/dev/null",
            "--project-directory",
            temporary,
            "-f",
            str(path),
            "up",
            "--detach",
            "--no-build",
            "--pull",
            "never",
            "--no-recreate",
            *sorted(ROLES),
        ]
        try:
            result = subprocess.run(argv, capture_output=True, timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise checker.planner.PlanError("installation_adopt_start_unavailable") from None
        if result.returncode:
            raise checker.planner.PlanError("installation_adopt_start_failed")
    active = active_applications(profile, digest, binding, images)
    adopted = {
        role: {"container_id": info["Id"], "image_id": info["Image"], "reused": role in existing}
        for role, info in active.items()
    }
    deadline = time.monotonic() + 60
    while True:
        try:
            https_check(value["request"], context)
            break
        except checker.planner.PlanError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)
    # HTTPS may become ready after another service has stopped or changed.
    # Receipt publication must sample the same complete active profiles again,
    # with their bound dependency/socket membership still intact.
    final = active_applications(profile, digest, binding, images)
    if any(final[role]["Id"] != adopted[role]["container_id"] for role in ROLES):
        raise checker.planner.PlanError("installation_adopt_service_identity_changed_during_readiness")
    prerequisites(value, binding, final)
    return {
        **checker.receipt(value, expected),
        "schema": "private_installation_adoption_v1",
        "initialization_id": initialized["initialization_id"],
        "application_profile_sha256": digest,
        "services": adopted,
        "private_runtime_preflight": "passed",
        "anonymous_https_session": "passed",
        "post_https_service_state": "verified",
        "services_adopted": True,
        "model_use_approved": False,
        "production_recovery_qualified": False,
        "host_firewall_qualified": False,
        "ingress_egress_policy_qualified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--client-ca", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(adoption(args.plan, args.expected_plan_sha256, args.client_ca)))


if __name__ == "__main__":
    try:
        main()
    except (checker.planner.PlanError, OSError, ValueError, UnicodeError) as error:
        print(
            str(error) if isinstance(error, checker.planner.PlanError) else "installation_adopt_io_failed",
            file=sys.stderr,
        )
        sys.exit(1)
