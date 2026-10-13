#!/usr/bin/env python3
"""Stored controller capture faults affect only owned temporary copies."""

import os
import re
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import private_dependency_start as startup


def qualify(value, parent):
    if (sys.platform != "linux" or os.geteuid() != 0 or parent.parent != Path("/srv")
            or not re.fullmatch(r"declarai-p37-[0-9a-f]{32}", parent.name)
            or value["request"]["root"] != str(parent / "installation")):
        raise startup.checker.planner.PlanError("controller_capture_fixture_scope_required")
    results = {}
    with tempfile.TemporaryDirectory(prefix="controller-capture-", dir=parent) as temporary:
        root = Path(temporary)
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        path, alias = root / "stored", root / "alias"
        data = b"synthetic-controller-evidence\n"
        try:
            for mode in (0o400, 0o600):
                if path.exists():
                    path.chmod(0o600)
                path.write_bytes(data)
                path.chmod(mode)
                assert startup.read_file(descriptor, path.name, 0, 0, mode, 64) == data
            results["exact_stored_bytes"] = "passed"
            for fault in ("bytes", "mode", "link", "uid", "gid", "acl"):
                path.chmod(0o600)
                path.write_bytes(data)
                before = path.stat()
                actual_fstat, actual_fdopen = os.fstat, os.fdopen
                acl_added = False

                class CoarseTimes:
                    st_mtime_ns, st_ctime_ns = before.st_mtime_ns, before.st_ctime_ns

                    def __init__(self, current):
                        self.current = current

                    def __getattr__(self, name):
                        return getattr(self.current, name)

                def fstat(fd):
                    current = actual_fstat(fd)
                    return CoarseTimes(current) if (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino) else current

                class ChangedRead:
                    def __init__(self, stream):
                        self.stream, self.changed = stream, False

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        self.stream.close()

                    def fileno(self):
                        return self.stream.fileno()

                    def seek(self, offset):
                        return self.stream.seek(offset)

                    def read(self, limit):
                        nonlocal acl_added
                        result = self.stream.read(limit)
                        current = actual_fstat(self.fileno())
                        if not self.changed and (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino):
                            self.changed = True
                            if fault == "bytes":
                                path.write_bytes(b"X" + result[1:])
                            elif fault == "mode":
                                path.chmod(0o666)
                            elif fault == "link":
                                os.link(path, alias)
                            elif fault == "uid":
                                os.chown(path, 10001, 0)
                            elif fault == "gid":
                                os.chown(path, 0, 10001)
                            else:
                                # An extended ACL with zero extra access keeps
                                # mode 0600; the no-ACL contract still applies.
                                acl = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in (
                                    (1, 6, 0xffffffff), (2, 0, 10001), (4, 0, 0xffffffff),
                                    (16, 0, 0xffffffff), (32, 0, 0xffffffff),
                                ))
                                os.setxattr(path, "system.posix_acl_access", acl)
                                acl_added = True
                        return result

                try:
                    with patch("os.fstat", side_effect=fstat), patch("os.fdopen", side_effect=lambda *a, **k: ChangedRead(actual_fdopen(*a, **k))):
                        try:
                            startup.read_file(descriptor, path.name, 0, 0, 0o600, 64)
                        except startup.checker.planner.PlanError as error:
                            expected = "installation_path_acl_unsupported" if fault == "acl" else "dependency_stored_file_changed"
                            assert str(error) == expected
                            results[fault] = "rejected"
                        else:
                            raise AssertionError("unstable_controller_capture_accepted")
                finally:
                    if alias.exists():
                        alias.unlink()
                    os.chown(path, 0, 0)
                    if acl_added:
                        os.removexattr(path, "system.posix_acl_access")
                    path.chmod(0o600)
        finally:
            os.close(descriptor)
    return {"controller_stored_capture": results, "installed_inputs_modified": False, "private_values_emitted": False}
