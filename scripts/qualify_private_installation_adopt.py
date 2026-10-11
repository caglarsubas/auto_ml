#!/usr/bin/env python3
"""Qualify adoption on a fresh synthetic Linux host installation only."""

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import private_installation_adopt as adopter
from qualify_private_installation_resources import fixture_plan

ROOT = Path(__file__).resolve().parents[1]


def host_case(plan, expected, parent):
    """Only the sudo child operates its fresh, UUID-owned host fixture."""
    import secrets
    import socket
    import time

    m = adopter.resources
    value = adopter.checker.verify(plan, expected)
    if (
        sys.platform != "linux"
        or __import__("os").geteuid() != 0
        or parent.parent != Path("/srv")
        or not m.re.fullmatch(r"declarai-p37-[0-9a-f]{32}", parent.name)
        or value["request"]["root"] != str(parent / "installation")
    ):
        raise adopter.checker.planner.PlanError("installation_adopt_fixture_scope_required")
    # The root already contains only this qualification's captured plan. It was
    # exclusively created by the parent helper; no existing host path is reused.
    token = parent.name.removeprefix("declarai-p37-")
    names = {role: "declarai-adopt-" + token + "-" + role for role in ["postgres", "cache", "job-broker"]}
    containers = []
    initialized = None
    redactions = []

    def command(args, data=None):
        result = subprocess.run([*m.PREFIX, *args], input=data, capture_output=True, timeout=120, check=False)
        if result.returncode:
            detail = (result.stdout + result.stderr).decode(errors="replace")
            for secret in redactions:
                detail = detail.replace(secret, "[synthetic-secret-redacted]")
            detail = m.re.sub(
                r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
                "[synthetic-key-redacted]",
                detail,
                flags=m.re.S,
            )
            print(json.dumps({"fixture_command": args[:3], "diagnostic": detail[:12000]}), file=sys.stderr)
            raise adopter.checker.planner.PlanError("installation_adopt_fixture_command_failed")
        return result.stdout

    try:
        with socket.socket() as available:
            available.bind((value["request"]["bind_ip"], 8443))
        cert = parent / "server.crt"
        key = parent / "server.key"
        result = subprocess.run(
            [
                "openssl",
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
                "/CN=api.private.test",
                "-addext",
                "subjectAltName=DNS:api.private.test,DNS:postgres,DNS:job-broker",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise adopter.checker.planner.PlanError("installation_adopt_fixture_certificate_failed")
        app_password, admin_password, broker_password = (
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
        )
        delivery = parent / "delivery"
        delivery.mkdir(mode=0o700)
        __import__("os").chown(delivery, 10001, 10001)
        for group in ["app", "tls"]:
            p = delivery / group
            p.mkdir(mode=0o700)
            __import__("os").chown(p, 10001, 10001)
        files = {
            "app/django-key": secrets.token_urlsafe(64).encode(),
            "app/app-password": app_password.encode(),
            "app/job-broker-url": ("rediss://:" + broker_password + "@job-broker:6379/1").encode(),
            "app/postgres-ca.crt": cert.read_bytes(),
            "app/job-ca.crt": cert.read_bytes(),
            "tls/tls.crt": cert.read_bytes(),
            "tls/tls.key": key.read_bytes(),
        }
        redactions.extend([app_password, admin_password, broker_password, files["app/django-key"].decode()])
        for name, data in files.items():
            p = delivery / name
            p.write_bytes(data)
            p.chmod(0o400)
            __import__("os").chown(p, 10001, 10001)
        initialized = m.initializer.initialize(plan, expected, delivery)
        m.prepare(plan, expected)
        binding = m.labels(value, expected, initialized["initialization_id"])
        private = value["prerequisites"]["networks"][0]["name"]
        for role in ["postgres", "job-broker"]:
            config = parent / role
            config.mkdir(mode=0o700)
            (config / "server.crt").write_bytes(cert.read_bytes())
            (config / "server.key").write_bytes(key.read_bytes())
            if role == "postgres":
                (config / "admin-password").write_text(admin_password)
            else:
                (config / "redis.conf").write_text(
                    "port 0\ntls-port 6379\ntls-cert-file /fixture/server.crt\ntls-key-file /fixture/server.key\ntls-ca-cert-file /fixture/server.crt\ntls-auth-clients no\nappendonly no\nrequirepass "
                    + broker_password
                    + "\n"
                )
        for role, name in names.items():
            if m.command(["container", "ls", "--all", "--filter", "name=" + name, "--format", "{{.Names}}"]).strip():
                raise adopter.checker.planner.PlanError("installation_adopt_fixture_container_exists")
            args = [
                "container",
                "create",
                "--name",
                name,
                "--pull",
                "never",
                "--network",
                private,
                "--network-alias",
                role,
            ]
            for k, v in {**binding, m.LABEL + "role": role}.items():
                args += ["--label", k + "=" + v]
            if role == "postgres":
                args += [
                    "--mount",
                    "type=bind,src=" + str(parent / role) + ",dst=/fixture",
                    "--env",
                    "POSTGRES_PASSWORD_FILE=/fixture/admin-password",
                    "--env",
                    "POSTGRES_USER=declarai_fixture_admin",
                    "--entrypoint",
                    "sh",
                    value["images"]["postgres"],
                    "-c",
                    "chown -R postgres:postgres /fixture; chmod 600 /fixture/server.key; exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/fixture/server.crt -c ssl_key_file=/fixture/server.key",
                ]
            elif role == "job-broker":
                args += [
                    "--mount",
                    "type=bind,src=" + str(parent / role) + ",dst=/fixture",
                    "--entrypoint",
                    "sh",
                    value["images"]["redis"],
                    "-c",
                    "chown -R redis:redis /fixture; chmod 600 /fixture/server.key /fixture/redis.conf; exec docker-entrypoint.sh redis-server /fixture/redis.conf",
                ]
            else:
                args += [value["images"]["redis"], "redis-server", "--save", "", "--appendonly", "no"]
            command(args)
            containers.append(name)
            command(["container", "start", name])
        deadline = time.monotonic() + 60
        while True:
            result = subprocess.run(
                [*m.PREFIX, "exec", names["postgres"], "pg_isready", "-h", "127.0.0.1", "-U", "declarai_fixture_admin"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if not result.returncode:
                break
            if time.monotonic() >= deadline:
                raise adopter.checker.planner.PlanError("installation_adopt_fixture_postgres_unavailable")
            time.sleep(1)
        db = value["request"]["database"]
        sql = (
            "CREATE ROLE "
            + db["user"]
            + " LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '"
            + app_password
            + "';\nCREATE DATABASE "
            + db["name"]
            + " OWNER "
            + db["user"]
            + ";\n"
        ).encode()
        command(
            [
                "exec",
                "-i",
                names["postgres"],
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "declarai_fixture_admin",
                "postgres",
            ],
            data=sql,
        )
        profile, _, _ = adopter.application_profile(value, expected, initialized["initialization_id"])
        environment = profile["services"]["api"]["environment"]
        migrate = "declarai-adopt-" + token + "-migrate"
        args = [
            "container",
            "create",
            "--name",
            migrate,
            "--pull",
            "never",
            "--network",
            private,
            "--read-only",
            "--user",
            "10001:10001",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--cpus",
            "2",
            "--memory",
            "2g",
            "--pids-limit",
            "256",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=134217728,uid=10001,gid=10001,mode=700",
        ]
        for k, v in {**binding, m.LABEL + "role": "fixture-migrate"}.items():
            args += ["--label", k + "=" + v]
        for k, v in environment.items():
            args += ["--env", k + "=" + v]
        for source, target in [
            (value["request"]["root"] + "/secrets/app", "/installation"),
            (value["request"]["root"] + "/artifacts", "/artifacts"),
        ]:
            args += [
                "--mount",
                "type=bind,src=" + source + ",dst=" + target + (",readonly" if target == "/installation" else ""),
            ]
        command(
            [*args, "--entrypoint", "python", value["images"]["api"], "/app/backend/manage.py", "migrate", "--noinput"]
        )
        containers.append(migrate)
        command(["container", "start", "--attach", migrate])
        if m.inspect("container", migrate)["State"]["ExitCode"] != 0:
            raise adopter.checker.planner.PlanError("installation_adopt_fixture_migrations_failed")
        invalid_ca = parent / "invalid-client-ca.pem"
        invalid_ca.write_text("synthetic malformed certificate")
        try:
            adopter.adoption(plan, expected, invalid_ca)
        except adopter.checker.planner.PlanError as error:
            if str(error) != "installation_adopt_client_ca_invalid":
                raise
        else:
            raise adopter.checker.planner.PlanError("installation_adopt_fixture_invalid_ca_not_blocked")
        if adopter.project_containers(profile["name"]):
            raise adopter.checker.planner.PlanError("installation_adopt_fixture_started_before_ca_check")
        first = adopter.adoption(plan, expected, cert)
        again = adopter.adoption(plan, expected, cert)
        if {k: v["container_id"] for k, v in first["services"].items()} != {
            k: v["container_id"] for k, v in again["services"].items()
        } or any(v["reused"] is not True for v in again["services"].values()):
            raise adopter.checker.planner.PlanError("installation_adopt_fixture_recreated_services")
        api_id = first["services"]["api"]["container_id"]
        command(["container", "update", "--memory", "1g", "--memory-swap", "2g", api_id])
        try:
            try:
                adopter.adoption(plan, expected, cert)
            except adopter.checker.planner.PlanError as error:
                if str(error) != "installation_adopt_application_profile_mismatch":
                    raise
            else:
                raise adopter.checker.planner.PlanError("installation_adopt_fixture_profile_change_not_blocked")
            if m.inspect("container", api_id)["HostConfig"]["Memory"] != 1024**3:
                raise adopter.checker.planner.PlanError("installation_adopt_fixture_profile_silently_repaired")
        finally:
            # Explicit fixture repair, outside the controller, of this one owned
            # injected memory fault. Operator resources never enter this path.
            command(["container", "update", "--memory", "2g", "--memory-swap", "4g", api_id])
        # Broader grants must block the sealed preflight without stopping/replacing
        # existing services or allowing their technical receipt to approve use.
        command(
            [
                "exec",
                "-i",
                names["postgres"],
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "declarai_fixture_admin",
                "postgres",
            ],
            data=("GRANT pg_read_all_data TO " + db["user"] + ";\n").encode(),
        )
        try:
            adopter.adoption(plan, expected, cert)
        except adopter.checker.planner.PlanError as error:
            if str(error) != "installation_adopt_preflight_failed":
                raise
        else:
            raise adopter.checker.planner.PlanError("installation_adopt_fixture_elevated_role_not_blocked")
        after = adopter.project_containers(profile["name"])
        if {c["Id"] for c in after} != {v["container_id"] for v in first["services"].values()} or any(
            c["State"]["Running"] is not True for c in after
        ):
            raise adopter.checker.planner.PlanError("installation_adopt_fixture_changed_existing_services")
        return {
            "actual_linux_root_adoption": "passed",
            "four_fixed_services": first,
            "repeat_without_recreation": "passed",
            "malformed_client_ca_before_start": "blocked",
            "altered_existing_application_profile": "blocked_without_repair",
            "elevated_database_membership": "blocked",
            "existing_services_preserved": "passed",
            "client_tls_hostname_and_ca": "verified",
            "operator_installation_modified": False,
        }
    except BaseException:
        # This exclusively owned synthetic fixture may retain neutral startup
        # logs/metadata. Never inspect containers outside its exact binding.
        if initialized is not None:
            binding = m.labels(value, expected, initialized["initialization_id"])
            profile, _, _ = adopter.application_profile(value, expected, initialized["initialization_id"])
            for info in adopter.project_containers(profile["name"]):
                if any(info.get("Config", {}).get("Labels", {}).get(k) != v for k, v in binding.items()):
                    continue
                logs = subprocess.run(
                    [*m.PREFIX, "container", "logs", "--tail", "20", info["Id"]],
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
                            "fixture_role": info["Config"]["Labels"].get(m.LABEL + "role"),
                            "state": {
                                k: info.get("State", {}).get(k) for k in ["Running", "Restarting", "ExitCode", "Error"]
                            },
                            "requested_ports": info.get("HostConfig", {}).get("PortBindings"),
                            "actual_ports": info.get("NetworkSettings", {}).get("Ports"),
                            "logs": detail[:12000],
                        }
                    ),
                    file=sys.stderr,
                )
        raise
    finally:
        if initialized is not None:
            binding = m.labels(value, expected, initialized["initialization_id"])
            profile, _, _ = adopter.application_profile(value, expected, initialized["initialization_id"])
            for info in adopter.project_containers(profile["name"]):
                if any(info.get("Config", {}).get("Labels", {}).get(k) != v for k, v in binding.items()):
                    raise adopter.checker.planner.PlanError("installation_adopt_fixture_cleanup_owner_invalid")
                command(["container", "rm", "--force", "--volumes", info["Id"]])
            for name in containers:
                info = m.inspect("container", name)
                if any(info.get("Config", {}).get("Labels", {}).get(k) != v for k, v in binding.items()):
                    raise adopter.checker.planner.PlanError("installation_adopt_fixture_cleanup_owner_invalid")
                command(["container", "rm", "--force", "--volumes", info["Id"]])
            for kind, specs in [
                ("network", value["prerequisites"]["networks"]),
                ("volume", [value["prerequisites"]["socket_volume"]]),
            ]:
                for spec in specs:
                    if m.listing(kind, spec["name"]):
                        if m.inspect(kind, spec["name"])["Labels"] != binding:
                            raise adopter.checker.planner.PlanError("installation_adopt_fixture_cleanup_owner_invalid")
                        command([kind, "rm", spec["name"]])
        # Only the exclusively-created qualification parent is removed by caller.


HOST_CODE = r"""
import json,sys,shutil
from pathlib import Path
v=json.load(sys.stdin);sys.path.insert(0,v['scripts'])
import qualify_private_installation_adopt as q
parent=Path(v['parent']);assert parent.parent==Path('/srv') and q.adopter.resources.re.fullmatch('declarai-p37-[0-9a-f]{32}',parent.name)
created=False
try:
    parent.mkdir(mode=0o700);created=True
    plan=parent/'plan';plan.mkdir(mode=0o700)
    for name,data in v['files'].items():(plan/name).write_text(data)
    print(json.dumps(q.host_case(plan,v['expected'],parent)))
finally:
    if created:shutil.rmtree(parent)
"""


def qualify(plan, expected, image, reports):
    value = adopter.checker.verify(plan, expected)
    if (
        image != value["images"]["api"]
        or value["request"]["installation_id"] != "qualification"
        or value["request"]["root"] != "/srv/declarai/qualification"
    ):
        raise adopter.checker.planner.PlanError("installation_adopt_fixture_scope_required")
    reports = reports.resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        raise adopter.checker.planner.PlanError("installation_reports_path_invalid")
    if sys.platform != "linux":
        raise adopter.checker.planner.PlanError("installation_adopt_fixture_linux_host_required")
    identifier = uuid.uuid4().hex
    files, pin = fixture_plan(plan, expected, identifier)
    payload = adopter.checker.planner.encoded(
        {
            "scripts": str(ROOT / "scripts"),
            "parent": "/srv/declarai-p37-" + identifier,
            "files": {k: v.decode() for k, v in files.items()},
            "expected": pin,
        }
    )
    run = subprocess.run(
        ["sudo", "-n", sys.executable, "-c", HOST_CODE], input=payload, capture_output=True, timeout=300, check=False
    )
    if run.returncode:
        # Synthetic-only traceback, retained locally for diagnosing this owned
        # fixture; product controller failures never emit credential values.
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "installation-adopt-fixture-failed.log").write_bytes(run.stderr)
        raise adopter.checker.planner.PlanError("installation_adopt_fixture_failed")
    result = {
        "schema": "private_installation_adoption_qualification_v1",
        "image_id": image,
        "source_plan_sha256": expected,
        "qualification": adopter.checker.planner.decode(run.stdout),
        "owned_host_root_and_resources_removed": True,
        "installation_qualified": False,
        "expert_isolation_qualified": False,
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "installation-adopt.json").write_bytes(adopter.checker.planner.encoded(result))
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
