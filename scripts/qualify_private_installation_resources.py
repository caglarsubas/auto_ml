#!/usr/bin/env python3
"""Own synthetic resources to qualify preparation; never adopt operator services."""

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

import private_installation_resources as resources

ROOT = Path(__file__).resolve().parents[1]

HOST_CASE = r"""
import json,os,shutil,sys,re
from pathlib import Path
v=json.load(sys.stdin);sys.path.insert(0,v['scripts'])
import private_installation_resources as m
import private_installation_init as init
parent=Path(v['parent']);assert re.fullmatch('/srv/declarai-p37-[0-9a-f]{32}',str(parent))
created=False;initialized=None
try:
    parent.mkdir(mode=0o700);created=True
    plan=parent/'plan';plan.mkdir(mode=0o700)
    for name,data in v['files'].items():(plan/name).write_text(data)
    source=parent/'delivery';source.mkdir(mode=0o700);os.chown(source,10001,10001)
    for group in ['app','tls']:
        p=source/group;p.mkdir(mode=0o700);os.chown(p,10001,10001)
    contents={'app/django-key':'Synthetic-Key-Only-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789',
    'app/app-password':'synthetic-not-a-real-password','app/job-broker-url':'rediss://:synthetic@job-broker:6379/1',
    'app/postgres-ca.crt':'synthetic opaque certificate','app/job-ca.crt':'synthetic opaque certificate',
'app/cache-url':'rediss://:synthetic@cache:6379/0','app/cache-ca.crt':'synthetic opaque certificate',
    'tls/tls.crt':'synthetic opaque certificate','tls/tls.key':'synthetic opaque key'}
    for name,data in contents.items():
        p=source/name;p.write_text(data);p.chmod(0o400);os.chown(p,10001,10001)
    initialized=init.initialize(plan,v['expected'],source)
    a=m.prepare(plan,v['expected']);b=m.prepare(plan,v['expected']);assert a==b
    print(json.dumps({'actual_linux_root_controller':'passed','receipt':a,'repeat_prepare':'passed'}))
finally:
    try:
        if initialized is not None:
            value=m.checker.verify(plan,v['expected']);binding=m.labels(value,v['expected'],initialized['initialization_id'])
            for kind,specs in [('network',value['prerequisites']['networks']),('volume',[value['prerequisites']['socket_volume']])]:
                for spec in specs:
                    if m.listing(kind,spec['name']):
                        assert m.inspect(kind,spec['name'])['Labels']==binding
                        m.command([kind,'rm',spec['name']])
    finally:
        if created:shutil.rmtree(parent)
"""


def fixture_plan(plan, expected, identifier):
    resources.checker.verify(plan, expected)
    files = resources.checker.read_plan(plan)
    request = resources.checker.planner.decode(files["request.json"])
    request.update(installation_id="q-" + identifier[:20], root="/srv/declarai-p37-" + identifier + "/installation")
    manifest = resources.checker.planner.decode(files["manifest.json"])
    outer = resources.checker.planner.decode(files["image-set.json"])
    images = {key: v["image_id"] for key, v in outer["components"].items()}
    files.update(
        {
            "request.json": resources.checker.planner.encoded(request),
            "compose.json": resources.checker.planner.encoded(resources.checker.planner.composition(request, images)),
            "prerequisites.json": resources.checker.planner.encoded(
                resources.checker.planner.prerequisites(request, images, legacy=manifest["schema"] == "private_installation_plan_v1")
            ),
        }
    )
    manifest.update(
        installation_id=request["installation_id"],
        files={name: hashlib.sha256(files[name]).hexdigest() for name in resources.checker.planner.FILES},
    )
    files["manifest.json"] = resources.checker.planner.encoded(manifest)
    return files, hashlib.sha256(files["manifest.json"]).hexdigest()


def owned_cleanup(value, expected, identifier, fixture_id, holders):
    for name in holders:
        resources.command(["container", "rm", "--force", name])
    binding = resources.labels(value, expected, identifier)
    fixture = {"org.declarai.qualification": fixture_id}
    for kind, specs in (
        ("network", value["prerequisites"]["networks"]),
        ("volume", [value["prerequisites"]["socket_volume"]]),
    ):
        for spec in specs:
            if not resources.listing(kind, spec["name"]):
                continue
            info = resources.inspect(kind, spec["name"])
            if info.get("Labels") not in (binding, fixture):
                raise resources.checker.planner.PlanError("installation_resources_fixture_cleanup_owner_invalid")
            resources.command([kind, "rm", spec["name"]])


def qualifier_helper(name, volume, image, code):
    # This trusted fixture mutation has only one owned socket mount and no
    # network. Never mount a host installation, source or Docker socket.
    resources.command(
        [
            "container",
            "create",
            "--name",
            name,
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--user",
            "0:0",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "DAC_OVERRIDE",
            "--cap-add",
            "FOWNER",
            "--security-opt",
            "no-new-privileges",
            "--cpus",
            "1",
            "--memory",
            "128m",
            "--pids-limit",
            "32",
            "--mount",
            "type=volume,src=" + volume + ",dst=/run/declarai,volume-nocopy",
            "--entrypoint",
            "python",
            image,
            "-c",
            code,
        ]
    )
    resources.command(["container", "start", "--attach", name])
    state = resources.inspect("container", name)["State"]
    if state["Running"] is not False or state["ExitCode"] != 0:
        raise resources.checker.planner.PlanError("installation_resources_fixture_mutation_failed")
    resources.command(["container", "rm", name])


def qualify(plan, expected, image, reports):
    original = resources.checker.verify(plan, expected)
    if (
        image != original["images"]["api"]
        or original["request"]["root"] != "/srv/declarai/qualification"
        or original["request"]["installation_id"] != "qualification"
    ):
        raise resources.checker.planner.PlanError("installation_resources_fixture_scope_required")
    resources.docker_host(original["manifest"]["architecture"])
    reports = reports.resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        raise resources.checker.planner.PlanError("installation_reports_path_invalid")
    reports.mkdir(parents=True, exist_ok=True)
    cases = []
    for fault, reason in {
        "clean": None,
        "foreign_network": "installation_resources_network_conflict",
        "public_network": "installation_resources_network_conflict",
        "foreign_volume": "installation_resources_volume_conflict",
        "occupied_volume": "installation_resources_socket_in_use",
        "nonempty_socket": "installation_resources_socket_init_failed",
        "wrong_socket_mode": "installation_resources_socket_init_failed",
    }.items():
        identifier = uuid.uuid4().hex
        files, pin = fixture_plan(plan, expected, identifier)
        directory = reports / ("resources-plan-" + fault)
        directory.mkdir()
        for name, data in files.items():
            (directory / name).write_bytes(data)
        value = resources.checker.verify(directory, pin)
        binding = resources.labels(value, pin, identifier)
        names = value["prerequisites"]["networks"]
        volume = value["prerequisites"]["socket_volume"]["name"]
        holders = []
        for kind, name in [("network", n["name"]) for n in names] + [("volume", volume)]:
            if resources.listing(kind, name):
                raise resources.checker.planner.PlanError("installation_resources_fixture_destination_exists")
        before = None
        try:
            if fault in {"foreign_network", "public_network"}:
                args = ["network", "create", "--driver", "bridge"]
                selected = {"org.declarai.qualification": identifier} if fault == "foreign_network" else binding
                for key, item in selected.items():
                    args += ["--label", key + "=" + item]
                resources.command([*args, names[0]["name"]])
                before = resources.inspect("network", names[0]["name"])
            elif fault == "foreign_volume":
                resources.command(["volume", "create", "--label", "org.declarai.qualification=" + identifier, volume])
                before = resources.inspect("volume", volume)
            elif fault in {"occupied_volume", "nonempty_socket", "wrong_socket_mode"}:
                resources.provision(value, pin, identifier)
                name = "declarai-p37-fixture-" + identifier
                if fault == "occupied_volume":
                    resources.command(
                        [
                            "container",
                            "create",
                            "--name",
                            name,
                            "--pull",
                            "never",
                            "--network",
                            "none",
                            "--read-only",
                            "--user",
                            "10001:10001",
                            "--cap-drop",
                            "ALL",
                            "--security-opt",
                            "no-new-privileges",
                            "--mount",
                            "type=volume,src=" + volume + ",dst=/run/declarai,volume-nocopy",
                            "--entrypoint",
                            "python",
                            image,
                            "-c",
                            "pass",
                        ]
                    )
                    holders.append(name)
                else:
                    code = (
                        "from pathlib import Path;Path('/run/declarai/sentinel').write_text('unchanged')"
                        if fault == "nonempty_socket"
                        else "import os;os.chmod('/run/declarai',0o700)"
                    )
                    qualifier_helper(name, volume, image, code)
            try:
                a = resources.provision(value, pin, identifier)
                if reason:
                    raise resources.checker.planner.PlanError("installation_resources_fixture_fault_not_blocked")
                b = resources.provision(value, pin, identifier)
                if a != b:
                    raise resources.checker.planner.PlanError("installation_resources_fixture_retry_changed")
                host = None
                if sys.platform == "linux":
                    host_identifier = uuid.uuid4().hex
                    host_files, host_pin = fixture_plan(plan, expected, host_identifier)
                    payload = resources.checker.planner.encoded(
                        {
                            "scripts": str(ROOT / "scripts"),
                            "parent": "/srv/declarai-p37-" + host_identifier,
                            "files": {k: v.decode() for k, v in host_files.items()},
                            "expected": host_pin,
                        }
                    )
                    run = subprocess.run(
                        ["sudo", "-n", sys.executable, "-c", HOST_CASE],
                        input=payload,
                        capture_output=True,
                        timeout=120,
                        check=False,
                    )
                    if run.returncode:
                        raise resources.checker.planner.PlanError(
                            "installation_resources_fixture_linux_controller_failed"
                        )
                    host = resources.checker.planner.decode(run.stdout)
                cases.append({"case": fault, "receipt": a, "repeat_prepare": "passed", "linux_root_controller": host})
            except resources.checker.planner.PlanError as error:
                if str(error) != reason:
                    raise
                cases.append({"case": fault, "blocked": reason})
            if before is not None:
                kind, name = ("volume", volume) if fault == "foreign_volume" else ("network", names[0]["name"])
                if resources.inspect(kind, name) != before:
                    raise resources.checker.planner.PlanError("installation_resources_fixture_foreign_changed")
            if fault in {"nonempty_socket", "wrong_socket_mode"}:
                code = (
                    "from pathlib import Path;assert Path('/run/declarai/sentinel').read_text()=='unchanged'"
                    if fault == "nonempty_socket"
                    else "import os;assert os.stat('/run/declarai').st_mode&0o777==0o700"
                )
                qualifier_helper("declarai-p37-check-" + identifier, volume, image, code)
        finally:
            owned_cleanup(value, pin, identifier, identifier, holders)
    result = {
        "schema": "private_installation_resources_qualification_v1",
        "image_id": image,
        "source_plan_sha256": expected,
        "cases": cases,
        "native_internal_networks": "passed",
        "native_socket_initialization": "passed",
        "owned_resource_cleanup": "passed",
        "operator_resources_modified": False,
        "application_services_started": False,
        "expert_isolation_qualified": False,
        "installation_qualified": False,
    }
    (reports / "installation-resources.json").write_bytes(resources.checker.planner.encoded(result))
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
