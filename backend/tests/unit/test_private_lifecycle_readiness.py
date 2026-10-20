"""Readiness observations must remain read-only, scoped and fail closed."""

import copy
import importlib
import json
import os
from types import SimpleNamespace

import pytest

from tests.unit.test_private_operation_lock import (  # noqa: F401
    checker, compatible, handoff, image_set, operation, planner, request_value, saved_plan,
    contender,
)

pytestmark = pytest.mark.unit


def service(number):
    return {"Id": f"{number:064x}", "Image": "sha256:" + "a" * 64, "RestartCount": 0,
            "Config": {"Env": ["DO_NOT_EMIT=customer-secret"]},
            "State": {"Running": True, "Paused": False, "Restarting": False, "Dead": False,
                      "StartedAt": "2026-10-20T00:00:00Z", "FinishedAt": "0001-01-01T00:00:00Z",
                      "ExitCode": 0, "Pid": number, "OOMKilled": False, "Error": ""}}


@pytest.fixture
def readiness(operation, monkeypatch):
    x = operation
    module = importlib.import_module("private_lifecycle_readiness")
    applications = {r: service(i) for i, r in enumerate(sorted(x.module.ROLES), 1)}
    dependencies = {r: service(i) for i, r in enumerate(sorted(module.startup.ROLES), 10)}
    history = x.dependencies / "started.json"
    history.write_text("{}")
    history.chmod(0o600)
    monkeypatch.setattr(x.module, "active_applications", lambda *a: applications)
    monkeypatch.setattr(module.startup, "prepared_value", lambda *a: (x.value, {}, {}, {}, {}, os.open(x.dependencies, os.O_RDONLY | os.O_DIRECTORY)))
    monkeypatch.setattr(module.startup, "snapshot", lambda *a: dependencies)
    monkeypatch.setattr(module.startup, "network", lambda *a: None)
    monkeypatch.setattr(module.startup, "prior_receipt", lambda *a: None)
    return SimpleNamespace(x=x, module=module, applications=applications, dependencies=dependencies, history=history)


def observe(t):
    return t.module.observe(t.x.plan, t.x.expected, t.x.root / "ca.pem")


def test_read_only_report_retains_guard_and_separates_qualification(readiness, monkeypatch):
    t, x = readiness, readiness.x
    before = {p.name: (p.read_bytes(), p.stat().st_mode) for p in x.dependencies.iterdir()}

    def https(*a):
        with pytest.raises(BlockingIOError):
            os.close(contender(x.lock))
        x.calls.append("https")

    monkeypatch.setattr(x.module, "https_check", https)
    result = observe(t)
    assert result["schema"] == "private_lifecycle_readiness_v1"
    assert result["read_only"] is result["managed_operation_serialized"] is True
    assert result["anonymous_selected_ca_https"] == "passed"
    assert result["services"]["applications"]["worker"]["container_id"] == t.applications["worker"]["Id"]
    for key in ("installation_qualified", "release_qualified", "expert_isolation_qualified", "fresh_runtime_preflight_executed",
                "maintenance_execution_authorized", "production_recovery_qualified", "upgrade_rollback_qualified", "customer_accepted",
                "secret_values_or_hashes_emitted"):
        assert result[key] is False
    assert len(result["operator_review_required"]) == 5 and len(result["limitations"]) == 4
    assert "customer-secret" not in json.dumps(result) and "Env" not in json.dumps(result)
    assert x.calls == ["docker", "https"]  # No preflight, service execution or repair.
    assert {p.name: (p.read_bytes(), p.stat().st_mode) for p in x.dependencies.iterdir()} == before
    os.close(contender(x.lock))


def test_missing_lock_is_not_created(readiness):
    t = readiness
    t.x.lock.unlink()
    with pytest.raises(FileNotFoundError):
        observe(t)
    assert not t.x.lock.exists() and t.x.calls == []


def test_unmanaged_installation_has_no_managed_readiness_claim(readiness):
    t = readiness
    t.x.lock.unlink()
    t.history.unlink()
    t.x.dependencies.rmdir()
    with pytest.raises(t.module.checker.planner.PlanError, match="lifecycle_managed_dependencies_required"):
        observe(t)
    assert not t.x.dependencies.exists() and t.x.calls == []


def test_held_lock_refuses_observation_before_docker(readiness):
    t = readiness
    fd = contender(t.x.lock)
    try:
        with pytest.raises(t.module.checker.planner.PlanError, match="dependency_operation_in_progress"):
            observe(t)
        assert t.x.calls == []
    finally:
        os.close(fd)


def test_failed_https_never_returns_report_and_releases_guard(readiness, monkeypatch):
    t = readiness

    def fail(*a):
        raise t.module.checker.planner.PlanError("installation_adopt_https_session_failed")

    monkeypatch.setattr(t.x.module, "https_check", fail)
    with pytest.raises(t.module.checker.planner.PlanError, match="installation_adopt_https_session_failed"):
        observe(t)
    os.close(contender(t.x.lock))


@pytest.mark.parametrize("group,role,key", [("applications", "worker", "Id"), ("applications", "api", "Image"),
                                          ("applications", "ingress", "RestartCount"), ("applications", "dispatcher", "StartedAt"),
                                          ("dependencies", "postgres", "Id"), ("dependencies", "job-broker", "Pid"),
                                          ("dependencies", "cache", "RestartCount")])
def test_changed_service_between_samples_rejects_report(readiness, monkeypatch, group, role, key):
    t = readiness

    def change(*a):
        info = getattr(t, group)[role]
        if key in {"Id", "Image"}:
            info[key] = ("sha256:" if key == "Image" else "") + "b" * 64
        elif key == "RestartCount":
            info[key] += 1
        elif key == "StartedAt":
            info["State"][key] = "2026-10-20T00:00:01Z"
        else:
            info["State"][key] += 1

    monkeypatch.setattr(t.x.module, "https_check", change)
    with pytest.raises(t.module.checker.planner.PlanError, match="lifecycle_services_changed_during_observation"):
        observe(t)
    os.close(contender(t.x.lock))


@pytest.mark.parametrize("key,value", [("Running", False), ("Paused", True), ("Restarting", True), ("Dead", True),
                                     ("OOMKilled", True), ("ExitCode", True), ("ExitCode", 2), ("Pid", 0),
                                     ("StartedAt", ""), ("Error", "customer-secret")])
def test_invalid_service_state_has_no_report_or_raw_error(readiness, key, value):
    t = readiness
    t.dependencies["postgres"]["State"][key] = value
    with pytest.raises(t.module.checker.planner.PlanError, match="^lifecycle_service_observation_invalid$"):
        observe(t)
    assert "https" not in t.x.calls


def test_missing_state_field_fails_closed(readiness):
    t = readiness
    del t.applications["worker"]["State"]["Dead"]
    with pytest.raises(t.module.checker.planner.PlanError, match="lifecycle_service_observation_invalid"):
        observe(t)


@pytest.mark.parametrize("field,value", [("Architecture", "unsupported"), ("Os", "windows"), ("Id", "sha256:" + "b" * 64)])
def test_mismatched_native_image_prevents_sampling(readiness, monkeypatch, field, value):
    t = readiness
    original = t.x.module.resources.inspect

    def inspect(kind, identity):
        result = original(kind, identity)
        result[field] = value
        return result

    monkeypatch.setattr(t.x.module.resources, "inspect", inspect)
    with pytest.raises(t.module.checker.planner.PlanError, match="lifecycle_native_images_required"):
        observe(t)
    assert "https" not in t.x.calls


@pytest.mark.parametrize("boundary", ["platform", "identity", "initialization", "runtime"])
def test_unsupported_execution_boundary_never_claims_readiness(readiness, monkeypatch, boundary):
    t = readiness
    if boundary == "platform":
        monkeypatch.setattr(t.module.sys, "platform", "darwin")
    elif boundary == "identity":
        monkeypatch.setattr(t.module.os, "geteuid", lambda: 10001)
    elif boundary == "initialization":
        monkeypatch.setattr(t.module.resources, "initialization", lambda *a: {"plan_manifest_sha256": "0" * 64})
    else:
        monkeypatch.setattr(t.module.resources, "record", lambda *a: {"DefaultRuntime": "unsupported"})
    with pytest.raises(t.module.checker.planner.PlanError, match="lifecycle_"):
        observe(t)
    assert "https" not in t.x.calls


def test_sample_failure_closes_dependency_descriptor(readiness, monkeypatch):
    t = readiness
    descriptor = os.open(t.x.dependencies, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(t.module.startup, "prepared_value", lambda *a: (t.x.value, {}, {}, {}, {}, descriptor))

    def fail(*a):
        raise t.module.checker.planner.PlanError("dependency_services_missing")

    monkeypatch.setattr(t.module.startup, "snapshot", fail)
    with pytest.raises(t.module.checker.planner.PlanError, match="dependency_services_missing"):
        observe(t)
    with pytest.raises(OSError):
        os.fstat(descriptor)
    os.close(contender(t.x.lock))


def test_service_projection_ignores_untrusted_extra_metadata(readiness):
    info = copy.deepcopy(readiness.applications["api"])
    info["customer-data"] = "never-emit"
    assert "never-emit" not in json.dumps(readiness.module.service_observation(info))
