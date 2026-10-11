#!/usr/bin/env python3
"""Inventory/verify an installed native runtime, before importing Django.

Hashes detect changes relative to a trusted image; they are not signatures.
No installation data, environment values or credentials enter the manifest.
"""

import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

SCHEMA = "private_native_runtime_v1"
GUNICORN_VERSION = "26.2.0"
LIMIT = 2_000_000


class ManifestError(Exception):
    pass


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def files(root):
    result = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(directory) / name
            if path.is_symlink():
                raise ManifestError("runtime_source_symlink")
        for name in names:
            path = Path(directory) / name
            if path == root / "runtime-manifest.json":
                continue
            if not path.is_file():
                raise ManifestError("runtime_source_not_regular")
            result[path.relative_to(root).as_posix()] = digest(path)
    return dict(sorted(result.items()))


def snapshot(root):
    packages = sorted(
        ({"name": dist.metadata["Name"], "version": dist.version} for dist in importlib.metadata.distributions()),
        key=lambda item: item["name"].lower(),
    )
    if importlib.metadata.version("gunicorn") != GUNICORN_VERSION:
        raise ManifestError("runtime_server_version")
    return {
        "schema": SCHEMA,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "machine": platform.machine(),
        "packages": packages,
        "source_sha256": files(root),
    }


def verify(root):
    manifest = root / "runtime-manifest.json"
    if manifest.is_symlink() or not manifest.is_file() or not 0 < manifest.stat().st_size <= LIMIT:
        raise ManifestError("runtime_manifest_unavailable")
    try:
        expected = json.loads(manifest.read_text())
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise ManifestError("runtime_manifest_invalid") from None
    actual = snapshot(root)
    if expected != actual:
        raise ManifestError("runtime_manifest_mismatch")
    return actual


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("create", "verify"):
        raise ManifestError("runtime_manifest_action_required")
    root = Path(__file__).resolve().parents[1]
    if sys.argv[1] == "create":
        value = snapshot(root)
        with (root / "runtime-manifest.json").open("x") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
    else:
        value = verify(root)
        print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ManifestError, OSError, importlib.metadata.PackageNotFoundError) as error:
        print(str(error) if isinstance(error, ManifestError) else "runtime_manifest_unavailable", file=sys.stderr)
        sys.exit(1)
