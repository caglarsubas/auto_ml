#!/usr/bin/env python3
"""Qualify the real dependency controller on a fresh, owned Linux host root."""

import argparse
import json
import os
import secrets
import subprocess
import sys
import uuid
from pathlib import Path

import private_dependency_start as startup
from qualify_private_installation_resources import fixture_plan

ROOT = Path(__file__).resolve().parents[1]


def host_case(plan, expected, parent):
    value = startup.checker.verify(plan, expected)
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or parent.parent != Path("/srv")
        or not startup.resources.re.fullmatch(r"declarai-p37-[0-9a-f]{32}", parent.name)
        or value["request"]["root"] != str(parent / "installation")
    ):
        raise startup.checker.planner.PlanError("dependency_start_fixture_scope_required")
    initialized, prepared = None, None
    other = None
    redactions = []

    def command(args, data=None):
        result = subprocess.run(
            [*startup.resources.PREFIX, *args], input=data, capture_output=True, timeout=60, check=False
        )
        if result.returncode:
            detail = (result.stdout + result.stderr).decode(errors="replace")
            for secret in redactions:
                detail = detail.replace(secret, "[synthetic-secret-redacted]")
            print(json.dumps({"fixture_command": args[:3], "diagnostic": detail[:8000]}), file=sys.stderr)
            raise startup.checker.planner.PlanError("dependency_start_fixture_command_failed")
        return result.stdout

    def delivery(path, files):
        path.mkdir(mode=0o700)
        os.chown(path, 10001, 10001)
        for group in {p.split("/")[0] for p in files}:
            child = path / group
            child.mkdir(mode=0o700)
            os.chown(child, 10001, 10001)
        for name, data in files.items():
            child = path / name
            child.write_bytes(data)
            child.chmod(0o400)
            os.chown(child, 10001, 10001)

    try:
        cert, key = parent / "server.crt", parent / "server.key"
        result = subprocess.run(
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "1",
                "-subj",
                "/CN=postgres",
                "-addext",
                "subjectAltName=DNS:postgres,DNS:job-broker,DNS:cache,DNS:api.private.test",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode:
            raise startup.checker.planner.PlanError("dependency_start_fixture_certificate_failed")
        cache_cert, cache_key = parent / "cache.crt", parent / "cache.key"
        cache_tls = subprocess.run([
            "/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(cache_key), "-out", str(cache_cert), "-days", "1",
            "-subj", "/CN=cache", "-addext", "subjectAltName=DNS:cache",
            "-addext", "basicConstraints=critical,CA:TRUE",
        ], capture_output=True, timeout=30, check=False)
        if cache_tls.returncode:
            raise startup.checker.planner.PlanError("cache_fixture_certificate_failed")
        app_password, broker_password, owner_password, django, cache_password = [secrets.token_urlsafe(48) for _ in range(5)]
        redactions.extend([app_password, broker_password, owner_password, django, cache_password])
        app_files = {
            "app/django-key": django.encode(),
            "app/app-password": app_password.encode(),
            "app/job-broker-url": ("rediss://:" + broker_password + "@job-broker:6379/1").encode(),
            "app/postgres-ca.crt": cert.read_bytes(),
            "app/job-ca.crt": cert.read_bytes(),
            "app/cache-url": ("rediss://:" + cache_password + "@cache:6379/0").encode(),
            "app/cache-ca.crt": cache_cert.read_bytes(),
            "tls/tls.crt": cert.read_bytes(),
            "tls/tls.key": key.read_bytes(),
        }
        delivery(parent / "app-delivery", app_files)
        initialized = startup.preparation.initializer.initialize(plan, expected, parent / "app-delivery")
        startup.resources.prepare(plan, expected)
        dep_files = {
            role + "/" + name: cert.read_bytes()
            if name.endswith(".crt")
            else key.read_bytes()
            if name.endswith(".key")
            else owner_password.encode()
            for role, names in startup.preparation.DELIVERY.items()
            for name in names
        }
        dep_files.update({"cache/server.crt": cache_cert.read_bytes(), "cache/server.key": cache_key.read_bytes()})
        delivery(parent / "dependency-delivery", dep_files)
        prepared = startup.preparation.initialize(plan, expected, parent / "dependency-delivery")
        first = startup.start(plan, expected)
        import private_installation_adopt as adopter

        _, _, app_binding = adopter.application_profile(value, expected, initialized["initialization_id"])
        adopter.prerequisites(value, app_binding, {})
        stored = Path(value["request"]["root"]) / "dependencies/started.json"
        original = stored.read_bytes()
        again = startup.start(plan, expected)
        ids = {role: row["container_id"] for role, row in first["services"].items()}
        if (
            ids != {role: row["container_id"] for role, row in again["services"].items()}
            or not all(row["reused"] is True for row in again["services"].values())
            or stored.read_bytes() != original
        ):
            raise startup.checker.planner.PlanError("dependency_start_fixture_recreated_or_republished")
        import private_schema_init as schema_init

        description = schema_init.initialize(plan, expected)
        pin = description["schema_sha256"]
        schema_root = parent / "installation" / "dependencies"
        if description["state"] != "fresh" or (schema_root / "schema-intent.json").exists():
            raise startup.checker.planner.PlanError("schema_fixture_description_mutated_state")
        try:
            schema_init.initialize(plan, expected, "f" * 64)
        except startup.checker.planner.PlanError as error:
            if str(error) != "schema_graph_changed":
                raise
        else:
            raise startup.checker.planner.PlanError("schema_fixture_wrong_graph_not_blocked")
        if (schema_root / "schema-intent.json").exists():
            raise startup.checker.planner.PlanError("schema_fixture_wrong_graph_published_intent")
        # Qualification-only post-DDL fault. No production code or approved
        # intent is changed; normal controller execution follows this rollback.
        original_code = schema_init.SCHEMA_CODE
        marker = "            executor=MigrationExecutor(connection);loader=executor.loader"
        if marker not in original_code:
            raise startup.checker.planner.PlanError("schema_fixture_fault_marker_missing")
        try:
            schema_init.SCHEMA_CODE = original_code.replace(
                marker, "            raise RuntimeError('qualification_only_rollback')\n" + marker
            )
            try:
                schema_init.helper(
                    value, prepared, startup.resources.inspect("image", value["images"]["api"]), "apply_fresh", pin
                )
            except startup.checker.planner.PlanError as error:
                if str(error) != "private_schema_migration_failed":
                    raise
            else:
                raise startup.checker.planner.PlanError("schema_fixture_ddl_failure_not_observed")
        finally:
            schema_init.SCHEMA_CODE = original_code
        if schema_init.initialize(plan, expected)["state"] != "fresh" or (schema_root / "schema.json").exists():
            raise startup.checker.planner.PlanError("schema_fixture_atomic_rollback_failed")
        schema_first = schema_init.initialize(plan, expected, pin)
        history = (schema_root / "schema.json").read_bytes()
        schema_repeat = schema_init.initialize(plan, expected, pin)
        if not schema_repeat["reused"] or (schema_root / "schema.json").read_bytes() != history:
            raise startup.checker.planner.PlanError("schema_fixture_history_changed")
        # A lost result publication retains exact intent. The product verifies
        # current state and discloses recovery; it never reapplies migrations.
        (schema_root / "schema.json").unlink()
        recovered_schema = schema_init.initialize(plan, expected, pin)
        if recovered_schema["migration_execution"] != "recovered_current_from_exact_intent":
            raise startup.checker.planner.PlanError("schema_fixture_recovery_not_disclosed")
        recovered_history = (schema_root / "schema.json").read_bytes()
        from qualify_private_account_enrollment import qualify as qualify_accounts

        accounts, account_passwords = qualify_accounts(value, prepared, parent)
        redactions.extend(account_passwords.values())
        artifacts = parent / "installation" / "artifacts"
        if list(artifacts.iterdir()):
            raise startup.checker.planner.PlanError("account_fixture_customer_artifacts_modified")
        try:
            adopted = adopter.adoption(plan, expected, parent / "server.crt")
            repeated_adoption = adopter.adoption(plan, expected, parent / "server.crt")
            if {r: v["container_id"] for r, v in adopted["services"].items()} != {
                r: v["container_id"] for r, v in repeated_adoption["services"].items()
            }:
                raise startup.checker.planner.PlanError("account_fixture_application_recreated")
            if not (artifacts / "data_files").is_dir():
                raise startup.checker.planner.PlanError("account_fixture_application_media_missing")
            from qualify_private_account_enrollment import https_roles

            https_account_roles = https_roles(value, accounts, account_passwords, parent)
            from qualify_private_cache import qualify as qualify_cache, recovery as qualify_cache_recovery

            cache_qualification = qualify_cache(value, adopted, command)
            cache_recovery = qualify_cache_recovery(value, adopted, first, parent, command)
            from qualify_private_broker import qualify as qualify_broker

            broker_qualification = qualify_broker(value, adopted, command)
            from qualify_private_broker_recovery import recovery as qualify_broker_recovery

            broker_recovery = qualify_broker_recovery(value, adopted, first, parent, command)
            from qualify_private_secret_capture import qualify as qualify_secrets

            secret_capture = qualify_secrets(value, adopted, command)
            from qualify_private_tls_capture import qualify as qualify_tls_inputs

            tls_capture = qualify_tls_inputs(value, adopted, command)
            from qualify_private_postgres_tls import qualify as qualify_postgres_tls

            postgres_tls = qualify_postgres_tls(value, adopted, command)
            from qualify_private_postgres_ca import qualify as qualify_postgres_ca

            postgres_ca = qualify_postgres_ca(value, adopted, command)
            from qualify_private_controller_capture import qualify as qualify_controller_capture

            controller_capture = qualify_controller_capture(value, parent)
            from qualify_private_delivery_capture import qualify as qualify_delivery_capture

            delivery_capture = qualify_delivery_capture(value, parent)
            from qualify_private_operation_lock import qualify as qualify_operation_lock

            operation_serialization = qualify_operation_lock(value, plan, expected, parent, adopted)
            from qualify_private_lifecycle_readiness import qualify as qualify_lifecycle_readiness

            lifecycle_readiness = qualify_lifecycle_readiness(value, plan, expected, parent, adopted)
            from qualify_private_queue_incidents import qualify as qualify_queue_incidents

            queue_incidents = qualify_queue_incidents(value, plan, expected, parent, adopted)
            from qualify_private_queue_evidence import qualify as qualify_queue_evidence

            queue_evidence = qualify_queue_evidence(value, expected, parent, adopted)
            account_adoption = {
                "queue_evidence": queue_evidence,
                "queue_incidents": queue_incidents,
                "operation_serialization": operation_serialization,
                "lifecycle_readiness": lifecycle_readiness,
                "controller_delivery_capture": delivery_capture,
                "controller_stored_capture": controller_capture,
                "postgresql_ca_preflight": postgres_ca,
                "postgresql_tls": postgres_tls,
                "cache_authentication_tls": cache_qualification,
                "cache_recovery": cache_recovery,
                "broker_ca_only_tls": broker_qualification,
                "broker_tls_recovery": broker_recovery,
                "private_secret_capture": secret_capture,
                "private_tls_input_capture": tls_capture,
                "fresh_empty_root_schema_accounts_and_four_services": "passed",
                "repeat_same_service_ids": "passed",
                "first": adopted,
                "https_account_roles": https_account_roles,
            }
        finally:
            # Only this owned project's exact labelled applications are removed.
            project, digest, binding = adopter.application_profile(value, expected, initialized["initialization_id"])
            for container in adopter.project_containers(project["name"]):
                role = container.get("Config", {}).get("Labels", {}).get("com.docker.compose.service")
                if role not in adopter.ROLES:
                    raise startup.checker.planner.PlanError("account_fixture_cleanup_owner_invalid")
                adopter.validate_application(
                    container,
                    role,
                    project["services"][role],
                    project,
                    digest,
                    binding,
                    startup.resources.inspect("image", value["images"]["ingress" if role == "ingress" else "api"]),
                )
                command(["container", "stop", "--time", "30", container["Id"]])
                command(["container", "rm", "--volumes", container["Id"]])
        db = value["request"]["database"]
        # Only this fresh fixture database is seeded; no operator table enters.
        command(
            [
                "exec",
                "--user",
                "70:70",
                "-i",
                ids["postgres"],
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                db["name"],
            ],
            data=b"CREATE TABLE dependency_fixture_persistence(value text); INSERT INTO dependency_fixture_persistence VALUES ('retained');\n",
        )
        for role in sorted(startup.ROLES):
            command(["container", "stop", "--time", "30", ids[role]])
        recovered = startup.start(plan, expected)
        if (
            ids != {role: row["container_id"] for role, row in recovered["services"].items()}
            or stored.read_bytes() != original
        ):
            raise startup.checker.planner.PlanError("dependency_start_fixture_restart_changed_history")
        data = command(
            [
                "exec",
                "--user",
                "70:70",
                ids["postgres"],
                "psql",
                "-X",
                "-A",
                "-t",
                "-U",
                "postgres",
                db["name"],
                "-c",
                "SELECT value FROM dependency_fixture_persistence;",
            ]
        )
        if data.strip() != b"retained":
            raise startup.checker.planner.PlanError("dependency_start_fixture_data_not_retained")
        try:
            schema_init.initialize(plan, expected, pin)
        except startup.checker.planner.PlanError as error:
            if str(error) != "schema_recorded_state_changed":
                raise
        else:
            raise startup.checker.planner.PlanError("schema_fixture_foreign_table_not_blocked")
        if (schema_root / "schema.json").read_bytes() != recovered_history:
            raise startup.checker.planner.PlanError("schema_fixture_history_overwritten")
        command(["container", "update", "--memory", "1g", "--memory-swap", "1g", ids["postgres"]])
        try:
            try:
                startup.start(plan, expected)
            except startup.checker.planner.PlanError as error:
                if str(error) != "dependency_container_profile_mismatch":
                    raise
            else:
                raise startup.checker.planner.PlanError("dependency_start_fixture_changed_profile_not_blocked")
            try:
                adopter.prerequisites(value, app_binding, {})
            except startup.checker.planner.PlanError as error:
                if str(error) != "dependency_container_profile_mismatch":
                    raise
            else:
                raise startup.checker.planner.PlanError("dependency_start_fixture_adoption_bypassed_hardening")
            if startup.resources.inspect("container", ids["postgres"])["HostConfig"]["Memory"] != 1024**3:
                raise startup.checker.planner.PlanError("dependency_start_fixture_profile_silently_repaired")
        finally:
            command(["container", "update", "--memory", "2g", "--memory-swap", "2g", ids["postgres"]])
        startup.owner_sql(ids["postgres"], "ALTER ROLE " + startup.sql_name(db["user"]) + " SUPERUSER;")
        try:
            try:
                startup.start(plan, expected)
            except startup.checker.planner.PlanError as error:
                if str(error) != "dependency_database_authority_changed":
                    raise
            else:
                raise startup.checker.planner.PlanError("dependency_start_fixture_elevated_role_not_blocked")
            if (
                startup.owner_sql(
                    ids["postgres"], "SELECT rolsuper FROM pg_roles WHERE rolname=" + startup.sql_text(db["user"]) + ";"
                )
                != "t"
            ):
                raise startup.checker.planner.PlanError("dependency_start_fixture_authority_silently_repaired")
        finally:
            startup.owner_sql(ids["postgres"], "ALTER ROLE " + startup.sql_name(db["user"]) + " NOSUPERUSER;")
        startup.owner_sql(ids["postgres"], "CREATE ROLE pga_fixture_foreign;")
        try:
            try:
                startup.start(plan, expected)
            except startup.checker.planner.PlanError as error:
                if str(error) != "dependency_database_foreign_catalog":
                    raise
            else:
                raise startup.checker.planner.PlanError("dependency_start_fixture_foreign_catalog_not_blocked")
        finally:
            startup.owner_sql(ids["postgres"], "DROP ROLE pga_fixture_foreign;")
        if stored.read_bytes() != original or any(
            startup.resources.inspect("container", cid)["State"]["Running"] is not True for cid in ids.values()
        ):
            raise startup.checker.planner.PlanError("dependency_start_fixture_existing_state_changed")
        return {
            "actual_linux_root_startup": "passed",
            "first": first,
            "repeat_without_recreation_or_republication": "passed",
            "graceful_restart_and_app_database_persistence": "passed",
            "changed_profile": "blocked_without_repair",
            "elevated_app_role": "blocked_without_repair",
            "foreign_catalog": "blocked_without_deletion",
            "existing_services_and_history_preserved": "passed",
            "managed_adoption_hardening": "verified_and_changed_profile_blocked",
            "dependency_start_does_not_migrate": True,
            "account_enrollment": accounts,
            "fresh_application_adoption": account_adoption,
            "schema_initialization": {
                "description_without_execution": "passed",
                "wrong_digest_without_intent": "blocked",
                "first": schema_first,
                "qualification_only_post_ddl_exception_rollback": "passed",
                "repeat_without_execution_or_republication": "passed",
                "lost_result_recovery": recovered_schema,
                "foreign_table": "blocked_without_repair",
                "history_preserved": "passed",
                "accounts_enrolled": False,
            },
            "operator_installation_modified": False,
        }
    except BaseException:
        if initialized is not None:
            binding = startup.resources.labels(value, expected, initialized["initialization_id"])
            for name in startup.names(value).values():
                rows = startup.resources.command(
                    ["container", "ls", "--all", "--filter", "name=" + name, "--format", "{{json .}}"]
                )
                if not any(startup.checker.planner.decode(line).get("Names") == name for line in rows.splitlines()):
                    continue
                info = startup.resources.inspect("container", name)
                if any(info.get("Config", {}).get("Labels", {}).get(k) != v for k, v in binding.items()):
                    continue
                logs = subprocess.run(
                    [*startup.resources.PREFIX, "logs", "--tail", "20", info["Id"]],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                detail = (logs.stdout + logs.stderr).decode(errors="replace")
                for secret in redactions:
                    detail = detail.replace(secret, "[synthetic-secret-redacted]")
                print(
                    json.dumps(
                        {
                            "fixture_role": info["Config"]["Labels"].get(startup.LABEL + "role"),
                            "state": {k: info.get("State", {}).get(k) for k in ["Running", "Restarting", "ExitCode"]},
                            "logs": detail[:8000],
                        }
                    ),
                    file=sys.stderr,
                )
        raise
    finally:
        if initialized is not None:
            binding = startup.resources.labels(value, expected, initialized["initialization_id"])
            for name in startup.names(value).values():
                rows = startup.resources.command(
                    ["container", "ls", "--all", "--filter", "name=" + name, "--format", "{{json .}}"]
                )
                if not any(startup.checker.planner.decode(line).get("Names") == name for line in rows.splitlines()):
                    continue
                info = startup.resources.inspect("container", name)
                if any(info.get("Config", {}).get("Labels", {}).get(k) != v for k, v in binding.items()):
                    raise startup.checker.planner.PlanError("dependency_start_fixture_cleanup_owner_invalid")
                command(["container", "rm", "--force", "--volumes", info["Id"]])
            for kind, specs in [
                ("network", value["prerequisites"]["networks"]),
                ("volume", [value["prerequisites"]["socket_volume"]]),
            ]:
                for spec in specs:
                    if startup.resources.listing(kind, spec["name"]):
                        if startup.resources.inspect(kind, spec["name"])["Labels"] != binding:
                            raise startup.checker.planner.PlanError("dependency_start_fixture_cleanup_owner_invalid")
                        command([kind, "rm", spec["name"]])


HOST_CODE = r"""
import json,sys,shutil
from pathlib import Path
v=json.load(sys.stdin);sys.path.insert(0,v['scripts']);import qualify_private_dependency_start as q
parent=Path(v['parent']);assert parent.parent==Path('/srv') and q.startup.resources.re.fullmatch('declarai-p37-[0-9a-f]{32}',parent.name)
created=False
try:
    parent.mkdir(mode=0o700);created=True;plan=parent/'plan';plan.mkdir(mode=0o700)
    for name,data in v['files'].items():(plan/name).write_text(data)
    print(json.dumps(q.host_case(plan,v['expected'],parent)))
finally:
    if created:shutil.rmtree(parent)
"""


def qualify(plan, expected, image, reports):
    value = startup.checker.verify(plan, expected)
    if (
        sys.platform != "linux"
        or image != value["images"]["api"]
        or value["request"]["root"] != "/srv/declarai/qualification"
        or value["request"]["installation_id"] != "qualification"
    ):
        raise startup.checker.planner.PlanError("dependency_start_fixture_scope_required")
    reports = reports.resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        raise startup.checker.planner.PlanError("installation_reports_path_invalid")
    identifier = uuid.uuid4().hex
    files, pin = fixture_plan(plan, expected, identifier)
    payload = startup.checker.planner.encoded(
        {
            "scripts": str(ROOT / "scripts"),
            "parent": "/srv/declarai-p37-" + identifier,
            "files": {k: data.decode() for k, data in files.items()},
            "expected": pin,
        }
    )
    result = subprocess.run(
        ["sudo", "-n", sys.executable, "-c", HOST_CODE], input=payload, capture_output=True, timeout=300, check=False
    )
    if result.returncode:
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "dependency-start-fixture-failed.log").write_bytes(result.stderr)
        raise startup.checker.planner.PlanError("dependency_start_fixture_failed")
    receipt = {
        "schema": "private_dependency_start_qualification_v1",
        "image_id": image,
        "source_plan_sha256": expected,
        "qualification": startup.checker.planner.decode(result.stdout),
        "owned_root_and_resources_removed": True,
        "installation_qualified": False,
        "expert_isolation_qualified": False,
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "dependency-start.json").write_bytes(startup.checker.planner.encoded(receipt))
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
