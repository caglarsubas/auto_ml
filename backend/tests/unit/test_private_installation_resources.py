"""Dedicated resource binding, conflict rejection and initialization trust checks."""

import importlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401
from tests.unit.test_private_installation_plan import compatible, planner, request_value  # noqa: F401
from tests.unit.test_private_installation_check import checker, saved_plan  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def resources(planner):
    return importlib.import_module("private_installation_resources")


@pytest.fixture
def binding(resources, saved_plan):
    root, expected = saved_plan
    value = resources.checker.verify(root, expected)
    return value, expected, resources.labels(value, expected, "a" * 32)


def network(spec, binding):
    return {
        "Name": spec["name"],
        "Labels": binding,
        "Driver": "bridge",
        "Scope": "local",
        "Internal": spec["internal"],
        "EnableIPv6": False,
        "Attachable": False,
        "Ingress": False,
        "Options": {},
        "Containers": {},
        "Id": "1" * 64,
    }


def volume(spec, binding):
    return {"Name": spec["name"], "Labels": binding, "Driver": "local", "Scope": "local", "Options": None}


@pytest.mark.parametrize("actual", [False, True, 0])
def test_v2_ingress_requires_exact_publishing_bridge_without_changing_private_network(resources, binding, actual):
    value, _, labels = binding
    private, edge = value["prerequisites"]["networks"]
    assert private["internal"] is True and edge["internal"] is False
    info = network(edge, labels)
    info["Internal"] = actual
    if actual is False:
        resources.validate_network(info, edge, labels)
    else:
        with pytest.raises(resources.checker.planner.PlanError, match="network_conflict"):
            resources.validate_network(info, edge, labels)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("Name", "other"),
        ("Labels", {}),
        ("Labels", None),
        ("Driver", "host"),
        ("Scope", "swarm"),
        ("Internal", False),
        ("Internal", 1),
        ("EnableIPv6", True),
        ("Attachable", True),
        ("Ingress", True),
        ("Options", {"com.docker.network.bridge.name": "existing"}),
        ("Containers", {"existing": {}}),
        ("Id", "not-an-id"),
    ],
)
def test_network_conflicts_are_rejected_without_repair(resources, binding, field, bad):
    value, _, labels = binding
    spec = value["prerequisites"]["networks"][0]
    info = network(spec, labels)
    info[field] = bad
    with pytest.raises(resources.checker.planner.PlanError, match="network_conflict"):
        resources.validate_network(info, spec, labels)


@pytest.mark.parametrize(
    "options", [{}, {"com.docker.network.enable_ipv4": "true", "com.docker.network.enable_ipv6": "false"}]
)
def test_native_default_ipv4_serialization_retains_internal_network_boundary(resources, binding, options):
    value, _, labels = binding
    spec = value["prerequisites"]["networks"][0]
    info = network(spec, labels)
    info["Options"] = options
    resources.validate_network(info, spec, labels)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("Name", "other"),
        ("Labels", {}),
        ("Driver", "nfs"),
        ("Scope", "swarm"),
        ("Options", {"type": "none", "device": "/"}),
    ],
)
def test_volume_conflicts_reject_host_driver_overrides(resources, binding, field, bad):
    value, _, labels = binding
    spec = value["prerequisites"]["socket_volume"]
    info = volume(spec, labels)
    info[field] = bad
    with pytest.raises(resources.checker.planner.PlanError, match="volume_conflict"):
        resources.validate_volume(info, spec, labels)


def test_binding_includes_plan_and_initialization_identifiers(resources, binding):
    value, expected, labels = binding
    assert labels == {
        resources.LABEL + "id": value["request"]["installation_id"],
        resources.LABEL + "plan": expected,
        resources.LABEL + "initialization": "a" * 32,
    }


def test_unbound_existing_network_blocks_before_any_create(resources, binding, monkeypatch):
    value, expected, labels = binding
    monkeypatch.setattr(resources, "listing", lambda *a: [{"Name": a[1]}])

    def inspect(kind, name):
        if kind == "image":
            return {"Id": value["images"]["api"], "Os": "linux", "Architecture": value["manifest"]["architecture"]}
        return network(value["prerequisites"]["networks"][0], {})

    monkeypatch.setattr(resources, "inspect", inspect)
    monkeypatch.setattr(resources, "command", lambda *a: pytest.fail("foreign resource modified"))
    with pytest.raises(resources.checker.planner.PlanError, match="network_conflict"):
        resources.provision(value, expected, "a" * 32)


def test_wrong_native_image_blocks_before_resource_mutations(resources, binding, monkeypatch):
    value, expected, _ = binding
    monkeypatch.setattr(
        resources, "inspect", lambda *a: {"Id": value["images"]["api"], "Os": "linux", "Architecture": "unsupported"}
    )
    monkeypatch.setattr(resources, "listing", lambda *a: pytest.fail("wrong image inspected resources"))
    with pytest.raises(resources.checker.planner.PlanError, match="native_image_required"):
        resources.provision(value, expected, "a" * 32)


def test_preparation_reuses_bound_empty_networks_and_never_creates_services(resources, binding, monkeypatch):
    value, expected, labels = binding
    calls = []
    monkeypatch.setattr(resources, "listing", lambda *a: [{"Name": a[1]}])

    def inspect(kind, name):
        if kind == "image":
            return {"Id": value["images"]["api"], "Os": "linux", "Architecture": value["manifest"]["architecture"]}
        return network(next(s for s in value["prerequisites"]["networks"] if s["name"] == name), labels)

    monkeypatch.setattr(resources, "inspect", inspect)
    monkeypatch.setattr(resources, "command", lambda a: calls.append(a) or b"")
    monkeypatch.setattr(
        resources,
        "socket_volume",
        lambda spec, image, b: {"name": spec["name"], "identity": "10001:10001", "mode": "0750", "empty": True},
    )
    result = resources.provision(value, expected, "a" * 32)
    assert result["resources_prepared"] and not result["services_adopted"] and not result["dependencies_initialized"]
    assert not calls


def test_occupied_socket_volume_is_never_opened_by_initializer(resources, binding, monkeypatch):
    value, _, labels = binding
    spec = value["prerequisites"]["socket_volume"]
    calls = []
    monkeypatch.setattr(resources, "inspect", lambda *a: volume(spec, labels))
    monkeypatch.setattr(resources, "command", lambda a: calls.append(a) or b"existing-container")
    with pytest.raises(resources.checker.planner.PlanError, match="socket_in_use"):
        resources.socket_volume(spec, value["images"]["api"], labels)
    assert len(calls) == 1 and calls[0][:2] == ["container", "ls"]


@pytest.mark.parametrize("fault", ["wrong_mount", "lost_binding", "failed_exit"])
def test_socket_initializer_rechecks_mount_and_binding_and_cleans_only_own_helper(
    resources, binding, monkeypatch, fault
):
    value, _, labels = binding
    spec = value["prerequisites"]["socket_volume"]
    calls = []
    image = value["images"]["api"]
    volume_reads = 0

    def inspect(kind, name):
        nonlocal volume_reads
        if kind == "volume":
            volume_reads += 1
            return volume(spec, {} if fault == "lost_binding" and volume_reads == 2 else labels)
        return {
            "Image": image,
            "Config": {"Labels": labels},
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": "other" if fault == "wrong_mount" else spec["name"],
                    "Destination": "/run/declarai",
                    "RW": True,
                }
            ],
            "State": {"Running": False, "ExitCode": 1 if fault == "failed_exit" else 0},
        }

    def command(args, **kwargs):
        calls.append(args)
        return b"socket_directory_ready" if args[:2] == ["container", "start"] else b""

    monkeypatch.setattr(resources, "inspect", inspect)
    monkeypatch.setattr(resources, "command", command)
    with pytest.raises(
        resources.checker.planner.PlanError, match="socket_mount_invalid|volume_conflict|socket_init_failed"
    ):
        resources.socket_volume(spec, image, labels)
    assert calls[-1][:3] == ["container", "rm", "--force"]
    assert calls[-1][-1].startswith("declarai-socket-init-")
    assert not any(c[:2] in [["network", "rm"], ["volume", "rm"]] for c in calls)
    if fault != "failed_exit":
        assert not any(c[:2] == ["container", "start"] for c in calls)


@pytest.mark.parametrize("name", ["DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"])
def test_docker_overrides_reject_before_any_call(resources, monkeypatch, name):
    monkeypatch.setenv(name, "unused")
    monkeypatch.setattr(resources, "record", lambda *a: pytest.fail("override called Docker"))
    with pytest.raises(resources.checker.planner.PlanError, match="remote_docker_rejected"):
        resources.docker_host("arm64")


def test_remote_context_rejected(resources, monkeypatch):
    for name in ["DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(resources, "record", lambda *a: [{"Endpoints": {"docker": {"Host": "tcp://remote"}}}])
    with pytest.raises(resources.checker.planner.PlanError, match="local_docker_required"):
        resources.docker_host("arm64")


def test_docker_failure_is_not_treated_as_missing_resource(resources, monkeypatch):
    monkeypatch.setattr(
        resources.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout=b"", stderr=b"credential-bearing daemon error"),
    )
    with pytest.raises(resources.checker.planner.PlanError, match="docker_failed") as e:
        resources.listing("network", "name")
    assert "credential" not in str(e.value)


def test_plan_verification_precedes_any_installation_or_docker_access(resources, saved_plan, monkeypatch):
    plan, expected = saved_plan
    (plan / "compose.json").write_text("tamper")
    monkeypatch.setattr(resources, "initialization", lambda *a: pytest.fail("bad plan inspected installation"))
    monkeypatch.setattr(resources, "docker_host", lambda *a: pytest.fail("bad plan touched Docker"))
    with pytest.raises(resources.checker.planner.PlanError, match="digest_mismatch"):
        resources.prepare(plan, expected)


def test_wrong_initialization_plan_blocks_before_paths_or_docker(resources, saved_plan, monkeypatch):
    plan, expected = saved_plan
    monkeypatch.setattr(resources.sys, "platform", "linux")
    monkeypatch.setattr(resources.os, "geteuid", lambda: 0)
    monkeypatch.setattr(resources, "initialization", lambda *a: {"plan_manifest_sha256": "0" * 64})
    monkeypatch.setattr(
        resources.checker, "check_paths", lambda *a: pytest.fail("mismatched initialization read paths")
    )
    with pytest.raises(resources.checker.planner.PlanError, match="initialization_plan_mismatch"):
        resources.prepare(plan, expected)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("filesystem_initialized", 1),
        ("services_adopted", True),
        ("secret_files_delivered", 9.0),
        ("initialization_id", "NOT-A-UUID"),
        ("extra", True),
    ],
)
def test_initialization_record_shape_and_types_are_bound_to_fresh_profile(
    resources, binding, tmp_path, monkeypatch, field, bad
):
    value, expected, _ = binding
    target = tmp_path / "installation"
    target.mkdir(mode=0o750)
    result = {
        **resources.checker.receipt(value, expected),
        "schema": "private_installation_initialization_v1",
        "initialization_id": "a" * 32,
        "filesystem_initialized": True,
        "secret_files_delivered": 9,
        "secret_values_emitted": False,
        "certificate_trust_verified": False,
        "encrypted_storage_verified": False,
        "dependencies_initialized": False,
        "services_adopted": False,
    }
    result[field] = bad
    (target / "initialization.json").write_text(json.dumps(result))
    (target / "initialization.json").chmod(0o600)
    value["request"]["root"] = str(target)
    monkeypatch.setattr(
        resources.initializer, "trusted_directory", lambda *a: os.open(target, resources.initializer.DIRECTORY_FLAGS)
    )
    original = os.fstat

    def fstat(fd):
        r = original(fd)
        attrs = {n: getattr(r, n) for n in dir(r) if n.startswith("st_")}
        attrs.update(st_uid=0, st_gid=10001 if stat.S_ISDIR(r.st_mode) else 0)
        return SimpleNamespace(**attrs)

    monkeypatch.setattr(resources.os, "fstat", fstat)
    with pytest.raises(resources.checker.planner.PlanError, match="initialization_invalid"):
        resources.initialization(value)


@pytest.mark.parametrize(
    "native,expected", [("aarch64", "arm64"), ("arm64", "arm64"), ("x86_64", "amd64"), ("amd64", "amd64")]
)
def test_local_linux_daemon_must_match_plan_architecture(resources, monkeypatch, native, expected):
    for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        resources,
        "record",
        lambda a: (
            [{"Endpoints": {"docker": {"Host": "unix:///var/run/docker.sock"}}}]
            if a[0] == "context"
            else {"OSType": "linux", "Architecture": native}
        ),
    )
    resources.docker_host(expected)
    with pytest.raises(resources.checker.planner.PlanError, match="native_daemon_required"):
        resources.docker_host("amd64" if expected == "arm64" else "arm64")


@pytest.mark.parametrize("endpoint", [None, [], [None], [{"Endpoints": None}], [{"Endpoints": {"docker": None}}]])
def test_malformed_docker_context_fails_closed(resources, monkeypatch, endpoint):
    for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(resources, "record", lambda *a: endpoint)
    with pytest.raises(resources.checker.planner.PlanError, match="local_docker_required"):
        resources.docker_host("arm64")
