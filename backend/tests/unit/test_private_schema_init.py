"""Fresh-only schema authority, exact helper isolation and immutable retry history."""

import copy
import importlib
import json
import os
from types import SimpleNamespace

import pytest

from tests.unit.test_private_dependency_start import context, startup, container  # noqa: F401
from tests.unit.test_private_installation_plan import compatible, planner, request_value  # noqa: F401
from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401
from tests.unit.test_private_installation_check import checker, saved_plan  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def schema(startup):
    return importlib.import_module("private_schema_init")


@pytest.fixture
def execution(schema, context, tmp_path, monkeypatch):
    value, spec, receipt, image = context
    image.update(Id=value["images"]["api"], Architecture=value["manifest"]["architecture"], Os="linux")
    deps = {r: container(schema.startup, context, r) for r in schema.startup.ROLES}
    stored = schema.startup.start_receipt(receipt["plan_manifest_sha256"], receipt, deps, set())
    (tmp_path / "started.json").write_bytes(schema.checker.planner.encoded(stored))
    (tmp_path / "started.json").chmod(0o600)
    calls = []
    state = {"state": "fresh"}
    pin = "e" * 64

    def helper(*args):
        action = args[3]
        calls.append(action)
        if action == "apply_fresh":
            state["state"] = "current"
        return {"schema_sha256": pin, "state": state["state"]}

    monkeypatch.setattr(
        schema.startup,
        "prepared",
        lambda *a: (value, spec, receipt, {}, {}, os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)),
    )
    monkeypatch.setattr(schema.resources, "docker_host", lambda *a: None)
    monkeypatch.setattr(schema.resources, "record", lambda *a: {"DefaultRuntime": "runc"})
    monkeypatch.setattr(schema.resources, "inspect", lambda kind, r: {**image, "Id": r})
    monkeypatch.setattr(schema.startup, "snapshot", lambda *a: deps)
    monkeypatch.setattr(schema.startup, "network", lambda *a: None)
    monkeypatch.setattr(schema.adopter, "project_containers", lambda *a: [])
    monkeypatch.setattr(schema, "helper", helper)
    return SimpleNamespace(
        value=value,
        spec=spec,
        receipt=receipt,
        image=image,
        deps=deps,
        root=tmp_path,
        calls=calls,
        state=state,
        pin=pin,
    )


def run(schema, x, pin=True):
    return schema.initialize(x.root, x.receipt["plan_manifest_sha256"], x.pin if pin else None)


def test_description_is_read_only_and_wrong_digest_does_not_publish_intent(schema, execution):
    x = execution
    result = run(schema, x, False)
    assert result["execution_authorized"] is False and result["state"] == "fresh"
    assert not (x.root / "schema-intent.json").exists()
    with pytest.raises(schema.checker.planner.PlanError, match="graph_changed"):
        schema.initialize(x.root, x.receipt["plan_manifest_sha256"], "f" * 64)
    assert x.calls == ["describe", "describe"] and not (x.root / "schema-intent.json").exists()


def test_success_is_bound_and_repeat_only_verifies_preserving_bytes(schema, execution):
    x = execution
    first = run(schema, x)
    prior = (x.root / "schema.json").read_bytes()
    intent = (x.root / "schema-intent.json").read_bytes()
    again = run(schema, x)
    assert first["migration_execution"] == "applied_atomically" and not first["reused"] and again["reused"]
    assert x.calls == ["describe", "apply_fresh", "describe", "verify_current"]
    assert (x.root / "schema.json").read_bytes() == prior and (x.root / "schema-intent.json").read_bytes() == intent
    assert first["accounts_enrolled"] is first["model_use_approved"] is first["release_qualified"] is False
    assert first["dependencies"]["postgres"]["container_id"] == x.deps["postgres"]["Id"]


def test_lost_result_is_recovered_with_explicit_provenance_not_reexecuted(schema, execution):
    x = execution
    run(schema, x)
    (x.root / "schema.json").unlink()
    result = run(schema, x)
    assert result["migration_execution"] == "recovered_current_from_exact_intent"
    assert x.calls == ["describe", "apply_fresh", "describe", "verify_current"]


def test_failed_apply_retains_exact_intent_and_can_resume_only_fresh(schema, execution, monkeypatch):
    x = execution
    real = schema.helper

    def fail(*args):
        if args[3] == "apply_fresh":
            raise schema.checker.planner.PlanError("fixture_ddl_rolled_back")
        return real(*args)

    monkeypatch.setattr(schema, "helper", fail)
    with pytest.raises(schema.checker.planner.PlanError, match="rolled_back"):
        run(schema, x)
    original = (x.root / "schema-intent.json").read_bytes()
    assert not (x.root / "schema.json").exists()
    monkeypatch.setattr(schema, "helper", real)
    assert run(schema, x)["migration_execution"] == "applied_atomically"
    assert (x.root / "schema-intent.json").read_bytes() == original


@pytest.mark.parametrize("state", ["current", "foreign", "partial_or_foreign"])
def test_unattributed_existing_schema_never_adopted_or_changed(schema, execution, state):
    x = execution
    x.state["state"] = state
    with pytest.raises(schema.checker.planner.PlanError, match="existing_requires_review"):
        run(schema, x)
    assert x.calls == ["describe"] and not (x.root / "schema-intent.json").exists()


@pytest.mark.parametrize(
    "key,bad",
    [
        ("schema_sha256", "f" * 64),
        ("image_id", "sha256:" + "f" * 64),
        ("helper_sha256", "f" * 64),
        ("dependency_initialization_id", "f" * 32),
        ("model_use_approved", True),
        ("accounts_enrolled", True),
    ],
)
def test_stale_or_tampered_intent_never_replays(schema, execution, key, bad):
    x = execution
    run(schema, x)
    (x.root / "schema.json").unlink()
    path = x.root / "schema-intent.json"
    value = json.loads(path.read_bytes())
    value[key] = bad
    path.write_bytes(schema.checker.planner.encoded(value))
    with pytest.raises(schema.checker.planner.PlanError, match="intent_changed"):
        run(schema, x)
    assert x.calls == ["describe", "apply_fresh", "describe"] and not (x.root / "schema.json").exists()


@pytest.mark.parametrize(
    "fault",
    ["missing_intent", "tampered_receipt", "empty_after_success", "foreign_after_success", "changed_dependency"],
)
def test_recorded_success_cannot_authorize_changed_state(schema, execution, fault):
    x = execution
    run(schema, x)
    prior = (x.root / "schema.json").read_bytes()
    if fault == "missing_intent":
        (x.root / "schema-intent.json").unlink()
    elif fault == "tampered_receipt":
        result = json.loads(prior)
        result["installation_qualified"] = True
        (x.root / "schema.json").write_bytes(schema.checker.planner.encoded(result))
    elif fault == "changed_dependency":
        x.deps["postgres"]["Id"] = "f" * 64
    else:
        x.state["state"] = "fresh" if fault == "empty_after_success" else "foreign"
    with pytest.raises(schema.checker.planner.PlanError):
        run(schema, x)
    assert x.calls == (
        ["describe", "apply_fresh"] if fault == "changed_dependency" else ["describe", "apply_fresh", "describe"]
    )
    if fault != "tampered_receipt":
        assert (x.root / "schema.json").read_bytes() == prior


def test_application_services_cannot_precede_initial_schema(schema, execution, monkeypatch):
    x = execution
    monkeypatch.setattr(schema.adopter, "project_containers", lambda *a: [{"Id": "f" * 64}])
    with pytest.raises(schema.checker.planner.PlanError, match="application_services_present"):
        run(schema, x)
    assert not (x.root / "schema-intent.json").exists()


def test_dependency_change_after_migration_cannot_publish_success(schema, execution, monkeypatch):
    x = execution
    original = copy.deepcopy(x.deps)
    count = []

    def snapshot(*args):
        count.append(True)
        if len(count) > 1:
            original["postgres"]["Id"] = "f" * 64
        return copy.deepcopy(original)

    # The first receipt validates; the second must still refer to that same ID.
    monkeypatch.setattr(schema.startup, "snapshot", snapshot)
    with pytest.raises(schema.checker.planner.PlanError):
        run(schema, x)
    assert (x.root / "schema-intent.json").exists() and not (x.root / "schema.json").exists()


def test_concurrent_operation_blocks_before_any_helper(schema, execution, monkeypatch):
    x = execution
    monkeypatch.setattr(schema.fcntl, "flock", lambda *a: (_ for _ in ()).throw(BlockingIOError()))
    with pytest.raises(schema.checker.planner.PlanError, match="operation_in_progress"):
        run(schema, x)
    assert not x.calls


@pytest.mark.parametrize("name", ["schema-intent.json", "schema.json"])
def test_no_replace_publication_preserves_existing_files(schema, tmp_path, name):
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        (tmp_path / name).write_bytes(b"original")
        with pytest.raises(schema.checker.planner.PlanError):
            schema.publish(fd, name, {"replacement": True})
        assert (tmp_path / name).read_bytes() == b"original" and set(p.name for p in tmp_path.iterdir()) == {name}
    finally:
        os.close(fd)


def test_helper_driver_errors_are_not_emitted_and_own_container_is_cleaned(schema, context, monkeypatch):
    value, spec, receipt, image = context
    calls = []
    identity = "d" * 64

    def command(args, **kwargs):
        calls.append(args)
        return identity.encode() if args[:2] == ["container", "create"] else b"password=private-value"

    monkeypatch.setattr(schema.resources, "command", command)
    monkeypatch.setattr(schema.resources, "inspect", lambda *a: {"State": {"Running": False, "ExitCode": 1}})
    monkeypatch.setattr(schema.adopter, "validate_preflight", lambda *a, **k: None)
    with pytest.raises(schema.checker.planner.PlanError, match="schema_helper_failed") as caught:
        schema.helper(value, receipt, image, "describe")
    assert "private-value" not in str(caught.value) and calls[-1] == ["container", "rm", "--force", identity]
    args = calls[0]
    assert "--entrypoint" in args and args[-3:] == ["-I", "-c", schema.SCHEMA_CODE]
    assert not any("owner-password" in a or "/var/run/docker.sock" in a for a in args)


def test_failed_staged_write_cannot_publish_partial_intent(schema, tmp_path, monkeypatch):
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        monkeypatch.setattr(schema.os, "fsync", lambda *a: (_ for _ in ()).throw(OSError("fixture_disk_error")))
        with pytest.raises(OSError):
            schema.publish(fd, "schema-intent.json", {"allowed": True})
        assert not list(tmp_path.iterdir())
    finally:
        os.close(fd)


@pytest.mark.parametrize(
    "fault", [None, "code", "root", "network", "artifact", "owner_secret", "writable", "environment", "extra_label"]
)
def test_exact_schema_helper_has_only_readonly_app_inputs(schema, saved_plan, monkeypatch, fault):
    from tests.unit.test_private_installation_adopt import application

    plan, pin = saved_plan
    value = schema.checker.verify(plan, pin)
    composition, digest, binding = schema.adopter.application_profile(value, pin, "a" * 32)
    image = {
        "Config": {
            "Env": ["PATH=/trusted/bin"],
            "Entrypoint": ["python", "/app/scripts/private_service.py"],
            "WorkingDir": "/app/backend",
            "Cmd": ["api"],
        }
    }
    info = application("api", (value, composition, digest, binding, image))
    env = {
        **composition["services"]["api"]["environment"],
        "DECLARAI_MEDIA_ROOT": "/tmp/schema-media",
        "SCHEMA_ACTION": "describe",
        "SCHEMA_EXPECTED": "",
    }
    info["Config"].update(
        Entrypoint=["python"],
        Cmd=["-I", "-c", schema.SCHEMA_CODE],
        Labels={**binding, schema.resources.LABEL + "role": "schema"},
        Env=["PATH=/trusted/bin", *[k + "=" + v for k, v in env.items()]],
    )
    info["HostConfig"].update(PidsLimit=64, NanoCpus=1_000_000_000, Memory=1024**3)
    info["Mounts"] = [m for m in info["Mounts"] if m["Destination"] == "/installation"]
    info["Mounts"][0]["RW"] = False
    if fault == "code":
        info["Config"]["Cmd"] = ["-I", "-c", "unreviewed_python"]
    elif fault == "root":
        info["Config"]["User"] = "0:0"
    elif fault == "network":
        info["NetworkSettings"]["Networks"] = {"public": {}}
    elif fault == "artifact":
        info["Mounts"].append(
            {
                "Type": "bind",
                "Destination": "/artifacts",
                "Source": value["request"]["root"] + "/artifacts",
                "RW": False,
            }
        )
    elif fault == "owner_secret":
        info["Mounts"][0]["Source"] = value["request"]["root"] + "/dependencies/postgres/config"
    elif fault == "writable":
        info["Mounts"][0]["RW"] = True
    elif fault == "environment":
        info["Config"]["Env"].append("PYTHONPATH=/installation")
    elif fault == "extra_label":
        info["Config"]["Labels"]["unreviewed"] = "true"
    args = (info, value, env, binding, image)
    kw = {
        "role": "schema",
        "entrypoint": ["python"],
        "command": ["-I", "-c", schema.SCHEMA_CODE],
        "mount_sources": {"/installation": value["request"]["root"] + "/secrets/app"},
    }
    if fault is None:
        schema.adopter.validate_preflight(*args, **kw)
    else:
        with pytest.raises(schema.checker.planner.PlanError, match="profile_mismatch"):
            schema.adopter.validate_preflight(*args, **kw)


@pytest.mark.parametrize("phase", ["runtime", "authority", "graph", "state", "migration"])
def test_only_fixed_helper_phase_codes_are_exposed(schema, context, monkeypatch, phase):
    value, _, receipt, image = context
    calls = []
    identity = "d" * 64

    def command(args, **kwargs):
        calls.append(args)
        return (
            identity.encode()
            if args[:2] == ["container", "create"]
            else ("private_schema_" + phase + "_failed").encode()
        )

    monkeypatch.setattr(schema.resources, "command", command)
    monkeypatch.setattr(schema.resources, "inspect", lambda *a: {"State": {"Running": False, "ExitCode": 1}})
    monkeypatch.setattr(schema.adopter, "validate_preflight", lambda *a, **k: None)
    with pytest.raises(schema.checker.planner.PlanError, match="private_schema_" + phase + "_failed"):
        schema.helper(value, receipt, image, "describe")
    assert calls[-1] == ["container", "rm", "--force", identity]
