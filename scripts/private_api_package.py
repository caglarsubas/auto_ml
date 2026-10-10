#!/usr/bin/env python3
"""Allowlisted build context and exact-image offline API handoff.

verify/load require a trusted, separately obtained manifest digest. Verification
does not certify provenance, absence of vulnerabilities or release readiness.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_IMAGE_BYTES = 8 * 1024**3
MAX_METADATA_BYTES = 2_000_000
APPS = {
    "backend",
    "access_control",
    "ai_assistant",
    "declaration",
    "deployment",
    "encoding",
    "evaluation",
    "execution_jobs",
    "feature_card",
    "modeling",
    "preprocessing",
}
RUNTIME_FILES = {
    "scripts/private_runtime_manifest.py",
    "scripts/private_service.py",
    "docker/private-gunicorn.py",
    "docker/private-job-entrypoint.sh",
}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class PackageError(Exception):
    pass


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run(argv, timeout=120):
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise PackageError("package_command_failed") from None
    if result.returncode:
        raise PackageError("package_command_failed")
    return result.stdout


def allowed_source(name):
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or any(part in (".", "..") for part in path.parts):
        return False
    if name in RUNTIME_FILES or name == "backend/manage.py":
        return True
    if len(path.parts) >= 3 and path.parts[0] == "backend" and path.parts[1] in APPS:
        if "tests" in path.parts or path.name == "tests.py":
            return False
        return path.suffix == ".py" or (
            path.parts[:3] == ("backend", "ai_assistant", "skills") and path.suffix in (".md", ".txt")
        )
    return len(path.parts) == 3 and path.parts[:2] == ("docs", "knowledge-bank") and path.suffix == ".md"


def read_source(root, name):
    path = root / name
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent):
        raise PackageError("package_source_symlink")
    if not path.is_file() or not 0 <= path.stat().st_size <= MAX_METADATA_BYTES:
        raise PackageError("package_source_unavailable")
    return path.read_bytes()


def context(destination, root=ROOT):
    if destination.exists() or destination.is_symlink():
        raise PackageError("package_destination_exists")
    names = run(["git", "-C", str(root), "ls-files", "-z"]).decode().split("\0")
    names = sorted(name for name in names if name and allowed_source(name))
    if not RUNTIME_FILES.issubset(names) or "backend/manage.py" not in names:
        raise PackageError("package_source_untracked")
    source = {name: read_source(root, name) for name in names}
    lock = read_source(root, "docker/private-api.requirements.lock")
    dockerfile = read_source(root, "docker/private-api.Dockerfile")
    dependencies = read_source(root, "docker/private-dependencies.Dockerfile")
    head = run(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    dirty = bool(run(["git", "-C", str(root), "status", "--porcelain"]).strip())
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in source.items()}
    metadata = {
        "schema": "private_api_source_v1",
        "git_commit": head,
        "working_tree_changes": dirty,
        "source_sha256": hashes,
        "requirements_sha256": hashlib.sha256(lock).hexdigest(),
        "dependency_dockerfile_sha256": hashlib.sha256(dependencies).hexdigest(),
        "dockerfile_sha256": hashlib.sha256(dockerfile).hexdigest(),
    }
    with tempfile.TemporaryDirectory(prefix="declarai-api-context-", dir=destination.parent) as temp:
        stage = Path(temp) / "context"
        stage.mkdir()
        for name, value in source.items():
            target = stage / "app" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        (stage / "app/source-manifest.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
        (stage / "requirements.lock").write_bytes(lock)
        (stage / "Dockerfile").write_bytes(dockerfile)
        (stage / "dependencies.Dockerfile").write_bytes(dependencies)
        # No caller-selected paths, data files, caches, .env, database or tests.
        stage.rename(destination)
    return metadata


def inspect_image(image):
    try:
        values = json.loads(run(["docker", "image", "inspect", image]))
        if len(values) != 1:
            raise ValueError
        info = values[0]
        if not DIGEST.fullmatch(info["Id"]) or info["Os"] != "linux":
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise PackageError("package_image_invalid") from None
    return info


def native_manifest(image_id):
    output = run(
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
            "--entrypoint",
            "python",
            image_id,
            "/app/scripts/private_runtime_manifest.py",
            "verify",
        ]
    )
    try:
        if len(output) > MAX_METADATA_BYTES:
            raise ValueError
        value = json.loads(output)
        if value["schema"] != "private_native_runtime_v1" or value["system"] != "Linux":
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise PackageError("package_runtime_invalid") from None
    return value


def export(image, destination):
    if destination.exists() or destination.is_symlink():
        raise PackageError("package_destination_exists")
    info = inspect_image(image)
    if info["Config"]["User"] != "10001:10001" or info["Config"]["Entrypoint"] != [
        "python",
        "/app/scripts/private_service.py",
    ]:
        raise PackageError("package_image_profile_invalid")
    inventory = native_manifest(info["Id"])
    with tempfile.TemporaryDirectory(prefix="declarai-api-export-", dir=destination.parent) as temp:
        stage = Path(temp) / "package"
        stage.mkdir()
        archive = stage / "image.tar"
        raw = Path(temp) / "docker-save.tar"
        run(["docker", "image", "save", "--output", str(raw), info["Id"]], timeout=600)
        normalize_save(raw, archive)
        if not 0 < archive.stat().st_size <= MAX_IMAGE_BYTES:
            raise PackageError("package_image_size")
        manifest = {
            "schema": "private_api_package_v1",
            "image_id": info["Id"],
            "os": info["Os"],
            "architecture": info["Architecture"],
            "variant": info.get("Variant", ""),
            "archive": {"file": "image.tar", "bytes": archive.stat().st_size, "sha256": sha(archive)},
            "runtime": inventory,
            "scope": "native_api_worker_dispatcher_image_only",
            "release_qualified": False,
            "expert_isolation_qualified": False,
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        expected = sha(stage / "manifest.json")
        verify_package(stage, expected)
        stage.rename(destination)
    return {"image_id": info["Id"], "manifest_sha256": expected, "scope": manifest["scope"]}


def normalize_save(raw, destination):
    """Reduce our trusted daemon's save to one tag-free legacy image graph.

    Drop OCI indexes/annotations that could otherwise select other images or
    tags independently of manifest.json. This never accepts a user archive.
    """
    if not 0 < raw.stat().st_size <= MAX_IMAGE_BYTES:
        raise PackageError("package_image_size")
    with tarfile.open(raw, "r:") as source, tarfile.open(destination, "w", format=tarfile.USTAR_FORMAT) as output:
        member = source.getmember("manifest.json")
        if not member.isfile() or not 0 < member.size <= MAX_METADATA_BYTES:
            raise PackageError("package_archive_manifest_invalid")
        records = json.load(source.extractfile(member))
        if len(records) != 1 or records[0].get("RepoTags") not in (None, []):
            raise PackageError("package_archive_tags_rejected")
        names = ["manifest.json", records[0]["Config"], *records[0]["Layers"]]
        if len(names) > 502 or len(names) != len(set(names)):
            raise PackageError("package_archive_layers_invalid")
        for name in names:
            item = source.getmember(name)
            if not item.isfile() or item.size > MAX_IMAGE_BYTES:
                raise PackageError("package_archive_layout_invalid")
            header = tarfile.TarInfo(name)
            header.size, header.mode = item.size, 0o644
            output.addfile(header, source.extractfile(item))


def verify_archive(path, image_id):
    try:
        # Bound raw headers before a generic TAR reader could allocate a PAX,
        # long-name or sparse extension payload. Docker save uses short names.
        with path.open("rb") as archive:
            entries = {}
            total = path.stat().st_size
            while archive.tell() < total:
                header = archive.read(512)
                if len(header) != 512:
                    raise PackageError("package_archive_truncated")
                if header == bytes(512):
                    if any(archive.read(1024 * 1024)):
                        raise PackageError("package_archive_trailing_data")
                    while block := archive.read(1024 * 1024):
                        if any(block):
                            raise PackageError("package_archive_trailing_data")
                    break

                def octal(field):
                    value = field.rstrip(b"\0 ").lstrip(b" ")
                    if not value or any(c not in b"01234567" for c in value):
                        raise PackageError("package_archive_header_invalid")
                    return int(value, 8)

                checksum = octal(header[148:156])
                if checksum != sum(header[:148]) + 8 * 32 + sum(header[156:]):
                    raise PackageError("package_archive_header_invalid")
                kind = header[156:157]
                if kind not in (b"\0", b"0", b"5"):
                    raise PackageError("package_archive_layout_invalid")
                name = header[:100].split(b"\0", 1)[0].decode("utf-8")
                prefix = header[345:500].split(b"\0", 1)[0].decode("utf-8")
                if prefix:
                    name = prefix + "/" + name
                if kind == b"5":
                    name = name.removesuffix("/")
                pure = PurePosixPath(name)
                if not name or pure.is_absolute() or pure.as_posix() != name or ".." in pure.parts or name in entries:
                    raise PackageError("package_archive_layout_invalid")
                size = octal(header[124:136])
                if len(entries) >= 10_000 or size > MAX_IMAGE_BYTES or kind == b"5" and size:
                    raise PackageError("package_archive_budget")
                offset = archive.tell()
                next_offset = offset + ((size + 511) // 512) * 512
                if next_offset > total:
                    raise PackageError("package_archive_truncated")
                entries[name] = (offset, size, kind)
                archive.seek(next_offset)

            def payload(name):
                offset, size, kind = entries[name]
                if kind == b"5" or not 0 < size <= MAX_METADATA_BYTES:
                    raise PackageError("package_archive_metadata_invalid")
                archive.seek(offset)
                return archive.read(size)

            records = json.loads(payload("manifest.json"))
            if len(records) != 1 or records[0].get("RepoTags") not in (None, []):
                raise PackageError("package_archive_tags_rejected")
            config = payload(records[0]["Config"])
            if "sha256:" + hashlib.sha256(config).hexdigest() != image_id:
                raise PackageError("package_archive_image_mismatch")
            layers = records[0]["Layers"]
            if not isinstance(layers, list) or not layers or len(layers) > 500:
                raise PackageError("package_archive_layers_invalid")
            for layer in layers:
                if entries[layer][2] == b"5":
                    raise PackageError("package_archive_layers_invalid")
            if set(entries) != {"manifest.json", records[0]["Config"], *layers}:
                raise PackageError("package_archive_graph_invalid")
    except PackageError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError, RecursionError):
        raise PackageError("package_archive_invalid") from None


def verify_package(directory, expected):
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise PackageError("package_trusted_digest_required")
    if directory.is_symlink() or not directory.is_dir():
        raise PackageError("package_directory_invalid")
    children = list(directory.iterdir())
    if {p.name for p in children} != {"image.tar", "manifest.json"} or any(
        p.is_symlink() or not p.is_file() for p in children
    ):
        raise PackageError("package_directory_layout_invalid")
    manifest = directory / "manifest.json"
    if not 0 < manifest.stat().st_size <= MAX_METADATA_BYTES or sha(manifest) != expected:
        raise PackageError("package_manifest_digest_mismatch")
    try:
        value = json.loads(manifest.read_text())
        image = directory / "image.tar"
        if set(value) != {
            "schema",
            "image_id",
            "os",
            "architecture",
            "variant",
            "archive",
            "runtime",
            "scope",
            "release_qualified",
            "expert_isolation_qualified",
        }:
            raise ValueError
        if value["schema"] != "private_api_package_v1" or not DIGEST.fullmatch(value["image_id"]):
            raise ValueError
        if value["os"] != "linux" or value["architecture"] not in ("amd64", "arm64"):
            raise ValueError
        if (
            not isinstance(value["variant"], str)
            or value["scope"] != "native_api_worker_dispatcher_image_only"
            or value["release_qualified"] is not False
            or value["expert_isolation_qualified"] is not False
        ):
            raise ValueError
        inventory = value["runtime"]
        if set(inventory) != {"schema", "python", "implementation", "system", "machine", "packages", "source_sha256"}:
            raise ValueError
        if (
            inventory["schema"] != "private_native_runtime_v1"
            or inventory["system"] != "Linux"
            or inventory["machine"] != {"arm64": "aarch64", "amd64": "x86_64"}[value["architecture"]]
        ):
            raise ValueError
        if not isinstance(inventory["python"], str) or inventory["implementation"] != "CPython":
            raise ValueError
        packages, sources = inventory["packages"], inventory["source_sha256"]
        if (
            not isinstance(packages, list)
            or not 0 < len(packages) <= 2000
            or not isinstance(sources, dict)
            or not 0 < len(sources) <= 2000
        ):
            raise ValueError
        if any(
            set(p) != {"name", "version"}
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", p["name"])
            or not re.fullmatch(r"[A-Za-z0-9_.+!\-]+", p["version"])
            for p in packages
        ):
            raise ValueError
        if any(
            (name != "source-manifest.json" and not allowed_source(name)) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for name, digest in sources.items()
        ):
            raise ValueError
        record = value["archive"]
        if (
            record["file"] != "image.tar"
            or type(record["bytes"]) is not int
            or not 0 < record["bytes"] <= MAX_IMAGE_BYTES
        ):
            raise ValueError
        if image.stat().st_size != record["bytes"] or sha(image) != record["sha256"]:
            raise PackageError("package_archive_digest_mismatch")
    except PackageError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise PackageError("package_manifest_invalid") from None
    verify_archive(image, value["image_id"])
    return value


def load(directory, expected):
    # Consume a private snapshot, not a path an external writer can swap between
    # verification and the consequential Docker import. Never extract a layer.
    if (
        directory.is_symlink()
        or not directory.is_dir()
        or {p.name for p in directory.iterdir()} != {"image.tar", "manifest.json"}
    ):
        raise PackageError("package_directory_layout_invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise PackageError("package_trusted_digest_required")
    with tempfile.TemporaryDirectory(prefix="declarai-api-import-") as temp:
        snapshot = Path(temp)
        for name, limit in (("manifest.json", MAX_METADATA_BYTES), ("image.tar", MAX_IMAGE_BYTES)):
            descriptor = os.open(directory / name, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as source, (snapshot / name).open("xb") as target:
                import stat

                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                    raise PackageError("package_directory_layout_invalid")
                copied = 0
                while block := source.read(1024 * 1024):
                    copied += len(block)
                    if copied > limit:
                        raise PackageError("package_archive_budget")
                    target.write(block)
        value = verify_package(snapshot, expected)
        platform = run(["docker", "info", "--format", "{{.OSType}} {{.Architecture}}"]).decode().strip().split()
        machine = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}
        if len(platform) != 2 or platform[0] != "linux" or machine.get(platform[1]) != value["architecture"]:
            raise PackageError("package_native_platform_required")
        # Numeric digest-only import cannot overwrite an unrelated image tag.
        run(["docker", "image", "load", "--input", str(snapshot / "image.tar")], timeout=600)
    info = inspect_image(value["image_id"])
    if any(info[k] != value[k.lower()] for k in ("Os", "Architecture")) or info.get("Variant", "") != value["variant"]:
        raise PackageError("package_loaded_platform_mismatch")
    if native_manifest(info["Id"]) != value["runtime"]:
        raise PackageError("package_loaded_runtime_mismatch")
    return {"image_id": info["Id"], "offline_image_verified": True, "release_qualified": False}


def build(base_image, tag):
    if not DIGEST.fullmatch(base_image):
        raise PackageError("package_pinned_base_required")
    if not re.fullmatch(r"declarai-private-api:[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", tag):
        raise PackageError("package_build_tag_required")
    if run(["docker", "image", "ls", "--quiet", tag]).strip():
        raise PackageError("package_build_tag_exists")
    dependencies = inspect_image(base_image)
    reference = "declarai-private-deps:" + uuid.uuid4().hex
    run(["docker", "image", "tag", dependencies["Id"], reference])
    try:
        with tempfile.TemporaryDirectory(prefix="declarai-api-build-") as temp:
            destination = Path(temp) / "context"
            context(destination)
            source = destination / "app/source-manifest.json"
            metadata = json.loads(source.read_text())
            metadata["dependency_image_id"] = dependencies["Id"]
            source.write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
            run(
                ["docker", "build", "--build-arg", "DEPENDENCY_IMAGE=" + reference, "--tag", tag, str(destination)],
                timeout=900,
            )
    finally:
        run(["docker", "image", "rm", reference])
    info = inspect_image(tag)
    return {"image_id": info["Id"], "base_image": base_image, "runtime_verified": native_manifest(info["Id"])["schema"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    image = commands.add_parser("build")
    image.add_argument("--base-image", required=True)
    image.add_argument("--tag", required=True)
    source_context = commands.add_parser("context")
    source_context.add_argument("destination", type=Path)
    output = commands.add_parser("export")
    output.add_argument("--image", required=True)
    output.add_argument("destination", type=Path)
    for name in ("verify", "load"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        command.add_argument("--expected-manifest-sha256", required=True)
    args = parser.parse_args()
    if args.action == "build":
        print(json.dumps(build(args.base_image, args.tag)))
    elif args.action == "context":
        result = context(args.destination.absolute())
        print(json.dumps({"source_files": len(result["source_sha256"]), "source_commit": result["git_commit"]}))
    elif args.action == "export":
        print(json.dumps(export(args.image, args.destination.absolute())))
    elif args.action == "load":
        print(json.dumps(load(args.directory.absolute(), args.expected_manifest_sha256)))
    else:
        value = verify_package(args.directory.absolute(), args.expected_manifest_sha256)
        print(json.dumps({"image_id": value["image_id"], "archive_verified": True, "release_qualified": False}))


if __name__ == "__main__":
    try:
        main()
    except (PackageError, OSError, UnicodeError) as error:
        print(str(error) if isinstance(error, PackageError) else "package_io_failed", file=sys.stderr)
        sys.exit(1)
