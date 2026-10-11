#!/usr/bin/env python3
"""Verify saved private plans and inspect Linux filesystem prerequisites only."""

import argparse
import errno
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import private_installation_plan as planner

LIMITS = {name: 65_536 for name in planner.FILES}
LIMITS.update(
    {
        "request.json": planner.MAX_REQUEST,
        "image-set.json": planner.image_set.api.MAX_METADATA_BYTES,
        "ingress.json": planner.image_set.api.MAX_METADATA_BYTES,
        "manifest.json": 16_384,
    }
)


def read_plan(directory):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if set(os.listdir(descriptor)) != set(LIMITS):
            raise planner.PlanError("installation_plan_members_invalid")
        values = {}
        for name, limit in LIMITS.items():
            fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=descriptor)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                    raise planner.PlanError("installation_plan_member_invalid")
                values[name] = stream.read(limit + 1)
                if not 0 < len(values[name]) <= limit:
                    raise planner.PlanError("installation_plan_member_budget")
        return values
    finally:
        os.close(descriptor)


def verify(directory, expected):
    if not isinstance(expected, str) or not planner.image_set.HEX.fullmatch(expected):
        raise planner.PlanError("installation_trusted_plan_digest_required")
    files = read_plan(directory)
    if hashlib.sha256(files["manifest.json"]).hexdigest() != expected:
        raise planner.PlanError("installation_plan_digest_mismatch")
    try:
        manifest = planner.decode(files["manifest.json"])
        if (
            set(manifest)
            != {
                "schema",
                "installation_id",
                "image_set_manifest_sha256",
                "architecture",
                "files",
                "scope",
                "archive_verified_at_render",
                "installation_qualified",
                "release_qualified",
                "expert_isolation_qualified",
            }
            or manifest["schema"] not in {"private_installation_plan_v1", planner.PLAN_SCHEMA}
            or manifest["scope"] != "native_application_layer_with_operator_managed_dependencies"
            or manifest["archive_verified_at_render"] is not True
            or manifest["architecture"] not in {"arm64", "amd64"}
            or any(
                manifest[k] is not False
                for k in (
                    "installation_qualified",
                    "release_qualified",
                    "expert_isolation_qualified",
                )
            )
            or set(manifest["files"]) != planner.FILES
        ):
            raise ValueError
        for name in planner.FILES:
            digest = manifest["files"][name]
            if (
                not isinstance(digest, str)
                or not planner.image_set.HEX.fullmatch(digest)
                or hashlib.sha256(files[name]).hexdigest() != digest
            ):
                raise planner.PlanError("installation_plan_file_digest_mismatch")
        outer = planner.decode(files["image-set.json"])
        if hashlib.sha256(files["image-set.json"]).hexdigest() != manifest["image_set_manifest_sha256"]:
            raise planner.PlanError("installation_plan_image_set_mismatch")
        if (
            set(outer)
            != {
                "schema",
                "architecture",
                "components",
                "scope",
                "installation_qualified",
                "release_qualified",
                "expert_isolation_qualified",
            }
            or outer["schema"] != "private_image_set_v1"
            or outer["scope"] != planner.image_set.SCOPE
            or outer["architecture"] != manifest["architecture"]
            or set(outer["components"]) != set(planner.image_set.ROLES)
            or any(
                outer[k] is not False
                for k in (
                    "installation_qualified",
                    "release_qualified",
                    "expert_isolation_qualified",
                )
            )
        ):
            raise ValueError
        for pin in outer["components"].values():
            if (
                set(pin) != {"image_id", "manifest_sha256"}
                or not planner.image_set.api.DIGEST.fullmatch(pin["image_id"])
                or not planner.image_set.HEX.fullmatch(pin["manifest_sha256"])
            ):
                raise ValueError
        images = {role: pin["image_id"] for role, pin in outer["components"].items()}
        if len(set(images.values())) != len(planner.image_set.ROLES):
            raise ValueError
        ingress = planner.decode(files["ingress.json"])
        if (
            hashlib.sha256(files["ingress.json"]).hexdigest() != outer["components"]["ingress"]["manifest_sha256"]
            or set(ingress)
            != {
                "schema",
                "role",
                "image_id",
                "os",
                "architecture",
                "variant",
                "runtime",
                "archive",
            }
            or ingress["schema"] != "private_component_image_v1"
            or ingress["role"] != "ingress"
            or ingress["image_id"] != images["ingress"]
            or ingress["os"] != "linux"
            or ingress["architecture"] != manifest["architecture"]
            or not isinstance(ingress["variant"], str)
            or len(ingress["variant"]) > 32
        ):
            raise ValueError
        archive = ingress["archive"]
        if (
            set(archive) != {"file", "bytes", "sha256"}
            or archive["file"] != "image.tar"
            or type(archive["bytes"]) is not int
            or not 0 < archive["bytes"] <= planner.image_set.api.MAX_IMAGE_BYTES
            or not planner.image_set.HEX.fullmatch(archive["sha256"])
        ):
            raise ValueError
        planner.image_set.validate_runtime("ingress", ingress["runtime"])
        request = planner.validate_request(planner.decode(files["request.json"]))
        if request["installation_id"] != manifest["installation_id"]:
            raise ValueError
        planner.bind_ingress(request, ingress)
        compose, prerequisites = (
            planner.composition(request, images),
            planner.prerequisites(request, images, legacy=manifest["schema"] == "private_installation_plan_v1"),
        )
        if planner.encoded(planner.decode(files["compose.json"])) != planner.encoded(compose) or planner.encoded(
            planner.decode(files["prerequisites.json"])
        ) != planner.encoded(prerequisites):
            raise planner.PlanError("installation_plan_profile_mismatch")
    except planner.PlanError:
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        RecursionError,
        planner.image_set.api.PackageError,
    ):
        raise planner.PlanError("installation_plan_invalid") from None
    return {
        "manifest": manifest,
        "images": images,
        "request": request,
        "prerequisites": prerequisites,
    }


def open_directory(path):
    """Pin every absolute ancestor, rejecting links and untrusted writable roots."""
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(path).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if info.st_uid not in {0, 10001} or stat.S_IMODE(info.st_mode) & 0o022:
                raise planner.PlanError("installation_path_ancestor_unsafe")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def no_directory_acl(descriptor):
    try:
        if {"system.posix_acl_access", "system.posix_acl_default"} & set(os.listxattr(descriptor)):
            raise planner.PlanError("installation_path_acl_unsupported")
    except OSError as error:
        if error.errno not in {errno.ENOTSUP, errno.EOPNOTSUPP}:
            raise planner.PlanError("installation_path_acl_unavailable") from None


def check_paths(directory, expected):
    value = verify(directory, expected)
    if sys.platform != "linux" or not hasattr(os, "O_PATH"):
        raise planner.PlanError("installation_paths_linux_required")
    roots, count = [], 0
    for spec in value["prerequisites"]["directories"]:
        descriptor = open_directory(spec["path"])
        try:
            info = os.fstat(descriptor)
            if (
                info.st_uid != spec["uid"]
                or info.st_gid != spec["gid"]
                or stat.S_IMODE(info.st_mode) != int(spec["mode"], 8)
            ):
                raise planner.PlanError("installation_path_identity_invalid")
            no_directory_acl(descriptor)
            roots.append(
                {
                    "kind": "artifacts" if spec["mount"] == "read_write" else Path(spec["path"]).name,
                    "device": info.st_dev,
                    "inode": info.st_ino,
                }
            )
            if spec["mount"] == "read_write":
                continue  # Never inspect or read customer artifact descendants.
            names = value["prerequisites"]["secret_files"][Path(spec["path"]).name]
            if set(os.listdir(descriptor)) != set(names):
                raise planner.PlanError("installation_secret_members_invalid")
            for name in names:
                # O_PATH opens metadata only, even for unreadable secret values.
                fd = os.open(name, os.O_PATH | os.O_NOFOLLOW, dir_fd=descriptor)
                try:
                    item = os.fstat(fd)
                    maximum = 65_536 if name.endswith((".crt", ".key")) else 4096
                    if (
                        not stat.S_ISREG(item.st_mode)
                        or item.st_nlink != 1
                        or item.st_uid != 10001
                        or item.st_gid != 10001
                        or stat.S_IMODE(item.st_mode) != 0o400
                        or not 0 < item.st_size <= maximum
                    ):
                        raise planner.PlanError("installation_secret_metadata_invalid")
                    count += 1
                finally:
                    os.close(fd)
        finally:
            os.close(descriptor)
    return {
        **receipt(value, expected),
        "filesystem_prerequisites": "passed",
        "secret_metadata_files": count,
        "roots": roots,
        "secret_contents_read": False,
        "artifact_descendants_inspected": False,
        "encrypted_storage_verified": False,
        "networks_and_socket_verified": False,
        "runtime_connectivity_verified": False,
    }


def receipt(value, expected):
    return {
        "schema": "private_installation_check_v1",
        "plan_manifest_sha256": expected,
        "installation_id": value["request"]["installation_id"],
        "architecture": value["manifest"]["architecture"],
        "plan_verified": True,
        "archives_reverified": False,
        "installation_qualified": False,
        "release_qualified": False,
        "expert_isolation_qualified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify", "check-paths"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    args = parser.parse_args()
    result = (
        check_paths(args.directory, args.expected_plan_sha256)
        if args.action == "check-paths"
        else receipt(verify(args.directory, args.expected_plan_sha256), args.expected_plan_sha256)
    )
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (planner.PlanError, OSError, ValueError, UnicodeError) as error:
        print(
            str(error) if isinstance(error, planner.PlanError) else "installation_check_io_failed",
            file=sys.stderr,
        )
        sys.exit(1)
