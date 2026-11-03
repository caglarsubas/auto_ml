#!/usr/bin/env python3
"""Own two complete installations; lose the first, then recover the second."""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from http.cookies import SimpleCookie
from pathlib import Path

import private_installation_recovery as recovery
import qualify_private_dependency_start as source_fixture
from qualify_private_installation_resources import fixture_plan
from qualify_private_installation_workflow import Session, require

ROOT = Path(__file__).resolve().parents[1]
startup, adopter = recovery.startup, recovery.adopter

# A deliberate worker-boundary fault through the unchanged production claim
# function. It keeps the original 180-second lease; no timestamps are edited.
BOUNDARY = r'''
import hashlib,json,os,sys,uuid
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
from pathlib import Path
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
import django;django.setup()
from execution_jobs import service
from execution_jobs.models import NativeJob
v=json.load(sys.stdin)
if v['action']=='claim':
    assert service.LIMITS['lease_seconds']==180
    result=service.claim(uuid.UUID(v['id']));assert result is not None
    job,_=result
    out={'state':job.state,'lease_until':job.lease_until.isoformat(),'attempts':job.attempts,'lease_seconds':180}
elif v['action']=='evidence':
    out={}
    for item in v['ids']:
        job=NativeJob.objects.get(pk=item)
        events=list(job.events.order_by('revision').values('revision','event_type'))
        out[item]={'state':job.state,'sha256':job.result_sha256,'attempts':job.attempts,
                   'events':hashlib.sha256(json.dumps(events,sort_keys=True).encode()).hexdigest()}
elif v['action']=='duplicates':
    from execution_jobs.tasks import run_native_job
    for item in v['ids']:
        for _ in range(3):run_native_job.delay(item)
    out={'published':3*len(v['ids'])}
elif v['action']=='broker':
    from backend.celery import app
    with app.connection_for_read() as conn:
        channel=conn.channel();client=channel.client
        queue=app.conf.task_default_queue
        queued=sum(client.llen(channel._q_for_pri(queue,p)) for p in channel.priority_steps)
        out={'queued':queued,'unacked':client.hlen(channel.unacked_key),'unacked_index':client.zcard(channel.unacked_index_key)}
else:raise RuntimeError('unknown qualification boundary')
print(json.dumps(out,sort_keys=True))
'''


def command(args, data=None):
    result = subprocess.run([*recovery.resources.PREFIX, *args], input=data, capture_output=True, timeout=60, check=False)
    require(result.returncode == 0, "recovery_fixture_command")
    return result.stdout


def boundary(api, action, **payload):
    return json.loads(command(["exec", "--user", "10001:10001", "-i", api, "python", "-I", "-c", BOUNDARY],
                              recovery.encoded({"action": action, **payload})))


def delivery(path, values):
    path.mkdir(mode=0o700)
    os.chown(path, 10001, 10001)
    for group in {name.split("/")[0] for name in values}:
        child = path / group
        child.mkdir(mode=0o700)
        os.chown(child, 10001, 10001)
    for name, raw in values.items():
        child = path / name
        child.write_bytes(raw)
        child.chmod(0o400)
        os.chown(child, 10001, 10001)


def prepare_empty(plan, expected, parent):
    value = startup.checker.verify(plan, expected)
    for stem, subject in (("server", "postgres"), ("cache", "cache")):
        names = "DNS:postgres,DNS:job-broker,DNS:cache,DNS:api.private.test" if stem == "server" else "DNS:cache"
        result = subprocess.run(["/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                                 "-keyout", str(parent / (stem + ".key")), "-out", str(parent / (stem + ".crt")),
                                 "-days", "1", "-subj", "/CN=" + subject, "-addext", "subjectAltName=" + names,
                                 "-addext", "basicConstraints=critical,CA:TRUE"], capture_output=True, timeout=30)
        require(result.returncode == 0, "recovery_fixture_certificate")
    cert, key = (parent / "server.crt").read_bytes(), (parent / "server.key").read_bytes()
    cache_cert, cache_key = (parent / "cache.crt").read_bytes(), (parent / "cache.key").read_bytes()
    app_password, broker_password, django_key, cache_password, owner_password = [secrets.token_urlsafe(48) for _ in range(5)]
    app = {"app/django-key": django_key.encode(), "app/app-password": app_password.encode(),
           "app/job-broker-url": ("rediss://:" + broker_password + "@job-broker:6379/1").encode(),
           "app/postgres-ca.crt": cert, "app/job-ca.crt": cert,
           "app/cache-url": ("rediss://:" + cache_password + "@cache:6379/0").encode(),
           "app/cache-ca.crt": cache_cert, "tls/tls.crt": cert, "tls/tls.key": key}
    delivery(parent / "app-delivery", app)
    initialized = startup.preparation.initializer.initialize(plan, expected, parent / "app-delivery")
    recovery.resources.prepare(plan, expected)
    dependencies = {role + "/" + name: cert if name.endswith(".crt") else key if name.endswith(".key") else owner_password.encode()
                    for role, names in startup.preparation.DELIVERY.items() for name in names}
    dependencies.update({"cache/server.crt": cache_cert, "cache/server.key": cache_key})
    delivery(parent / "dependency-delivery", dependencies)
    prepared = startup.preparation.initialize(plan, expected, parent / "dependency-delivery")
    startup.start(plan, expected)
    description = recovery.schema_init.initialize(plan, expected)
    recovery.schema_init.initialize(plan, expected, description["schema_sha256"])
    return value, initialized, prepared


def cleanup(plan, expected):
    if not (Path(plan).parent / "installation/initialization.json").exists():
        return
    value = startup.checker.verify(plan, expected)
    initialized = recovery.resources.initialization(value)
    profile, profile_sha, binding = adopter.application_profile(value, expected, initialized["initialization_id"])
    for info in adopter.project_containers(profile["name"]):
        role = info["Config"]["Labels"].get("com.docker.compose.service")
        require(role in adopter.ROLES, "recovery_cleanup_role")
        adopter.validate_application(info, role, profile["services"][role], profile, profile_sha, binding,
                                     recovery.resources.inspect("image", value["images"]["ingress" if role == "ingress" else "api"]))
        command(["container", "rm", "--force", "--volumes", info["Id"]])
    owner = recovery.resources.labels(value, expected, initialized["initialization_id"])
    for name in startup.names(value).values():
        if not recovery.resources.listing("container", name):
            continue
        info = recovery.resources.inspect("container", name)
        require(all(info["Config"]["Labels"].get(k) == v for k, v in owner.items()), "recovery_cleanup_owner")
        command(["container", "rm", "--force", "--volumes", info["Id"]])
    for kind, specs in (("network", value["prerequisites"]["networks"]), ("volume", [value["prerequisites"]["socket_volume"]])):
        for spec in specs:
            if recovery.resources.listing(kind, spec["name"]):
                require(recovery.resources.inspect(kind, spec["name"])["Labels"] == owner, "recovery_cleanup_owner")
                command([kind, "rm", spec["name"]])


class Scenario:
    def __init__(self, custody):
        self.custody = custody
        self.key = custody / "backup.key"
        self.key.write_bytes(os.urandom(32))
        self.key.chmod(0o400)
        self.archive = custody / "backup.aesgcm"
        self.handles = []

    def observe(self, value, accounts, passwords, parent, prepared, adopted, invoke):
        self.accounts, self.passwords, self.token = accounts, passwords, parent.name.removeprefix("declarai-p37-")
        self.source_id = value["request"]["installation_id"]

        def callback(session, handles):
            self.handles = handles
            self.completed = [row[k]["id"] for row in handles for k in ("training", "scoring")]
            self.source_evidence = boundary(adopted["services"]["api"]["container_id"], "evidence", ids=self.completed)
            for role in ("worker", "dispatcher"):
                identifier = adopted["services"][role]["container_id"]
                invoke(["container", "stop", "--time", "30", identifier])
                invoke(["container", "rm", "--volumes", identifier])
            row = handles[0]

            def submit():
                trained = row["training"]
                preview = session.data("POST", f'/api/jobs/{trained["id"]}/scoring-input/?project_id={accounts["project_id"]}',
                                       {"input_file_id": row["input_file_id"], "training_result_sha256": trained["result_sha256"]})
                request = {k: preview[k] for k in ("kind", "training_job_id", "training_result_sha256", "input_file_id", "input_sha256", "scoring_sha256")}
                request["request_id"] = str(uuid.uuid4())
                return session.data("POST", f'/api/jobs/datasets/{row["dataset_id"]}/?project_id={accounts["project_id"]}', request, 202)["id"]
            self.queued, self.orphan, self.cancelled = submit(), submit(), submit()
            require(session.data("POST", f'/api/jobs/{self.cancelled}/', {"action": "cancel"})["state"] == "cancelled", "recovery_cancel")
            self.claimed = boundary(adopted["services"]["api"]["container_id"], "claim", id=self.orphan)
            require(self.claimed["state"] == "running" and self.claimed["lease_seconds"] == 180, "recovery_claim")
            # Keep a separate valid session alive across the backup. The normal
            # workflow logs out its own session after this callback.
            old = Session(value, parent)
            anonymous = old.data("GET", "/api/auth/session/")
            old.csrf = anonymous["csrf_token"]
            old.data("POST", "/api/auth/login/", {"username": "fixture-developer-" + self.token, "password": passwords["developer"]})
            self.old_cookies = old.cookies.output(header="", sep=";")
        return callback

    def capture(self, plan, expected):
        self.backup = recovery.backup(plan, expected, self.key, self.archive)

    def restore(self, plan, expected, parent, prepared):
        value = startup.checker.verify(plan, expected)
        approved = self.custody / "restore-plan.json"
        spec = recovery.render(self.archive, self.backup["backup_sha256"], self.key, plan, expected, approved)
        # Wrong plan/key/tampered bytes must fail before any target mutation.
        original = self.archive.read_bytes()
        bad = self.custody / "tampered.aesgcm"
        bad.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        bad.chmod(0o600)
        try:
            recovery.render(bad, self.backup["backup_sha256"], self.key, plan, expected, self.custody / "bad-plan.json")
        except recovery.checker.planner.PlanError:
            pass
        else:
            require(False, "recovery_tamper_accepted")
        wrong_key = self.custody / "wrong.key"
        wrong_key.write_bytes(os.urandom(32));wrong_key.chmod(0o400)
        try:
            recovery.render(self.archive, self.backup["backup_sha256"], wrong_key, plan, expected, self.custody / "wrong-plan.json")
        except recovery.checker.planner.PlanError as error:
            require(str(error) == "recovery_authentication_failed", "recovery_wrong_key_diagnostic")
        else:
            require(False, "recovery_wrong_key_accepted")
        occupied = parent / "installation/artifacts/occupied"
        occupied.write_bytes(b"existing evidence")
        try:
            recovery.restore(self.archive, self.key, plan, expected, approved, spec["restore_plan_sha256"])
        except recovery.checker.planner.PlanError as error:
            require(str(error) == "recovery_target_artifacts_occupied" and occupied.read_bytes() == b"existing evidence"
                    and not (parent / "installation/recovery").exists(), "recovery_occupied_diagnostic")
        else:
            require(False, "recovery_occupied_accepted")
        occupied.unlink()
        postgres = startup.names(value)["postgres"]
        sql_args = ["exec", "--user", "70:70", "-i", postgres, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                    "-U", "postgres", value["request"]["database"]["name"]]
        command(sql_args, b"INSERT INTO auth_group(name) VALUES ('occupied recovery fixture');")
        try:
            recovery.restore(self.archive, self.key, plan, expected, approved, spec["restore_plan_sha256"])
        except recovery.checker.planner.PlanError as error:
            require(str(error) == "recovery_target_database_occupied"
                    and not (parent / "installation/recovery").exists(), "recovery_occupied_database_diagnostic")
        else:
            require(False, "recovery_occupied_database_accepted")
        command(sql_args, b"DELETE FROM auth_group WHERE name='occupied recovery fixture';")
        wrong_schema = recovery.unseal(original, self.key.read_bytes(), self.backup["backup_sha256"])
        wrong_schema["schema_sha256"] = "f" * 64
        changed = self.custody / "wrong-schema.aesgcm"
        changed.write_bytes(recovery.seal(wrong_schema, self.key.read_bytes()));changed.chmod(0o600)
        changed_plan = self.custody / "wrong-schema-plan.json"
        changed_spec = recovery.render(changed, recovery.digest(changed.read_bytes()), self.key, plan, expected, changed_plan)
        try:
            recovery.restore(changed, self.key, plan, expected, changed_plan, changed_spec["restore_plan_sha256"])
        except recovery.checker.planner.PlanError as error:
            require(str(error) == "recovery_schema_binding" and not (parent / "installation/recovery").exists(),
                    "recovery_schema_diagnostic")
        else:
            require(False, "recovery_wrong_schema_accepted")
        # Lose the controller's acknowledgement AFTER the real COPY transaction
        # commits. No test mutation touches job state, clocks or lease lengths.
        real_helper = recovery.helper
        def lose_copy_ack(*args, **kwargs):
            result = real_helper(*args, **kwargs)
            if args[3] == "restore":
                raise RuntimeError("qualification_lost_copy_ack")
            return result
        recovery.helper = lose_copy_ack
        try:
            recovery.restore(self.archive, self.key, plan, expected, approved, spec["restore_plan_sha256"])
        except RuntimeError as error:
            require(str(error) == "qualification_lost_copy_ack", "recovery_lost_ack")
        finally:
            recovery.helper = real_helper
        require((parent / "installation/recovery/intent.json").exists()
                and not (parent / "installation/recovery/complete.json").exists(), "recovery_missing_pending_intent")
        try:
            adopter.adoption(plan, expected, parent / "server.crt")
        except recovery.checker.planner.PlanError as error:
            require(str(error) == "recovery_pending", "recovery_pending_adoption_diagnostic")
        else:
            require(False, "recovery_pending_adopted")
        real_publish = recovery.publish
        def lose_artifact_ack(path, raw):
            if Path(path).name == "complete.json":
                raise RuntimeError("qualification_before_completion")
            return real_publish(path, raw)
        recovery.publish = lose_artifact_ack
        try:
            recovery.restore(self.archive, self.key, plan, expected, approved, spec["restore_plan_sha256"])
        except RuntimeError as error:
            require(str(error) == "qualification_before_completion", "recovery_artifact_ack")
        finally:
            recovery.publish = real_publish
        require(not (parent / "installation/recovery/complete.json").exists()
                and not (parent / "installation/recovery/staged-artifacts").exists(), "recovery_artifacts_not_published")
        first = recovery.restore(self.archive, self.key, plan, expected, approved, spec["restore_plan_sha256"])
        before = (parent / "installation/recovery/complete.json").read_bytes()
        again = recovery.restore(self.archive, self.key, plan, expected, approved, spec["restore_plan_sha256"])
        require(first["reused"] is False and again["reused"] is True and (parent / "installation/recovery/complete.json").read_bytes() == before, "recovery_repeat")
        adopted = adopter.adoption(plan, expected, parent / "server.crt")
        api = adopted["services"]["api"]["container_id"]
        from qualify_private_account_enrollment import https_roles

        https_roles(value, self.accounts, self.passwords, parent, username_token=self.token)
        stale = Session(value, parent)
        stale.cookies = SimpleCookie(self.old_cookies)
        require(stale.data("GET", "/api/auth/session/")["authenticated"] is False, "recovery_old_session")
        session = Session(value, parent)
        session.csrf = session.data("GET", "/api/auth/session/")["csrf_token"]
        login = session.data("POST", "/api/auth/login/", {"username": "fixture-developer-" + self.token, "password": self.passwords["developer"]})
        session.csrf = login["csrf_token"]
        for row in self.handles:
            trained, scored = row["training"], row["scoring"]
            export, _ = session.request("GET", f'/api/jobs/{trained["id"]}/candidate/?sha256={trained["result_sha256"]}')
            scores, _ = session.request("GET", f'/api/jobs/{scored["id"]}/scores/?sha256={scored["result_sha256"]}')
            require(export == row["export"] and scores == row["scores"], "recovery_completed_bytes_changed")
        require(boundary(api, "evidence", ids=self.completed) == self.source_evidence, "recovery_completed_history_changed")
        deadline = time.monotonic() + 240
        while True:
            rows = [session.data("GET", f"/api/jobs/{item}/") for item in (self.queued, self.orphan, self.cancelled)]
            if all(r["state"] in {"succeeded", "failed", "blocked", "cancelled"} for r in rows):
                break
            require(time.monotonic() < deadline, "recovery_pending_deadline")
            time.sleep(.3)
        require([r["state"] for r in rows] == ["succeeded", "succeeded", "cancelled"], "recovery_pending_outcomes")
        require(rows[0]["result"]["scores"] == self.handles[0]["scoring"]["result"]["scores"]
                and rows[1]["result"]["scores"] == rows[0]["result"]["scores"], "recovery_scoring_parity")
        ids = [*self.completed, self.queued, self.orphan, self.cancelled]
        evidence = boundary(api, "evidence", ids=ids)
        require(evidence[self.orphan]["attempts"] == 2 and evidence[self.queued]["attempts"] == 1
                and evidence[self.cancelled]["attempts"] == 0, "recovery_attempts")
        boundary(api, "duplicates", ids=ids)
        deadline = time.monotonic() + 30
        while any(boundary(api, "broker").values()):
            require(time.monotonic() < deadline, "recovery_broker_drain")
            time.sleep(.2)
        command(["container", "stop", "--time", "30", adopted["services"]["worker"]["container_id"]])
        require(not any(boundary(api, "broker").values()), "recovery_unacked_after_shutdown")
        require(boundary(api, "evidence", ids=ids) == evidence, "recovery_duplicate_publication")
        # Idempotent restore remains read-only after legitimate new work.
        require(recovery.restore(self.archive, self.key, plan, expected, approved, spec["restore_plan_sha256"])["reused"] is True,
                "recovery_post_use_replay")
        return {"schema": "private_installed_recovery_v1", "source_installation_id": self.source_id,
                "target_installation_id": value["request"]["installation_id"], "same_exact_images": True,
                "database_artifact_and_schema_binding": "passed", "classification_regression_export_score_bytes": "passed",
                "restored_account_project_authority": "passed", "old_sessions_invalidated": True,
                "original_completed_job_history": "preserved", "empty_broker_pending_reconstruction": "passed",
                "original_lease_seconds": 180, "lease_clock_modified": False,
                "orphan_completed_attempts": evidence[self.orphan]["attempts"], "cancellation_preserved": True,
                "duplicate_deliveries": len(ids) * 3, "duplicate_publication": "refused",
                "post_use_restore_replay": "read_only", "tampered_backup": "refused",
                "wrong_key": "refused", "occupied_artifacts": "preserved_and_refused",
                "occupied_database": "refused_without_intent", "wrong_schema": "refused_without_intent",
                "lost_database_commit_ack": "resumed", "lost_artifact_publication_ack": "resumed",
                "pending_recovery_adoption": "refused",
                "source_backup_sha256": self.backup["backup_sha256"], "restore_plan_sha256": spec["restore_plan_sha256"],
                "operator_key_custody_qualified": False, "customer_RPO_RTO_qualified": False,
                "customer_accepted": False, "release_qualified": False}


def run_case(v):
    require(sys.platform == "linux" and os.geteuid() == 0, "recovery_fixture_linux_root")
    source, target, custody = (Path(v[k]) for k in ("source", "target", "custody"))
    require(all(p.parent == Path("/srv") for p in (source, target, custody))
            and all(recovery.resources.re.fullmatch(r"declarai-p37-[0-9a-f]{32}", p.name) for p in (source, target))
            and recovery.resources.re.fullmatch(r"declarai-recovery-[0-9a-f]{32}", custody.name), "recovery_fixture_scope")
    created = []
    src_plan, dst_plan = source / "plan", target / "plan"
    try:
        custody.mkdir(mode=0o700);created.append(custody)
        scenario = Scenario(custody)
        source.mkdir(mode=0o700);created.append(source);src_plan.mkdir(mode=0o700)
        for name, raw in v["source_files"].items():
            (src_plan / name).write_text(raw)
        source_result = source_fixture.host_case(src_plan, v["source_sha"], source, recovery=scenario)
        shutil.rmtree(source)
        require(not source.exists(), "recovery_source_storage_survived")
        target.mkdir(mode=0o700);created.append(target);dst_plan.mkdir(mode=0o700)
        for name, raw in v["target_files"].items():
            (dst_plan / name).write_text(raw)
        _, _, prepared = prepare_empty(dst_plan, v["target_sha"], target)
        result = scenario.restore(dst_plan, v["target_sha"], target, prepared)
        result.update(source_installation_storage_unavailable=True, original_source_controller_assertions="passed",
                      source_profile=source_result["installation_profile"])
        return result
    finally:
        if src_plan.exists():
            cleanup(src_plan, v["source_sha"])
        if dst_plan.exists():
            cleanup(dst_plan, v["target_sha"])
        for path in reversed(created):
            if path.exists():
                shutil.rmtree(path)


def qualify(reports):
    reports = reports.resolve()
    require(reports.is_relative_to(ROOT / "test-reports"), "recovery_reports_scope")
    import tempfile

    with tempfile.TemporaryDirectory(prefix="declarai-recovery-plan-") as temp:
        plan = Path(temp)
        for name in recovery.checker.planner.FILES | {"manifest.json"}:
            (plan / name).write_bytes((reports / ("installation-plan-" + name)).read_bytes())
        expected = recovery.digest((plan / "manifest.json").read_bytes())
        value = recovery.checker.verify(plan, expected)
        require(value["request"]["root"] == "/srv/declarai/qualification" and value["request"]["installation_id"] == "qualification", "recovery_fixture_template")
        source, target, custody = (uuid.uuid4().hex for _ in range(3))
        sf, sp = fixture_plan(plan, expected, source)
        tf, tp = fixture_plan(plan, expected, target)
        payload = {"scripts": str(ROOT / "scripts"), "source": "/srv/declarai-p37-" + source,
                   "target": "/srv/declarai-p37-" + target, "custody": "/srv/declarai-recovery-" + custody,
                   "source_files": {k: x.decode() for k, x in sf.items()}, "source_sha": sp,
                   "target_files": {k: x.decode() for k, x in tf.items()}, "target_sha": tp}
        code = "import json,sys;v=json.load(sys.stdin);sys.path.insert(0,v['scripts']);from qualify_private_installation_recovery import run_case;print(json.dumps(run_case(v)))"
        result = subprocess.run(["sudo", "-n", sys.executable, "-c", code], input=recovery.encoded(payload),
                                capture_output=True, timeout=600, check=False)
        if result.returncode:
            (reports / "installed-recovery-failed.log").write_bytes(result.stderr)
            require(False, "recovery_fixture_failed")
        record = json.loads(result.stdout)
        profile = record["source_profile"]
        require(profile["architecture"] == {"arm64": "aarch64", "amd64": "x86_64"}[value["manifest"]["architecture"]]
                and profile["os_release"]["ID"] == "ubuntu"
                and profile["os_release"]["VERSION_ID"] == "24.04" and profile["cpu_count"] == 4
                and 14 * 1024**3 <= profile["observed_memory_bytes"] <= 17 * 1024**3, "recovery_reference_profile")
        record.update(owned_roots_and_resources_removed=True, synthetic_installed_recovery_qualified=True)
        (reports / "installed-recovery.json").write_bytes(recovery.encoded(record))
        return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=ROOT / "test-reports/postgresql")
    print(json.dumps(qualify(parser.parse_args().reports)))
