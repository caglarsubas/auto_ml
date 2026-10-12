#!/usr/bin/env python3
"""Prepare dedicated private networks and an empty native API socket volume.

The root controller rechecks the plan and fresh initialization. Existing unbound
or occupied resources fail closed; dependencies and application services remain
separate adoption steps. Only the bounded socket initializer runs here.
"""

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import private_installation_check as checker
import private_installation_init as initializer

PREFIX = ["docker", "--context", "default"]
LABEL = "org.declarai.installation."

SOCKET_INIT = r"""
import os,stat
fd=os.open('/run/declarai',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
    s=os.fstat(fd)
    assert not os.listdir(fd),'socket_volume_not_empty'
    assert not {'system.posix_acl_access','system.posix_acl_default'}&set(os.listxattr(fd)),'socket_acl_unsupported'
    identity=(s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))
    assert identity in {(0,0,0o755),(10001,10001,0o750)},'socket_identity_invalid'
    if identity==(0,0,0o755):
        os.fchown(fd,10001,10001);os.fchmod(fd,0o750);os.fsync(fd)
    print('socket_directory_ready')
finally:os.close(fd)
"""


def command(args, *, allow_failure=False):
    try:
        result = subprocess.run([*PREFIX, *args], capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise checker.planner.PlanError("installation_resources_docker_unavailable") from None
    if result.returncode and not allow_failure:
        raise checker.planner.PlanError("installation_resources_docker_failed")
    return result.stdout


def record(args):
    try:
        return checker.planner.decode(command(args))
    except (ValueError, UnicodeError):
        raise checker.planner.PlanError("installation_resources_response_invalid") from None


def initialization(value):
    target = Path(value["request"]["root"])
    descriptor = initializer.trusted_directory(target)
    try:
        info = os.fstat(descriptor)
        if info.st_gid != 10001 or stat.S_IMODE(info.st_mode) != 0o750:
            raise checker.planner.PlanError("installation_resources_root_identity_invalid")
        fd = os.open("initialization.json", os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=descriptor)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
                or not 0 < info.st_size <= 16384
            ):
                raise checker.planner.PlanError("installation_resources_initialization_file_invalid")
            data = stream.read(16385)
    finally:
        os.close(descriptor)
    try:
        result = checker.planner.decode(data)
        identifier = result["initialization_id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise ValueError
        expected = {
            **checker.receipt(value, result["plan_manifest_sha256"]),
            "schema": "private_installation_initialization_v1",
            "initialization_id": identifier,
            "filesystem_initialized": True,
            "secret_files_delivered": sum(map(len, value["prerequisites"]["secret_files"].values())),
            "secret_values_emitted": False,
            "certificate_trust_verified": False,
            "encrypted_storage_verified": False,
            "dependencies_initialized": False,
            "services_adopted": False,
        }
        if checker.planner.encoded(expected) != checker.planner.encoded(result):
            raise ValueError
    except (KeyError, ValueError, TypeError, AttributeError):
        raise checker.planner.PlanError("installation_resources_initialization_invalid") from None
    return result


def docker_host(architecture):
    if any(name in os.environ for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")):
        raise checker.planner.PlanError("installation_resources_remote_docker_rejected")
    endpoint = record(["context", "inspect", "default"])
    if not isinstance(endpoint, list) or len(endpoint) != 1 or not isinstance(endpoint[0], dict):
        raise checker.planner.PlanError("installation_resources_local_docker_required")
    endpoints = endpoint[0].get("Endpoints")
    selected = endpoints.get("docker") if isinstance(endpoints, dict) else None
    if not isinstance(selected, dict) or selected.get("Host") != "unix:///var/run/docker.sock":
        raise checker.planner.PlanError("installation_resources_local_docker_required")
    info = record(["info", "--format", "{{json .}}"])
    if not isinstance(info, dict) or info.get("OSType") != "linux":
        raise checker.planner.PlanError("installation_resources_linux_daemon_required")
    native = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(info.get("Architecture"))
    if native != architecture:
        raise checker.planner.PlanError("installation_resources_native_daemon_required")


def labels(value, expected, identifier):
    return {
        LABEL + "id": value["request"]["installation_id"],
        LABEL + "plan": expected,
        LABEL + "initialization": identifier,
    }


def listing(kind, name):
    lines = command([kind, "ls", "--filter", "name=" + name, "--format", "{{json .}}"])
    try:
        values = [checker.planner.decode(line) for line in lines.splitlines() if line]
        return [v for v in values if v["Name"] == name]
    except (KeyError, TypeError, ValueError):
        raise checker.planner.PlanError("installation_resources_listing_invalid") from None


def inspect(kind, name):
    result = record([kind, "inspect", name])
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
        raise checker.planner.PlanError("installation_resources_response_invalid")
    return result[0]


def validate_network(info, spec, binding):
    if (
        info.get("Name") != spec["name"]
        or info.get("Labels") != binding
        or info.get("Driver") != "bridge"
        or info.get("Scope") != "local"
        or info.get("Internal") is not spec["internal"]
        or info.get("EnableIPv6") is not False
        or info.get("Attachable") is not False
        or info.get("Ingress") is not False
        or info.get("Options")
        not in ({}, {"com.docker.network.enable_ipv4": "true", "com.docker.network.enable_ipv6": "false"})
        or info.get("Containers") != {}
        or not isinstance(info.get("Id"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", info["Id"])
    ):
        raise checker.planner.PlanError("installation_resources_network_conflict")


def validate_volume(info, spec, binding):
    if (
        info.get("Name") != spec["name"]
        or info.get("Labels") != binding
        or info.get("Driver") != "local"
        or info.get("Scope") != "local"
        or info.get("Options") not in (None, {})
    ):
        raise checker.planner.PlanError("installation_resources_volume_conflict")


def socket_volume(spec, image, binding):
    name = spec["name"]
    validate_volume(inspect("volume", name), spec, binding)
    # Reuse is permitted only while the dedicated volume is unoccupied. A
    # running or stopped service using it must be reconciled by adoption instead.
    if command(["container", "ls", "--all", "--filter", "volume=" + name, "--format", "{{.ID}}"]).strip():
        raise checker.planner.PlanError("installation_resources_socket_in_use")
    helper = "declarai-socket-init-" + uuid.uuid4().hex
    created = False
    try:
        args = [
            "container",
            "create",
            "--name",
            helper,
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--user",
            "0:0",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CHOWN",
            "--cap-add",
            "FOWNER",
            "--cap-add",
            "DAC_OVERRIDE",
            "--security-opt",
            "no-new-privileges",
            "--cpus",
            "1",
            "--memory",
            "128m",
            "--pids-limit",
            "32",
            "--mount",
            "type=volume,src=" + name + ",dst=/run/declarai,volume-nocopy",
            "--entrypoint",
            "python",
        ]
        for key, value in binding.items():
            args += ["--label", key + "=" + value]
        command([*args, image, "-c", SOCKET_INIT])
        created = True
        # Container creation can implicitly recreate a deleted volume; recheck
        # the actual mount and ownership labels before starting the initializer.
        current = inspect("container", helper)
        mounts = current.get("Mounts", [])
        if (
            current.get("Image") != image
            or current.get("Config", {}).get("Labels") != binding
            or len(mounts) != 1
            or mounts[0].get("Type") != "volume"
            or mounts[0].get("Name") != name
            or mounts[0].get("Destination") != "/run/declarai"
            or mounts[0].get("RW") is not True
        ):
            raise checker.planner.PlanError("installation_resources_socket_mount_invalid")
        validate_volume(inspect("volume", name), spec, binding)
        output = command(["container", "start", "--attach", helper], allow_failure=True)
        state = inspect("container", helper).get("State", {})
        if (
            output.strip() != b"socket_directory_ready"
            or state.get("Running") is not False
            or type(state.get("ExitCode")) is not int
            or state["ExitCode"] != 0
        ):
            raise checker.planner.PlanError("installation_resources_socket_init_failed")
    finally:
        if created:
            # Remove only our created helper, never a service or a volume.
            command(["container", "rm", "--force", helper])
    return {"name": name, "identity": "10001:10001", "mode": "0750", "empty": True}


def provision(value, expected, identifier):
    image = inspect("image", value["images"]["api"])
    if (
        image.get("Id") != value["images"]["api"]
        or image.get("Os") != "linux"
        or image.get("Architecture") != value["manifest"]["architecture"]
    ):
        raise checker.planner.PlanError("installation_resources_native_image_required")
    binding = labels(value, expected, identifier)
    networks = []
    for spec in value["prerequisites"]["networks"]:
        name = spec["name"]
        if not listing("network", name):
            args = ["network", "create", "--driver", "bridge", *(["--internal"] if spec["internal"] else [])]
            for key, item in binding.items():
                args += ["--label", key + "=" + item]
            command([*args, name])
        info = inspect("network", name)
        validate_network(info, spec, binding)
        networks.append({"name": name, "id": info["Id"], "internal": spec["internal"]})
    volume = value["prerequisites"]["socket_volume"]
    if not listing("volume", volume["name"]):
        args = ["volume", "create", "--driver", "local"]
        for key, item in binding.items():
            args += ["--label", key + "=" + item]
        command([*args, volume["name"]])
    socket = socket_volume(volume, value["images"]["api"], binding)
    return {
        **checker.receipt(value, expected),
        "schema": "private_installation_resources_v1",
        "initialization_id": identifier,
        "networks": networks,
        "socket_volume": socket,
        "resources_prepared": True,
        "dependencies_initialized": False,
        "services_adopted": False,
        "existing_resources_repaired": False,
    }


def prepare(plan, expected):
    value = checker.verify(plan, expected)
    if sys.platform != "linux" or os.geteuid() != 0:
        raise checker.planner.PlanError("installation_resources_linux_root_required")
    result = initialization(value)
    if result["plan_manifest_sha256"] != expected:
        raise checker.planner.PlanError("installation_resources_initialization_plan_mismatch")
    checker.check_paths(plan, expected)
    docker_host(value["manifest"]["architecture"])
    return provision(value, expected, result["initialization_id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.plan, args.expected_plan_sha256)))


if __name__ == "__main__":
    try:
        main()
    except (checker.planner.PlanError, OSError, ValueError, UnicodeError) as error:
        print(
            str(error) if isinstance(error, checker.planner.PlanError) else "installation_resources_io_failed",
            file=sys.stderr,
        )
        sys.exit(1)
