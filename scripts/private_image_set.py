#!/usr/bin/env python3
"""Verify one offline native image set using a separately trusted manifest digest.

Inputs are explicitly trusted, pristine operator images, never installation
snapshots. This is an image handoff, not an installer or supply authentication.
No image tags, dependency pulls, migrations or service adoption are performed.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import uuid
from pathlib import Path

import private_api_package as api
from private_frontend_package import LICENSES, STATIC, safe_name

ROLES = ("api", "ingress", "postgres", "redis")
HEX = re.compile(r"[0-9a-f]{64}\Z")
SCOPE = "private_native_images_only"
CONFIG = {"/etc/nginx/nginx.conf", "/opt/declarai/start-ingress.sh"}


def prepare_dependency(role, base_image, tag):
    if role not in {"postgres", "redis"} or not isinstance(base_image, str) or not api.DIGEST.fullmatch(base_image):
        raise api.PackageError("image_set_dependency_base_required")
    if not re.fullmatch(r"declarai-private-" + role + r":[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", tag):
        raise api.PackageError("image_set_dependency_tag_invalid")
    if api.run(["docker", "image", "ls", "--quiet", tag]).strip():
        raise api.PackageError("package_build_tag_exists")
    info = api.inspect_image(base_image)
    if info["Id"] != base_image or info["Architecture"] not in {"amd64", "arm64"}:
        raise api.PackageError("image_set_native_architecture_required")
    inventory = runtime(role, info)
    reference = "declarai-private-component-base:" + uuid.uuid4().hex
    api.run(["docker", "image", "tag", base_image, reference])
    try:
        with tempfile.TemporaryDirectory(prefix="declarai-component-build-") as temp:
            # A fresh native manifest preserves the pinned base filesystem and
            # entrypoint, without weakening the tag-free single-graph reader to
            # accept upstream multi-platform/attestation graph selections.
            Path(temp, "Dockerfile").write_text(
                "ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\n"
                + "LABEL org.declarai.private.component="
                + role
                + "\n"
                + "LABEL org.declarai.private.base.image="
                + base_image
                + "\n"
            )
            api.run(
                [
                    "docker",
                    "build",
                    "--provenance=false",
                    "--pull=false",
                    "--network=none",
                    "--platform=linux/" + info["Architecture"],
                    "--build-arg",
                    "BASE_IMAGE=" + reference,
                    "--tag",
                    tag,
                    temp,
                ],
                timeout=600,
            )
    finally:
        api.run(["docker", "image", "rm", reference])
    result = api.inspect_image(tag)
    if runtime(role, result) != inventory or result["Architecture"] != info["Architecture"]:
        raise api.PackageError("image_set_prepared_runtime_mismatch")
    return {
        "role": role,
        "image_id": result["Id"],
        "base_image_id": base_image,
        "architecture": result["Architecture"],
        "runtime": inventory,
        "installation_qualified": False,
    }


def probe(image, entrypoint, arguments, user="65534:65534"):
    return api.run(
        [
            "docker",
            "run",
            "--rm",
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            user,
            "--cpus",
            "1",
            "--memory",
            "256m",
            "--pids-limit",
            "32",
            "--entrypoint",
            entrypoint,
            image,
            *arguments,
        ]
    )


def runtime(role, info):
    config = info["Config"]
    if role == "api":
        if config.get("User") != "10001:10001" or config.get("Entrypoint") != [
            "python",
            "/app/scripts/private_service.py",
        ]:
            raise api.PackageError("image_set_api_profile_invalid")
        return json.loads(
            probe(info["Id"], "python", ["/app/scripts/private_runtime_manifest.py", "verify"], "10001:10001")
        )
    if role == "ingress":
        if (
            config.get("User") != "10001:10001"
            or config.get("Entrypoint") != ["/bin/sh", "/opt/declarai/start-ingress.sh"]
            or config.get("Cmd") not in (None, [])
        ):
            raise api.PackageError("image_set_ingress_profile_invalid")
        version = probe(info["Id"], "/bin/sh", ["-c", "nginx -v 2>&1"], "10001:10001").decode().strip()
        # Hash every sealed asset and fixed runtime file without TLS keys,
        # installation mounts, templates, startup or application execution.
        output = probe(
            info["Id"],
            "/bin/sh",
            [
                "-c",
                'test -z "$(find /opt/declarai/frontend ! -type d ! -type f -print)" && '
                "sha256sum /etc/nginx/nginx.conf /opt/declarai/start-ingress.sh && "
                "find /opt/declarai/frontend -type f -exec sha256sum {} +",
            ],
            "10001:10001",
        )
        if len(output) > api.MAX_METADATA_BYTES:
            raise api.PackageError("image_set_inventory_budget")
        files = {}
        for line in output.decode().splitlines():
            digest, name = line.split("  ", 1)
            if name in files:
                raise api.PackageError("image_set_inventory_invalid")
            files[name] = digest
        value = {"version": version, "files": files}
    else:
        program = "postgres" if role == "postgres" else "redis-server"
        if config.get("Entrypoint") != ["docker-entrypoint.sh"] or config.get("Cmd") != [program]:
            raise api.PackageError("image_set_dependency_profile_invalid")
        value = {"version": probe(info["Id"], program, ["--version"]).decode().strip()}
    validate_runtime(role, value)
    return value


def validate_runtime(role, value):
    if not isinstance(value, dict):
        raise api.PackageError("image_set_runtime_invalid")
    if role == "ingress":
        if set(value) != {"version", "files"} or value["version"] != "nginx version: nginx/1.30.5":
            raise api.PackageError("image_set_ingress_runtime_invalid")
        files = value["files"]
        if not isinstance(files, dict) or not 3 <= len(files) <= 514 or not CONFIG <= set(files):
            raise api.PackageError("image_set_inventory_invalid")
        assets = set()
        for name, digest in files.items():
            if not isinstance(digest, str) or not HEX.fullmatch(digest):
                raise api.PackageError("image_set_inventory_invalid")
            if name in CONFIG:
                continue
            if not isinstance(name, str) or not name.startswith("/opt/declarai/frontend/"):
                raise api.PackageError("image_set_inventory_invalid")
            relative = name.removeprefix("/opt/declarai/frontend/")
            if (
                not safe_name(relative)
                or relative.split("/")[0] in {"api", "media", "admin"}
                or Path(relative).suffix not in STATIC
                and relative not in LICENSES | {"3rdpartylicenses.txt"}
            ):
                raise api.PackageError("image_set_inventory_invalid")
            assets.add(relative)
        if not {"index.html", "3rdpartylicenses.txt", *LICENSES} <= assets or not any(
            n.endswith(".js") for n in assets
        ):
            raise api.PackageError("image_set_frontend_required")
    else:
        if set(value) != {"version"} or not isinstance(value["version"], str) or len(value["version"]) > 500:
            raise api.PackageError("image_set_dependency_runtime_invalid")
        pattern = (
            r"postgres \(PostgreSQL\) 17\.\d+(?:[ .][ -~]*)?"
            if role == "postgres"
            else r"Redis server v=7\.\d+\.\d+ [ -~]+"
        )
        if not re.fullmatch(pattern, value["version"]):
            raise api.PackageError("image_set_dependency_version_invalid")


def record_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    return api.sha(path)


def read_record(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise api.PackageError("image_set_duplicate_json_key")
            value[key] = item
        return value

    return json.loads(path.read_text(), object_pairs_hook=unique)


def export(images, destination):
    if set(images) != set(ROLES) or any(not isinstance(v, str) or not api.DIGEST.fullmatch(v) for v in images.values()):
        raise api.PackageError("image_set_exact_roles_required")
    if len(set(images.values())) != len(ROLES):
        raise api.PackageError("image_set_distinct_roles_required")
    if destination.exists() or destination.is_symlink():
        raise api.PackageError("package_destination_exists")
    infos = {role: api.inspect_image(image) for role, image in images.items()}
    if any(info["Id"] != images[role] for role, info in infos.items()):
        raise api.PackageError("image_set_exact_identity_required")
    architectures = {v["Architecture"] for v in infos.values()}
    if len(architectures) != 1 or not architectures <= {"amd64", "arm64"}:
        raise api.PackageError("image_set_native_architecture_required")
    with tempfile.TemporaryDirectory(prefix="declarai-image-set-export-", dir=destination.parent) as temp:
        stage = Path(temp) / "set"
        stage.mkdir(mode=0o700)
        components = {}
        for role in ROLES:
            target = stage / role
            if role == "api":
                result = api.export(images[role], target)
                digest = result["manifest_sha256"]
            else:
                info = infos[role]
                inventory = runtime(role, info)
                target.mkdir(mode=0o700)
                raw = Path(temp) / (role + "-save.tar")
                archive = target / "image.tar"
                api.run(["docker", "image", "save", "--output", str(raw), info["Id"]], timeout=600)
                api.normalize_save(raw, archive, info["Id"])
                raw.unlink()
                digest = record_json(
                    target / "manifest.json",
                    {
                        "schema": "private_component_image_v1",
                        "role": role,
                        "image_id": info["Id"],
                        "os": "linux",
                        "architecture": info["Architecture"],
                        "variant": info.get("Variant", ""),
                        "runtime": inventory,
                        "archive": {"file": "image.tar", "bytes": archive.stat().st_size, "sha256": api.sha(archive)},
                    },
                )
            components[role] = {"image_id": images[role], "manifest_sha256": digest}
        digest = record_json(
            stage / "manifest.json",
            {
                "schema": "private_image_set_v1",
                "architecture": architectures.pop(),
                "components": components,
                "scope": SCOPE,
                "installation_qualified": False,
                "release_qualified": False,
                "expert_isolation_qualified": False,
            },
        )
        verify_staged(stage, digest)
        stage.rename(destination)
    return {"manifest_sha256": digest, "images": images, "scope": SCOPE}


def copy_file(source_fd, name, target, limit):
    descriptor = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=source_fd)
    with os.fdopen(descriptor, "rb") as source, target.open("xb") as output:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise api.PackageError("image_set_member_invalid")
        copied = 0
        while block := source.read(1024 * 1024):
            copied += len(block)
            if copied > limit:
                raise api.PackageError("image_set_member_budget")
            output.write(block)


def snapshot(directory, stage):
    # Directory FDs pin the source tree, rejecting links/FIFOs before reading.
    # A replacement of the caller's path cannot replace our verified import.
    root = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if set(os.listdir(root)) != {"manifest.json", *ROLES}:
            raise api.PackageError("image_set_members_invalid")
        copy_file(root, "manifest.json", stage / "manifest.json", api.MAX_METADATA_BYTES)
        for role in ROLES:
            child = os.open(role, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            try:
                if set(os.listdir(child)) != {"manifest.json", "image.tar"}:
                    raise api.PackageError("image_set_component_members_invalid")
                target = stage / role
                target.mkdir(mode=0o700)
                copy_file(child, "manifest.json", target / "manifest.json", api.MAX_METADATA_BYTES)
                copy_file(child, "image.tar", target / "image.tar", api.MAX_IMAGE_BYTES)
            finally:
                os.close(child)
    finally:
        os.close(root)


def verify_staged(stage, expected):
    if not isinstance(expected, str) or not HEX.fullmatch(expected):
        raise api.PackageError("package_trusted_digest_required")
    file = stage / "manifest.json"
    if not 0 < file.stat().st_size <= api.MAX_METADATA_BYTES or api.sha(file) != expected:
        raise api.PackageError("image_set_manifest_digest_mismatch")
    try:
        value = read_record(file)
        if (
            set(value)
            != {
                "schema",
                "architecture",
                "components",
                "scope",
                "installation_qualified",
                "release_qualified",
                "expert_isolation_qualified",
            }
            or value["schema"] != "private_image_set_v1"
            or value["scope"] != SCOPE
            or value["architecture"] not in {"amd64", "arm64"}
            or any(
                value[k] is not False
                for k in ["installation_qualified", "release_qualified", "expert_isolation_qualified"]
            )
            or set(value["components"]) != set(ROLES)
        ):
            raise ValueError
        ids = set()
        for role in ROLES:
            pin = value["components"][role]
            if (
                set(pin) != {"image_id", "manifest_sha256"}
                or not api.DIGEST.fullmatch(pin["image_id"])
                or not HEX.fullmatch(pin["manifest_sha256"])
            ):
                raise ValueError
            if role == "api":
                read_record(stage / role / "manifest.json")
                component = api.verify_package(stage / role, pin["manifest_sha256"])
            else:
                manifest = stage / role / "manifest.json"
                if (
                    not 0 < manifest.stat().st_size <= api.MAX_METADATA_BYTES
                    or api.sha(manifest) != pin["manifest_sha256"]
                ):
                    raise api.PackageError("image_set_component_digest_mismatch")
                component = read_record(manifest)
                if (
                    set(component)
                    != {"schema", "role", "image_id", "os", "architecture", "variant", "runtime", "archive"}
                    or component["schema"] != "private_component_image_v1"
                    or component["role"] != role
                    or component["os"] != "linux"
                    or not isinstance(component["variant"], str)
                    or len(component["variant"]) > 32
                ):
                    raise ValueError
                validate_runtime(role, component["runtime"])
                archive = component["archive"]
                if (
                    set(archive) != {"file", "bytes", "sha256"}
                    or archive["file"] != "image.tar"
                    or type(archive["bytes"]) is not int
                    or not 0 < archive["bytes"] <= api.MAX_IMAGE_BYTES
                    or not HEX.fullmatch(archive["sha256"])
                ):
                    raise ValueError
                path = stage / role / "image.tar"
                if path.stat().st_size != archive["bytes"] or api.sha(path) != archive["sha256"]:
                    raise api.PackageError("package_archive_digest_mismatch")
                api.verify_archive(path, pin["image_id"])
            if component["image_id"] != pin["image_id"] or component["architecture"] != value["architecture"]:
                raise api.PackageError("image_set_identity_platform_mismatch")
            ids.add(component["image_id"])
        if len(ids) != len(ROLES):
            raise api.PackageError("image_set_distinct_roles_required")
    except api.PackageError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        raise api.PackageError("image_set_manifest_invalid") from None
    return value


def consume(directory, expected, *, load=False):
    if not isinstance(expected, str) or not HEX.fullmatch(expected):
        raise api.PackageError("package_trusted_digest_required")
    with tempfile.TemporaryDirectory(prefix="declarai-image-set-import-") as temp:
        stage = Path(temp)
        snapshot(directory, stage)
        value = verify_staged(stage, expected)
        if load:
            platform = api.run(["docker", "info", "--format", "{{.OSType}} {{.Architecture}}"]).decode().strip().split()
            machines = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}
            if len(platform) != 2 or platform[0] != "linux" or machines.get(platform[1]) != value["architecture"]:
                raise api.PackageError("package_native_platform_required")
            # Every component is verified before the first consequential load.
            # A later engine/runtime failure can leave imported digests; it
            # cannot retag, start services or adopt an installation.
            for role in ROLES:
                component = read_record(stage / role / "manifest.json")
                api.run(["docker", "image", "load", "--input", str(stage / role / "image.tar")], timeout=600)
                info = api.inspect_image(component["image_id"])
                if (
                    info["Id"] != component["image_id"]
                    or info["Os"] != component["os"]
                    or info["Architecture"] != component["architecture"]
                    or info.get("Variant", "") != component["variant"]
                    or runtime(role, info) != component["runtime"]
                ):
                    raise api.PackageError("image_set_loaded_runtime_mismatch")
    return {
        "manifest_sha256": expected,
        "images": {k: v["image_id"] for k, v in value["components"].items()},
        "archive_verified": True,
        "loaded": load,
        "installation_qualified": False,
        "release_qualified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("prepare")
    prepare.add_argument("--role", choices=["postgres", "redis"], required=True)
    prepare.add_argument("--base-image", required=True)
    prepare.add_argument("--tag", required=True)
    output = actions.add_parser("export")
    output.add_argument("destination", type=Path)
    for role in ROLES:
        output.add_argument("--" + role + "-image", required=True)
    for action in ["verify", "load"]:
        command = actions.add_parser(action)
        command.add_argument("directory", type=Path)
        command.add_argument("--expected-manifest-sha256", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        value = prepare_dependency(args.role, args.base_image, args.tag)
    elif args.action == "export":
        value = export({role: getattr(args, role + "_image") for role in ROLES}, args.destination.absolute())
    else:
        value = consume(args.directory.absolute(), args.expected_manifest_sha256, load=args.action == "load")
    print(json.dumps(value))


if __name__ == "__main__":
    try:
        main()
    except (api.PackageError, OSError, ValueError, UnicodeError) as error:
        print(str(error) if isinstance(error, api.PackageError) else "image_set_io_failed", file=sys.stderr)
        sys.exit(1)
