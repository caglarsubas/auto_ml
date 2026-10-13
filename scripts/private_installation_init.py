#!/usr/bin/env python3
"""Initialize a fresh Linux installation from a verified plan and secret delivery.

No credentials are generated, hashed in evidence, or printed. No dependency,
network, migration, container or existing installation is modified.
"""

import argparse
import ctypes
import errno
import json
import os
import re
import stat
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import private_installation_check as checker

UID = 10001
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def trusted_directory(path):
    """Initialization needs root-owned, non-writable, ACL-free ancestors."""
    descriptor = os.open("/", DIRECTORY_FLAGS)
    try:
        for part in Path(path).parts[1:]:
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
                raise checker.planner.PlanError("installation_init_parent_unsafe")
            checker.no_directory_acl(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def absent(parent, name):
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise checker.planner.PlanError("installation_init_destination_exists")


def rename_noreplace(parent, source, destination):
    """Atomic Linux no-replace publication; no weaker rename fallback."""
    library = ctypes.CDLL(None, use_errno=True)
    try:
        rename = library.renameat2
    except AttributeError:
        raise checker.planner.PlanError("installation_init_atomic_publish_unavailable") from None
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    if rename(parent, source.encode(), parent, destination.encode(), 1):
        code = ctypes.get_errno()
        reason = (
            "installation_init_destination_exists"
            if code in {errno.EEXIST, errno.ENOTEMPTY}
            else "installation_init_atomic_publish_failed"
        )
        raise checker.planner.PlanError(reason)


def delivery(path, names):
    """Capture seven bounded secret files using pinned descriptors."""
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise checker.planner.PlanError("installation_init_delivery_path_invalid")
    root = checker.open_directory(path)
    files = {}
    try:
        check_directory(root)
        if set(os.listdir(root)) != {"app", "tls"}:
            raise checker.planner.PlanError("installation_init_delivery_members_invalid")
        for group, members in names.items():
            descriptor = os.open(group, DIRECTORY_FLAGS, dir_fd=root)
            try:
                check_directory(descriptor)
                if set(os.listdir(descriptor)) != set(members):
                    raise checker.planner.PlanError("installation_init_delivery_members_invalid")
                for name in members:
                    fd = os.open(
                        name,
                        os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                        dir_fd=descriptor,
                    )
                    with os.fdopen(fd, "rb") as stream:
                        info = os.fstat(stream.fileno())
                        maximum = 65_536 if name.endswith((".crt", ".key")) else 4096
                        if (
                            not stat.S_ISREG(info.st_mode)
                            or info.st_nlink != 1
                            or info.st_uid != UID
                            or info.st_gid != UID
                            or stat.S_IMODE(info.st_mode) != 0o400
                            or not 0 < info.st_size <= maximum
                        ):
                            raise checker.planner.PlanError("installation_init_delivery_file_invalid")
                        checker.no_directory_acl(stream.fileno())
                        data = stream.read(maximum + 1)
                        stream.seek(0)
                        repeated = stream.read(maximum + 1)
                        if len(data) != info.st_size or not 0 < len(data) <= maximum:
                            raise checker.planner.PlanError("installation_init_delivery_file_changed")
                        after = os.fstat(stream.fileno())
                        fields = ("st_dev", "st_ino", "st_size", "st_mode", "st_uid", "st_gid", "st_nlink", "st_mtime_ns", "st_ctime_ns")
                        if data != repeated or any(getattr(info, key) != getattr(after, key) for key in fields):
                            raise checker.planner.PlanError("installation_init_delivery_file_changed")
                        checker.no_directory_acl(stream.fileno())
                        files[group + "/" + name] = data
            finally:
                os.close(descriptor)
    finally:
        os.close(root)
    validate_secrets(files)
    return files


def check_directory(descriptor):
    info = os.fstat(descriptor)
    if info.st_uid != UID or info.st_gid != UID or stat.S_IMODE(info.st_mode) != 0o700:
        raise checker.planner.PlanError("installation_init_delivery_identity_invalid")
    checker.no_directory_acl(descriptor)


def validate_secrets(files):
    """Validate initial application value shape; certificate trust stays external."""
    try:
        values = {}
        for name in ("django-key", "app-password", "job-broker-url"):
            value = files["app/" + name].decode("utf-8").rstrip("\r\n")
            if not value or any(c in value for c in "\x00\r\n"):
                raise ValueError
            values[name] = value
        key = values["django-key"]
        if len(key) < 50 or len(set(key)) < 5 or key.startswith("django-insecure-"):
            raise ValueError
        url = values["job-broker-url"]
        parsed = urlsplit(url)
        # No query options may weaken TLS, inject a different endpoint or change
        # transport behavior. Operator-delivered credentials stay opaque.
        if (
            parsed.scheme != "rediss"
            or parsed.hostname != "job-broker"
            or parsed.port != 6379
            or parsed.username not in (None, "")
            or not parsed.password
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"/(?:0|[1-9][0-9]?)", parsed.path)
            or any(c.isspace() for c in url)
        ):
            raise ValueError
        if "app/cache-url" in files:
            cache_url = files["app/cache-url"].decode("utf-8").rstrip("\r\n")
            cache = urlsplit(cache_url)
            if (cache.scheme != "rediss" or cache.hostname != "cache" or cache.port != 6379
                    or cache.username not in (None, "") or not cache.password or cache.path != "/0"
                    or cache.query or cache.fragment or any(c.isspace() for c in cache_url)):
                raise ValueError
    except (UnicodeError, ValueError, KeyError):
        raise checker.planner.PlanError("installation_init_secret_value_invalid") from None


def directory(parent, name, uid, gid, mode):
    os.mkdir(name, mode=0o700, dir_fd=parent)
    descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent)
    try:
        os.fchown(descriptor, uid, gid)
        os.fchmod(descriptor, mode)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def write_file(parent, name, data, uid, gid, mode):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fchown(stream.fileno(), uid, gid)
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())


def remove_stage(parent, name):
    """Remove only this invocation's private staging tree, through directory FDs."""
    descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent)
    try:
        for member in os.listdir(descriptor):
            info = os.stat(member, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                remove_stage(descriptor, member)
            else:
                os.unlink(member, dir_fd=descriptor)
    finally:
        os.close(descriptor)
    os.rmdir(name, dir_fd=parent)


def initialize(plan, expected, source):
    value = checker.verify(plan, expected)
    if sys.platform != "linux" or os.geteuid() != 0:
        raise checker.planner.PlanError("installation_init_linux_root_required")
    target = Path(value["request"]["root"])
    parent = trusted_directory(target.parent)
    stage = ".declarai-init-" + uuid.uuid4().hex
    staged = False
    try:
        absent(parent, target.name)  # Existing targets block before secret reads.
        files = delivery(source, value["prerequisites"]["secret_files"])
        result = {
            **checker.receipt(value, expected),
            "schema": "private_installation_initialization_v1",
            "initialization_id": stage.removeprefix(".declarai-init-"),
            "filesystem_initialized": True,
            "secret_files_delivered": len(files),
            "secret_values_emitted": False,
            "certificate_trust_verified": False,
            "encrypted_storage_verified": False,
            "dependencies_initialized": False,
            "services_adopted": False,
        }
        os.mkdir(stage, mode=0o700, dir_fd=parent)
        staged = True
        root = os.open(stage, DIRECTORY_FLAGS, dir_fd=parent)
        try:
            secrets = directory(root, "secrets", 0, UID, 0o750)
            try:
                for group in ("app", "tls"):
                    child = directory(secrets, group, 0, 0, 0o700)
                    try:
                        for name in value["prerequisites"]["secret_files"][group]:
                            write_file(child, name, files[group + "/" + name], UID, UID, 0o400)
                        os.fchown(child, UID, UID)
                        os.fsync(child)
                    finally:
                        os.close(child)
                os.fsync(secrets)
            finally:
                os.close(secrets)
            artifacts = directory(root, "artifacts", UID, UID, 0o700)
            try:
                os.fsync(artifacts)
            finally:
                os.close(artifacts)
            write_file(
                root,
                "initialization.json",
                checker.planner.encoded(result),
                0,
                0,
                0o600,
            )
            os.fchown(root, 0, UID)
            os.fsync(root)
            rename_noreplace(parent, stage, target.name)
            staged = False
            # Do not expose the staged UID 10001 directories until publication.
            os.fchmod(root, 0o750)
            os.fsync(root)
            os.fsync(parent)
        finally:
            os.close(root)
        return result
    finally:
        try:
            if staged:
                remove_stage(parent, stage)
        finally:
            os.close(parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--secret-delivery", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(initialize(args.plan, args.expected_plan_sha256, args.secret_delivery)))


if __name__ == "__main__":
    try:
        main()
    except (checker.planner.PlanError, OSError, ValueError, UnicodeError) as error:
        print(
            str(error) if isinstance(error, checker.planner.PlanError) else "installation_init_io_failed",
            file=sys.stderr,
        )
        sys.exit(1)
