#!/usr/bin/env python3
"""Qualify dependency preparation on exclusively owned Linux volumes."""

import argparse
import json
import uuid
from pathlib import Path

import private_dependency_init as dependency
from qualify_private_installation_check import command

ROOT = Path(__file__).resolve().parents[1]

PREPARE = r"""
import json,os,secrets,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/harness')
import private_installation_init as m
v=json.load(sys.stdin);plan=Path('/plan');parent=Path('/srv/declarai')
for name,data in v['files'].items(): (plan/name).write_text(data)
parent.chmod(0o755)
cert=parent/'server.crt';key=parent/'server.key'
r=subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=postgres','-addext','subjectAltName=DNS:postgres,DNS:job-broker,DNS:cache,DNS:api.private.test','-addext','basicConstraints=critical,CA:TRUE'],capture_output=True,check=False)
assert r.returncode==0,'synthetic_certificate_generation_failed'
pwd=secrets.token_urlsafe(32)
app={'app/django-key':secrets.token_urlsafe(64).encode(),'app/app-password':secrets.token_urlsafe(32).encode(),'app/job-broker-url':('rediss://:'+pwd+'@job-broker:6379/1').encode(),'app/postgres-ca.crt':cert.read_bytes(),'app/job-ca.crt':cert.read_bytes(),'app/cache-url':('rediss://:'+secrets.token_urlsafe(32)+'@cache:6379/0').encode(),'app/cache-ca.crt':cert.read_bytes(),'tls/tls.crt':cert.read_bytes(),'tls/tls.key':key.read_bytes()}
delivered={'postgres/server.crt':cert.read_bytes(),'postgres/server.key':key.read_bytes(),'postgres/owner-password':secrets.token_urlsafe(32).encode(),'job-broker/server.crt':cert.read_bytes(),'job-broker/server.key':key.read_bytes(),'cache/server.crt':cert.read_bytes(),'cache/server.key':key.read_bytes()}
def delivery(root,files):
    root.mkdir(mode=0o700);os.chown(root,10001,10001)
    for group in {name.split('/')[0] for name in files}:
        p=root/group;p.mkdir(mode=0o700);os.chown(p,10001,10001)
    for name,data in files.items():
        p=root/name;p.write_bytes(data);p.chmod(0o400);os.chown(p,10001,10001)
delivery(parent/'app-delivery',app)
m.initialize(plan,v['expected'],parent/'app-delivery')
if v['fault']=='weak_password':delivered['postgres/owner-password']=b'weak'
elif v['fault']=='bad_ca':
    p=parent/'qualification/secrets/app/postgres-ca.crt';p.chmod(0o600);p.write_bytes(b'not a CA');p.chmod(0o400)
elif v['fault']=='wrong_key':
    other=parent/'other.key';r=subprocess.run(['/usr/bin/openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048','-out',str(other)],capture_output=True,check=False);assert r.returncode==0
    delivered['postgres/server.key']=other.read_bytes()
elif v['fault']=='wrong_hostname':
    csr=parent/'wrong.csr';wrong=parent/'wrong.crt'
    r=subprocess.run(['/usr/bin/openssl','req','-new','-key',str(key),'-out',str(csr),'-subj','/CN=wrong.private.test','-addext','subjectAltName=DNS:wrong.private.test'],capture_output=True,check=False);assert r.returncode==0
    r=subprocess.run(['/usr/bin/openssl','x509','-req','-in',str(csr),'-CA',str(cert),'-CAkey',str(key),'-CAcreateserial','-out',str(wrong),'-days','1','-copy_extensions','copy'],capture_output=True,check=False);assert r.returncode==0
    delivered['postgres/server.crt']=wrong.read_bytes()
elif v['fault']=='encrypted_key':
    locked=parent/'locked.key'
    r=subprocess.run(['/usr/bin/openssl','pkey','-in',str(key),'-aes-256-cbc','-passout','stdin','-out',str(locked)],input=b'synthetic-only-lockpass\n',capture_output=True,check=False);assert r.returncode==0
    delivered['postgres/server.key']=locked.read_bytes()
delivery(parent/'delivery',delivered)
if v['fault']=='hardlink':os.link(parent/'delivery/postgres/owner-password',parent/'outside')
elif v['fault']=='symlink':
    p=parent/'delivery/postgres/server.key';p.unlink();p.symlink_to(key)
elif v['fault']=='extra_file':(parent/'delivery/postgres/extra').write_bytes(b'unknown')
elif v['fault']=='unsafe_parent':parent.chmod(0o777)
"""

RUN = r"""
import json,sys
from pathlib import Path
sys.path.insert(0,'/harness')
import private_dependency_init as m
fault,expected,source=sys.argv[1:]
if fault=='write_failure':
    original=m.initializer.write_file;count=0
    def fail(*args):
        global count
        count+=1
        if count==3:raise m.checker.planner.PlanError('synthetic_dependency_write_failure')
        return original(*args)
    m.initializer.write_file=fail
elif fault=='competing_empty':
    original=m.initializer.rename_noreplace
    def publish(parent,source,target):
        m.os.mkdir(target,mode=0o700,dir_fd=parent)
        original(parent,source,target)
    m.initializer.rename_noreplace=publish
try:print(json.dumps(m.initialize(Path('/plan'),expected,Path(source))))
except (m.checker.planner.PlanError,OSError) as e:
    print(str(e) if isinstance(e,m.checker.planner.PlanError) else 'dependency_init_io_failed',file=sys.stderr);sys.exit(1)
"""

VERIFY = r"""
import json,os,sys
from pathlib import Path
sys.path.insert(0,'/harness');import private_dependency_init as m
parent=Path('/srv/declarai');root=parent/'qualification';target=root/'dependencies';fault=sys.argv[1]
assert not list(root.glob('.declarai-dependencies-*'))
if fault=='competing_empty':assert target.is_dir() and not list(target.iterdir())
elif fault!='clean':assert not target.exists()
else:
    s=target.stat();assert (s.st_uid,s.st_gid,s.st_mode&0o777)==(0,0,0o700)
    for name in ['profile.json','initialization.json']:
        s=(target/name).stat();assert (s.st_uid,s.st_gid,s.st_mode&0o777,s.st_nlink)==(0,0,0o600,1)
    for role,(uid,gid) in m.IDENTITY.items():
        for p in [target/role,target/role/'config']:
            s=p.stat();assert (s.st_uid,s.st_gid,s.st_mode&0o777)==(0,gid,0o750)
        for p in (target/role/'config').iterdir():
            s=p.stat();assert (s.st_uid,s.st_gid,s.st_mode&0o777,s.st_nlink)==(0,gid,0o440,1)
        if role!='cache':
            p=target/role/'data';s=p.stat();assert (s.st_uid,s.st_gid,s.st_mode&0o777)==(uid,gid,0o700) and not list(p.iterdir())
        for name in m.DELIVERY.get(role,[]):assert (target/role/'config'/name).read_bytes()==(parent/'delivery'/role/name).read_bytes()
    receipt=json.loads((target/'initialization.json').read_text())
    assert receipt['database_initialized'] is False and receipt['dependencies_started'] is False
    assert (target/'job-broker/config/server-ca.crt').read_bytes()==(root/'secrets/app/job-ca.crt').read_bytes()
if fault!='bad_ca':
    for group in ['app','tls']:
        for p in (root/'secrets'/group).iterdir():assert p.read_bytes()==(parent/'app-delivery'/group/p.name).read_bytes()
print('owned_dependency_fixture_verified')
"""


def qualify(plan, expected, image, reports):
    value = dependency.checker.verify(plan, expected)
    if (
        image != value["images"]["api"]
        or value["request"]["root"] != "/srv/declarai/qualification"
        or value["request"]["installation_id"] != "qualification"
    ):
        raise dependency.checker.planner.PlanError("dependency_fixture_scope_required")
    reports = reports.resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        raise dependency.checker.planner.PlanError("installation_reports_path_invalid")
    files = {name: data.decode() for name, data in dependency.checker.read_plan(plan).items()}
    prefix = "declarai-dependencies-" + uuid.uuid4().hex
    volumes, containers, cases = [], [], []
    faults = {
        "clean": None,
        "weak_password": "dependency_password_invalid",
        "bad_ca": "dependency_certificate_invalid",
        "wrong_key": "dependency_certificate_key_mismatch",
        "wrong_hostname": "dependency_certificate_invalid",
        "encrypted_key": "dependency_certificate_invalid",
        "hardlink": "dependency_delivery_file_invalid",
        "symlink": "dependency_init_io_failed",
        "extra_file": "dependency_delivery_members_invalid",
        "unsafe_parent": "installation_init_parent_unsafe",
        "write_failure": "synthetic_dependency_write_failure",
        "competing_empty": "installation_init_destination_exists",
    }
    try:
        for fault, reason in faults.items():
            installation, metadata = prefix + "-" + fault + "-data", prefix + "-" + fault + "-plan"
            for name in (installation, metadata):
                if command(["docker", "volume", "create", name]).returncode:
                    raise dependency.checker.planner.PlanError("dependency_fixture_volume_failed")
                volumes.append(name)

            def run(role, script, *args, data=None):
                name = prefix + "-" + fault + "-" + role
                containers.append(name)
                return command(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--name",
                        name,
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
                        "--user",
                        "0:0",
                        "--cap-add",
                        "CHOWN",
                        "--cap-add",
                        "DAC_OVERRIDE",
                        "--cap-add",
                        "FOWNER",
                        "--tmpfs",
                        "/tmp:rw,noexec,nosuid,size=67108864",
                        "-v",
                        installation + ":/srv/declarai",
                        "-v",
                        metadata + ":/plan",
                        "-v",
                        str(ROOT / "scripts") + ":/harness:ro",
                        *(["-i"] if data is not None else []),
                        "--entrypoint",
                        "python",
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
                data=dependency.checker.planner.encoded({"files": files, "expected": expected, "fault": fault}),
            ).returncode:
                raise dependency.checker.planner.PlanError("dependency_fixture_prepare_failed")
            result = run("initialize", RUN, fault, expected, "/srv/declarai/delivery")
            if reason:
                if not result.returncode or result.stdout or result.stderr.decode().strip() != reason:
                    raise dependency.checker.planner.PlanError("dependency_fixture_fault_not_blocked")
                cases.append({"case": fault, "blocked": reason})
            else:
                if result.returncode:
                    raise dependency.checker.planner.PlanError("dependency_fixture_failed")
                receipt = dependency.checker.planner.decode(result.stdout)
                if receipt["delivered_files"] != 7 or receipt["dependencies_started"] is not False:
                    raise dependency.checker.planner.PlanError("dependency_fixture_receipt_invalid")
                cases.append({"case": fault, "receipt": receipt})
                retry = run("retry", RUN, fault, expected, "/does-not-exist")
                if (
                    not retry.returncode
                    or retry.stdout
                    or retry.stderr.decode().strip() != "installation_init_destination_exists"
                ):
                    raise dependency.checker.planner.PlanError("dependency_fixture_retry_not_blocked")
            verified = run("verify", VERIFY, fault)
            if verified.returncode or verified.stdout.decode().strip() != "owned_dependency_fixture_verified":
                raise dependency.checker.planner.PlanError("dependency_fixture_state_failed")
    finally:
        for name in reversed(containers):
            command(["docker", "container", "rm", "--force", name])
        for name in reversed(volumes):
            if command(["docker", "volume", "rm", name]).returncode:
                raise dependency.checker.planner.PlanError("dependency_fixture_cleanup_failed")
    receipt = {
        "schema": "private_dependency_init_qualification_v1",
        "image_id": image,
        "plan_manifest_sha256": expected,
        "cases": cases,
        "owned_volumes_removed": len(volumes),
        "operator_installation_modified": False,
        "dependency_services_started": False,
        "installation_qualified": False,
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "dependency-init.json").write_bytes(dependency.checker.planner.encoded(receipt))
    return receipt


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
