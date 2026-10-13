"""Installation inputs retain custody and bytes throughout capture."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

from tests.unit.test_private_installation_init import values

pytestmark = pytest.mark.unit


@pytest.fixture(params=["application", "dependency", "prepared_app"])
def delivered(request, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    import private_installation_init as initializer
    import private_dependency_init as dependency

    root = tmp_path / "delivery"
    prepared = request.param == "prepared_app"
    root.mkdir(mode=0o750 if prepared else 0o700)
    data = values() if request.param != "dependency" else {
        "postgres/owner-password": b"synthetic-owner-password-0123456789-abcdefghijklmnopqrstuvwxyz",
        "job-broker/server.crt": b"synthetic-public-certificate",
        "cache/server.crt": b"synthetic-public-certificate",
    }
    groups = {group: [name.split("/", 1)[1] for name in data if name.startswith(group + "/")]
              for group in dict.fromkeys(name.split("/")[0] for name in data)}
    for group in groups:
        (root / group).mkdir(mode=0o700)
    for name, content in data.items():
        (root / name).write_bytes(content)
        (root / name).chmod(0o400)
    target = root / next(iter(data))
    initial, directory = target.stat(), root.stat()
    actual_fstat, actual_fdopen, actual_listxattr = os.fstat, os.fdopen, os.listxattr
    state = {"fault": None, "changed": False}

    class Snapshot:
        def __init__(self, current):
            self.current = current
            identity = (current.st_dev, current.st_ino)
            self.target = identity == (initial.st_dev, initial.st_ino)
            self.st_uid = 0 if prepared and identity == (directory.st_dev, directory.st_ino) else 10001
            self.st_gid = 10001
            if self.target and state["changed"]:
                self.st_uid += int(state["fault"] == "uid")
                self.st_gid += int(state["fault"] == "gid")
            self.st_mtime_ns = initial.st_mtime_ns if self.target else current.st_mtime_ns
            self.st_ctime_ns = initial.st_ctime_ns if self.target else current.st_ctime_ns

        def __getattr__(self, name):
            return getattr(self.current, name)

    def listxattr(fd):
        current = actual_fstat(fd)
        selected = (current.st_dev, current.st_ino) == (initial.st_dev, initial.st_ino)
        if selected and (state["fault"] == "initial_acl" or state["changed"] and state["fault"] == "acl"):
            return ["system.posix_acl_access"]
        return actual_listxattr(fd)

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
            content = self.stream.read(limit)
            current = actual_fstat(self.fileno())
            if not state["changed"] and state["fault"] and (current.st_dev, current.st_ino) == (initial.st_dev, initial.st_ino):
                state["changed"] = True
                if state["fault"] == "bytes":
                    target.chmod(0o600)
                    target.write_bytes(b"X" + content[1:])
                    target.chmod(0o400)
                elif state["fault"] == "mode":
                    target.chmod(0o666)
                elif state["fault"] == "link":
                    os.link(target, tmp_path / "alias")
            return content

    monkeypatch.setattr(os, "fstat", lambda fd: Snapshot(actual_fstat(fd)))
    monkeypatch.setattr(os, "listxattr", listxattr)
    monkeypatch.setattr(os, "fdopen", lambda *a, **k: ChangedRead(actual_fdopen(*a, **k)))
    # The unit fixture emulates delivery ownership below a pytest temporary
    # directory. Real ancestor custody is qualified on the owned /srv fixture.
    monkeypatch.setattr(initializer.checker, "open_directory", lambda path: os.open(path, initializer.DIRECTORY_FLAGS))
    capture = (lambda: initializer.delivery(root, groups)) if request.param == "application" else (
        lambda: dependency.capture(root, groups, (0, 10001, 0o750) if prepared else (10001, 10001, 0o700)))
    return capture, state, data, initializer.checker.planner.PlanError, request.param


def test_stable_delivery_preserves_all_exact_bytes(delivered):
    capture, _, data, _, _ = delivered
    assert capture() == data


@pytest.mark.parametrize("fault", ["bytes", "mode", "link", "uid", "gid", "acl"])
def test_changed_delivery_refused_despite_coarse_timestamps(delivered, fault):
    capture, state, _, error, route = delivered
    state["fault"] = fault
    reason = "installation_path_acl_unsupported" if fault == "acl" else (
        "installation_init_delivery_file_changed" if route == "application" else "dependency_delivery_file_changed")
    with pytest.raises(error, match=reason):
        capture()


def test_initial_file_acl_is_consistently_unsupported(delivered):
    capture, state, _, error, _ = delivered
    state["fault"] = "initial_acl"
    with pytest.raises(error, match="installation_path_acl_unsupported"):
        capture()


@pytest.mark.parametrize("fault", ["platform", "uid", "parent", "name", "binding"])
def test_delivery_capture_qualification_refuses_foreign_scope(monkeypatch, fault):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    import qualify_private_delivery_capture as qualifier

    monkeypatch.setattr(sys, "platform", "darwin" if fault == "platform" else "linux")
    monkeypatch.setattr(os, "geteuid", lambda: 1 if fault == "uid" else 0)
    parent = Path("/tmp" if fault == "parent" else "/srv") / ("customer" if fault == "name" else "declarai-p37-" + "a" * 32)
    value = {"request": {"root": str(parent / ("other" if fault == "binding" else "installation"))}}
    monkeypatch.setattr(tempfile, "TemporaryDirectory", lambda **_: pytest.fail("foreign scope touched"))
    with pytest.raises(qualifier.initializer.checker.planner.PlanError, match="delivery_capture_fixture_scope_required"):
        qualifier.qualify(value, parent)
