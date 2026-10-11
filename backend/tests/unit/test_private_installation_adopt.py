"""Exact application adoption profile and private preflight boundaries."""

import copy
import importlib
from types import SimpleNamespace

import pytest

from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401
from tests.unit.test_private_installation_plan import compatible, planner, request_value  # noqa: F401
from tests.unit.test_private_installation_check import checker, saved_plan  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def adopter(planner):
    return importlib.import_module("private_installation_adopt")


@pytest.fixture
def profile(adopter, saved_plan):
    plan, expected = saved_plan
    value = adopter.checker.verify(plan, expected)
    composition, digest, labels = adopter.application_profile(value, expected, "a" * 32)
    image = {
        "Config": {
            "Env": ["PATH=/trusted/bin"],
            "Entrypoint": ["python", "/app/scripts/private_service.py"],
            "WorkingDir": "/app/backend",
            "Cmd": ["api"],
        }
    }
    return value, composition, digest, labels, image


def application(role, profile):
    value, composition, digest, labels, image = profile
    service = composition["services"][role]
    env = dict(item.split("=", 1) for item in image["Config"]["Env"])
    env.update(service.get("environment", {}))
    mounts = []
    for mount in service["volumes"]:
        item = {"Type": mount["type"], "Destination": mount["target"], "RW": not mount.get("read_only", False)}
        item["Name" if mount["type"] == "volume" else "Source"] = (
            composition["volumes"]["api-socket"]["name"] if mount["type"] == "volume" else mount["source"]
        )
        mounts.append(item)
    ports = {}
    if role == "ingress":
        p = service["ports"][0]
        ports = {"8443/tcp": [{"HostIp": p["host_ip"], "HostPort": p["published"]}]}
    return {
        "Id": role + "-id",
        "Image": service["image"],
        "State": {"Running": True},
        "Config": {
            "User": "10001:10001",
            "Entrypoint": image["Config"]["Entrypoint"],
            "WorkingDir": image["Config"]["WorkingDir"],
            "StopTimeout": 60,
            "Cmd": service.get("command", image["Config"]["Cmd"]),
            "Env": [k + "=" + v for k, v in env.items()],
            "Labels": {
                **service["labels"],
                "com.docker.compose.project": composition["name"],
                "com.docker.compose.service": role,
                "com.docker.compose.oneoff": "False",
            },
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "CapAdd": None,
            "SecurityOpt": ["no-new-privileges:true"],
            "PidsLimit": service["pids_limit"],
            "NanoCpus": service["cpus"] * 1_000_000_000,
            "Memory": 256 * 1024**2 if role == "ingress" else 2 * 1024**3,
            "PidMode": "",
            "IpcMode": "private",
            "UTSMode": "",
            "UsernsMode": "",
            "DeviceRequests": None,
            "Runtime": "runc",
            "Devices": [],
            "Tmpfs": {"/tmp": service["tmpfs"][0].removeprefix("/tmp:")},
            "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 3},
            "PortBindings": ports,
        },
        "NetworkSettings": {
            "Ports": copy.deepcopy(ports),
            "Networks": {composition["networks"][name]["name"]: {} for name in service["networks"]},
        },
        "Mounts": mounts,
    }


@pytest.mark.parametrize("role", ["api", "worker", "dispatcher", "ingress"])
def test_exact_application_profile_is_inspectable_without_secret_values(adopter, profile, role):
    _, composition, digest, binding, image = profile
    info = application(role, profile)
    adopter.validate_application(info, role, composition["services"][role], composition, digest, binding, image)
    assert not any("PASSWORD=" in value for value in info["Config"]["Env"])


def test_requested_https_port_does_not_substitute_for_actual_publication(adopter, profile):
    _, composition, digest, binding, image = profile
    info = application("ingress", profile)
    info["NetworkSettings"]["Ports"] = {"8443/tcp": None}
    with pytest.raises(adopter.checker.planner.PlanError, match="https_port_not_published"):
        adopter.validate_application(
            info, "ingress", composition["services"]["ingress"], composition, digest, binding, image
        )


def test_trusted_image_unpublished_port_is_not_a_host_binding(adopter, profile):
    _, composition, digest, binding, image = profile
    image["Config"]["ExposedPorts"] = {"80/tcp": {}, "8443/tcp": {}}
    info = application("ingress", profile)
    info["NetworkSettings"]["Ports"]["80/tcp"] = None
    adopter.validate_application(
        info, "ingress", composition["services"]["ingress"], composition, digest, binding, image
    )


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "80"}]},
        {"8443/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8443"}]},
        {"8443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "1"}]},
    ],
)
def test_only_exact_actual_https_binding_is_accepted(adopter, profile, bad):
    _, composition, digest, binding, image = profile
    image["Config"]["ExposedPorts"] = {"80/tcp": {}, "8443/tcp": {}}
    info = application("ingress", profile)
    info["NetworkSettings"]["Ports"] = bad
    with pytest.raises(adopter.checker.planner.PlanError, match="https_port_not_published"):
        adopter.validate_application(
            info, "ingress", composition["services"]["ingress"], composition, digest, binding, image
        )


@pytest.mark.parametrize("bindings", [None, [], [{"HostIp": "127.0.0.1", "HostPort": "80"}]])
def test_additional_actual_port_cannot_hide_behind_valid_https(adopter, profile, bindings):
    _, composition, digest, binding, image = profile
    image["Config"]["ExposedPorts"] = {"80/tcp": {}, "8443/tcp": {}}
    info = application("ingress", profile)
    info["NetworkSettings"]["Ports"]["9999/tcp"] = bindings
    with pytest.raises(adopter.checker.planner.PlanError, match="https_port_not_published"):
        adopter.validate_application(
            info, "ingress", composition["services"]["ingress"], composition, digest, binding, image
        )


@pytest.mark.parametrize(
    "part,field,bad",
    [
        ("Config", "User", "0:0"),
        ("Config", "Cmd", ["expert.py"]),
        ("Config", "Entrypoint", ["sh", "-c"]),
        ("Config", "WorkingDir", "/tmp"),
        ("Config", "StopTimeout", 0),
        ("Config", "Healthcheck", {"Test": ["CMD", "expert.py"]}),
        ("HostConfig", "Privileged", True),
        ("HostConfig", "ReadonlyRootfs", False),
        ("HostConfig", "ReadonlyRootfs", 1),
        ("HostConfig", "CapDrop", []),
        ("HostConfig", "CapAdd", ["SYS_ADMIN"]),
        ("HostConfig", "SecurityOpt", []),
        ("HostConfig", "PidMode", "host"),
        ("HostConfig", "IpcMode", "host"),
        ("HostConfig", "UTSMode", "host"),
        ("HostConfig", "UsernsMode", "host"),
        ("HostConfig", "DeviceRequests", [{"Driver": "nvidia"}]),
        ("HostConfig", "Runtime", "nvidia"),
        ("HostConfig", "GroupAdd", ["0"]),
        ("HostConfig", "ExtraHosts", ["postgres:192.168.1.1"]),
        ("HostConfig", "Links", ["foreign:cache"]),
        ("HostConfig", "Dns", ["8.8.8.8"]),
        ("HostConfig", "DnsOptions", ["use-vc"]),
        ("HostConfig", "DnsSearch", ["outside.example"]),
        ("HostConfig", "VolumesFrom", ["foreign"]),
        ("HostConfig", "Sysctls", {"net.ipv4.ip_forward": "1"}),
        ("HostConfig", "PidsLimit", -1),
        ("HostConfig", "Memory", 0),
        ("HostConfig", "NanoCpus", 0),
        ("HostConfig", "Devices", [{"PathOnHost": "/dev/sda"}]),
        ("HostConfig", "Tmpfs", {}),
        ("HostConfig", "RestartPolicy", {"Name": "always", "MaximumRetryCount": 0}),
    ],
)
def test_changed_service_profile_cannot_be_silently_reused(adopter, profile, part, field, bad):
    _, composition, digest, binding, image = profile
    info = application("api", profile)
    info[part][field] = bad
    with pytest.raises(adopter.checker.planner.PlanError, match="profile_mismatch"):
        adopter.validate_application(info, "api", composition["services"]["api"], composition, digest, binding, image)


@pytest.mark.parametrize(
    "fault",
    [
        "image",
        "binding",
        "profile_digest",
        "oneoff",
        "network",
        "mount",
        "extra_mount",
        "writable_secret",
        "port",
        "environment",
    ],
)
def test_identity_network_mount_and_environment_conflicts_stop_adoption(adopter, profile, fault):
    _, composition, digest, binding, image = profile
    info = application("api", profile)
    if fault == "image":
        info["Image"] = "sha256:" + "f" * 64
    elif fault in {"binding", "profile_digest"}:
        info["Config"]["Labels"][adopter.resources.LABEL + ("plan" if fault == "binding" else "profile")] = "f" * 64
    elif fault == "oneoff":
        info["Config"]["Labels"]["com.docker.compose.oneoff"] = "True"
    elif fault == "network":
        info["NetworkSettings"]["Networks"] = {"external": {}}
    elif fault == "mount":
        info["Mounts"][0]["Source"] = "/other"
    elif fault == "extra_mount":
        info["Mounts"].append({"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/socket", "RW": True})
    elif fault == "writable_secret":
        info["Mounts"][0]["RW"] = True
    elif fault == "port":
        info["HostConfig"]["PortBindings"] = {"8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8000"}]}
    else:
        info["Config"]["Env"].append("PYTHONPATH=/unapproved")
    with pytest.raises(adopter.checker.planner.PlanError):
        adopter.validate_application(info, "api", composition["services"]["api"], composition, digest, binding, image)


def test_untrusted_plan_blocks_before_host_or_docker_access(adopter, saved_plan, monkeypatch, tmp_path):
    plan, expected = saved_plan
    (plan / "compose.json").write_text("tampered")
    monkeypatch.setattr(adopter.resources, "initialization", lambda *a: pytest.fail("untrusted plan read installation"))
    with pytest.raises(adopter.checker.planner.PlanError, match="digest_mismatch"):
        adopter.adoption(plan, expected, tmp_path / "ca.crt")


@pytest.mark.parametrize("values", [["KEY=1", "KEY=2"], ["KEY"], [True], None])
def test_environment_representation_is_unambiguous(adopter, values):
    with pytest.raises(adopter.checker.planner.PlanError, match="environment_invalid"):
        adopter.parsed_environment(values)


@pytest.mark.parametrize("row", [(False,) * 5, (False,) * 5 + (True,), (False,) * 5 + (0,), None])
def test_private_application_role_check_rejects_missing_or_elevated_authority(monkeypatch, row):
    from execution_jobs import preflight

    cursor = SimpleNamespace(execute=lambda *a: None, fetchone=lambda: row)

    class Context:
        def __enter__(self):
            return cursor

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(preflight, "connection", SimpleNamespace(vendor="postgresql", cursor=Context))
    with pytest.raises(preflight.RuntimeUnavailable, match="application_role_elevated"):
        preflight.check_application_role()


def test_private_application_role_query_checks_server_and_cross_database_grants(monkeypatch):
    from execution_jobs import preflight

    statements = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, statement):
            statements.append(statement)

        def fetchone(self):
            return (False,) * 6

    monkeypatch.setattr(preflight, "connection", SimpleNamespace(vendor="postgresql", cursor=Cursor))
    preflight.check_application_role()
    assert (
        "pg_execute_server_program" in statements[0]
        and "pg_read_all_data" in statements[0]
        and "pg_has_role" in statements[0]
        and "privileged.rolsuper" in statements[0]
    )


def test_fixed_preflight_role_returns_without_launching_services(planner, monkeypatch, capsys):
    service = importlib.import_module("private_service")
    calls = []
    monkeypatch.setenv("DECLARAI_RUNTIME_PROFILE", "private")
    monkeypatch.setenv("DJANGO_TRUST_PROXY_TLS", "true")
    for name in (
        "GUNICORN_CMD_ARGS",
        "FORWARDED_ALLOW_IPS",
        "PYTHONPATH",
        "PYTHONHOME",
        "PROMETA_SKILLS_DIR",
        "DJANGO_SETTINGS_MODULE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(service.os, "geteuid", lambda: 10001)
    monkeypatch.setattr(service.os, "getegid", lambda: 10001)
    monkeypatch.setattr(service, "verify", lambda *a: None)
    monkeypatch.setattr(service.os, "chdir", lambda *a: None)
    monkeypatch.setattr(service.subprocess, "run", lambda a, **k: calls.append(a) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(service.os, "execv", lambda *a: pytest.fail("preflight started a service"))
    service.launch(["preflight"])
    assert (
        calls[0][-1] == "--require-application-role"
        and capsys.readouterr().out.strip() == "private_service_preflight_passed"
    )


@pytest.mark.parametrize("fault", ["ca", "preflight", "existing"])
def test_failed_approval_prerequisites_never_start_application_services(
    adopter, saved_plan, profile, monkeypatch, tmp_path, fault
):
    plan, expected = saved_plan
    value, composition, digest, binding, image = profile
    monkeypatch.setattr(adopter.sys, "platform", "linux")
    monkeypatch.setattr(adopter.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        adopter.resources,
        "initialization",
        lambda *a: {"plan_manifest_sha256": expected, "initialization_id": "a" * 32},
    )
    monkeypatch.setattr(adopter.checker, "check_paths", lambda *a: None)
    monkeypatch.setattr(
        adopter.subprocess, "run", lambda *a, **kw: pytest.fail("failed prerequisite started application")
    )

    def blocked(*a):
        raise adopter.checker.planner.PlanError("test_prerequisite_failed")

    monkeypatch.setattr(adopter, "client_context", blocked if fault == "ca" else lambda *a: object())
    monkeypatch.setattr(
        adopter.resources, "docker_host", lambda *a: pytest.fail("invalid CA reached Docker") if fault == "ca" else None
    )

    def inspected(kind, identifier):
        return {"Id": identifier, "Architecture": value["manifest"]["architecture"], "Os": "linux", **image}

    monkeypatch.setattr(adopter.resources, "inspect", inspected)
    monkeypatch.setattr(adopter.resources, "record", lambda *a: {"DefaultRuntime": "runc"})
    info = application("api", profile)
    info["Config"]["Cmd"] = ["foreign"]
    monkeypatch.setattr(adopter, "project_containers", lambda *a: [info] if fault == "existing" else [])
    monkeypatch.setattr(adopter, "prerequisites", lambda *a: None)
    monkeypatch.setattr(adopter, "preflight", blocked)
    with pytest.raises(adopter.checker.planner.PlanError):
        adopter.adoption(plan, expected, tmp_path / "ca.crt")


@pytest.mark.parametrize("fault", [None, "image", "network", "mount", "writable", "privileged", "environment"])
def test_preflight_cannot_run_with_changed_data_or_authority(adopter, profile, fault):
    value, composition, _, binding, image = profile
    info = application("api", profile)
    info["Config"]["Cmd"] = ["preflight"]
    info["Config"]["Labels"] = {**binding, adopter.resources.LABEL + "role": "preflight"}
    info["HostConfig"].update(PidsLimit=64, NanoCpus=1_000_000_000, Memory=1024**3)
    info["Mounts"] = [m for m in info["Mounts"] if m["Type"] == "bind"]
    for mount in info["Mounts"]:
        mount["RW"] = False
    if fault == "image":
        info["Image"] = "changed"
    elif fault == "network":
        info["NetworkSettings"]["Networks"] = {"public": {}}
    elif fault == "mount":
        info["Mounts"][0]["Source"] = "/unapproved"
    elif fault == "writable":
        info["Mounts"][0]["RW"] = True
    elif fault == "privileged":
        info["HostConfig"]["Privileged"] = True
    elif fault == "environment":
        info["Config"]["Env"] = [
            "OPENAI_API_KEY=external" if v.startswith("OPENAI_API_KEY=") else v for v in info["Config"]["Env"]
        ]
    args = (info, value, composition["services"]["api"]["environment"], binding, image)
    if fault is None:
        adopter.validate_preflight(*args)
    else:
        with pytest.raises(adopter.checker.planner.PlanError, match="preflight_profile_mismatch"):
            adopter.validate_preflight(*args)


@pytest.mark.parametrize("ca", ["relative.pem", "/srv/../etc/ca.pem"])
def test_client_ca_requires_exact_absolute_non_traversing_path(adopter, ca):
    from pathlib import Path

    with pytest.raises(adopter.checker.planner.PlanError, match="client_ca_invalid"):
        adopter.client_context(Path(ca))


def test_legacy_plan_remains_verifiable_but_cannot_adopt_or_touch_host(adopter, saved_plan, monkeypatch, tmp_path):
    import hashlib
    import json

    plan, _ = saved_plan
    manifest = json.loads((plan / "manifest.json").read_text())
    request = json.loads((plan / "request.json").read_text())
    outer = json.loads((plan / "image-set.json").read_text())
    images = {k: v["image_id"] for k, v in outer["components"].items()}
    historical = adopter.checker.planner.prerequisites(request, images, legacy=True)
    (plan / "prerequisites.json").write_bytes(adopter.checker.planner.encoded(historical))
    manifest["schema"] = "private_installation_plan_v1"
    manifest["files"]["prerequisites.json"] = hashlib.sha256((plan / "prerequisites.json").read_bytes()).hexdigest()
    data = adopter.checker.planner.encoded(manifest)
    (plan / "manifest.json").write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    before = {p.name: p.read_bytes() for p in plan.iterdir()}
    value = adopter.checker.verify(plan, expected)
    assert value["manifest"]["schema"] == "private_installation_plan_v1"
    assert all(n["internal"] is True for n in value["prerequisites"]["networks"])
    monkeypatch.setattr(adopter.resources, "initialization", lambda *a: pytest.fail("legacy plan touched host"))
    with pytest.raises(adopter.checker.planner.PlanError, match="v2_plan_required_render_new_root"):
        adopter.adoption(plan, expected, tmp_path / "ca.pem")
    assert before == {p.name: p.read_bytes() for p in plan.iterdir()}
