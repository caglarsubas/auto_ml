#!/usr/bin/env python3
"""Delivery capture faults affect only synthetic copies in an owned fixture."""

import os
import re
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import private_dependency_init as dependency
import private_installation_init as initializer


def qualify(value, parent):
    if (sys.platform != "linux" or os.geteuid() != 0 or parent.parent != Path("/srv")
            or not re.fullmatch(r"declarai-p37-[0-9a-f]{32}", parent.name)
            or value["request"]["root"] != str(parent / "installation")):
        raise initializer.checker.planner.PlanError("delivery_capture_fixture_scope_required")
    application = {
        "app/django-key": b"Synthetic-Key-Only-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789",
        "app/app-password": b"synthetic-not-a-real-password",
        "app/job-broker-url": b"rediss://:synthetic@job-broker:6379/1",
        "app/postgres-ca.crt": b"synthetic opaque certificate",
        "app/job-ca.crt": b"synthetic opaque certificate",
        "app/cache-url": b"rediss://:synthetic@cache:6379/0",
        "app/cache-ca.crt": b"synthetic opaque certificate",
        "tls/tls.crt": b"synthetic opaque certificate",
        "tls/tls.key": b"synthetic opaque key",
    }
    dependencies = {
        "postgres/owner-password": b"synthetic-owner-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "postgres/server.crt": b"synthetic opaque certificate",
        "postgres/server.key": b"synthetic opaque key",
        "job-broker/server.crt": b"synthetic opaque certificate",
        "job-broker/server.key": b"synthetic opaque key",
        "cache/server.crt": b"synthetic opaque certificate",
        "cache/server.key": b"synthetic opaque key",
    }
    results = {}
    with tempfile.TemporaryDirectory(prefix="delivery-capture-", dir=parent) as temporary:
        for route in ("application", "dependency", "prepared_app"):
            root = Path(temporary) / route
            root.mkdir(mode=0o750 if route == "prepared_app" else 0o700)
            identity = (0, 10001, 0o750) if route == "prepared_app" else (10001, 10001, 0o700)
            os.chown(root, *identity[:2])
            data = dependencies if route == "dependency" else application
            groups = {group: [name.split("/", 1)[1] for name in data if name.startswith(group + "/")]
                      for group in dict.fromkeys(name.split("/")[0] for name in data)}
            for group in groups:
                (root / group).mkdir(mode=0o700)
                os.chown(root / group, 10001, 10001)
            for name, content in data.items():
                (root / name).write_bytes(content)
                os.chown(root / name, 10001, 10001)
                (root / name).chmod(0o400)
            capture = (lambda: initializer.delivery(root, groups)) if route == "application" else (
                lambda: dependency.capture(root, groups, identity))
            assert capture() == data
            row = {"exact_delivered_bytes": "passed"}
            path, alias = root / next(iter(data)), root / "alias"
            for fault in ("bytes", "mode", "link", "uid", "gid", "acl", "initial_acl"):
                before = path.stat()
                actual_fstat, actual_fdopen = os.fstat, os.fdopen
                acl_added = False

                def add_acl():
                    nonlocal acl_added
                    # Zero extra access preserves mode 0400; custody forbids
                    # even an otherwise harmless extended ACL.
                    acl = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in (
                        (1, 4, 0xffffffff), (2, 0, 10002), (4, 0, 0xffffffff),
                        (16, 0, 0xffffffff), (32, 0, 0xffffffff),
                    ))
                    os.setxattr(path, "system.posix_acl_access", acl)
                    acl_added = True

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
                        result = self.stream.read(limit)
                        current = actual_fstat(self.fileno())
                        if not self.changed and (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino):
                            self.changed = True
                            if fault == "bytes":
                                path.chmod(0o600)
                                path.write_bytes(b"X" + result[1:])
                                path.chmod(0o400)
                            elif fault == "mode":
                                path.chmod(0o666)
                            elif fault == "link":
                                os.link(path, alias)
                            elif fault == "uid":
                                os.chown(path, 10002, 10001)
                            elif fault == "gid":
                                os.chown(path, 10001, 10002)
                            else:
                                add_acl()
                        return result

                try:
                    if fault == "initial_acl":
                        add_acl()
                    with patch("os.fstat", side_effect=fstat), patch("os.fdopen", side_effect=lambda *a, **k: ChangedRead(actual_fdopen(*a, **k))):
                        try:
                            capture()
                        except initializer.checker.planner.PlanError as error:
                            expected = "installation_path_acl_unsupported" if fault in {"acl", "initial_acl"} else (
                                "installation_init_delivery_file_changed" if route == "application" else "dependency_delivery_file_changed")
                            assert str(error) == expected
                            row[fault] = "rejected"
                        else:
                            raise AssertionError("unstable_delivery_capture_accepted")
                finally:
                    if alias.exists():
                        alias.unlink()
                    os.chown(path, 10001, 10001)
                    if acl_added:
                        os.removexattr(path, "system.posix_acl_access")
                    path.chmod(0o600)
                    path.write_bytes(data[next(iter(data))])
                    path.chmod(0o400)
            assert capture() == data
            row["copied_inputs_restored"] = "passed"
            results[route] = row
    return {"controller_delivery_capture": results, "installed_inputs_modified": False, "private_values_emitted": False}
