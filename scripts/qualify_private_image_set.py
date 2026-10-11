#!/usr/bin/env python3
"""Exercise owned image-set tamper rejection and idempotent offline import.

No existing image/tag is removed. CI separately empties only its own freshly
built image slots before this probe; an operator installation is never adopted.
"""

import argparse
import json
import subprocess
from pathlib import Path

import private_api_package as api
import private_image_set as image_set

ROOT = Path(__file__).resolve().parents[1]


def tags(image):
    result = subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False)
    if result.returncode:
        return []
    return sorted(json.loads(result.stdout)[0].get("RepoTags") or [])


def qualify(directory, expected, reports, *, empty_slots=False):
    value = image_set.consume(directory, expected)
    images = value["images"]
    before = {role: tags(image) for role, image in images.items()}
    if empty_slots:
        api.run(["docker", "info", "--format", "{{.OSType}}"])
        for image in images.values():
            result = subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False)
            if not result.returncode:
                raise RuntimeError("Owned image slot must be empty before qualification")
    original_run = api.run

    def no_docker(*args, **kwargs):
        raise RuntimeError("Invalid handoff reached Docker")

    archive = directory / "redis/image.tar"
    with archive.open("r+b") as stream:
        original = stream.read(1)
        stream.seek(0)
        stream.write(bytes([original[0] ^ 1]))
    try:
        api.run = no_docker
        try:
            image_set.consume(directory, expected, load=True)
        except api.PackageError as error:
            if str(error) != "package_archive_digest_mismatch":
                raise
        else:
            raise RuntimeError("Changed last component was not rejected")
        try:
            image_set.consume(directory, "0" * 64, load=True)
        except api.PackageError as error:
            if str(error) != "image_set_manifest_digest_mismatch":
                raise
        else:
            raise RuntimeError("Wrong manifest digest was not rejected")
    finally:
        api.run = original_run
        with archive.open("r+b") as stream:
            stream.write(original)
    first = image_set.consume(directory, expected, load=True)
    second = image_set.consume(directory, expected, load=True)
    if first != second or before != {role: tags(image) for role, image in images.items()}:
        raise RuntimeError("Offline import changed selected identities or existing tags")
    receipt = {
        "schema": "private_image_set_qualification_v1", "manifest_sha256": expected, "images": images,
        "all_components_verified_before_import": "passed", "changed_last_archive_before_docker": "blocked",
        "wrong_manifest_before_docker": "blocked", "native_runtime_after_load": "passed",
        "repeat_digest_only_import": "passed", "selected_image_tags": "unchanged",
        "owned_slots_empty_before_import": empty_slots, "services_started": False,
        "installation_qualified": False, "release_qualified": False,
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "image-set-qualification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--reports", required=True, type=Path)
    parser.add_argument("--require-empty-slots", action="store_true")
    args = parser.parse_args()
    reports = args.reports.resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        parser.error("Qualification reports must be in the ignored test-reports directory")
    print(json.dumps(qualify(args.directory.absolute(), args.expected_manifest_sha256, reports,
                             empty_slots=args.require_empty_slots)))


if __name__ == "__main__":
    main()
