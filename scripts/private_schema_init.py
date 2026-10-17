#!/usr/bin/env python3
"""Initialize only a fresh schema from an explicitly pinned, sealed migration graph.

Existing/partial schemas require a separate reviewed upgrade. No owner credential,
account enrollment, application launch, schema repair or release approval.
"""

import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys
import uuid
from pathlib import Path

import private_dependency_start as startup
import private_installation_adopt as adopter

resources, checker = startup.resources, startup.checker

# This is trusted installer code, not an expert-code interface. -I and the exact
# image/readonly profile prevent loading caller modules or installation artifacts.
SCHEMA_CODE = r"""
import contextlib,hashlib,io,json,logging,os,sys
from pathlib import Path
logging.disable(logging.CRITICAL)
phase='runtime'
try:
    assert os.geteuid()==10001 and os.getegid()==10001
    sys.path.insert(0,'/app/scripts')
    from private_runtime_manifest import verify
    verify(Path('/app'))
    runtime=hashlib.sha256(Path('/app/runtime-manifest.json').read_bytes()).hexdigest()
    sys.path.insert(0,'/app/backend')
    os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
    Path('/tmp/schema-media').mkdir(mode=0o700)
    import django
    django.setup()
    from django.apps import apps
    from django.db import connection,transaction
    from django.db.migrations.executor import MigrationExecutor
    from django.core.management import call_command
    phase='authority'
    with connection.cursor() as c:
        c.execute("SET lock_timeout='5s'; SET statement_timeout='45s'")
        c.execute("SELECT current_database(),current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid) FROM pg_roles r WHERE rolname=current_user")
        row=c.fetchone()
        assert row[:4]==(os.environ['DECLARAI_DB_NAME'],os.environ['DECLARAI_DB_USER'],True,True) and all(x is False for x in row[4:])
        c.execute("SELECT pg_get_userbyid(datdba)=current_user AND pg_encoding_to_char(encoding)='UTF8' FROM pg_database WHERE datname=current_database()")
        assert c.fetchone()==(True,)
        c.execute("SELECT pg_catalog.pg_try_advisory_lock(1584948041,42)")
        assert c.fetchone()==(True,)
    phase='graph'
    executor=MigrationExecutor(connection)
    loader=executor.loader
    loader.check_consistent_history(connection)
    assert not loader.replacements
    vertices=[{'app':a,'name':n,'parents':[list(p.key) for p in sorted(loader.graph.node_map[(a,n)].parents,key=lambda p:p.key)]} for a,n in sorted(loader.disk_migrations)]
    graph={'runtime_manifest_sha256':runtime,'vertices':vertices,'targets':[list(k) for k in sorted(loader.graph.leaf_nodes())]}
    encoded=lambda x:(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
    digest=hashlib.sha256(encoded(graph)).hexdigest()
    action=os.environ['SCHEMA_ACTION']; expected=os.environ['SCHEMA_EXPECTED']
    assert action in ('describe','apply_fresh','verify_current')
    if action!='describe':assert digest==expected
    def state():
        applied=set(loader.applied_migrations)
        with connection.cursor() as c:
            c.execute("SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname OPERATOR(pg_catalog.<>) 'public'::pg_catalog.name AND nspname OPERATOR(pg_catalog.<>) 'information_schema'::pg_catalog.name AND pg_catalog.left(nspname::pg_catalog.text,3) OPERATOR(pg_catalog.<>) 'pg_'::pg_catalog.text")
            if c.fetchall():return 'foreign'
            c.execute("SELECT extname FROM pg_catalog.pg_extension WHERE extname OPERATOR(pg_catalog.<>) 'plpgsql'::pg_catalog.name")
            if c.fetchall():return 'foreign'
            c.execute("SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid OPERATOR(pg_catalog.=) p.pronamespace WHERE n.nspname OPERATOR(pg_catalog.=) 'public'::pg_catalog.name")
            if c.fetchone()!=(0,):return 'foreign'
            c.execute("SELECT pg_catalog.count(*) FROM pg_catalog.pg_event_trigger")
            if c.fetchone()!=(0,):return 'foreign'
            c.execute("SELECT n.nspname,c.relname,c.relkind,pg_catalog.pg_get_userbyid(c.relowner) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid OPERATOR(pg_catalog.=) c.relnamespace WHERE n.nspname OPERATOR(pg_catalog.=) 'public'::pg_catalog.name AND c.relkind OPERATOR(pg_catalog.=) ANY(ARRAY['r','p','v','m','S','f']::pg_catalog.\"char\"[])")
            relations=c.fetchall()
        if not relations and not applied:return 'fresh'
        tables={name for _,name,kind,_ in relations if kind!='S'}
        wanted={'django_migrations'}|{m._meta.db_table for m in apps.get_models(include_auto_created=True) if m._meta.managed and not m._meta.proxy}
        if any(owner!=os.environ['DECLARAI_DB_USER'] for _,_,_,owner in relations):return 'foreign'
        with connection.cursor() as c:
            c.execute("SELECT seq.relname,t.relname FROM pg_catalog.pg_class seq JOIN pg_catalog.pg_namespace n ON n.oid OPERATOR(pg_catalog.=) seq.relnamespace LEFT JOIN pg_catalog.pg_depend d ON d.classid OPERATOR(pg_catalog.=) 'pg_catalog.pg_class'::pg_catalog.regclass::pg_catalog.oid AND d.objid OPERATOR(pg_catalog.=) seq.oid AND d.deptype OPERATOR(pg_catalog.=) ANY(ARRAY['a','i']::pg_catalog.\"char\"[]) LEFT JOIN pg_catalog.pg_class t ON t.oid OPERATOR(pg_catalog.=) d.refobjid WHERE n.nspname OPERATOR(pg_catalog.=) 'public'::pg_catalog.name AND seq.relkind OPERATOR(pg_catalog.=) 'S'::pg_catalog.\"char\"")
            if any(table not in wanted for _,table in c.fetchall()):return 'foreign'
        if applied==set(loader.disk_migrations) and not executor.migration_plan(loader.graph.leaf_nodes()) and tables==wanted:return 'current'
        return 'partial_or_foreign'
    phase='state'
    before=state()
    if action=='verify_current':assert before=='current'
    elif action=='apply_fresh':
        assert before=='fresh'
        phase='migration'
        # PostgreSQL rolls back all DDL, migration history and post_migrate seeds
        # together on failure; never fake, skip, reverse or repair migrations.
        with transaction.atomic():
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                call_command('migrate',interactive=False,verbosity=0,skip_checks=True)
            executor=MigrationExecutor(connection);loader=executor.loader
            assert state()=='current'
        phase='state'
    print(json.dumps({'schema':'private_schema_probe_v1','schema_sha256':digest,'graph':graph,'state':state(),'action':action,'application_role_elevated':False},sort_keys=True))
except Exception:
    print('private_schema_'+phase+'_failed');raise SystemExit(1)
finally:
    if 'connection' in globals():connection.close()
"""


def helper(value, receipt, image, action, expected=""):
    environment = checker.planner.composition(value["request"], value["images"])["services"]["api"]["environment"]
    environment = {
        **environment,
        "DECLARAI_MEDIA_ROOT": "/tmp/schema-media",
        "SCHEMA_ACTION": action,
        "SCHEMA_EXPECTED": expected,
    }
    binding = startup.labels(value, receipt)
    args = [
        "container",
        "create",
        "--name",
        "declarai-schema-" + uuid.uuid4().hex,
        "--pull",
        "never",
        "--network",
        value["prerequisites"]["networks"][0]["name"],
        "--read-only",
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--cpus",
        "1",
        "--memory",
        "1g",
        "--pids-limit",
        "64",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=134217728,uid=10001,gid=10001,mode=700",
        "--entrypoint",
        "python",
    ]
    for key, item in {**binding, resources.LABEL + "role": "schema"}.items():
        args += ["--label", key + "=" + item]
    for key, item in environment.items():
        args += ["--env", key + "=" + item]
    for source, target in [("secrets/app", "/installation")]:
        args += ["--mount", "type=bind,src=" + value["request"]["root"] + "/" + source + ",dst=" + target + ",readonly"]
    identifier = None
    try:
        identifier = resources.command([*args, value["images"]["api"], "-I", "-c", SCHEMA_CODE]).decode().strip()
        if not resources.re.fullmatch(r"[0-9a-f]{64}", identifier):
            identifier = None
            raise checker.planner.PlanError("schema_helper_identity_invalid")
        adopter.validate_preflight(
            resources.inspect("container", identifier),
            value,
            environment,
            binding,
            image,
            role="schema",
            entrypoint=["python"],
            command=["-I", "-c", SCHEMA_CODE],
            mount_sources={"/installation": value["request"]["root"] + "/secrets/app"},
        )
        output = resources.command(["container", "start", "--attach", identifier], allow_failure=True)
        state = resources.inspect("container", identifier).get("State", {})
        phases = {
            ("private_schema_" + phase + "_failed").encode()
            for phase in ("runtime", "authority", "graph", "state", "migration")
        }
        if output.strip() in phases:
            raise checker.planner.PlanError(output.strip().decode())
        if (
            state.get("Running") is not False
            or type(state.get("ExitCode")) is not int
            or state["ExitCode"] != 0
            or len(output) > 65536
        ):
            raise checker.planner.PlanError("schema_helper_failed")
        try:
            result = checker.planner.decode(output)
            digest = hashlib.sha256(
                (json.dumps(result["graph"], sort_keys=True, separators=(",", ":")) + "\n").encode()
            ).hexdigest()
            if (
                set(result) != {"schema", "schema_sha256", "graph", "state", "action", "application_role_elevated"}
                or result["schema"] != "private_schema_probe_v1"
                or result["action"] != action
                or result["application_role_elevated"] is not False
                or result["schema_sha256"] != digest
                or result["state"] not in {"fresh", "current", "foreign", "partial_or_foreign"}
                or action != "describe"
                and (digest != expected or result["state"] != "current")
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise checker.planner.PlanError("schema_helper_result_invalid") from None
        return result
    finally:
        if identifier:
            resources.command(["container", "rm", "--force", identifier])


def publish(root, name, value):
    data = checker.planner.encoded(value)
    stage = ".schema-stage-" + uuid.uuid4().hex
    try:
        fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        resources.initializer.rename_noreplace(root, stage, name)
        os.fsync(root)
    finally:
        if stage in os.listdir(root):
            os.unlink(stage, dir_fd=root)


def bound_intent(value, expected, receipt, dependencies, schema):
    return {
        "schema": "private_schema_intent_v1",
        "plan_manifest_sha256": expected,
        "dependency_initialization_id": receipt["dependency_initialization_id"],
        "dependency_profile_sha256": receipt["dependency_profile_sha256"],
        "image_id": value["images"]["api"],
        "schema_sha256": schema,
        "helper_sha256": hashlib.sha256(SCHEMA_CODE.encode()).hexdigest(),
        "dependencies": {r: {"container_id": c["Id"], "image_id": c["Image"]} for r, c in dependencies.items()},
        "scope": "fresh_schema_initialization_only",
        "accounts_enrolled": False,
        "model_use_approved": False,
        "installation_qualified": False,
        "release_qualified": False,
    }


def result_receipt(intent, recovered):
    return {
        **intent,
        "schema": "private_schema_initialization_v1",
        "schema_current": True,
        "migration_execution": "recovered_current_from_exact_intent" if recovered else "applied_atomically",
        "application_role_elevated": False,
        "production_recovery_qualified": False,
        "expert_isolation_qualified": False,
    }


def initialize(plan, expected, schema=None):
    if schema is not None and (not isinstance(schema, str) or not resources.re.fullmatch(r"[0-9a-f]{64}", schema)):
        raise checker.planner.PlanError("schema_trusted_digest_required")
    value, spec, receipt, _, _, root = startup.prepared(plan, expected)
    lock = None
    try:
        lock = os.open("start.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=root)
        info = os.fstat(lock)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (0, 0, 0o600)
        ):
            raise checker.planner.PlanError("dependency_lock_invalid")
        checker.no_directory_acl(lock)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise checker.planner.PlanError("dependency_operation_in_progress") from None
        resources.docker_host(value["manifest"]["architecture"])
        if resources.record(["info", "--format", "{{json .}}"]).get("DefaultRuntime") != "runc":
            raise checker.planner.PlanError("dependency_default_runtime_required")
        images = {r: resources.inspect("image", identity) for r, identity in value["images"].items()}
        if any(
            i.get("Id") != value["images"][r]
            or i.get("Architecture") != value["manifest"]["architecture"]
            or i.get("Os") != "linux"
            for r, i in images.items()
        ):
            raise checker.planner.PlanError("dependency_native_image_required")

        def current():
            deps = startup.snapshot(value, spec, receipt, images, True)
            startup.network(value, receipt, deps)
            startup.prior_receipt(
                checker.planner.decode(startup.read_file(root, "started.json", 0, 0, 0o600, 16384)),
                expected,
                receipt,
                deps,
            )
            return deps

        dependencies = current()
        report = helper(value, receipt, images["api"], "describe")
        if schema is None:
            return {
                **report,
                "schema": "private_schema_description_v1",
                "image_id": value["images"]["api"],
                "plan_manifest_sha256": expected,
                "execution_authorized": False,
            }
        if report["schema_sha256"] != schema:
            raise checker.planner.PlanError("schema_graph_changed")
        intent = bound_intent(value, expected, receipt, dependencies, schema)
        members = set(os.listdir(root))
        prior = None
        if "schema.json" in members and "schema-intent.json" not in members:
            raise checker.planner.PlanError("schema_intent_required")
        if "schema-intent.json" in members:
            old = checker.planner.decode(startup.read_file(root, "schema-intent.json", 0, 0, 0o600, 16384))
            if checker.planner.encoded(old) != checker.planner.encoded(intent):
                raise checker.planner.PlanError("schema_intent_changed")
        elif report["state"] != "fresh":
            raise checker.planner.PlanError("schema_existing_requires_review")
        if "schema.json" in members:
            prior = checker.planner.decode(startup.read_file(root, "schema.json", 0, 0, 0o600, 16384))
            if not any(
                checker.planner.encoded(prior) == checker.planner.encoded(result_receipt(intent, recovered))
                for recovered in (False, True)
            ):
                raise checker.planner.PlanError("schema_receipt_changed")
            if report["state"] != "current":
                raise checker.planner.PlanError("schema_recorded_state_changed")
        if report["state"] not in {"fresh", "current"}:
            raise checker.planner.PlanError("schema_existing_requires_review")
        if report["state"] == "fresh" and adopter.project_containers(
            checker.planner.composition(value["request"], value["images"])["name"]
        ):
            raise checker.planner.PlanError("schema_application_services_present")
        if "schema-intent.json" not in members:
            publish(root, "schema-intent.json", intent)
        recovered = report["state"] == "current"
        helper(value, receipt, images["api"], "verify_current" if recovered else "apply_fresh", schema)
        if {r: c["Id"] for r, c in current().items()} != {r: c["Id"] for r, c in dependencies.items()}:
            raise checker.planner.PlanError("schema_dependencies_changed_during_execution")
        result = prior or result_receipt(intent, recovered)
        if prior is None:
            publish(root, "schema.json", result)
        return {**result, "reused": prior is not None}
    finally:
        if lock is not None:
            os.close(lock)
        os.close(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--schema-sha256", help="Explicit approved digest from description; absence only describes")
    args = parser.parse_args()
    try:
        print(json.dumps(initialize(args.plan, args.expected_manifest_sha256, args.schema_sha256), sort_keys=True))
    except (checker.planner.PlanError, OSError, ValueError, TypeError) as error:
        print(
            str(error) if isinstance(error, checker.planner.PlanError) else "private_schema_initialization_failed",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
