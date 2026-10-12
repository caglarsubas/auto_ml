#!/usr/bin/env python3
"""Own disposable Linux volumes to qualify plan/filesystem checks, never adoption."""

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import private_installation_check as checker

ROOT = Path(__file__).resolve().parents[1]

PREPARE = r"""
import json,os,sys
from pathlib import Path
value=json.load(sys.stdin)
plan=Path('/plan');root=Path('/srv/declarai/qualification')
for name,data in value['files'].items():
    path=plan/name;path.write_text(data);path.chmod(0o400);os.chown(path,10001,10001)
plan.chmod(0o700);os.chown(plan,10001,10001)
for relative in ['secrets/app','secrets/tls','artifacts']:
    directory=root/relative;directory.mkdir(parents=True,exist_ok=True)
    directory.chmod(0o700);os.chown(directory,10001,10001)
for group,names in {'app':['django-key','app-password','job-broker-url','postgres-ca.crt','job-ca.crt','cache-url','cache-ca.crt'],'tls':['tls.crt','tls.key']}.items():
    for name in names:
        file=root/'secrets'/group/name;file.write_text('Synthetic metadata only; not installation secrets')
        file.chmod(0o400);os.chown(file,10001,10001)
os.mkfifo(root/'artifacts'/'uninspected-artifact-fifo')
file=root/'secrets/app/app-password'
if value['fault']=='file_mode':file.chmod(0o644)
elif value['fault']=='hardlink':os.link(file,root/'artifacts'/'hardlink')
elif value['fault']=='file_link':
    other=root/'artifacts'/'original';file.rename(other);file.symlink_to(other)
root.chmod(0o777 if value['fault']=='ancestor_mode' else 0o700);os.chown(root,10001,10001)
"""


def command(argv, data=None):
    try:
        return subprocess.run(
            argv, input=data, capture_output=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise checker.planner.PlanError(
            "installation_path_fixture_unavailable"
        ) from None


def qualify(plan, expected, image, reports):
    value = checker.verify(plan, expected)
    images = value["images"]
    if (
        image != images["api"]
        or value["request"]["root"] != "/srv/declarai/qualification"
        or value["request"]["installation_id"] != "qualification"
    ):
        raise checker.planner.PlanError("installation_path_fixture_scope_required")
    reports = reports.resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        raise checker.planner.PlanError("installation_reports_path_invalid")
    # The checker re-verifies these captured files against the trusted digest in
    # every native fixture; a replaced caller path cannot authorize different bytes.
    files = {name: data.decode() for name, data in checker.read_plan(plan).items()}
    receipts, volumes, containers = [], [], []
    prefix = "declarai-plan-paths-" + uuid.uuid4().hex
    try:
        for fault in ("clean", "file_mode", "hardlink", "file_link", "ancestor_mode"):
            installation, metadata = (
                prefix + "-" + fault + "-installation",
                prefix + "-" + fault + "-plan",
            )
            for name in (installation, metadata):
                volumes.append(name)
                if command(["docker", "volume", "create", name]).returncode:
                    raise checker.planner.PlanError(
                        "installation_path_fixture_unavailable"
                    )
            common = [
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
                "--cpus",
                "1",
                "--memory",
                "256m",
                "--pids-limit",
                "64",
                "--entrypoint",
                "python",
            ]
            prepare_name = prefix + "-" + fault + "-prepare"
            containers.append(prepare_name)
            # Only this synthetic-volume initializer has the three bounded
            # filesystem capabilities. The checker receives no capabilities.
            prepare = command(
                [
                    *common,
                    "--name",
                    prepare_name,
                    "--user",
                    "0:0",
                    "--cap-add",
                    "CHOWN",
                    "--cap-add",
                    "DAC_OVERRIDE",
                    "--cap-add",
                    "FOWNER",
                    "-i",
                    "-v",
                    installation + ":/srv/declarai/qualification",
                    "-v",
                    metadata + ":/plan",
                    image,
                    "-c",
                    PREPARE,
                ],
                data=checker.planner.encoded({"fault": fault, "files": files}),
            )
            if prepare.returncode:
                raise checker.planner.PlanError(
                    "installation_path_fixture_prepare_failed"
                )
            check_name = prefix + "-" + fault + "-check"
            containers.append(check_name)
            checked = command(
                [
                    *common,
                    "--name",
                    check_name,
                    "--user",
                    "10001:10001",
                    "-v",
                    installation + ":/srv/declarai/qualification:ro",
                    "-v",
                    metadata + ":/plan:ro",
                    "-v",
                    str(ROOT / "scripts") + ":/harness:ro",
                    image,
                    "/harness/private_installation_check.py",
                    "check-paths",
                    "/plan",
                    "--expected-plan-sha256",
                    expected,
                ]
            )
            if fault == "clean":
                if checked.returncode:
                    raise checker.planner.PlanError(
                        "installation_path_fixture_check_failed"
                    )
                result = checker.planner.decode(checked.stdout)
                if (
                    result["filesystem_prerequisites"] != "passed"
                    or result["secret_metadata_files"] != sum(map(len, value["prerequisites"]["secret_files"].values()))
                    or result["secret_contents_read"] is not False
                    or result["artifact_descendants_inspected"] is not False
                    or result["installation_qualified"] is not False
                ):
                    raise checker.planner.PlanError(
                        "installation_path_fixture_receipt_invalid"
                    )
                receipts.append({"case": fault, "receipt": result})
            else:
                reason = (
                    "installation_path_ancestor_unsafe"
                    if fault == "ancestor_mode"
                    else "installation_secret_metadata_invalid"
                )
                if (
                    not checked.returncode
                    or checked.stderr.decode().strip() != reason
                    or checked.stdout
                ):
                    raise checker.planner.PlanError(
                        "installation_path_fixture_fault_not_blocked"
                    )
                receipts.append({"case": fault, "blocked": reason})
    finally:
        cleanup_failed = False
        for name in containers:
            try:
                command(["docker", "container", "rm", "--force", name])
            except checker.planner.PlanError:
                cleanup_failed = True
        for name in volumes:
            try:
                cleanup_failed = (
                    bool(command(["docker", "volume", "rm", name]).returncode)
                    or cleanup_failed
                )
            except checker.planner.PlanError:
                cleanup_failed = True
        if cleanup_failed:
            raise checker.planner.PlanError("installation_path_fixture_cleanup_failed")
    result = {
        "schema": "private_installation_paths_qualification_v1",
        "image_id": image,
        "plan_manifest_sha256": expected,
        "cases": receipts,
        "owned_volumes_removed": len(volumes),
        "services_started": False,
        "operator_installation_modified": False,
        "secret_contents_read": False,
        "installation_qualified": False,
        "expert_isolation_qualified": False,
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "installation-paths.json").write_bytes(checker.planner.encoded(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reports", type=Path, default=ROOT / "test-reports/postgresql"
    )
    parser.add_argument("--image", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            qualify(args.plan, args.expected_plan_sha256, args.image, args.reports)
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (checker.planner.PlanError, OSError, ValueError, UnicodeError) as error:
        print(
            str(error)
            if isinstance(error, checker.planner.PlanError)
            else "installation_path_fixture_io_failed",
            file=sys.stderr,
        )
        sys.exit(1)
