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
            # P108: append role-authority qualification without changing the
            # original 440 schema/runtime cases or their expected outcomes.
            def authority_case(name, denied=False, unavailable=False):
                for entry in ("role", "role_command"):
                    started = time.monotonic()
                    result = application(entry=entry)
                    error = "job_application_role_unavailable" if unavailable else (
                        "job_application_role_elevated" if denied else None)
                    # Preserve the command's existing runtime-before-role order.
                    expected = dict(error=error, broker_calls=int(entry == "role_command"))
                    cases.append(dict(name="parameter_authority/" + name + "/" + entry,
                        passed=result == expected, expected=expected, observed=result,
                        seconds=time.monotonic() - started))

            def authority_catalog():
                return json.loads(admin("""SELECT pg_catalog.json_build_object(
                    'parameters',(SELECT pg_catalog.json_agg(pg_catalog.json_build_array(parname,paracl::pg_catalog.text) ORDER BY parname) FROM pg_catalog.pg_parameter_acl),
                    'roles',(SELECT pg_catalog.json_agg(pg_catalog.json_build_array(oid,rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolconfig) ORDER BY oid) FROM pg_catalog.pg_roles),
                    'memberships',(SELECT pg_catalog.json_agg(pg_catalog.json_build_array(roleid,member,grantor,admin_option,inherit_option,set_option) ORDER BY roleid,member,grantor) FROM pg_catalog.pg_auth_members),
                    'relation_acls',(SELECT pg_catalog.json_agg(pg_catalog.json_build_array(oid,relacl::pg_catalog.text) ORDER BY oid) FROM pg_catalog.pg_class WHERE relnamespace='public'::pg_catalog.regnamespace)
                    );"""))

            receipt["authority_baseline"] = authority_catalog()
            assert not receipt["authority_baseline"]["parameters"]
            assert all(row[1] is None for row in receipt["authority_baseline"]["relation_acls"])
            receipt["authority_profiles"] = []
            for value in ("origin", "local"):
                mode(value)
                authority_case("baseline_" + value)
            mode("origin")
            admin("""CREATE ROLE ri_cap_carrier NOLOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                CREATE ROLE ri_cap_bridge NOLOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                CREATE ROLE ri_cap_child NOLOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO ri_cap_child;""")

            def clear_authority():
                application("authority_switch", role="reset")
                admin("""REVOKE ALL PRIVILEGES ON PARAMETER session_replication_role FROM ri_application,ri_cap_carrier,ri_cap_child,PUBLIC;
                    REVOKE ri_cap_carrier FROM ri_application,ri_cap_bridge;
                    REVOKE ri_cap_bridge,ri_cap_child FROM ri_application;
                    DELETE FROM pg_catalog.pg_parameter_acl WHERE parname='session_replication_role';""")

            try:
                for privilege in ("SET", "ALTER SYSTEM"):
                    key = "set" if privilege == "SET" else "alter_system"
                    for profile in ("direct", "public", "inherited", "switch_only", "transitive",
                                    "session_only", "active_only", "unrelated"):
                        try:
                            grantee = {"direct":"ri_application", "public":"PUBLIC", "session_only":"ri_application",
                                       "active_only":"ri_cap_child"}.get(profile, "ri_cap_carrier")
                            admin("GRANT " + privilege + " ON PARAMETER session_replication_role TO " + grantee + ";")
                            if profile in {"inherited", "switch_only"}:
                                admin("GRANT ri_cap_carrier TO ri_application WITH INHERIT " + (
                                    "TRUE" if profile == "inherited" else "FALSE") + ", SET TRUE;")
                            elif profile == "transitive":
                                admin("GRANT ri_cap_carrier TO ri_cap_bridge WITH INHERIT FALSE, SET TRUE; GRANT ri_cap_bridge TO ri_application WITH INHERIT FALSE, SET TRUE;")
                            elif profile in {"session_only", "active_only"}:
                                admin("GRANT ri_cap_child TO ri_application WITH INHERIT FALSE, SET TRUE;")
                                application("authority_switch", role="ri_cap_child")
                            state = application("authority_state")
                            assert state["mode"] == "origin"
                            assert state["current_" + key] == (profile in {"direct", "public", "inherited", "active_only"})
                            assert state["session_" + key] == (profile in {"direct", "public", "inherited", "session_only"})
                            receipt["authority_profiles"].append(dict(privilege=privilege, profile=profile, state=state,
                                catalog=authority_catalog()))
                            authority_case(privilege + "/" + profile, denied=profile != "unrelated")
                        finally:
                            clear_authority()
                for variant in ("parameter_function", "membership_function", "both_functions", "operator", "combined"):
                    admin("CREATE TABLE public.authority_lookup_effect(marker pg_catalog.text); GRANT INSERT,SELECT ON public.authority_lookup_effect TO ri_application;")
                    try:
                        if variant in {"parameter_function", "both_functions", "combined"}:
                            admin("CREATE FUNCTION public.has_parameter_privilege(pg_catalog.oid,pg_catalog.text,pg_catalog.text) RETURNS pg_catalog.bool LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.authority_lookup_effect VALUES ('parameter'); RETURN false; END$$;")
                        if variant in {"membership_function", "both_functions", "combined"}:
                            admin("CREATE FUNCTION public.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text) RETURNS pg_catalog.bool LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.authority_lookup_effect VALUES ('membership'); RETURN false; END$$;")
                        if variant in {"operator", "combined"}:
                            admin("CREATE FUNCTION public.authority_equal(pg_catalog.name,pg_catalog.name) RETURNS pg_catalog.bool LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.authority_lookup_effect VALUES ('operator'); RETURN true; END$$; CREATE OPERATOR public.= (LEFTARG=pg_catalog.name,RIGHTARG=pg_catalog.name,PROCEDURE=public.authority_equal);")
                        application("authority_search_path", public_first=True)
                        authority_case("shadow_" + variant + "/healthy")
                        for privilege in ("SET", "ALTER SYSTEM"):
                            try:
                                admin("GRANT " + privilege + " ON PARAMETER session_replication_role TO ri_application;")
                                authority_case("shadow_" + variant + "/" + privilege, denied=True)
                            finally:
                                clear_authority()
                        assert admin("SELECT count(*) FROM public.authority_lookup_effect;").strip() == b"0"
                    finally:
                        application("authority_search_path", public_first=False)
                        if variant in {"parameter_function", "both_functions", "combined"}:
                            admin("DROP FUNCTION public.has_parameter_privilege(pg_catalog.oid,pg_catalog.text,pg_catalog.text);")
                        if variant in {"membership_function", "both_functions", "combined"}:
                            admin("DROP FUNCTION public.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text);")
                        if variant in {"operator", "combined"}:
                            admin("DROP OPERATOR public.= (pg_catalog.name,pg_catalog.name); DROP FUNCTION public.authority_equal(pg_catalog.name,pg_catalog.name);")
                        admin("DROP TABLE public.authority_lookup_effect;")
                receipt["authority_forged_lookup_side_effects"] = 0
                assert admin("SELECT proacl IS NULL FROM pg_catalog.pg_proc WHERE oid='pg_catalog.has_parameter_privilege(oid,text,text)'::pg_catalog.regprocedure;").strip() == b"t"
                try:
                    admin("REVOKE EXECUTE ON FUNCTION pg_catalog.has_parameter_privilege(pg_catalog.oid,pg_catalog.text,pg_catalog.text) FROM PUBLIC;")
                    authority_case("unavailable_lookup", unavailable=True)
                finally:
                    admin("GRANT EXECUTE ON FUNCTION pg_catalog.has_parameter_privilege(pg_catalog.oid,pg_catalog.text,pg_catalog.text) TO PUBLIC; UPDATE pg_catalog.pg_proc SET proacl=NULL WHERE oid='pg_catalog.has_parameter_privilege(oid,text,text)'::pg_catalog.regprocedure;")
                authority_case("restored_lookup")
            finally:
                clear_authority()
                admin("REVOKE SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public FROM ri_cap_child; DROP ROLE ri_cap_child,ri_cap_bridge,ri_cap_carrier; UPDATE pg_catalog.pg_class SET relacl=NULL WHERE relnamespace='public'::pg_catalog.regnamespace;")
            receipt["authority_restored"] = authority_catalog()
            assert receipt["authority_restored"] == receipt["authority_baseline"]
            assert application("replication_controls") == receipt["replication_baseline"]
            assert application("controls") == receipt["restored_controls"]
            assert application("snapshot") == baseline
            # P109: append checkpoint-role admission cases; all 510 original
            # schema/runtime/parameter cases and expectations remain unchanged.
            def checkpoint_case(name, denied=False, unavailable=False):
                for entry in ("role", "role_command"):
                    started = time.monotonic()
                    result = application(entry=entry)
                    error = "job_application_role_unavailable" if unavailable else (
                        "job_application_role_elevated" if denied else None)
                    expected = dict(error=error, broker_calls=int(entry == "role_command"))
                    cases.append(dict(name="checkpoint_authority/" + name + "/" + entry,
                        passed=result == expected, expected=expected, observed=result,
                        seconds=time.monotonic() - started))

            receipt["checkpoint_baseline"] = authority_catalog()
            receipt["checkpoint_denied_baseline"] = application("checkpoint_operation")
            assert receipt["checkpoint_denied_baseline"] == dict(status=None,sqlstate="42501")
            for value in ("origin", "local"):
                mode(value)
                checkpoint_case("baseline_" + value)
            mode("origin")
            admin("""CREATE ROLE ri_cap_carrier NOLOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                CREATE ROLE ri_cap_bridge NOLOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                CREATE ROLE ri_cap_child NOLOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO ri_cap_child;""")
            receipt["checkpoint_profiles"] = []

            def clear_checkpoint():
                application("checkpoint_switch", role="reset")
                admin("""REVOKE pg_checkpoint FROM ri_application,ri_cap_carrier,ri_cap_child;
                    REVOKE ri_cap_carrier FROM ri_application,ri_cap_bridge;
                    REVOKE ri_cap_bridge,ri_cap_child FROM ri_application;""")

            try:
                for profile in ("direct", "inherited", "switch_only", "transitive",
                                "session_only", "active_only", "options_disabled", "unrelated"):
                    try:
                        grantee = {"direct":"ri_application", "session_only":"ri_application",
                                   "active_only":"ri_cap_child"}.get(profile, "ri_cap_carrier")
                        admin("GRANT pg_checkpoint TO " + grantee + ";")
                        if profile in {"inherited", "switch_only", "options_disabled"}:
                            admin("GRANT ri_cap_carrier TO ri_application WITH INHERIT " + (
                                "TRUE" if profile == "inherited" else "FALSE") + ", SET " + (
                                "FALSE" if profile == "options_disabled" else "TRUE") + ";")
                        elif profile == "transitive":
                            admin("GRANT ri_cap_carrier TO ri_cap_bridge WITH INHERIT FALSE, SET TRUE; GRANT ri_cap_bridge TO ri_application WITH INHERIT FALSE, SET TRUE;")
                        elif profile in {"session_only", "active_only"}:
                            admin("GRANT ri_cap_child TO ri_application WITH INHERIT FALSE, SET TRUE;")
                            application("checkpoint_switch", role="ri_cap_child")
                        state = application("checkpoint_state")
                        assert state["current_member"] == (profile not in {"session_only", "unrelated"})
                        assert state["session_member"] == (profile != "unrelated")
                        assert state["current_usage"] == (profile in {"direct", "inherited", "active_only"})
                        assert state["session_usage"] == (profile in {"direct", "inherited", "session_only"})
                        assert state["state"]["mode"] == "origin"
                        assert not any(state["state"][k] for k in (
                            "current_set", "current_alter_system", "session_set", "session_alter_system"))
                        operation = application("checkpoint_operation")
                        assert operation == (dict(status="CHECKPOINT",sqlstate=None) if state["current_usage"]
                                             else dict(status=None,sqlstate="42501"))
                        checkpoint_case(profile, denied=profile != "unrelated")
                        switched = None
                        if profile in {"switch_only", "transitive"}:
                            switched = application("checkpoint_switch", role="ri_cap_carrier")
                            assert switched["current_usage"] is True
                            assert application("checkpoint_operation") == dict(status="CHECKPOINT",sqlstate=None)
                        receipt["checkpoint_profiles"].append(dict(profile=profile,state=state,
                            operation=operation,switched=switched,catalog=authority_catalog()))
                    finally:
                        clear_checkpoint()
                for variant in ("catalog", "membership_function", "operator", "combined"):
                    admin("CREATE TABLE public.checkpoint_lookup_effect(marker pg_catalog.text); GRANT INSERT,SELECT ON public.checkpoint_lookup_effect TO ri_application;")
                    try:
                        if variant in {"catalog", "combined"}:
                            admin("CREATE VIEW public.pg_roles AS SELECT oid,rolname,false AS rolsuper,false AS rolcreatedb,false AS rolcreaterole,false AS rolreplication,false AS rolbypassrls FROM pg_catalog.pg_roles WHERE rolname<>'pg_checkpoint'; GRANT SELECT ON public.pg_roles TO PUBLIC;")
                        if variant in {"membership_function", "combined"}:
                            admin("CREATE FUNCTION public.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text) RETURNS pg_catalog.bool LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.checkpoint_lookup_effect VALUES ('membership'); RETURN false; END$$;")
                        if variant in {"operator", "combined"}:
                            admin("CREATE FUNCTION public.checkpoint_equal(pg_catalog.name,pg_catalog.name) RETURNS pg_catalog.bool LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.checkpoint_lookup_effect VALUES ('operator'); RETURN false; END$$; CREATE OPERATOR public.= (LEFTARG=pg_catalog.name,RIGHTARG=pg_catalog.name,PROCEDURE=public.checkpoint_equal);")
                        application("authority_search_path", public_first=True)
                        checkpoint_case("shadow_" + variant + "/healthy")
                        try:
                            admin("GRANT pg_checkpoint TO ri_application;")
                            checkpoint_case("shadow_" + variant + "/direct", denied=True)
                            admin("GRANT ri_cap_child TO ri_application WITH INHERIT FALSE, SET TRUE;")
                            application("checkpoint_switch", role="ri_cap_child")
                            checkpoint_case("shadow_" + variant + "/session_only", denied=True)
                        finally:
                            clear_checkpoint()
                        assert admin("SELECT count(*) FROM public.checkpoint_lookup_effect;").strip() == b"0"
                    finally:
                        application("authority_search_path", public_first=False)
                        if variant in {"catalog", "combined"}:
                            admin("DROP VIEW public.pg_roles;")
                        if variant in {"membership_function", "combined"}:
                            admin("DROP FUNCTION public.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text);")
                        if variant in {"operator", "combined"}:
                            admin("DROP OPERATOR public.= (pg_catalog.name,pg_catalog.name); DROP FUNCTION public.checkpoint_equal(pg_catalog.name,pg_catalog.name);")
                        admin("DROP TABLE public.checkpoint_lookup_effect;")
                receipt["checkpoint_forged_lookup_side_effects"] = 0
                assert admin("SELECT proacl IS NULL FROM pg_catalog.pg_proc WHERE oid='pg_catalog.pg_has_role(name,oid,text)'::pg_catalog.regprocedure;").strip() == b"t"
                try:
                    admin("REVOKE EXECUTE ON FUNCTION pg_catalog.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text) FROM PUBLIC;")
                    checkpoint_case("unavailable_lookup", unavailable=True)
                finally:
                    admin("GRANT EXECUTE ON FUNCTION pg_catalog.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text) TO PUBLIC; UPDATE pg_catalog.pg_proc SET proacl=NULL WHERE oid='pg_catalog.pg_has_role(name,oid,text)'::pg_catalog.regprocedure;")
                checkpoint_case("restored_lookup")
            finally:
                clear_checkpoint()
                admin("REVOKE SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public FROM ri_cap_child; DROP ROLE ri_cap_child,ri_cap_bridge,ri_cap_carrier; UPDATE pg_catalog.pg_class SET relacl=NULL WHERE relnamespace='public'::pg_catalog.regnamespace;")
            receipt["checkpoint_restored"] = authority_catalog()
            assert receipt["checkpoint_restored"] == receipt["checkpoint_baseline"]
            assert application("checkpoint_operation") == receipt["checkpoint_denied_baseline"]
            checkpoint_case("restored_authority")
            assert application("replication_controls") == receipt["replication_baseline"]
            assert application("controls") == receipt["restored_controls"]
            assert application("snapshot") == baseline
            admin("""CREATE SCHEMA maintain_fixture;
                CREATE TABLE maintain_fixture.protected(id integer PRIMARY KEY, payload text);
                INSERT INTO maintain_fixture.protected VALUES (1,'unchanged');
                GRANT USAGE ON SCHEMA maintain_fixture TO ri_application;
            """)
            def maintain_target():
                return json.loads(admin("""SELECT pg_catalog.json_build_object(
                    'owner',pg_catalog.pg_get_userbyid(c.relowner),
                    'acl',c.relacl::pg_catalog.text,
                    'rows',(SELECT pg_catalog.json_agg(t ORDER BY id) FROM maintain_fixture.protected t))
                    FROM pg_catalog.pg_class c WHERE c.oid='maintain_fixture.protected'::pg_catalog.regclass;
                """))

            receipt["maintain_target_baseline"] = maintain_target()
            assert receipt["maintain_target_baseline"] == dict(owner="postgres",acl=None,
                rows=[dict(id=1,payload="unchanged")])
            admin("""CREATE FUNCTION maintain_fixture.lock_probe() RETURNS text LANGUAGE plpgsql AS $$
                BEGIN
                    LOCK TABLE maintain_fixture.protected IN ACCESS SHARE MODE NOWAIT;
                    RETURN 'LOCK TABLE';
                EXCEPTION WHEN lock_not_available THEN RETURN SQLSTATE;
                END$$;
                REVOKE ALL ON FUNCTION maintain_fixture.lock_probe() FROM PUBLIC;
            """)
            receipt["maintain_lock_observations"] = []

            def maintain_operation():
                operation = application("maintain_lock")
                if operation["status"] is None:
                    assert operation == dict(status=None,sqlstate="42501")
                    return operation
                assert operation["status"] == "LOCK TABLE" and operation["sqlstate"] is None
                pid = operation["backend_pid"]
                assert isinstance(pid,int) and pid > 0
                try:
                    observed = json.loads(admin("""SELECT pg_catalog.json_build_object(
                        'granted',(SELECT count(*) FROM pg_catalog.pg_locks WHERE pid=""" + str(pid) + """
                            AND relation='maintain_fixture.protected'::pg_catalog.regclass
                            AND mode='AccessExclusiveLock' AND granted),
                        'conflict_sqlstate',maintain_fixture.lock_probe());"""))
                    assert observed == dict(granted=1,conflict_sqlstate="55P03")
                finally:
                    assert application("maintain_unlock") == dict(released=True)
                assert admin("SELECT maintain_fixture.lock_probe();").strip() == b"LOCK TABLE"
                assert admin("SELECT count(*) FROM pg_catalog.pg_locks WHERE pid=" + str(pid) +
                    " AND relation='maintain_fixture.protected'::pg_catalog.regclass;").strip() == b"0"
                assert maintain_target() == receipt["maintain_target_baseline"]
                receipt["maintain_lock_observations"].append(dict(**observed,transaction_end_released=True))
                return dict(status="LOCK TABLE",sqlstate=None)

            # P110: append maintenance-role admission cases; all 560 original
            # schema/runtime/authority cases and expectations remain unchanged.
            def maintain_case(name, denied=False, unavailable=False):
                for entry in ("role", "role_command"):
                    started = time.monotonic()
                    result = application(entry=entry)
                    error = "job_application_role_unavailable" if unavailable else (
                        "job_application_role_elevated" if denied else None)
                    expected = dict(error=error, broker_calls=int(entry == "role_command"))
                    cases.append(dict(name="maintain_authority/" + name + "/" + entry,
                        passed=result == expected, expected=expected, observed=result,
                        seconds=time.monotonic() - started))

            receipt["maintain_baseline"] = authority_catalog()
            receipt["maintain_denied_baseline"] = maintain_operation()
            assert receipt["maintain_denied_baseline"] == dict(status=None,sqlstate="42501")
            for value in ("origin", "local"):
                mode(value)
                maintain_case("baseline_" + value)
            mode("origin")
            admin("""CREATE ROLE ri_cap_carrier NOLOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                CREATE ROLE ri_cap_bridge NOLOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                CREATE ROLE ri_cap_child NOLOGIN NOCREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO ri_cap_child;
                GRANT USAGE ON SCHEMA maintain_fixture TO ri_cap_child,ri_cap_carrier,ri_cap_bridge;""")
            receipt["maintain_profiles"] = []

            def clear_maintain():
                application("maintain_switch", role="reset")
                admin("""REVOKE pg_maintain FROM ri_application,ri_cap_carrier,ri_cap_child;
                    REVOKE ri_cap_carrier FROM ri_application,ri_cap_bridge;
                    REVOKE ri_cap_bridge,ri_cap_child FROM ri_application;""")

            try:
                for profile in ("direct", "inherited", "switch_only", "transitive",
                                "session_only", "active_only", "options_disabled", "unrelated"):
                    try:
                        grantee = {"direct":"ri_application", "session_only":"ri_application",
                                   "active_only":"ri_cap_child"}.get(profile, "ri_cap_carrier")
                        admin("GRANT pg_maintain TO " + grantee + ";")
                        if profile in {"inherited", "switch_only", "options_disabled"}:
                            admin("GRANT ri_cap_carrier TO ri_application WITH INHERIT " + (
                                "TRUE" if profile == "inherited" else "FALSE") + ", SET " + (
                                "FALSE" if profile == "options_disabled" else "TRUE") + ";")
                        elif profile == "transitive":
                            admin("GRANT ri_cap_carrier TO ri_cap_bridge WITH INHERIT FALSE, SET TRUE; GRANT ri_cap_bridge TO ri_application WITH INHERIT FALSE, SET TRUE;")
                        elif profile in {"session_only", "active_only"}:
                            admin("GRANT ri_cap_child TO ri_application WITH INHERIT FALSE, SET TRUE;")
                            application("maintain_switch", role="ri_cap_child")
                        state = application("maintain_state")
                        assert state["current_member"] == (profile not in {"session_only", "unrelated"})
                        assert state["session_member"] == (profile != "unrelated")
                        assert state["current_usage"] == (profile in {"direct", "inherited", "active_only"})
                        assert state["session_usage"] == (profile in {"direct", "inherited", "session_only"})
                        assert state["state"]["mode"] == "origin"
                        assert not any(state["state"][k] for k in (
                            "current_set", "current_alter_system", "session_set", "session_alter_system"))
                        operation = maintain_operation()
                        assert operation == (dict(status="LOCK TABLE",sqlstate=None) if state["current_usage"]
                                             else dict(status=None,sqlstate="42501"))
                        maintain_case(profile, denied=profile != "unrelated")
                        switched = None
                        if profile in {"switch_only", "transitive"}:
                            switched = application("maintain_switch", role="ri_cap_carrier")
                            assert switched["current_usage"] is True
                            assert maintain_operation() == dict(status="LOCK TABLE",sqlstate=None)
                        receipt["maintain_profiles"].append(dict(profile=profile,state=state,
                            operation=operation,switched=switched,catalog=authority_catalog()))
                    finally:
                        clear_maintain()
                for variant in ("catalog", "membership_function", "operator", "combined"):
                    admin("CREATE TABLE public.maintain_lookup_effect(marker pg_catalog.text); GRANT INSERT,SELECT ON public.maintain_lookup_effect TO ri_application;")
                    try:
                        if variant in {"catalog", "combined"}:
                            admin("CREATE VIEW public.pg_roles AS SELECT oid,rolname,false AS rolsuper,false AS rolcreatedb,false AS rolcreaterole,false AS rolreplication,false AS rolbypassrls FROM pg_catalog.pg_roles WHERE rolname<>'pg_maintain'; GRANT SELECT ON public.pg_roles TO PUBLIC;")
                        if variant in {"membership_function", "combined"}:
                            admin("CREATE FUNCTION public.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text) RETURNS pg_catalog.bool LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.maintain_lookup_effect VALUES ('membership'); RETURN false; END$$;")
                        if variant in {"operator", "combined"}:
                            admin("CREATE FUNCTION public.maintain_equal(pg_catalog.name,pg_catalog.name) RETURNS pg_catalog.bool LANGUAGE plpgsql AS $$BEGIN INSERT INTO public.maintain_lookup_effect VALUES ('operator'); RETURN false; END$$; CREATE OPERATOR public.= (LEFTARG=pg_catalog.name,RIGHTARG=pg_catalog.name,PROCEDURE=public.maintain_equal);")
                        application("authority_search_path", public_first=True)
                        maintain_case("shadow_" + variant + "/healthy")
                        try:
                            admin("GRANT pg_maintain TO ri_application;")
                            maintain_case("shadow_" + variant + "/direct", denied=True)
                            admin("GRANT ri_cap_child TO ri_application WITH INHERIT FALSE, SET TRUE;")
                            application("maintain_switch", role="ri_cap_child")
                            maintain_case("shadow_" + variant + "/session_only", denied=True)
                        finally:
                            clear_maintain()
                        assert admin("SELECT count(*) FROM public.maintain_lookup_effect;").strip() == b"0"
                    finally:
                        application("authority_search_path", public_first=False)
                        if variant in {"catalog", "combined"}:
                            admin("DROP VIEW public.pg_roles;")
                        if variant in {"membership_function", "combined"}:
                            admin("DROP FUNCTION public.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text);")
                        if variant in {"operator", "combined"}:
                            admin("DROP OPERATOR public.= (pg_catalog.name,pg_catalog.name); DROP FUNCTION public.maintain_equal(pg_catalog.name,pg_catalog.name);")
                        admin("DROP TABLE public.maintain_lookup_effect;")
                receipt["maintain_forged_lookup_side_effects"] = 0
                assert admin("SELECT proacl IS NULL FROM pg_catalog.pg_proc WHERE oid='pg_catalog.pg_has_role(name,oid,text)'::pg_catalog.regprocedure;").strip() == b"t"
                try:
                    admin("REVOKE EXECUTE ON FUNCTION pg_catalog.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text) FROM PUBLIC;")
                    maintain_case("unavailable_lookup", unavailable=True)
                finally:
                    admin("GRANT EXECUTE ON FUNCTION pg_catalog.pg_has_role(pg_catalog.name,pg_catalog.oid,pg_catalog.text) TO PUBLIC; UPDATE pg_catalog.pg_proc SET proacl=NULL WHERE oid='pg_catalog.pg_has_role(name,oid,text)'::pg_catalog.regprocedure;")
                maintain_case("restored_lookup")
            finally:
                clear_maintain()
                admin("REVOKE SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public FROM ri_cap_child; REVOKE USAGE ON SCHEMA maintain_fixture FROM ri_cap_child,ri_cap_carrier,ri_cap_bridge; DROP ROLE ri_cap_child,ri_cap_bridge,ri_cap_carrier; UPDATE pg_catalog.pg_class SET relacl=NULL WHERE relnamespace='public'::pg_catalog.regnamespace;")
            receipt["maintain_restored"] = authority_catalog()
            assert receipt["maintain_restored"] == receipt["maintain_baseline"]
            assert maintain_operation() == receipt["maintain_denied_baseline"]
            maintain_case("restored_authority")
            assert application("replication_controls") == receipt["replication_baseline"]
            assert application("controls") == receipt["restored_controls"]
            assert application("snapshot") == baseline
            receipt["maintain_target_restored"] = maintain_target()
            assert receipt["maintain_target_restored"] == receipt["maintain_target_baseline"]
            admin("DROP SCHEMA maintain_fixture CASCADE;")
            assert admin("SELECT pg_catalog.to_regnamespace('maintain_fixture') IS NULL;").strip() == b"t"
            receipt["maintain_fixture_removed"] = True
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
    if receipt["failed"] or len(cases) != 610:
        raise SystemExit("RI-trigger qualification failed; retain original reports.")
    print(json.dumps(dict(passed=receipt["passed"], failed=0, owned_cleanup="passed", actual_tls=False)))


if __name__ == "__main__":
    main()
