"""Stored controller evidence cannot adopt changes hidden by coarse timestamps."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    import private_dependency_start

    return private_dependency_start


@pytest.mark.parametrize("mode", [0o400, 0o600])
def test_pinned_stored_file_preserves_exact_bytes(controller, tmp_path, mode):
    path = tmp_path / "stored"
    data = b"synthetic-controller-value\n"
    path.write_bytes(data)
    path.chmod(mode)
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert controller.read_file(parent, path.name, os.geteuid(), os.getegid(), mode, 64) == data
    finally:
        os.close(parent)


@pytest.mark.parametrize("fault", ["platform", "uid", "parent", "name", "binding"])
def test_controller_capture_qualification_refuses_foreign_scope(controller, monkeypatch, fault):
    import qualify_private_controller_capture as qualifier

    monkeypatch.setattr(sys, "platform", "darwin" if fault == "platform" else "linux")
    monkeypatch.setattr(os, "geteuid", lambda: 1 if fault == "uid" else 0)
    parent = Path("/tmp" if fault == "parent" else "/srv") / ("customer" if fault == "name" else "declarai-p37-" + "a" * 32)
    value = {"request": {"root": str(parent / ("other" if fault == "binding" else "installation"))}}
    monkeypatch.setattr(tempfile, "TemporaryDirectory", lambda **_: pytest.fail("foreign scope touched"))
    with pytest.raises(controller.checker.planner.PlanError, match="controller_capture_fixture_scope_required"):
        qualifier.qualify(value, parent)


@pytest.mark.parametrize("fault", ["bytes", "mode", "link", "uid", "gid", "acl"])
def test_interread_controller_change_refused_under_coarse_timestamps(controller, tmp_path, monkeypatch, fault):
    path = tmp_path / "stored"
    path.write_bytes(b"synthetic-controller-value")
    path.chmod(0o600)
    initial = path.stat()
    actual_fstat, actual_fdopen, actual_listxattr = os.fstat, os.fdopen, os.listxattr
    changed = False

    class Snapshot:
        st_mtime_ns, st_ctime_ns = initial.st_mtime_ns, initial.st_ctime_ns

        def __init__(self, current):
            self.current = current
            self.st_uid = current.st_uid + int(changed and fault == "uid")
            self.st_gid = current.st_gid + int(changed and fault == "gid")

        def __getattr__(self, name):
            return getattr(self.current, name)

    def fstat(fd):
        current = actual_fstat(fd)
        return Snapshot(current) if (current.st_dev, current.st_ino) == (initial.st_dev, initial.st_ino) else current

    def listxattr(fd):
        return ["system.posix_acl_access"] if changed and fault == "acl" else actual_listxattr(fd)

    class ChangedRead:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def seek(self, offset):
            return self.stream.seek(offset)

        def read(self, limit):
            nonlocal changed
            data = self.stream.read(limit)
            current = actual_fstat(self.fileno())
            if not changed and (current.st_dev, current.st_ino) == (initial.st_dev, initial.st_ino):
                changed = True
                if fault == "bytes":
                    path.write_bytes(b"X" + data[1:])
                elif fault == "mode":
                    path.chmod(0o666)
                elif fault == "link":
                    os.link(path, tmp_path / "alias")
            return data

    monkeypatch.setattr(os, "fstat", fstat)
    monkeypatch.setattr(os, "fdopen", lambda *a, **k: ChangedRead(actual_fdopen(*a, **k)))
    monkeypatch.setattr(os, "listxattr", listxattr)
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        reason = "installation_path_acl_unsupported" if fault == "acl" else "dependency_stored_file_changed"
        with pytest.raises(controller.checker.planner.PlanError, match=reason):
            controller.read_file(parent, path.name, os.geteuid(), os.getegid(), 0o600, 64)
    finally:
        os.close(parent)
