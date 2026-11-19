#!/usr/bin/env python3
"""Own a disposable TLS database, verify a quiescent restore, then run pytest.

Requires Docker and openssl. Secrets, dump and session state live outside the
checkout and are removed on exit. No existing installation is read or changed.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_DATA_DIRECTORY = "/var/lib/postgresql/data"  # Pinned PostgreSQL 17 image.
TEST_DATABASE_TMPFS = POSTGRES_DATA_DIRECTORY + ":rw,nosuid,nodev,noexec,size=1g"
TEST_DATABASE_TMPFS_BYTES = 1024 ** 3


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


def database_settings(name):
    sql = (
        "SELECT name || '=' || setting FROM pg_catalog.pg_settings WHERE name IN "
        "('fsync', 'full_page_writes', 'ssl', 'synchronous_commit') ORDER BY name"
    )
    rows = command(["docker", "exec", name, "psql", "-At", "-v", "ON_ERROR_STOP=1",
                    "-U", "declarai_fixture_admin", "-d", "postgres", "-c", sql])
    return dict(row.split("=", 1) for row in rows.decode().splitlines())


def verify_test_storage(name, expected_image):
    actual_image = command(["docker", "inspect", "-f", "{{.Image}}", name]).decode().strip()
    mount_info = command(["docker", "exec", name, "cat", "/proc/self/mountinfo"]).decode()
    storage = []
    for line in mount_info.splitlines():
        mount, filesystem = line.split(" - ", 1)
        if mount.split()[4] == POSTGRES_DATA_DIRECTORY:
            storage.append(filesystem.split()[0])
    disk_usage = command(["docker", "exec", name, "df", "-kP", POSTGRES_DATA_DIRECTORY]).decode()
    capacity = int(disk_usage.splitlines()[-1].split()[1]) * 1024
    if actual_image != expected_image or storage != ["tmpfs"] or capacity != TEST_DATABASE_TMPFS_BYTES:
        raise RuntimeError("Native pytest PostgreSQL image or scratch storage differs from its fixture contract.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runner-image", help="Local core test image; omitted in host Python CI"
    )
    parser.add_argument("--reports", default="test-reports/postgresql")
    parser.add_argument("--private-api-image", help="Exact local private API image sha256; adds real fixed-image socket smoke")
    parser.add_argument("--private-ingress-image", help="Exact local TLS ingress image for api.private.test:8443 with 1 MiB body limit")
    parser.add_argument("--private-frontend-browser", action="store_true", help="Qualify baked frontend with installed Node 24/Playwright Chromium")
    parser.add_argument("--postgres-image", help="Exact local offline PostgreSQL image ID; never pulled")
    parser.add_argument("--redis-image", help="Exact local offline Redis image ID; never pulled")
    args = parser.parse_args()
    if args.private_ingress_image and not args.private_api_image:
        parser.error("Private ingress qualification requires the fixed private API.")
    if args.private_frontend_browser and not args.private_ingress_image:
        parser.error("Private browser qualification requires the fixed private ingress.")
    for image in [args.postgres_image, args.redis_image]:
        if image is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            parser.error("Offline fixture images must use exact sha256 image identities.")

    def image_args(image, default):
        return ["--pull", "never", image] if image else [default]
    reports = (ROOT / args.reports).resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        parser.error("Reports must be inside the ignored test-reports directory.")
    reports.mkdir(parents=True, exist_ok=True)
    suite_database_report = reports / "postgresql-suite-database.json"
    suite_database_report.unlink(missing_ok=True)
    token = uuid.uuid4().hex[:12]
    network, db, redis, runner, job_broker, test_db = (
        f"declarai-fixture-{token}-{suffix}"
        for suffix in ("net", "db", "redis", "runner", "job-broker", "test-db")
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
                     "--network-alias", "job-broker", "-p", "127.0.0.1::6379", *image_args(args.redis_image, "redis:7-alpine"),
                     "sh", "-c", "chown -R redis:redis /fixture; exec docker-entrypoint.sh redis-server /fixture/job-broker.conf"])
            command(["docker", "cp", str(job_tls), job_broker + ":/fixture"])
            command(["docker", "start", job_broker])
            port = command(["docker", "port", job_broker, "6379/tcp"]).decode().strip().rsplit(":", 1)[1]
            host = "job-broker:6379" if args.runner_image else "127.0.0.1:" + port
            (fixture / "job-broker-url").write_text("rediss://:" + broker_password + "@" + host + "/1")
            (fixture / "job-broker-url").chmod(0o600)
            return port

        sql = (
            f"CREATE ROLE declarai_fixture_app LOGIN PASSWORD '{app_password}';\n"
            "CREATE DATABASE declarai_fixture OWNER declarai_fixture_app;\n"
            f"CREATE ROLE declarai_fixture_tests LOGIN CREATEDB PASSWORD '{test_password}';\n"
            "CREATE DATABASE declarai_fixture_tests OWNER declarai_fixture_tests;\n"
        )

        def start_database(name, image, source, *, tmpfs=False):
            command(
                [
                    "docker",
                    "create",
                    "--name",
                    name,
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
                    *(["--tmpfs", TEST_DATABASE_TMPFS] if tmpfs else []),
                    *image_args(image, "postgres:17-alpine"),
                    "sh",
                    "-c",
                    (
                        "chown -R postgres:postgres /fixture; chmod 600 /fixture/server.key; "
                        "exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/fixture/server.crt -c ssl_key_file=/fixture/server.key"
                    ),
                ]
            )
            command(["docker", "cp", str(source), name + ":/fixture"])
            command(["docker", "start", name])

        def initialize_database(name):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        name,
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-U",
                        "declarai_fixture_admin",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
                if result.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Disposable PostgreSQL did not become ready.")
            command(
                [
                    "docker",
                    "exec",
                    "-i",
                    name,
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
            return (
                command(["docker", "port", name, "5432/tcp"])
                .decode()
                .strip()
                .rsplit(":", 1)[1]
            )

        try:
            command(["docker", "network", "create", network])
            start_database(db, args.postgres_image, fixture)
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
                    *image_args(args.redis_image, "redis:7-alpine"),
                ]
            )
            job_broker_port = start_job_broker()
            db_port = initialize_database(db)
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
                if arguments[:2] == ["-m", "pytest"] and args.private_api_image and not args.runner_image:
                    from private_native_suite import prepare

                    prefix, native_receipt = prepare(
                        args.private_api_image, root=ROOT, fixture=fixture,
                        name=runner, environment=current, fixture_network=network,
                    )
                    # The controller retains the original 900-second child cap.
                    # Every selected case, branch measurement, fit and fold runs
                    # under the application's exact native interpreter image.
                    native_dependencies = command(
                        [*prefix, str(ROOT / "scripts/verify_private_dependency_profile.py")],
                        timeout=60,
                    )
                    (reports / "native-suite-dependency-profile.json").write_bytes(native_dependencies)
                    scratch_address = command([
                        "docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", test_db
                    ]).decode().strip()
                    native_receipt["database_session"] = json.loads(command(
                        [*prefix, str(ROOT / "scripts/private_native_suite.py"), "--verify-database", scratch_address],
                        timeout=60,
                    ))
                    (reports / "native-suite-runtime.json").write_text(json.dumps(native_receipt, indent=2) + "\n")
                    argv = [*prefix, *arguments]
                    cwd = ROOT
                elif args.runner_image:
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
                qualify_image(args.private_api_image, network, fixture, env, reports, args.private_ingress_image, args.private_frontend_browser)
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
            run_python(["scripts/qualify_private_training_search.py"], job_env, report="private-training-search.log")
            run_python(["scripts/qualify_private_native_candidate.py"], job_env, report="private-native-candidate.log")
            run_python(["scripts/qualify_private_native_assessment.py"], job_env, report="private-native-assessment.log")
            run_python(["scripts/qualify_private_native_operations.py"], job_env, report="private-native-operations.log")
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
            run_python(["scripts/qualify_private_native_assessment.py", "verify-restored"], restored_job_env, report="private-native-assessment.log")
            run_python(["scripts/qualify_private_native_operations.py", "verify-restored"], restored_job_env, report="private-native-operations.log")
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
            version = command(["docker", "exec", db, "postgres", "--version"]).decode().strip()
            postgres_image = command(["docker", "inspect", "-f", "{{.Image}}", db]).decode().strip()
            suite_storage = "disposable_volume"
            if args.private_api_image and not args.runner_image:
                # The persistent fixture has already qualified restart, broker
                # loss and restore. Only the isolated native test suite switches
                # to bounded tmpfs. Preserve the base test database's state and
                # the role and TLS settings from the disk-backed qualification.
                server_settings = database_settings(db)
                test_dump = command(["docker", "exec", db, "pg_dump", "-U", "declarai_fixture_admin",
                                     "-Fc", "declarai_fixture_tests"])
                command(["docker", "stop", "--time", "10", db], timeout=20)
                test_tls = fixture / "test-postgres-tls"
                test_tls.mkdir(mode=0o700)
                for name in ("admin-password", "server.crt", "server.key"):
                    shutil.copy2(fixture / name, test_tls / name)
                start_database(test_db, postgres_image, test_tls, tmpfs=True)
                test_env["DECLARAI_DB_PORT"] = initialize_database(test_db)
                verify_test_storage(test_db, postgres_image)
                if database_settings(test_db) != server_settings or server_settings.get("ssl") != "on":
                    raise RuntimeError("Native pytest PostgreSQL server settings differ from the disk fixture.")
                command(["docker", "exec", "-i", test_db, "pg_restore", "--exit-on-error",
                         "-U", "declarai_fixture_admin", "-d", "declarai_fixture_tests"], data=test_dump)
                run_python(query, test_env, report="postgresql-suite-tls.log")
                # The native test container joins the owned bridge. Its credentials
                # and verify-full policy apply on the direct PostgreSQL listener.
                test_env.update(DECLARAI_DB_HOST="postgres", DECLARAI_DB_PORT="5432",
                                REDIS_URL=f"redis://{redis}:6379/0")
                suite_database_report.write_text(json.dumps({
                    "schema": "private_native_postgresql_fixture_v1",
                    "postgresql_image_id": postgres_image,
                    "storage": "tmpfs",
                    "pgdata": POSTGRES_DATA_DIRECTORY,
                    "tmpfs_limit_bytes": TEST_DATABASE_TMPFS_BYTES,
                    "sslmode": env["DECLARAI_DB_SSLMODE"],
                    "server_settings": server_settings,
                    "disk_fixture_stopped": True,
                    "restored_test_database": True,
                    "restored_dump_sha256": hashlib.sha256(test_dump).hexdigest(),
                }, indent=2) + "\n")
                suite_storage = "disposable_tmpfs_1gib"
            relative = reports.relative_to(ROOT).as_posix()
            scratch_test_database = suite_storage == "disposable_tmpfs_1gib"
            run_python(
                [
                    "-m",
                    "pytest",
                    "-p", "tests.postgresql_parallel",
                    # Use the existing two-CPU budget; pytest-django gives each
                    # worker its own migrated database. Keep each file together
                    # and fail on worker loss rather than restarting tests.
                    "-n", "2",
                    "--dist=loadfile",
                    "--max-worker-restart=0",
                    # Still create and migrate fresh worker databases. Dispose
                    # of both databases with their verified scratch container.
                    *(["--reuse-db", "--create-db"] if scratch_test_database else []),
                    f"--postgresql-isolation-report=../{relative}/postgresql-isolation.json",
                    "-m",
                    "unit or functional or regression or integration or uat",
                    "--tb=short",
                    "--durations=5",
                    f"--junitxml=../{relative}/postgresql.xml",
                    "--cov",
                    f"--cov-report=xml:../{relative}/postgresql-coverage.xml",
                    "--cov-fail-under=50",
                ],
                test_env,
                report="postgresql.log",
            )
            if scratch_test_database:
                command(["docker", "rm", "-f", "-v", test_db], timeout=30)
            summary = {
                "postgresql": version,
                "image_id": postgres_image,
                "redis_image_id": command(["docker", "inspect", "-f", "{{.Image}}", job_broker]).decode().strip(),
                "dependency_selection": "exact_local_no_pull" if args.postgres_image and args.redis_image else "legacy_fixture_defaults",
                "private_tls_session_api": "passed",
                "wrong_ca": "rejected",
                "wrong_hostname": "rejected",
                "restart_persistence": "passed",
                "quiescent_database_artifact_restore": "passed",
                "full_postgresql_suite": "passed",
                "postgresql_suite_storage": suite_storage,
                "postgresql_suite_scratch_removed": scratch_test_database,
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
            for name in [runner, test_db, db, redis, job_broker]:
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
