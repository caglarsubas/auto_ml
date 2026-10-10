#!/usr/bin/env python3
"""Own a disposable TLS database, verify a quiescent restore, then run pytest.

Requires Docker and openssl. Secrets, dump and session state live outside the
checkout and are removed on exit. No existing installation is read or changed.
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def command(args, *, data=None, env=None, cwd=None, timeout=120):
    result = subprocess.run(
        args,
        input=data,
        env=env,
        cwd=cwd,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode:
        # Commands may include SQL or fixtures containing credentials.
        raise RuntimeError("Disposable fixture command failed: " + Path(args[0]).name)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runner-image", help="Local core test image; omitted in host Python CI"
    )
    parser.add_argument("--reports", default="test-reports/postgresql")
    parser.add_argument("--private-api-image", help="Exact local private API image sha256; adds real fixed-image socket smoke")
    args = parser.parse_args()
    reports = (ROOT / args.reports).resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        parser.error("Reports must be inside the ignored test-reports directory.")
    reports.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    network, db, redis, runner, job_broker = (
        f"declarai-fixture-{token}-{suffix}"
        for suffix in ("net", "db", "redis", "runner", "job-broker")
    )
    with tempfile.TemporaryDirectory(prefix="declarai-pg-fixture-") as directory:
        fixture = Path(directory)
        for name in ["artifacts", "restored-artifacts"]:
            (fixture / name).mkdir()
        admin_password, app_password, test_password = (
            secrets.token_urlsafe(32) for _ in range(3)
        )
        for name, value in [
            ("admin-password", admin_password),
            ("app-password", app_password),
            ("django-key", secrets.token_urlsafe(64)),
        ]:
            (fixture / name).write_text(value)
            (fixture / name).chmod(0o600)
        for name in ["server", "wrong-ca", "job-server"]:
            command(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=job-broker" if name == "job-server" else "/CN=localhost",
                    "-addext",
                    "subjectAltName=DNS:job-broker,IP:127.0.0.1" if name == "job-server" else "subjectAltName=DNS:localhost,DNS:postgres,IP:127.0.0.1",
                    "-keyout",
                    str(fixture / (name + ".key")),
                    "-out",
                    str(fixture / (name + ".crt")),
                ]
            )
        broker_password = secrets.token_urlsafe(32)
        (fixture / "job-broker.conf").write_text(
            "port 0\ntls-port 6379\ntls-cert-file /fixture/job-server.crt\n"
            "tls-key-file /fixture/job-server.key\ntls-ca-cert-file /fixture/job-server.crt\n"
            "tls-auth-clients no\nappendonly yes\ndir /data\nrequirepass " + broker_password + "\n"
        )
        (fixture / "job-broker.conf").chmod(0o600)

        job_tls = fixture / "job-tls"
        job_tls.mkdir()
        for name in ["job-server.crt", "job-server.key", "job-broker.conf"]:
            shutil.copy2(fixture / name, job_tls / name)

        def start_job_broker():
            command(["docker", "create", "--name", job_broker, "--network", network,
                     "--network-alias", "job-broker", "-p", "127.0.0.1::6379", "redis:7-alpine",
                     "sh", "-c", "chown -R redis:redis /fixture; exec docker-entrypoint.sh redis-server /fixture/job-broker.conf"])
            command(["docker", "cp", str(job_tls), job_broker + ":/fixture"])
            command(["docker", "start", job_broker])
            port = command(["docker", "port", job_broker, "6379/tcp"]).decode().strip().rsplit(":", 1)[1]
            host = "job-broker:6379" if args.runner_image else "127.0.0.1:" + port
            (fixture / "job-broker-url").write_text("rediss://:" + broker_password + "@" + host + "/1")
            (fixture / "job-broker-url").chmod(0o600)
            return port

        try:
            command(["docker", "network", "create", network])
            command(
                [
                    "docker",
                    "create",
                    "--name",
                    db,
                    "--network",
                    network,
                    "--network-alias",
                    "postgres",
                    "-p",
                    "127.0.0.1::5432",
                    "-e",
                    "POSTGRES_PASSWORD_FILE=/fixture/admin-password",
                    "-e",
                    "POSTGRES_USER=declarai_fixture_admin",
                    "postgres:17-alpine",
                    "sh",
                    "-c",
                    (
                        "chown -R postgres:postgres /fixture; chmod 600 /fixture/server.key; "
                        "exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/fixture/server.crt -c ssl_key_file=/fixture/server.key"
                    ),
                ]
            )
            command(["docker", "cp", str(fixture), db + ":/fixture"])
            command(["docker", "start", db])
            command(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    redis,
                    "--network",
                    network,
                    "-p",
                    "127.0.0.1::6379",
                    "redis:7-alpine",
                ]
            )
            job_broker_port = start_job_broker()
            ready = False
            for _ in range(60):
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        db,
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-U",
                        "declarai_fixture_admin",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if result.returncode == 0:
                    ready = True
                    break
                time.sleep(1)
            if not ready:
                raise RuntimeError("Disposable PostgreSQL did not become ready.")
            sql = (
                f"CREATE ROLE declarai_fixture_app LOGIN PASSWORD '{app_password}';\n"
                "CREATE DATABASE declarai_fixture OWNER declarai_fixture_app;\n"
                f"CREATE ROLE declarai_fixture_tests LOGIN CREATEDB PASSWORD '{test_password}';\n"
                "CREATE DATABASE declarai_fixture_tests OWNER declarai_fixture_tests;\n"
            )
            command(
                [
                    "docker",
                    "exec",
                    "-i",
                    db,
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "declarai_fixture_admin",
                    "-d",
                    "postgres",
                ],
                data=sql.encode(),
            )
            db_port = (
                command(["docker", "port", db, "5432/tcp"])
                .decode()
                .strip()
                .rsplit(":", 1)[1]
            )
            redis_port = (
                command(["docker", "port", redis, "6379/tcp"])
                .decode()
                .strip()
                .rsplit(":", 1)[1]
            )
            env = {
                **os.environ,
                "DECLARAI_TEST_INSTALLATION": "1",
                "PROMETA_DISABLE": "1",
                "OPENAI_API_KEY": "",
                "LLM_ENGINE_BASE_URL": "http://127.0.0.1:9/v1",
                "DECLARAI_RUNTIME_PROFILE": "private",
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY_FILE": str(fixture / "django-key"),
                "DJANGO_ALLOWED_HOSTS": "api.private.test",
                "DECLARAI_ALLOWED_ORIGINS": "https://console.private.test",
                "DECLARAI_MEDIA_ROOT": str(fixture / "artifacts"),
                "DECLARAI_DB_ENGINE": "postgresql",
                "DECLARAI_DB_NAME": "declarai_fixture",
                "DECLARAI_DB_USER": "declarai_fixture_app",
                "DECLARAI_DB_PASSWORD_FILE": str(fixture / "app-password"),
                "DECLARAI_DB_HOST": "postgres" if args.runner_image else "localhost",
                "DECLARAI_DB_PORT": "5432" if args.runner_image else db_port,
                "DECLARAI_DB_SSLMODE": "verify-full",
                "DECLARAI_DB_SSLROOTCERT": str(fixture / "server.crt"),
                "DECLARAI_FIXTURE_STATE": str(fixture / "state.json"),
                "DECLARAI_JOB_FIXTURE_STATE": str(fixture / "jobs-state.json"),
                "REDIS_URL": f"redis://{redis}:6379/0"
                if args.runner_image
                else f"redis://localhost:{redis_port}/0",
                "OMP_NUM_THREADS": "2",
                "OPENBLAS_NUM_THREADS": "2",
                "MKL_NUM_THREADS": "2",
            }
            # Remove inherited alternate sources rather than accidentally selecting them.
            for name in [
                "DJANGO_SECRET_KEY",
                "DECLARAI_DB_PASSWORD",
                "DJANGO_TRUST_PROXY_TLS",
                "DECLARAI_JOB_BROKER_URL",
                "DECLARAI_JOB_BROKER_URL_FILE",
                "DECLARAI_JOB_BROKER_CA_FILE",
            ]:
                env.pop(name, None)

            def run_python(
                arguments, values=None, *, succeed=True, report=None, rejection=None
            ):
                current = {**env, **(values or {})}
                if args.runner_image:
                    env_file = fixture / "runner.env"
                    selected = {
                        k: v
                        for k, v in current.items()
                        if k.startswith(
                            (
                                "DECLARAI_",
                                "DJANGO_",
                                "LLM_ENGINE_",
                                "OPENAI_",
                                "REDIS_",
                                "PROMETA_",
                                "OMP_",
                                "OPENBLAS_",
                                "MKL_",
                            )
                        )
                    }
                    env_file.write_text(
                        "".join(f"{k}={v}\n" for k, v in selected.items())
                    )
                    env_file.chmod(0o600)
                    argv = [
                        "docker",
                        "run",
                        "--rm",
                        "--name",
                        runner,
                        "--cpuset-cpus=2-3",
                        "--network",
                        network,
                        "--env-file",
                        str(env_file),
                        "-v",
                        f"{ROOT}:/app",
                        "-v",
                        f"{fixture}:{fixture}",
                        "-w",
                        "/app/backend" if arguments[0] == "-m" else "/app",
                        args.runner_image,
                        "python",
                        *arguments,
                    ]
                    cwd = ROOT
                else:
                    argv = [sys.executable, *arguments]
                    cwd = ROOT / "backend" if arguments[0] == "-m" else ROOT
                log_path = reports / (report or "private-runtime.log")
                offset = log_path.stat().st_size if log_path.exists() else 0
                with log_path.open("ab") as log:
                    result = subprocess.run(
                        argv,
                        env=current,
                        cwd=cwd,
                        stdout=log,
                        stderr=log,
                        timeout=900,
                        check=False,
                    )
                if (result.returncode == 0) != succeed:
                    raise RuntimeError(
                        "Fixture Python check failed; inspect its ignored report."
                    )

                if rejection and rejection not in log_path.read_bytes()[offset:].decode(
                    "utf-8", errors="replace"
                ):
                    raise RuntimeError(
                        "TLS rejection did not report its expected cause."
                    )

            run_python(["backend/manage.py", "migrate", "--noinput"])
            run_python(["scripts/qualify_private_runtime.py", "seed"])
            # Force an actual connection; Django's system checks alone do not verify TLS.
            query = [
                "backend/manage.py",
                "shell",
                "-c",
                "from django.db import connection; connection.ensure_connection()",
            ]
            run_python(
                query,
                {"DECLARAI_DB_SSLROOTCERT": str(fixture / "wrong-ca.crt")},
                succeed=False,
                report="tls-wrong-ca-connect.log",
                rejection="certificate verify failed",
            )
            # Fixture address is reachable, but it is absent from the server certificate.
            ip = (
                command(
                    [
                        "docker",
                        "inspect",
                        "-f",
                        "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                        db,
                    ]
                )
                .decode()
                .strip()
            )
            if args.runner_image:
                run_python(
                    query,
                    {"DECLARAI_DB_HOST": ip},
                    succeed=False,
                    report="tls-wrong-host.log",
                    rejection="does not match host name",
                )
            else:
                # libpq hostaddr preserves the connection endpoint while checking the supplied host.
                run_python(
                    [
                        "-c",
                        'import os, psycopg; psycopg.connect(dbname=os.environ["DECLARAI_DB_NAME"], user=os.environ["DECLARAI_DB_USER"], password=open(os.environ["DECLARAI_DB_PASSWORD_FILE"]).read(), host="wrong.private.test", hostaddr="127.0.0.1", port=os.environ["DECLARAI_DB_PORT"], sslmode="verify-full", sslrootcert=os.environ["DECLARAI_DB_SSLROOTCERT"], connect_timeout=5)',
                    ],
                    succeed=False,
                    report="tls-wrong-host.log",
                    rejection="does not match host name",
                )
            dump = command(
                [
                    "docker",
                    "exec",
                    db,
                    "pg_dump",
                    "-U",
                    "declarai_fixture_admin",
                    "-Fc",
                    "declarai_fixture",
                ]
            )
            command(
                [
                    "docker",
                    "exec",
                    db,
                    "createdb",
                    "-U",
                    "declarai_fixture_admin",
                    "-O",
                    "declarai_fixture_app",
                    "declarai_fixture_restored",
                ]
            )
            command(
                [
                    "docker",
                    "exec",
                    "-i",
                    db,
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "-U",
                    "declarai_fixture_app",
                    "-d",
                    "declarai_fixture_restored",
                ],
                data=dump,
            )
            shutil.copytree(
                fixture / "artifacts",
                fixture / "restored-artifacts",
                dirs_exist_ok=True,
            )
            command(["docker", "restart", db])
            for _ in range(30):
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        db,
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-U",
                        "declarai_fixture_admin",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if result.returncode == 0:
                    break
                time.sleep(1)
            if not args.runner_image:
                # Docker may allocate a different ephemeral published port on restart.
                # The core-image runner uses the stable internal service port instead.
                env["DECLARAI_DB_PORT"] = (
                    command(["docker", "port", db, "5432/tcp"])
                    .decode()
                    .strip()
                    .rsplit(":", 1)[1]
                )
            run_python(["scripts/qualify_private_runtime.py", "verify"])
            run_python(
                ["scripts/qualify_private_runtime.py", "verify"],
                {
                    "DECLARAI_DB_NAME": "declarai_fixture_restored",
                    "DECLARAI_MEDIA_ROOT": str(fixture / "restored-artifacts"),
                },
            )
            run_python(
                ["scripts/qualify_private_identity.py"], report="private-identity.log"
            )
            run_python(["scripts/qualify_private_projects.py"], report="private-projects.log")
            job_env = {
                "DECLARAI_JOB_BROKER_URL_FILE": str(fixture / "job-broker-url"),
                "DECLARAI_JOB_BROKER_CA_FILE": str(fixture / "job-server.crt"),
            }
            preflight = ["backend/manage.py", "check_job_runtime"]
            run_python(preflight, job_env, report="private-jobs.log")
            if args.private_api_image:
                from qualify_private_api_image import qualify_image
                qualify_image(args.private_api_image, network, fixture, env, reports)
            run_python(preflight, {**job_env, "DECLARAI_JOB_BROKER_CA_FILE": str(fixture / "wrong-ca.crt")},
                       succeed=False, report="job-tls-wrong-ca.log", rejection="job_broker_unavailable")
            broker_ip = command(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", job_broker]).decode().strip()
            bad_host = broker_ip + ":6379" if args.runner_image else "localhost:" + job_broker_port
            wrong_host_file = fixture / "job-wrong-host-url"
            wrong_host_file.write_text("rediss://:" + broker_password + "@" + bad_host + "/1")
            wrong_host_file.chmod(0o600)
            run_python(preflight, {**job_env, "DECLARAI_JOB_BROKER_URL_FILE": str(wrong_host_file)},
                       succeed=False, report="job-tls-wrong-host.log", rejection="job_broker_unavailable")
            wrong_auth_file = fixture / "job-wrong-auth-url"
            host = "job-broker:6379" if args.runner_image else "127.0.0.1:" + job_broker_port
            wrong_auth_file.write_text("rediss://:invalid-fixture-password@" + host + "/1")
            wrong_auth_file.chmod(0o600)
            run_python(preflight, {**job_env, "DECLARAI_JOB_BROKER_URL_FILE": str(wrong_auth_file)},
                       succeed=False, report="job-wrong-auth.log", rejection="job_broker_unavailable")
            run_python(["scripts/qualify_private_jobs.py", "seed"], job_env, report="private-jobs.log")
            run_python(["scripts/qualify_private_scoring.py", "seed"], job_env, report="private-scoring.log")
            # Quiesce all owned job processes, then remove the actual broker and its
            # anonymous AOF volume. PostgreSQL metadata remains the outbox authority.
            command(["docker", "rm", "-f", "-v", job_broker])
            run_python(["scripts/qualify_private_jobs.py", "broker-down"], job_env, report="private-jobs.log")
            run_python(["scripts/qualify_private_scoring.py", "broker-down"], job_env, report="private-scoring.log")
            jobs_dump = command(["docker", "exec", db, "pg_dump", "-U", "declarai_fixture_admin", "-Fc", "declarai_fixture"])
            command(["docker", "exec", db, "createdb", "-U", "declarai_fixture_admin", "-O", "declarai_fixture_app", "declarai_fixture_jobs_restored"])
            command(["docker", "exec", "-i", db, "pg_restore", "--exit-on-error", "--no-owner", "--no-acl", "-U", "declarai_fixture_app", "-d", "declarai_fixture_jobs_restored"], data=jobs_dump)
            (fixture / "restored-job-artifacts").mkdir()
            shutil.copytree(fixture / "artifacts", fixture / "restored-job-artifacts", dirs_exist_ok=True)
            start_job_broker()  # Empty broker, no restoration of Celery/AOF queues.
            run_python(["scripts/qualify_private_jobs.py", "verify"], job_env, report="private-jobs.log")
            run_python(["scripts/qualify_private_scoring.py", "verify"], job_env, report="private-scoring.log")
            restored_job_env = {**job_env, "DECLARAI_DB_NAME": "declarai_fixture_jobs_restored",
                                "DECLARAI_MEDIA_ROOT": str(fixture / "restored-job-artifacts")}
            run_python(["scripts/qualify_private_jobs.py", "verify"], restored_job_env, report="private-jobs.log")
            run_python(["scripts/qualify_private_scoring.py", "verify"], restored_job_env, report="private-scoring.log")
            run_python(["scripts/qualify_private_scoring.py", "prepare-recovery"], restored_job_env, report="private-scoring.log")
            run_python(["scripts/qualify_private_jobs.py", "recover"], restored_job_env, report="private-jobs.log")
            run_python(["scripts/qualify_private_scoring.py", "recover"], restored_job_env, report="private-scoring.log")
            # Only synthetic export evidence is retained; sessions/leases, TLS keys,
            # credentials and dumps stay in the owner's temporary directory.
            shutil.copytree(fixture / "recovered-scoring", reports / "recovered-scoring", dirs_exist_ok=True)
            test_env = {
                "DECLARAI_RUNTIME_PROFILE": "development",
                "DJANGO_DEBUG": "true",
                "DJANGO_ALLOWED_HOSTS": "*",
                "DECLARAI_DB_NAME": "declarai_fixture_tests",
                "DECLARAI_DB_USER": "declarai_fixture_tests",
                "DECLARAI_DB_PASSWORD_FILE": str(fixture / "test-password"),
            }
            (fixture / "test-password").write_text(test_password)
            (fixture / "test-password").chmod(0o600)
            run_python(
                ['backend/manage.py', 'migrate', '--noinput'], test_env, report='native-jobs.log'
            )
            run_python(
                ['scripts/qualify_native_jobs.py'],
                {**test_env, 'DECLARAI_JOB_BROKER_URL': env['REDIS_URL'].rsplit('/', 1)[0] + '/1'},
                report='native-jobs.log',
            )
            relative = reports.relative_to(ROOT).as_posix()
            run_python(
                [
                    "-m",
                    "pytest",
                    "-m",
                    "unit or functional or regression or integration or uat",
                    "--tb=short",
                    "--durations=5",
                    f"--junitxml=../{relative}/postgresql.xml",
                    "--cov",
                    f"--cov-report=xml:../{relative}/postgresql-coverage.xml",
                    "--cov-report=term-missing",
                    "--cov-fail-under=50",
                ],
                test_env,
                report="postgresql.log",
            )
            version = (
                command(["docker", "exec", db, "postgres", "--version"])
                .decode()
                .strip()
            )
            summary = {
                "postgresql": version,
                "image_id": command(["docker", "inspect", "-f", "{{.Image}}", db])
                .decode()
                .strip(),
                "private_tls_session_api": "passed",
                "wrong_ca": "rejected",
                "wrong_hostname": "rejected",
                "restart_persistence": "passed",
                "quiescent_database_artifact_restore": "passed",
                "full_postgresql_suite": "passed",
                "private_job_broker_tls_authentication": "passed",
                "job_wrong_ca_hostname_credentials": "blocked",
                "actual_job_broker_loss": "passed",
                "quiescent_job_database_artifact_restore_empty_broker": "passed",
                "natural_orphan_lease_recovery": "passed",
                "private_native_scoring_restore_parity": "passed",
                "private_scoring_full_receipts_and_duplicate_completion": "passed",
                "private_scoring_changed_missing_inputs_revocation": "blocked",
                "private_scoring_source_scope_fault": "blocked",
                "production_deployment_recovery": "not_qualified",
            }
            (reports / "postgresql-summary.json").write_text(
                json.dumps(summary, indent=2) + "\n"
            )
            print(json.dumps(summary))
        finally:
            # Only exact random names created by this invocation are eligible for cleanup.
            for name in [runner, db, redis, job_broker]:
                subprocess.run(
                    ["docker", "rm", "-f", "-v", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            subprocess.run(
                ["docker", "network", "rm", network],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


if __name__ == "__main__":
    main()
