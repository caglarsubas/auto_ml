#!/usr/bin/env python3
"""Qualify fresh initialization on owned Linux volumes with synthetic secrets."""

import argparse
import json
import uuid
from pathlib import Path

import private_installation_check as checker
from qualify_private_installation_check import command

ROOT = Path(__file__).resolve().parents[1]

PREPARE = r"""
import json,os,sys
from pathlib import Path
v=json.load(sys.stdin);plan=Path('/plan');parent=Path('/srv/declarai')
for name,data in v['files'].items():
    p=plan/name;p.write_text(data);p.chmod(0o400);os.chown(p,10001,10001)
plan.chmod(0o700);os.chown(plan,10001,10001)
parent.chmod(0o755)
source=parent/'delivery';source.mkdir(mode=0o700);os.chown(source,10001,10001)
files={'app/django-key':'Synthetic-Key-Only-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789',
'app/app-password':'synthetic-not-a-real-password','app/job-broker-url':'rediss://:synthetic@job-broker:6379/1',
'app/postgres-ca.crt':'synthetic opaque certificate','app/job-ca.crt':'synthetic opaque certificate',
'app/cache-url':'rediss://:synthetic@cache:6379/0','app/cache-ca.crt':'synthetic opaque certificate',
'tls/tls.crt':'synthetic opaque certificate','tls/tls.key':'synthetic opaque key'}
for group in ['app','tls']:
    p=source/group;p.mkdir(mode=0o700);os.chown(p,10001,10001)
for name,data in files.items():
    p=source/name;p.write_text(data);p.chmod(0o400);os.chown(p,10001,10001)
p=source/'app/app-password'
if v['fault']=='bad_value':
    p=source/'app/job-broker-url';p.chmod(0o600);p.write_text('redis://:synthetic@external:6379/1');p.chmod(0o400)
elif v['fault']=='hardlink':os.link(p,parent/'outside')
elif v['fault']=='link':
    p.unlink();p.symlink_to(source/'app/django-key')
elif v['fault']=='unsafe_parent':parent.chmod(0o777)
"""

RUN = r"""
import sys,json
from pathlib import Path
sys.path.insert(0,'/harness')
import private_installation_init as m
fault,expected=sys.argv[1:]
if fault=='write_failure':
    original=m.write_file;count=0
    def fail(*args):
        global count
        count+=1
        if count==3:raise m.checker.planner.PlanError('synthetic_write_failure')
        return original(*args)
    m.write_file=fail
elif fault=='competing_empty':
    original=m.rename_noreplace
    def publish(parent,source,target):
        m.os.mkdir(target,mode=0o700,dir_fd=parent)
        original(parent,source,target)
    m.rename_noreplace=publish
try:print(json.dumps(m.initialize(Path('/plan'),expected,Path('/srv/declarai/delivery'))))
except (m.checker.planner.PlanError,OSError) as e:
    print(str(e) if isinstance(e,m.checker.planner.PlanError) else 'installation_init_io_failed',file=sys.stderr);sys.exit(1)
"""

VERIFY = r"""
import os,sys
from pathlib import Path
parent=Path('/srv/declarai');target=parent/'qualification';fault=sys.argv[1]
assert not list(parent.glob('.declarai-init-*'))
if fault=='competing_empty':assert target.is_dir() and not list(target.iterdir())
elif fault!='clean':assert not target.exists()
else:
    for p in [target,target/'secrets']:
        s=p.stat();assert (s.st_uid,s.st_gid,s.st_mode&0o777)==(0,10001,0o750)
    for relative in ['secrets/app','secrets/tls','artifacts']:
        s=(target/relative).stat();assert (s.st_uid,s.st_gid,s.st_mode&0o777)==(10001,10001,0o700)
    assert not list((target/'artifacts').iterdir())
    for group in ['app','tls']:
        for p in (target/'secrets'/group).iterdir():
            s=p.stat();assert (s.st_uid,s.st_gid,s.st_mode&0o777,s.st_nlink)==(10001,10001,0o400,1)
            assert p.read_bytes()==(parent/'delivery'/group/p.name).read_bytes()
    s=(target/'initialization.json').stat();assert (s.st_uid,s.st_mode&0o777)==(0,0o600)
print('owned_fixture_verified')
"""


def qualify(plan, expected, image, reports):
    value = checker.verify(plan, expected)
    if (
        image != value["images"]["api"]
        or value["request"]["root"] != "/srv/declarai/qualification"
        or value["request"]["installation_id"] != "qualification"
    ):
        raise checker.planner.PlanError("installation_init_fixture_scope_required")
    reports = reports.resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        raise checker.planner.PlanError("installation_reports_path_invalid")
    files = {name: data.decode() for name, data in checker.read_plan(plan).items()}
    prefix = "declarai-init-" + uuid.uuid4().hex
    volumes, containers, cases = [], [], []
    try:
        for fault, reason in {
            "clean": None,
            "bad_value": "installation_init_secret_value_invalid",
            "hardlink": "installation_init_delivery_file_invalid",
            "link": "installation_init_io_failed",
            "unsafe_parent": "installation_init_parent_unsafe",
            "write_failure": "synthetic_write_failure",
            "competing_empty": "installation_init_destination_exists",
        }.items():
            installation, metadata = (
                prefix + "-" + fault,
                prefix + "-" + fault + "-plan",
            )
            for name in (installation, metadata):
                volumes.append(name)
                if command(["docker", "volume", "create", name]).returncode:
                    raise checker.planner.PlanError("installation_init_fixture_unavailable")
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
            privileged = [
                "--user",
                "0:0",
                "--cap-add",
                "CHOWN",
                "--cap-add",
                "DAC_OVERRIDE",
                "--cap-add",
                "FOWNER",
            ]
            mounts = [
                "-v",
                installation + ":/srv/declarai",
                "-v",
                metadata + ":/plan",
                "-v",
                str(ROOT / "scripts") + ":/harness:ro",
            ]

            def run(
                role,
                script,
                *args,
                data=None,
                identity=None,
                fault=fault,
                common=common,
                privileged=privileged,
                mounts=mounts,
            ):
                name = prefix + "-" + fault + "-" + role
                containers.append(name)
                return command(
                    [
                        *common,
                        "--name",
                        name,
                        *(privileged if identity is None else identity),
                        *mounts,
                        *(["-i"] if data is not None else []),
                        image,
                        "-c",
                        script,
                        *args,
                    ],
                    data=data,
                )

            if run(
                "prepare",
                PREPARE,
                data=checker.planner.encoded({"files": files, "fault": fault}),
            ).returncode:
                raise checker.planner.PlanError("installation_init_fixture_prepare_failed")
            result = run("initialize", RUN, fault, expected)
            if reason:
                if not result.returncode or result.stdout or result.stderr.decode().strip() != reason:
                    raise checker.planner.PlanError("installation_init_fixture_fault_not_blocked")
                cases.append({"case": fault, "blocked": reason})
            else:
                if result.returncode:
                    raise checker.planner.PlanError("installation_init_fixture_failed")
                receipt = checker.planner.decode(result.stdout)
                if receipt["secret_files_delivered"] != 9 or receipt["services_adopted"] is not False:
                    raise checker.planner.PlanError("installation_init_fixture_receipt_invalid")
                cases.append({"case": fault, "receipt": receipt})
                again = run("retry", RUN, fault, expected)
                if (
                    not again.returncode
                    or again.stdout
                    or again.stderr.decode().strip() != "installation_init_destination_exists"
                ):
                    raise checker.planner.PlanError("installation_init_fixture_retry_not_blocked")
                checked = run(
                    "check",
                    "import sys;sys.path.insert(0,'/harness');import private_installation_check as m;from pathlib import Path;import json;print(json.dumps(m.check_paths(Path('/plan'),sys.argv[1])))",
                    expected,
                    identity=["--user", "10001:10001"],
                )
                if checked.returncode or checker.planner.decode(checked.stdout)["secret_metadata_files"] != 7:
                    raise checker.planner.PlanError("installation_init_fixture_path_check_failed")
            verified = run("verify", VERIFY, fault)
            if verified.returncode or verified.stdout.decode().strip() != "owned_fixture_verified":
                raise checker.planner.PlanError("installation_init_fixture_state_failed")
    finally:
        failed = False
        for name in containers:
            try:
                command(["docker", "container", "rm", "--force", name])
            except checker.planner.PlanError:
                failed = True
        for name in volumes:
            try:
                failed = bool(command(["docker", "volume", "rm", name]).returncode) or failed
            except checker.planner.PlanError:
                failed = True
        if failed:
            raise checker.planner.PlanError("installation_init_fixture_cleanup_failed")
    result = {
        "schema": "private_installation_init_qualification_v1",
        "image_id": image,
        "plan_manifest_sha256": expected,
        "cases": cases,
        "owned_volumes_removed": len(volumes),
        "native_no_replace_publication": "passed",
        "existing_destination_retry": "blocked",
        "operator_installation_modified": False,
        "secret_values_emitted": False,
        "services_adopted": False,
        "installation_qualified": False,
        "expert_isolation_qualified": False,
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "installation-init.json").write_bytes(checker.planner.encoded(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--reports", type=Path, default=ROOT / "test-reports/postgresql")
    args = parser.parse_args()
    print(json.dumps(qualify(args.plan, args.expected_plan_sha256, args.image, args.reports)))


if __name__ == "__main__":
    main()
