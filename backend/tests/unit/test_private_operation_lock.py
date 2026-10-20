"""Managed adoption must share the existing startup/schema operation boundary."""

import fcntl
import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401
from tests.unit.test_private_installation_plan import compatible, planner, request_value  # noqa: F401
from tests.unit.test_private_installation_check import checker, saved_plan  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def operation(planner, saved_plan, monkeypatch, tmp_path):
    module = importlib.import_module("private_installation_adopt")
    plan, expected = saved_plan
    value = module.checker.verify(plan, expected)
    dependencies = tmp_path / "dependencies"
    dependencies.mkdir(mode=0o700)
    lock = dependencies / "start.lock"
    lock.touch(mode=0o600)
    # Unit-only owner adaptation; actual Linux-root ownership is separately
    # exercised by the managed-installation qualifier. Kernel locks are real.
    actual_stat = os.fstat

    def ownership(fd):
        info = actual_stat(fd)
        return SimpleNamespace(**{k: (0 if k in {"st_uid", "st_gid"} else getattr(info, k))
                                  for k in dir(info) if k.startswith("st_")})

    monkeypatch.setattr(module.os, "fstat", ownership)
    monkeypatch.setattr(module.resources.initializer, "trusted_directory", lambda p: os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY))
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.resources, "initialization", lambda v: {"plan_manifest_sha256": expected, "initialization_id": "a" * 32})
    monkeypatch.setattr(module.checker, "check_paths", lambda *a: None)
    monkeypatch.setattr(module, "client_context", lambda *a: object())
    calls = []
    monkeypatch.setattr(module.resources, "docker_host", lambda *a: calls.append("docker"))
    monkeypatch.setattr(module.resources, "record", lambda *a: {"DefaultRuntime": "runc"})
    monkeypatch.setattr(module.resources, "inspect", lambda kind, identity: {"Id": identity, "Architecture": value["manifest"]["architecture"], "Os": "linux"})
    monkeypatch.setattr(module, "project_containers", lambda *a: [])
    monkeypatch.setattr(module, "prerequisites", lambda *a: None)
    monkeypatch.setattr(module, "preflight", lambda *a: calls.append("preflight"))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(module, "active_applications", lambda *a: {role: {"Id": role, "Image": value["images"]["ingress" if role == "ingress" else "api"]} for role in module.ROLES})
    monkeypatch.setattr(module, "https_check", lambda *a: calls.append("https"))
    return SimpleNamespace(module=module, plan=plan, expected=expected, value=value, root=tmp_path,
                           dependencies=dependencies, lock=lock, calls=calls)


def adoption(x):
    return x.module.adoption(x.plan, x.expected, x.root / "ca.pem")


def contender(path):
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


def test_held_lock_blocks_before_docker(operation):
    x = operation
    fd = contender(x.lock)
    try:
        with pytest.raises(x.module.checker.planner.PlanError, match="dependency_operation_in_progress"):
            adoption(x)
        assert x.calls == []
    finally:
        os.close(fd)


def test_guard_spans_first_docker_and_final_https_then_releases(operation, monkeypatch):
    x = operation
    sampled = []

    def sample(stage):
        with pytest.raises(BlockingIOError):
            fd = contender(x.lock)
            os.close(fd)
        sampled.append(stage)

    monkeypatch.setattr(x.module.resources, "docker_host", lambda *a: sample("first_docker"))
    monkeypatch.setattr(x.module, "https_check", lambda *a: sample("https"))
    result = adoption(x)
    assert sampled == ["first_docker", "https"] and result["managed_operation_serialized"] is True
    os.close(contender(x.lock))


def test_failure_releases_guard_without_publishing_receipt(operation, monkeypatch):
    x = operation

    def fail(*a):
        raise x.module.checker.planner.PlanError("owned_preflight_failure")

    monkeypatch.setattr(x.module, "preflight", fail)
    with pytest.raises(x.module.checker.planner.PlanError, match="owned_preflight_failure"):
        adoption(x)
    os.close(contender(x.lock))
    assert x.calls == ["docker"]


def test_operator_managed_scope_is_preserved_without_serialization_claim(operation):
    x = operation
    x.lock.unlink()
    x.dependencies.rmdir()
    assert adoption(x)["managed_operation_serialized"] is False
    assert not (x.root / "start.lock").exists()


@pytest.mark.parametrize("fault", ["directory_mode", "directory_link", "file_mode", "file_link", "hardlink", "fifo", "acl", "owner"])
def test_unsafe_operation_boundary_never_reaches_docker(operation, monkeypatch, fault):
    x = operation
    if fault == "directory_mode":
        x.dependencies.chmod(0o750)
    elif fault == "directory_link":
        x.dependencies.rename(x.root / "elsewhere")
        x.dependencies.symlink_to(x.root / "elsewhere", target_is_directory=True)
    elif fault == "file_mode":
        x.lock.chmod(0o640)
    elif fault in {"file_link", "fifo"}:
        x.lock.unlink()
        if fault == "file_link":
            x.lock.symlink_to(x.root / "foreign")
        else:
            os.mkfifo(x.lock, 0o600)
    elif fault == "hardlink":
        os.link(x.lock, x.root / "foreign")
    elif fault == "acl":
        monkeypatch.setattr(x.module.checker, "no_directory_acl", lambda fd: (_ for _ in ()).throw(x.module.checker.planner.PlanError("acl_rejected")))
    else:
        original = x.module.os.fstat

        def changed(fd):
            info = original(fd)
            return SimpleNamespace(**{**vars(info), "st_uid": 10001})

        monkeypatch.setattr(x.module.os, "fstat", changed)
    with pytest.raises((x.module.checker.planner.PlanError, OSError)):
        adoption(x)
    assert x.calls == []


def test_replaced_lock_path_is_not_reported_as_serialized(operation, monkeypatch):
    x = operation
    original = x.module.fcntl.flock

    def replace(fd, flags):
        original(fd, flags)
        x.lock.rename(x.dependencies / "old.lock")
        x.lock.touch(mode=0o600)

    monkeypatch.setattr(x.module.fcntl, "flock", replace)
    with pytest.raises(x.module.checker.planner.PlanError, match="dependency_lock_changed"):
        adoption(x)
    assert x.calls == []


def test_absent_managed_lock_is_created_with_private_mode(operation):
    x = operation
    x.lock.unlink()
    assert adoption(x)["managed_operation_serialized"] is True
    assert x.lock.stat().st_mode & 0o777 == 0o600
    os.close(contender(x.lock))
