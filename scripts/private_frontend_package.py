#!/usr/bin/env python3
"""Compile a recorded source snapshot with explicitly trusted Node/npm dependencies.

Install the locked dependencies separately with Node 24 and npm ci. This tool
never downloads dependencies; it builds in a fresh allowlisted source snapshot.
The dependency directory and compiler are trusted operator inputs, not a code
sandbox or an authenticated software supply chain.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = {".html", ".js", ".css", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".woff", ".woff2", ".ttf"}
LICENSES = {"assets/fonts/" + name for name in ("ibm-plex-mono-OFL.txt", "instrument-sans-OFL.txt",
                                              "instrument-serif-OFL.txt", "material-icons-LICENSE.txt")}
CONFIG = {"angular.json", "package.json", "package-lock.json", "tsconfig.json", "tsconfig.app.json", "server.ts"}
LIMIT = 64 * 1024 * 1024


class FrontendError(RuntimeError):
    pass


def safe_name(name):
    return (isinstance(name, str) and len(name) <= 240
            and all(re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", part)
                    for part in name.split("/")))


def source_names(root):
    raw = subprocess.run(["git", "ls-files", "-z", "frontend"], cwd=root, capture_output=True, check=True).stdout
    result = []
    for name in raw.decode().split("\0"):
        if not name:
            continue
        relative = name.removeprefix("frontend/")
        if not safe_name(relative):
            continue
        path = Path(relative)
        if relative in CONFIG or (
            relative.startswith("src/") and not relative.endswith(".spec.ts")
            and (path.suffix in {".ts", ".html", ".css", ".scss"}
                 or relative.startswith("src/assets/") and (path.suffix in STATIC or relative.removeprefix('src/') in LICENSES))
        ) or relative.startswith("public/") and path.suffix in STATIC:
            result.append(relative)
    required = CONFIG | {"src/main.ts", "src/index.html", "src/environments/environment.private.ts"}
    if not required <= set(result):
        raise FrontendError("private_frontend_sources_missing")
    return sorted(result)


def snapshot(destination, root=ROOT):
    files = {}
    for name in source_names(root):
        path = root / "frontend" / name
        if any(p.is_symlink() for p in [path, *path.parents]) or not path.is_file() or path.stat().st_size > LIMIT:
            raise FrontendError("private_frontend_source_invalid")
        files[name] = path.read_bytes()
    if sum(map(len, files.values())) > LIMIT:
        raise FrontendError("private_frontend_source_budget_exceeded")
    destination.mkdir(mode=0o700)
    # Angular analytics never runs in the isolated build snapshot.
    config = json.loads(files["angular.json"])
    config["cli"]["analytics"] = False
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (destination / "angular.json").write_text(json.dumps(config))
    (destination / "public").mkdir(exist_ok=True)
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


def asset_bytes(browser):
    if browser.is_symlink() or not browser.is_dir():
        raise FrontendError("private_frontend_assets_invalid")
    files = {}
    for path in sorted(browser.rglob("*")):
        if path.is_symlink():
            raise FrontendError("private_frontend_asset_link_rejected")
        if path.is_dir():
            continue
        name = path.relative_to(browser).as_posix()
        if (not safe_name(name) or (path.suffix not in STATIC and name not in LICENSES | {'3rdpartylicenses.txt'}) or not path.is_file()
                or name.split('/')[0] in {"api", "media", "admin"}):
            raise FrontendError("private_frontend_asset_type_rejected")
        if path.stat().st_size > LIMIT:
            raise FrontendError("private_frontend_asset_budget_exceeded")
        files[name] = path.read_bytes()
        if len(files) > 512 or sum(map(len, files.values())) > LIMIT:
            raise FrontendError("private_frontend_asset_budget_exceeded")
    if "index.html" not in files or not any(name.endswith(".js") for name in files):
        raise FrontendError("private_frontend_entrypoint_missing")
    return files


def inventory(files):
    return {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)} for name, data in files.items()}


def verified_assets(package):
    package = Path(package)
    manifest = package / "manifest.json"
    if package.is_symlink() or manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 2 * 1024 * 1024:
        raise FrontendError("private_frontend_manifest_invalid")
    record = json.loads(manifest.read_text())
    if not isinstance(record, dict) or record.get("schema") != "private_frontend_v1" or record.get("api_root") != "/api/":
        raise FrontendError("private_frontend_manifest_invalid")
    if {p.name for p in package.iterdir()} != {"manifest.json", "browser"}:
        raise FrontendError("private_frontend_package_members_invalid")
    files = asset_bytes(package / "browser")
    if inventory(files) != record.get("assets"):
        raise FrontendError("private_frontend_asset_integrity_failed")
    return record, files


def build(destination, dependencies, root=ROOT):
    destination = Path(destination)
    dependencies = Path(dependencies).resolve()
    if destination.exists() or destination.is_symlink():
        raise FrontendError("private_frontend_destination_exists")
    node = subprocess.run(["node", "--version"], capture_output=True, check=True).stdout.decode().strip()
    if not re.fullmatch(r"v24\.\d+\.\d+", node):
        raise FrontendError("private_frontend_node_24_required")
    lock = json.loads((root / "frontend/package-lock.json").read_text())
    versions = {}
    for name in ("@angular/cli", "@angular/compiler-cli", "@angular/core", "typescript"):
        version = json.loads((dependencies / name / "package.json").read_text())["version"]
        if version != lock["packages"]["node_modules/" + name]["version"]:
            raise FrontendError("private_frontend_compiler_lock_mismatch")
        versions[name] = version
    with tempfile.TemporaryDirectory(prefix="declarai-frontend-build-") as temporary:
        stage = Path(temporary) / "source"
        hashes = snapshot(stage, root)
        (stage / "node_modules").symlink_to(dependencies, target_is_directory=True)
        # Fixed AOT production options plus the same-origin private replacement.
        # No arbitrary build command, source directory or runtime configuration.
        env = {**os.environ, "NG_CLI_ANALYTICS": "false", "CI": "true"}
        result = subprocess.run(["node", str(dependencies / "@angular/cli/bin/ng.js"), "build",
                                 "--configuration=production,private"], cwd=stage, env=env,
                                capture_output=True, timeout=180, check=False)
        if result.returncode:
            raise FrontendError("private_frontend_compile_failed")
        browser = stage / "dist/frontend/browser"
        # Angular writes dependency notices beside browser assets. Carry them
        # with the fonts' original notices into the immutable published image.
        shutil.copyfile(stage / 'dist/frontend/3rdpartylicenses.txt', browser / '3rdpartylicenses.txt')
        files = asset_bytes(browser)
        if not LICENSES <= set(files):
            raise FrontendError('private_frontend_font_notices_missing')
        record = {"schema": "private_frontend_v1", "api_root": "/api/", "node": node,
                  "compiler_versions": versions, "source_sha256": hashes,
                  "build_configuration": "production,private", "analytics": False,
                  "assets": inventory(files), "dependency_trust": "operator_acquired_locked_dependencies"}
        destination.mkdir(mode=0o700)
        shutil.copytree(stage / "dist/frontend/browser", destination / "browser")
        (destination / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    args = parser.parse_args()
    try:
        record = build(args.destination, args.dependencies)
    except (FrontendError, OSError, ValueError, subprocess.SubprocessError, KeyError):
        parser.exit(1, "Private frontend preparation failed.\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
