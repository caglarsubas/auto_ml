"""Operator authority, degraded observations, transport and no-replace export."""

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.test_private_operation_lock import (  # noqa: F401
    checker, compatible, handoff, image_set, operation, planner, request_value, saved_plan, contender,
)
from tests.unit.test_private_lifecycle_readiness import service

pytestmark = pytest.mark.unit


@pytest.fixture
def incident(operation, monkeypatch):
    x = operation
    module = importlib.import_module("private_queue_incidents")
    apps = {r: service(i) for i, r in enumerate(sorted(x.module.ROLES), 1)}
    monkeypatch.setattr(module, "applications", lambda *a: {r: module.service_observation(i) for r, i in apps.items()})
    monkeypatch.setattr(module, "dependencies", lambda *a: {})
    monkeypatch.setattr(module, "probe", lambda *a: {"status": "observed", "incident_total": 0, "rows": []})
    return SimpleNamespace(x=x, module=module, apps=apps)


def observe(t):
    return t.module.observe(t.x.plan, t.x.expected)


def test_verified_operator_report_has_no_repair_or_secret_claim(incident):
    t = incident
    before = t.x.lock.read_bytes()
    value = observe(t)
    assert value["sha256"] == t.module.hashlib.sha256(t.module.encode(value["evidence"])).hexdigest()
    report = value["evidence"]
    assert report["authority"] == "linux_root_with_trusted_installation_plan" and report["read_only"]
    assert report["stable_service_observations"] and report["managed_operation_serialized"]
    assert report["dependency_health"] == report["https_health"] == "not_tested"
    assert not any(report[k] for k in ["recovery_authorized", "review_approved", "production_use_approved", "installation_qualified", "release_qualified"])
    assert "customer-secret" not in json.dumps(value) and t.x.calls == ["docker"]
    assert t.x.lock.read_bytes() == before


@pytest.mark.parametrize("state,value", [("Paused", True), ("Running", False), ("Restarting", True), ("Dead", True), ("OOMKilled", True), ("ExitCode", 1)])
def test_degraded_worker_is_observed_without_repair(incident, state, value):
    t = incident
    t.apps["worker"]["State"][state] = value
    report = observe(t)["evidence"]
    assert report["services_after"]["worker"]["attention_required"]
    assert t.apps["worker"]["State"][state] == value and t.x.calls == ["docker"]


def test_guard_is_held_during_probe_and_released_afterward(incident, monkeypatch):
    t = incident

    def probe(*a):
        with pytest.raises(BlockingIOError):
            os.close(contender(t.x.lock))
        return {"status": "unavailable", "reason": "queue_metadata_unavailable"}

    monkeypatch.setattr(t.module, "probe", probe)
    assert observe(t)["evidence"]["queue"]["status"] == "unavailable"
    os.close(contender(t.x.lock))


def test_held_or_missing_lock_blocks_before_docker(incident):
    t = incident
    fd = contender(t.x.lock)
    try:
        with pytest.raises(t.module.checker.planner.PlanError, match="dependency_operation_in_progress"):
            observe(t)
    finally:
        os.close(fd)
    t.x.lock.unlink()
    with pytest.raises(FileNotFoundError):
        observe(t)
    assert not t.x.lock.exists() and t.x.calls == []


def test_changed_service_observations_are_disclosed(incident, monkeypatch):
    t = incident

    def probe(*a):
        t.apps["worker"]["State"]["Paused"] = True
        return {"status": "unavailable", "reason": "probe_unavailable"}

    monkeypatch.setattr(t.module, "probe", probe)
    report = observe(t)["evidence"]
    assert report["stable_service_observations"] is False
    assert not report["services_before"]["worker"]["state"]["Paused"] and report["services_after"]["worker"]["state"]["Paused"]


@pytest.mark.parametrize("boundary", ["platform", "identity", "initialization", "image", "runtime"])
def test_invalid_operator_boundary_prevents_probe(incident, monkeypatch, boundary):
    t = incident
    if boundary == "platform":
        monkeypatch.setattr(t.module.sys, "platform", "darwin")
    elif boundary == "identity":
        monkeypatch.setattr(t.module.os, "geteuid", lambda: 10001)
    elif boundary == "initialization":
        monkeypatch.setattr(t.module.resources, "initialization", lambda *a: {"plan_manifest_sha256": "b" * 64})
    elif boundary == "image":
        monkeypatch.setattr(t.module.resources, "inspect", lambda *a: {})
    else:
        monkeypatch.setattr(t.module.resources, "record", lambda *a: {"DefaultRuntime": "untrusted"})
    monkeypatch.setattr(t.module, "probe", lambda *a: pytest.fail("invalid boundary reached probe"))
    with pytest.raises(t.module.checker.planner.PlanError):
        observe(t)


def test_exclusive_private_export_checks_digest_and_never_overwrites(incident):
    t = incident
    value = observe(t)
    target = t.x.root / "incident.json"
    t.module.export(value, target)
    assert json.loads(target.read_text()) == value and target.stat().st_mode & 0o777 == 0o600
    before = target.read_bytes()
    with pytest.raises((OSError, t.module.checker.planner.PlanError)):
        t.module.export(value, target)
    assert target.read_bytes() == before and not list(t.x.root.glob(".queue-evidence-*"))
    value["evidence"]["queue"] = {"status": "altered"}
    with pytest.raises(t.module.checker.planner.PlanError, match="digest_mismatch"):
        t.module.export(value, t.x.root / "tampered.json")
    assert not (t.x.root / "tampered.json").exists()


@pytest.mark.parametrize("fault", ["symlink", "public_directory", "relative"])
def test_unsafe_export_destination_is_not_published(incident, fault):
    t = incident
    value = observe(t)
    target = t.x.root / "unsafe.json"
    if fault == "symlink":
        target.symlink_to(t.x.lock)
    elif fault == "public_directory":
        t.x.root.chmod(0o750)
    else:
        target = Path("relative.json")
    with pytest.raises((OSError, t.module.checker.planner.PlanError)):
        t.module.export(value, target)
    assert t.x.lock.read_bytes() == b"" and not list(t.x.root.glob(".queue-evidence-*"))


@pytest.mark.parametrize("kind", ["missing", "paused"])
def test_probe_skips_unavailable_api(kind, monkeypatch):
    m = importlib.import_module("private_queue_incidents")
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: pytest.fail("inactive api executed"))
    value = m.probe({"status": "missing"} if kind == "missing" else {"attention_required": True})
    assert value == {"status": "unavailable", "reason": "api_not_active"}


@pytest.mark.parametrize("fault", ["valid", "database", "bad_json", "large", "failed", "timeout"])
def test_fixed_probe_transport_has_bounded_sanitized_outputs(monkeypatch, fault):
    m = importlib.import_module("private_queue_incidents")
    api = {"container_id": "a" * 64, "attention_required": False}

    def run(args, **kwargs):
        assert args == [*m.resources.PREFIX, "exec", "--user", "10001:10001", api["container_id"], "python", "-m", "execution_jobs.operator_triage"]
        assert kwargs["timeout"] == 20 and kwargs["stderr"] == m.subprocess.DEVNULL
        if fault == "timeout":
            raise m.subprocess.TimeoutExpired(args, 20, stderr="sensitive-secret")
        value = {"schema": "native_queue_operator_snapshot_v1", "status": "unavailable" if fault == "database" else "observed"}
        kwargs["stdout"].write(b"secret-not-json" if fault == "bad_json" else b"a" * 131073 if fault == "large" else json.dumps(value).encode())
        return SimpleNamespace(returncode=1 if fault == "failed" else 0)

    monkeypatch.setattr(m.subprocess, "run", run)
    if fault in {"bad_json", "large"}:
        with pytest.raises(m.checker.planner.PlanError, match="probe_output_invalid"):
            m.probe(api)
    else:
        value = m.probe(api)
        assert value["status"] == ("observed" if fault == "valid" else "unavailable") and "secret" not in json.dumps(value)
