"""Dependency authority, exact profiles, secret handling and immutable receipts."""

import copy
import importlib
from types import SimpleNamespace

import pytest

from tests.unit.test_private_installation_plan import compatible, planner, request_value  # noqa: F401
from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401
from tests.unit.test_private_installation_check import checker, saved_plan  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def startup(planner):
    return importlib.import_module("private_dependency_start")


@pytest.fixture
def context(startup, saved_plan):
    plan, expected = saved_plan
    value = startup.checker.verify(plan, expected)
    spec = startup.preparation.profile(value, expected, "a" * 32)
    receipt = {
        "plan_manifest_sha256": expected,
        "initialization_id": "a" * 32,
        "dependency_initialization_id": "b" * 32,
        "dependency_profile_sha256": "c" * 64,
    }
    image = {"Config": {"Env": ["PATH=/trusted/bin"], "WorkingDir": ""}}
    return value, spec, receipt, image


def container(startup, context, role):
    value, spec, receipt, image = context
    service = spec["services"][role]
    env = {"PATH": "/trusted/bin", **service["environment"]}
    return {
        "Id": {"postgres": "1", "job-broker": "2", "cache": "3"}[role] * 64,
        "Name": "/" + startup.names(value)[role],
        "Image": service["image_id"],
        "Config": {
            "Labels": {**startup.labels(value, receipt), startup.LABEL + "role": role},
            "User": f"{service['uid']}:{service['gid']}",
            "Entrypoint": service["entrypoint"],
            "Cmd": service["command"],
            "WorkingDir": image["Config"]["WorkingDir"],
            "StopTimeout": 60,
            "Env": [k + "=" + v for k, v in env.items()],
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "CapAdd": None,
            "SecurityOpt": ["no-new-privileges:true"],
            "PidsLimit": service["pids"],
            "NanoCpus": service["cpus"] * 1_000_000_000,
            "Memory": service["memory_bytes"],
            "MemorySwap": service["memory_bytes"],
            "Tmpfs": service["tmpfs"],
            "RestartPolicy": service["restart"],
            "Runtime": "runc",
            "IpcMode": "private",
            "CgroupnsMode": "private",
            "ShmSize": 64 * 1024**2,
            "PortBindings": {},
            "PidMode": "",
            "UTSMode": "",
            "UsernsMode": "",
        },
        "NetworkSettings": {"Networks": {spec["private_network"]: {"Aliases": [role]}}, "Ports": {}},
        "State": {"Running": True, "Paused": False, "Restarting": False, "Dead": False},
        "Mounts": [
            {"Destination": m["target"], "Source": m["source"], "RW": not m["read_only"], "Type": "bind"}
            for m in service["mounts"]
        ],
    }


@pytest.mark.parametrize("role", ["postgres", "job-broker", "cache"])
def test_exact_dependency_profiles_are_active_and_nonprivileged(startup, context, role):
    value, spec, receipt, image = context
    startup.validate(
        container(startup, context, role),
        role,
        spec,
        startup.labels(value, receipt),
        image,
        startup.names(value)[role],
        True,
    )
    args = startup.create_args(role, value, spec, receipt)
    assert "--pull" in args and args[args.index("--pull") + 1] == "never" and "--publish" not in args
    assert all("owner-password" not in item or item.endswith("/installation/owner-password") for item in args)


@pytest.mark.parametrize("fault", [None, "changed", "extra"])
def test_only_exact_trusted_image_labels_accompany_installation_binding(startup, context, fault):
    value, spec, receipt, image = context
    image["Config"]["Labels"] = {"org.declarai.private.component": "postgres"}
    info = container(startup, context, "postgres")
    info["Config"]["Labels"].update(image["Config"]["Labels"])
    if fault == "changed":
        info["Config"]["Labels"]["org.declarai.private.component"] = "untrusted"
    elif fault == "extra":
        info["Config"]["Labels"]["unapproved"] = "value"
    if fault is None:
        startup.validate(
            info, "postgres", spec, startup.labels(value, receipt), image, startup.names(value)["postgres"]
        )
    else:
        with pytest.raises(startup.checker.planner.PlanError, match="identity_mismatch"):
            startup.validate(
                info, "postgres", spec, startup.labels(value, receipt), image, startup.names(value)["postgres"]
            )


@pytest.mark.parametrize(
    "part,key,bad",
    [
        ("Config", "User", "0:0"),
        ("Config", "Entrypoint", ["sh"]),
        ("Config", "Cmd", ["expert.py"]),
        ("Config", "WorkingDir", "/tmp"),
        ("Config", "StopTimeout", 0),
        ("Config", "Healthcheck", {"Test": ["CMD", "expert.py"]}),
        ("HostConfig", "ReadonlyRootfs", False),
        ("HostConfig", "Privileged", True),
        ("HostConfig", "CapDrop", []),
        ("HostConfig", "CapAdd", ["SYS_ADMIN"]),
        ("HostConfig", "SecurityOpt", []),
        ("HostConfig", "PidsLimit", 4096),
        ("HostConfig", "NanoCpus", 0),
        ("HostConfig", "Memory", 1),
        ("HostConfig", "MemorySwap", -1),
        ("HostConfig", "Tmpfs", {}),
        ("HostConfig", "RestartPolicy", {"Name": "always"}),
        ("HostConfig", "Runtime", "custom"),
        ("HostConfig", "IpcMode", "host"),
        ("HostConfig", "CgroupnsMode", "host"),
        ("HostConfig", "ShmSize", 1),
        ("HostConfig", "PortBindings", {"5432/tcp": []}),
        ("HostConfig", "PidMode", "host"),
        ("HostConfig", "UTSMode", "host"),
        ("HostConfig", "UsernsMode", "host"),
        ("HostConfig", "Devices", [{"PathOnHost": "/dev/mem"}]),
        ("HostConfig", "DeviceRequests", [{"Driver": "nvidia"}]),
        ("HostConfig", "GroupAdd", ["0"]),
        ("HostConfig", "ExtraHosts", ["external:1.1.1.1"]),
        ("HostConfig", "Links", ["external"]),
        ("HostConfig", "Dns", ["1.1.1.1"]),
        ("HostConfig", "DnsOptions", ["ndots:0"]),
        ("HostConfig", "DnsSearch", ["external"]),
        ("HostConfig", "VolumesFrom", ["foreign"]),
        ("HostConfig", "Sysctls", {"net.ipv4.ip_forward": "1"}),
    ],
)
def test_changed_profiles_are_rejected_without_repair(startup, context, part, key, bad):
    value, spec, receipt, image = context
    info = container(startup, context, "postgres")
    info[part][key] = bad
    with pytest.raises(startup.checker.planner.PlanError, match="profile_mismatch"):
        startup.validate(
            info, "postgres", spec, startup.labels(value, receipt), image, startup.names(value)["postgres"]
        )
    assert info[part][key] == bad


@pytest.mark.parametrize(
    "fault",
    [
        "image",
        "name",
        "label",
        "env",
        "env_duplicate",
        "network",
        "mount",
        "extra_mount",
        "writable_config",
        "actual_port",
        "paused",
        "dead",
        "restarting",
        "stopped",
    ],
)
def test_identity_data_and_live_state_cannot_inherit_readiness(startup, context, fault):
    value, spec, receipt, image = context
    info = container(startup, context, "postgres")
    if fault == "image":
        info["Image"] = "sha256:" + "f" * 64
    elif fault == "name":
        info["Name"] = "/foreign"
    elif fault == "label":
        info["Config"]["Labels"][startup.LABEL + "dependency"] = "f" * 32
    elif fault == "env":
        info["Config"]["Env"].append("LD_PRELOAD=external")
    elif fault == "env_duplicate":
        info["Config"]["Env"].append("PATH=/other")
    elif fault == "network":
        info["NetworkSettings"]["Networks"]["external"] = {}
    elif fault == "mount":
        info["Mounts"][0]["Source"] = "/foreign"
    elif fault == "extra_mount":
        info["Mounts"].append({"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/socket", "RW": True})
    elif fault == "writable_config":
        info["Mounts"][0]["RW"] = True
    elif fault == "actual_port":
        info["NetworkSettings"]["Ports"] = {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]}
    elif fault == "stopped":
        info["State"]["Running"] = False
    else:
        info["State"][fault.title()] = True
    with pytest.raises(startup.checker.planner.PlanError):
        startup.validate(
            info, "postgres", spec, startup.labels(value, receipt), image, startup.names(value)["postgres"], True
        )


def test_sql_credentials_are_quoted_and_passed_only_on_stdin(startup, context, monkeypatch):
    value, _, _, _ = context
    original = startup.owner_sql
    password = "Synthetic-Secret-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'\\"
    statements = []
    replies = iter(["0", "0", "created", "t", "0", "created", "revoked", "t"])
    monkeypatch.setattr(startup, "owner_sql", lambda cid, sql: statements.append(sql) or next(replies))
    startup.bootstrap(value, {"app/app-password": password.encode()}, "owned-id")
    assert any(startup.sql_text(password) in sql for sql in statements)
    assert all("ALTER ROLE" not in sql for sql in statements) and "left(rolname,3)<>'pg_'" in statements[0]
    calls = []
    monkeypatch.setattr(startup, "owner_sql", original)
    monkeypatch.setattr(
        startup.subprocess,
        "run",
        lambda args, **kw: calls.append((args, kw)) or SimpleNamespace(returncode=0, stdout=b"ok", stderr=b""),
    )
    startup.owner_sql("owned-id", statements[2])
    assert password not in str(calls[0][0]) and startup.sql_text(password).encode() in calls[0][1]["input"]


@pytest.mark.parametrize(
    "replies,error",
    [
        (["1"], "foreign_catalog"),
        (["0", "2"], "authority_changed"),
        (["0", "1", "f"], "authority_changed"),
        (["0", "1", "t", "2"], "authority_changed"),
        (["0", "1", "t", "1", "f"], "authority_changed"),
    ],
)
def test_foreign_catalog_or_changed_authority_is_preserved(startup, context, monkeypatch, replies, error):
    value, _, _, _ = context
    statements = []
    source = iter(replies)
    monkeypatch.setattr(startup, "owner_sql", lambda cid, sql: statements.append(sql) or next(source))
    with pytest.raises(startup.checker.planner.PlanError, match=error):
        startup.bootstrap(
            value, {"app/app-password": b"Synthetic-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789"}, "owned"
        )
    assert all("DROP" not in s and "ALTER" not in s and "CREATE" not in s for s in statements)


def test_repeated_database_bootstrap_does_not_reset_credentials_or_data(startup, context, monkeypatch):
    value, _, _, _ = context
    replies = iter(["0", "1", "t", "1", "t"])
    statements = []
    monkeypatch.setattr(startup, "owner_sql", lambda cid, sql: statements.append(sql) or next(replies))
    startup.bootstrap(value, {}, "owned")
    assert all(sql.startswith("SELECT") for sql in statements)


@pytest.mark.parametrize("value", [None, {}, {"services": []}, {"services": {"postgres": {}}}])
def test_malformed_start_history_cannot_be_silently_adopted(startup, context, value):
    _, _, receipt, _ = context
    with pytest.raises(startup.checker.planner.PlanError, match="recorded_identity_changed"):
        startup.prior_receipt(value, receipt["plan_manifest_sha256"], receipt, {})


@pytest.mark.parametrize("fault", [None, "id", "image", "reused_numeric", "approval", "profile", "extra"])
def test_recorded_start_identity_and_claims_are_immutable(startup, context, fault):
    _, _, receipt, _ = context
    existing = {role: container(startup, context, role) for role in startup.ROLES}
    prior = startup.start_receipt(receipt["plan_manifest_sha256"], receipt, existing, set())
    if fault == "id":
        prior["services"]["postgres"]["container_id"] = "f" * 64
    elif fault == "image":
        prior["services"]["postgres"]["image_id"] = "sha256:" + "f" * 64
    elif fault == "reused_numeric":
        prior["services"]["postgres"]["reused"] = 0
    elif fault == "approval":
        prior["model_use_approved"] = True
    elif fault == "profile":
        prior["dependency_profile_sha256"] = "f" * 64
    elif fault == "extra":
        prior["customer_accepted"] = True
    if fault is None:
        startup.prior_receipt(prior, receipt["plan_manifest_sha256"], receipt, existing)
        assert prior["migrations_applied"] is False and prior["model_use_approved"] is False
    else:
        with pytest.raises(startup.checker.planner.PlanError, match="recorded_identity_changed"):
            startup.prior_receipt(prior, receipt["plan_manifest_sha256"], receipt, existing)


def test_owner_command_errors_never_expose_secrets(startup, monkeypatch):
    monkeypatch.setattr(
        startup.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout=b"", stderr=b"Synthetic-Secret"),
    )
    with pytest.raises(startup.checker.planner.PlanError) as error:
        startup.owner_sql("owned", "SELECT 'Synthetic-Secret'")
    assert str(error.value) == "dependency_database_owner_unavailable"


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "script",
        "env",
        "privileged",
        "caps",
        "memory",
        "pids",
        "tmpfs",
        "device",
        "dns",
        "namespace",
        "mount_source",
        "mount_writable",
        "network",
    ],
)
def test_authenticated_probe_cannot_gain_admin_data_or_host_authority(startup, context, fault):
    value, spec, receipt, image = context
    info = copy.deepcopy(container(startup, context, "postgres"))
    info["Image"] = value["images"]["api"]
    info["Config"].update(
        Labels={**startup.labels(value, receipt), startup.LABEL + "role": "dependency-check"},
        User="10001:10001",
        Entrypoint=["python"],
        Cmd=["-I", "-c", startup.PROBE],
        Env=[
            "PATH=/trusted/bin",
            "DEPENDENCY_DATABASE=" + value["request"]["database"]["name"],
            "DEPENDENCY_USER=" + value["request"]["database"]["user"],
        ],
    )
    info["HostConfig"].update(
        PidsLimit=32,
        NanoCpus=1_000_000_000,
        Memory=256 * 1024**2,
        Tmpfs={"/tmp": "rw,noexec,nosuid,size=67108864,uid=10001,gid=10001,mode=700"},
    )
    info["Mounts"] = [
        {
            "Type": "bind",
            "Source": value["request"]["root"] + "/secrets/app/" + file,
            "Destination": "/installation/" + file,
            "RW": False,
        }
        for file in ["app-password", "postgres-ca.crt", "job-broker-url", "job-ca.crt", "cache-url", "cache-ca.crt"]
    ]
    if fault == "script":
        info["Config"]["Cmd"] = ["-c", "expert.py"]
    elif fault == "env":
        info["Config"]["Env"].append("PYTHONPATH=/unapproved")
    elif fault == "privileged":
        info["HostConfig"]["Privileged"] = True
    elif fault == "caps":
        info["HostConfig"]["CapAdd"] = ["SYS_ADMIN"]
    elif fault == "memory":
        info["HostConfig"]["Memory"] = 1
    elif fault == "pids":
        info["HostConfig"]["PidsLimit"] = 9999
    elif fault == "tmpfs":
        info["HostConfig"]["Tmpfs"] = {}
    elif fault == "device":
        info["HostConfig"]["Devices"] = [{"PathOnHost": "/dev/mem"}]
    elif fault == "dns":
        info["HostConfig"]["Dns"] = ["1.1.1.1"]
    elif fault == "namespace":
        info["HostConfig"]["PidMode"] = "host"
    elif fault == "mount_source":
        info["Mounts"][0]["Source"] = value["request"]["root"] + "/dependencies/postgres/config/owner-password"
    elif fault == "mount_writable":
        info["Mounts"][0]["RW"] = True
    elif fault == "network":
        info["NetworkSettings"]["Networks"] = {"public": {}}
    if fault is None:
        startup.validate_probe(info, value, spec, receipt, image)
    else:
        with pytest.raises(startup.checker.planner.PlanError, match="probe_profile_invalid"):
            startup.validate_probe(info, value, spec, receipt, image)


@pytest.mark.parametrize("fault", [None, "profile", "recorded_id", "approval"])
def test_managed_adoption_rechecks_exact_profiles_and_start_history(startup, context, monkeypatch, fault):
    value, spec, receipt, image = context
    rows = {role: container(startup, context, role) for role in startup.ROLES}
    prior = startup.start_receipt(receipt["plan_manifest_sha256"], receipt, rows, set())
    if fault == "profile":
        rows["postgres"]["HostConfig"]["Memory"] = 1
    elif fault == "recorded_id":
        prior["services"]["postgres"]["container_id"] = "f" * 64
    elif fault == "approval":
        prior["model_use_approved"] = True
    monkeypatch.setattr(startup, "prepared_value", lambda *a: (value, spec, receipt, {}, {}, 99))
    monkeypatch.setattr(startup.resources, "inspect", lambda *a: image)
    monkeypatch.setattr(startup, "read_file", lambda *a: startup.checker.planner.encoded(prior))
    closed = []
    monkeypatch.setattr(startup.os, "close", lambda fd: closed.append(fd))
    binding = startup.resources.labels(value, receipt["plan_manifest_sha256"], receipt["initialization_id"])
    if fault is None:
        startup.adoption_check(value, binding, rows)
    else:
        with pytest.raises(startup.checker.planner.PlanError):
            startup.adoption_check(value, binding, rows)
    assert closed == [99]


@pytest.mark.parametrize("phase", ["postgres", "broker", "cache", "unknown"])
def test_probe_errors_publish_only_fixed_phase_codes_and_clean_the_owned_helper(startup, context, monkeypatch, phase):
    value, spec, receipt, _ = context
    calls = []
    identity = "d" * 64
    output = ("private_dependency_" + phase + "_failed").encode() if phase != "unknown" else b"password=secret"

    def command(args, **kwargs):
        calls.append(args)
        return identity.encode() if args[:2] == ["container", "create"] else output

    monkeypatch.setattr(startup.resources, "command", command)
    monkeypatch.setattr(startup.resources, "inspect", lambda *a: {"State": {"Running": False, "ExitCode": 1}})
    monkeypatch.setattr(startup, "validate_probe", lambda *a: None)
    error = (
        "private_dependency_" + phase + "_failed" if phase != "unknown" else "dependency_authenticated_readiness_failed"
    )
    with pytest.raises(startup.checker.planner.PlanError, match=error) as caught:
        startup.probe(value, spec, receipt)
    assert "secret" not in str(caught.value)
    assert calls[-1] == ["container", "rm", "--force", identity]
