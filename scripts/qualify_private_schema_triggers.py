#!/usr/bin/env python3
"""Qualify RI-trigger guards in a separately owned PostgreSQL 17 fixture.

The host controller alone injects privileged faults using docker exec. The
application process has only its non-elevated login, never admin credentials or
a Docker socket. This is a bounded catalog/integrity qualifier, not TLS proof.
"""

import argparse
import json
import re
import secrets
import selectors
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-image", required=True)
    parser.add_argument("--runner-image", required=True)
    parser.add_argument("--source", default=str(ROOT))
    parser.add_argument("--reports", default="test-reports/postgresql/ri-triggers")
    args = parser.parse_args()
    for image in (args.postgres_image, args.runner_image):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            parser.error("Exact local image IDs are required; images are never pulled.")
    source = Path(args.source).resolve()
    reports = (ROOT / args.reports).resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        parser.error("Reports must be inside ignored test-reports.")
    reports.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    administrator_password, application_password = secrets.token_hex(32), secrets.token_hex(32)
    network, database, runner = ["declarai-ri-" + token + "-" + role for role in ("net", "db", "app")]
    created, cases = [], []
    process = None
    receipt = dict(scope="owned_catalog_integrity_only", actual_tls=False, customer_installation_modified=False,
                   application_role="NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS",
                   administrator_boundary="host controller docker exec; absent from application process",
                   images=dict(postgres=args.postgres_image, runner=args.runner_image))

    def command(arguments, sql=None):
        result = subprocess.run(["docker", *arguments], input=sql, capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError("owned_fixture_command_failed")
        return result.stdout

    def admin(sql):
        return command(["exec", "-i", database, "psql", "-U", "postgres", "-d", "ri_fixture",
                        "-v", "ON_ERROR_STOP=1", "-At"], sql.encode())

    def receive():
        selector = selectors.DefaultSelector()
        try:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(120):
                raise RuntimeError("application_response_timeout")
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("application_process_stopped")
            return json.loads(line)
        finally:
            selector.close()

    def application(action="check", **kwargs):
        process.stdin.write(json.dumps(dict(action=action, **kwargs)) + "\n")
        process.stdin.flush()
        response = receive()
        if response.get("ok") is not True:
            raise RuntimeError("application_qualification_failed")
        return response["result"]

    def case(name, entry, rejected, unavailable=False):
        started = time.monotonic()
        result = application(entry=entry)
        expected = dict(error="job_schema_invalid" if rejected else None,
                        broker_calls=0 if rejected or entry == "schema" else 1)
        if unavailable:
            expected = dict(error="database_error" if entry == "schema" else "job_storage_unavailable", broker_calls=0)
        cases.append(dict(name=name + "/" + entry, passed=result == expected,
                          expected=expected, observed=result, seconds=time.monotonic() - started))

    def check_all(name, rejected, unavailable=False):
        for entry in ("schema", "runtime", "command"):
            case(name, entry, rejected, unavailable)

    try:
        command(["network", "create", "--internal", network])
        created.append(("network", network))
        # Alpine's selected native PostgreSQL 17 profile uses postgres UID/GID 70.
        command(["run", "-d", "--name", database, "--pull", "never", "--network", network,
                 "--network-alias", "postgres", "--read-only", "--user", "70:70", "--cap-drop", "ALL",
                 "--security-opt", "no-new-privileges", "--cpus", "1", "--memory", "512m", "--pids-limit", "128",
                 "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=134217728,uid=70,gid=70,mode=700",
                 "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16777216,uid=70,gid=70,mode=700",
                 "--tmpfs", "/tmp:rw,noexec,nosuid,size=16777216,uid=70,gid=70,mode=700",
                 "-e", "POSTGRES_PASSWORD=" + administrator_password, "-e", "POSTGRES_DB=ri_fixture", args.postgres_image])
        created.append(("container", database))
        deadline = time.monotonic() + 30
        while subprocess.run(["docker", "exec", database, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "ri_fixture"], capture_output=True, timeout=5).returncode:
            if time.monotonic() >= deadline:
                raise RuntimeError("owned_postgresql_start_timeout")
            time.sleep(.5)
        admin("CREATE ROLE ri_application LOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '" + application_password + "'; ALTER DATABASE ri_fixture OWNER TO ri_application;")
        env = dict(PYTHONDONTWRITEBYTECODE="1", DJANGO_SETTINGS_MODULE="backend.settings", PROMETA_DISABLE="1",
                   OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2", DECLARAI_RUNTIME_PROFILE="development",
                   DECLARAI_DB_ENGINE="postgresql", DECLARAI_DB_HOST="postgres", DECLARAI_DB_NAME="ri_fixture",
                   DECLARAI_DB_USER="ri_application", DECLARAI_DB_PASSWORD=application_password, DECLARAI_DB_SSLMODE="disable")
        docker = ["docker", "run", "--rm", "-i", "--name", runner, "--pull", "never", "--network", network,
                  "--read-only", "--user", "10001:10001", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                  "--cpus", "2", "--memory", "2g", "--pids-limit", "256", "--tmpfs", "/tmp:rw,noexec,nosuid,size=268435456",
                  "-v", str(source) + ":/work:ro", "-v", str(ROOT / "backend/tests/qualification/private_schema_triggers.py") + ":/harness.py:ro",
                  "-w", "/work/backend", "--entrypoint", "python"]
        for key, value in env.items():
            docker += ["-e", key + "=" + value]
        docker += [args.runner_image, "-u", "-c", "import sys; sys.path.insert(0, '/work/backend'); exec(compile(open('/harness.py').read(), '/harness.py', 'exec'))"]
        with (reports / "application.log").open("w") as log:
            process = subprocess.Popen(docker, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
            ready = receive()
            assert ready["ready"] is True
            baseline = ready["snapshot"]
            receipt["baseline"] = ready
            assert baseline["migrations"] == 31 and baseline["internal_triggers"] == 152
            assert len(baseline["triggers"]) == 4
            admin('CREATE FUNCTION public."RI_FKey_check_ins"() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END$$; CREATE TRIGGER ri_qual_fixture AFTER INSERT ON public.access_control_projectmembership FOR EACH ROW WHEN (NEW.actor_id > 0) EXECUTE FUNCTION public."RI_FKey_check_ins"();')
            check_all("healthy", False)
            for trigger in baseline["triggers"]:
                oid, table, name = trigger[:3]
                assert re.fullmatch(r"[a-z_]+", table) and re.fullmatch(r"RI_ConstraintTrigger_[ac]_[0-9]+", name)
                role = trigger[-1]
                for mode, sql_mode in (("D", "DISABLE"), ("R", "ENABLE REPLICA"), ("A", "ENABLE ALWAYS")):
                    try:
                        admin(f'ALTER TABLE public.{table} {sql_mode} TRIGGER "{name}";')
                        check_all(role + "/mode_" + mode, mode != "A")
                        if role == "RI_FKey_check_ins" and mode == "D":
                            receipt["committed_orphan"] = application("orphan")
                    finally:
                        admin(f'ALTER TABLE public.{table} ENABLE TRIGGER "{name}";')
                try:
                    admin(f"UPDATE pg_catalog.pg_trigger SET tgname='arbitrary_ri_{oid}' WHERE oid={oid};")
                    check_all(role + "/arbitrary_name", False)
                finally:
                    admin(f"UPDATE pg_catalog.pg_trigger SET tgname='{name}' WHERE oid={oid};")
                # Direct catalog faults model privileged corruption, not valid
                # migration DDL or authority available to the application owner.
                faults = {
                    "tgrelid": "'public.django_session'::pg_catalog.regclass", "tgconstraint": "0", "tgconstrrelid": "0", "tgconstrindid": "0", "tgparentid": "1",
                    "tgisinternal": "false", "tgtype": "0", "tgdeferrable": "false", "tginitdeferred": "false",
                    "tgnargs": "1", "tgattr": "'1'::pg_catalog.int2vector", "tgargs": "'x'::pg_catalog.bytea",
                    "tgfoid": "'pg_catalog.suppress_redundant_updates_trigger()'::pg_catalog.regprocedure::pg_catalog.oid",
                    "tgfoid_namespace": "'public.\"RI_FKey_check_ins\"()'::pg_catalog.regprocedure::pg_catalog.oid",
                    "tgqual": "(SELECT tgqual FROM pg_catalog.pg_trigger WHERE tgname='ri_qual_fixture')",
                }
                fields = dict(zip(("oid", "tgrelid", "tgname", "tgfoid", "tgtype", "tgenabled", "tgisinternal", "tgconstrrelid",
                                   "tgconstrindid", "tgconstraint", "tgdeferrable", "tginitdeferred", "tgnargs", "tgattr", "tgqual", "tgargs", "tgparentid"), trigger[:-1]))
                for label, value in faults.items():
                    field = "tgfoid" if label == "tgfoid_namespace" else label
                    original = fields[field]
                    restore = ("true" if original else "false") if type(original) is bool else str(original)
                    if field in {"tgattr", "tgargs"}:
                        assert original in {"", "\\x"}
                        restore = "''::pg_catalog." + ("int2vector" if field == "tgattr" else "bytea")
                    if field == "tgrelid":
                        restore = "'public." + table + "'::pg_catalog.regclass"
                    if field == "tgqual":
                        restore = "NULL"
                    try:
                        admin(f"UPDATE pg_catalog.pg_trigger SET {field}={value} WHERE oid={oid};")
                        check_all(role + "/" + label, True)
                    finally:
                        admin(f"UPDATE pg_catalog.pg_trigger SET {field}={restore} WHERE oid={oid};")
                assert application("snapshot") == baseline
            admin('DROP TRIGGER ri_qual_fixture ON public.access_control_projectmembership; DROP FUNCTION public."RI_FKey_check_ins"();')
            # Every required FK's four roles must be observed, not just the
            # representative membership FK used for the detailed fault matrix.
            for oid, table, name in baseline["all_internal"]:
                assert re.fullmatch(r"[a-z_]+", table) and re.fullmatch(r"RI_ConstraintTrigger_[ac]_[0-9]+", name)
                try:
                    admin(f'ALTER TABLE public.{table} DISABLE TRIGGER "{name}";')
                    case("each_required_role/" + table + "/" + str(oid), "schema", True)
                finally:
                    admin(f'ALTER TABLE public.{table} ENABLE TRIGGER "{name}";')
            for table in ("access_control_projectmembership", "auth_user"):
                try:
                    admin(f"UPDATE pg_catalog.pg_class SET relhastriggers=false WHERE oid='public.{table}'::pg_catalog.regclass;")
                    check_all("relation_trigger_flag/" + table, True)
                finally:
                    admin(f"UPDATE pg_catalog.pg_class SET relhastriggers=true WHERE oid='public.{table}'::pg_catalog.regclass;")
            receipt["restored"] = application("snapshot")
            assert receipt["restored"] == baseline
            receipt["restored_controls"] = application("controls")
            check_all("restored_healthy", False)
            # P107: preserve the complete P106 matrix above; append physical
            # current-session, default-disagreement and namespace regressions.
            receipt["replication_baseline"] = application("replication_controls")
            receipt["replication_states"] = []

            def mode(value):
                assert value in {"origin", "local", "replica"}
                try:
                    admin("ALTER ROLE ri_application SET session_replication_role TO " + value + ";")
                    state = application("reconnect")
                    assert state["mode"] == value and state["can_set"] is False
                finally:
                    admin("ALTER ROLE ri_application RESET session_replication_role;")
                state = application("state")
                assert state["mode"] == value and state["login_default"] is None
                receipt["replication_states"].append(state)
                return state

            for value in ("origin", "local", "replica"):
                mode(value)
                check_all("replication/current_" + value + "_after_default_reset", value == "replica")
                if value == "replica":
                    receipt["replication_committed_orphan"] = application("orphan")
                else:
                    assert application("controls") == receipt["restored_controls"]
                assert application("snapshot") == baseline
            for value in ("origin", "local"):
                mode(value)
                try:
                    admin("ALTER ROLE ri_application SET session_replication_role TO replica;")
                    state = application("state")
                    assert state["mode"] == value and state["login_default"] == ["session_replication_role=replica"]
                    check_all("replication/active_" + value + "_default_replica", False)
                finally:
                    admin("ALTER ROLE ri_application RESET session_replication_role;")
            for variant in ("function", "operator", "both"):
                admin("CREATE TABLE public.replication_lookup_effect(marker pg_catalog.text); GRANT INSERT,SELECT ON public.replication_lookup_effect TO ri_application;")
                try:
                    if variant in {"function", "both"}:
                        admin("CREATE FUNCTION public.current_setting(pg_catalog.text) RETURNS pg_catalog.text LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.replication_lookup_effect VALUES ('function'); RETURN 'origin'; END$$;")
                    if variant in {"operator", "both"}:
                        admin("CREATE FUNCTION public.replication_equal(pg_catalog.text,pg_catalog.text) RETURNS pg_catalog.bool LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.replication_lookup_effect VALUES ('operator'); RETURN true; END$$; CREATE OPERATOR public.= (LEFTARG=pg_catalog.text,RIGHTARG=pg_catalog.text,PROCEDURE=public.replication_equal);")
                    for value in ("origin", "local", "replica"):
                        mode(value)
                        application("search_path", public_first=True)
                        check_all("replication/shadow_" + variant + "/" + value, value == "replica")
                        assert admin("SELECT count(*) FROM public.replication_lookup_effect;").strip() == b"0"
                finally:
                    application("search_path", public_first=False)
                    if variant in {"function", "both"}:
                        admin("DROP FUNCTION public.current_setting(pg_catalog.text);")
                    if variant in {"operator", "both"}:
                        admin("DROP OPERATOR public.= (pg_catalog.text,pg_catalog.text); DROP FUNCTION public.replication_equal(pg_catalog.text,pg_catalog.text);")
                    admin("DROP TABLE public.replication_lookup_effect;")
            receipt["replication_forged_lookup_side_effects"] = 0
            mode("origin")
            assert admin("SELECT proacl IS NULL FROM pg_catalog.pg_proc WHERE oid='pg_catalog.current_setting(text)'::pg_catalog.regprocedure;").strip() == b"t"
            try:
                # A genuine PostgreSQL permission failure, not a fabricated GUC
                # response; restore the original NULL ACL after this fault.
                admin("REVOKE EXECUTE ON FUNCTION pg_catalog.current_setting(pg_catalog.text) FROM PUBLIC;")
                check_all("replication/unavailable_lookup", True, unavailable=True)
            finally:
                admin("GRANT EXECUTE ON FUNCTION pg_catalog.current_setting(pg_catalog.text) TO PUBLIC; UPDATE pg_catalog.pg_proc SET proacl=NULL WHERE oid='pg_catalog.current_setting(text)'::pg_catalog.regprocedure;")
            check_all("replication/restored_lookup", False)
            receipt["replication_restored"] = application("replication_controls")
            assert receipt["replication_baseline"] == receipt["replication_restored"]
            assert application("controls") == receipt["restored_controls"]
            assert application("snapshot") == baseline
            process.stdin.close()
            assert process.wait(timeout=30) == 0
            process = None
    finally:
        if process is not None:
            subprocess.run(["docker", "rm", "-f", runner], capture_output=True, timeout=30, check=False)
            process.wait(timeout=30)
        cleanup = []
        for resource, name in reversed(created):
            command([resource, "rm", *(["--force", "--volumes"] if resource == "container" else []), name])
            cleanup.append(name)
        receipt.update(cases=cases, passed=sum(c["passed"] for c in cases), failed=sum(not c["passed"] for c in cases),
                       cleanup=dict(owned_resources_removed=cleanup, published_ports=False))
        (reports / "qualification.json").write_text(json.dumps(receipt, indent=2) + "\n")
        suite = ET.Element("testsuite", name="private_schema_ri_triggers", tests=str(len(cases)), failures=str(receipt["failed"]), errors="0", skipped="0")
        for result in cases:
            case_xml = ET.SubElement(suite, "testcase", classname="private_schema_ri_triggers", name=result["name"], time=str(result["seconds"]))
            if not result["passed"]:
                ET.SubElement(case_xml, "failure", message="unexpected startup evidence").text = json.dumps(result)
        ET.ElementTree(suite).write(reports / "qualification.xml", encoding="unicode")
    if receipt["failed"] or len(cases) != 440:
        raise SystemExit("RI-trigger qualification failed; retain original reports.")
    print(json.dumps(dict(passed=receipt["passed"], failed=0, owned_cleanup="passed", actual_tls=False)))


if __name__ == "__main__":
    main()
