"""Private startup must fail before an invalid configuration can serve requests."""

from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from backend.runtime_config import load_runtime

pytestmark = pytest.mark.unit
DEV_KEY = "django-insecure-synthetic-development-key-not-a-real-credential"
KEY = "synthetic-private-key-that-is-distinct-and-long-for-runtime-tests-123456"


@pytest.fixture
def private(tmp_path):
    media = tmp_path / "artifacts"
    media.mkdir()
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic CA: runtime parser does not authenticate certificates")
    return {
        "DECLARAI_RUNTIME_PROFILE": "private",
        "DJANGO_SECRET_KEY": KEY,
        "DJANGO_ALLOWED_HOSTS": "api.private.test,127.0.0.1",
        "DECLARAI_ALLOWED_ORIGINS": "https://console.private.test",
        "DECLARAI_MEDIA_ROOT": str(media),
        "DECLARAI_DB_NAME": "declarai",
        "DECLARAI_DB_USER": "app",
        "DECLARAI_DB_PASSWORD": "synthetic-db-password",
        "DECLARAI_DB_HOST": "postgres",
        "DECLARAI_DB_SSLROOTCERT": str(ca),
    }


def test_default_development_preserves_sqlite_and_local_session_workflow(tmp_path):
    result = load_runtime(tmp_path, DEV_KEY, {})
    assert result["DEBUG"] is True
    assert result["SECRET_KEY"] == DEV_KEY
    assert result["DATABASES"]["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert result["DATABASES"]["default"]["NAME"] == tmp_path / "db.sqlite3"
    assert result["SESSION_COOKIE_SECURE"] is False
    assert "http://localhost:4300" in result["CORS_ALLOWED_ORIGINS"]
    assert result["SECURE_PROXY_SSL_HEADER"] is None


def test_private_requires_exact_configuration_and_verified_database(private, tmp_path):
    result = load_runtime(tmp_path, DEV_KEY, private)
    assert result["DEBUG"] is False and result["SECURE_SSL_REDIRECT"] is True
    assert result["SESSION_COOKIE_SECURE"] is True and result["CSRF_COOKIE_SECURE"] is True
    assert result["SECRET_KEY"] != DEV_KEY and result["MEDIA_ROOT"].is_absolute()
    assert result["ALLOWED_HOSTS"] == ["api.private.test", "127.0.0.1"]
    assert result["DATABASES"]["default"]["OPTIONS"] == {
        "sslmode": "verify-full",
        "sslrootcert": private["DECLARAI_DB_SSLROOTCERT"],
        "connect_timeout": 10,
    }
    assert result["DATABASES"]["default"]["CONN_HEALTH_CHECKS"] is True
    assert result["SECURE_PROXY_SSL_HEADER"] is None
    assert result["SECURE_HSTS_INCLUDE_SUBDOMAINS"] is False
    assert result["SECURE_HSTS_PRELOAD"] is False


@pytest.mark.parametrize(
    "name",
    [
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "DECLARAI_ALLOWED_ORIGINS",
        "DECLARAI_MEDIA_ROOT",
        "DECLARAI_DB_NAME",
        "DECLARAI_DB_USER",
        "DECLARAI_DB_HOST",
        "DECLARAI_DB_PASSWORD",
        "DECLARAI_DB_SSLROOTCERT",
    ],
)
def test_missing_private_fields_stop_without_sqlite_fallback(private, tmp_path, name):
    del private[name]
    with pytest.raises(ImproperlyConfigured):
        load_runtime(tmp_path, DEV_KEY, private)


@pytest.mark.parametrize(
    "name,value",
    [
        ("DECLARAI_RUNTIME_PROFILE", "production-typo"),
        ("DJANGO_DEBUG", "true"),
        ("DJANGO_DEBUG", "yes"),
        ("DJANGO_SECRET_KEY", DEV_KEY),
        ("DJANGO_SECRET_KEY", "short"),
        ("DJANGO_SECRET_KEY", "a" * 64),
        ("DJANGO_ALLOWED_HOSTS", "[:::]"),
        ("DJANGO_ALLOWED_HOSTS", "bad..test"),
        ("DJANGO_ALLOWED_HOSTS", "-bad.test"),
        ("DJANGO_ALLOWED_HOSTS", "999.0.0.1"),
        ("DECLARAI_DB_HOST", "postgres,other"),
        ("DECLARAI_DB_HOST", "postgres,"),
        ("DECLARAI_DB_HOST", " postgres "),
        ("DJANGO_ALLOWED_HOSTS", "*"),
        ("DJANGO_ALLOWED_HOSTS", ".private.test"),
        ("DJANGO_ALLOWED_HOSTS", "api.private.test:443"),
        ("DECLARAI_ALLOWED_ORIGINS", "http://console.private.test"),
        ("DECLARAI_ALLOWED_ORIGINS", "https://*.private.test"),
        ("DECLARAI_ALLOWED_ORIGINS", "https://user:secret@console.private.test"),
        ("DECLARAI_ALLOWED_ORIGINS", "https://console.private.test/path"),
        ("DECLARAI_ALLOWED_ORIGINS", "https://console.private.test?query=x"),
        ("DECLARAI_ALLOWED_ORIGINS", "https://console.private.test:99999"),
        ("DECLARAI_ALLOWED_ORIGINS", "https://console.\tprivate.test"),
        ("DECLARAI_ALLOWED_ORIGINS", "https://console.private.test:0"),
        ("DECLARAI_DB_ENGINE", "sqlite"),
        ("DECLARAI_DB_ENGINE", "postgres"),
        ("DECLARAI_DB_SSLMODE", "disable"),
        ("DECLARAI_DB_SSLMODE", "require"),
        ("DECLARAI_DB_SSLMODE", "verify-ca"),
        ("DECLARAI_DB_SSLMODE", "prefer"),
        ("DECLARAI_DB_HOST", "postgres:///local"),
        ("DECLARAI_DB_HOST", "/var/run/postgresql"),
        ("DECLARAI_DB_PORT", "0"),
        ("DECLARAI_DB_PORT", "65536"),
        ("DECLARAI_DB_PORT", "5432oops"),
        ("DJANGO_HSTS_SECONDS", "-1"),
        ("DJANGO_HSTS_SECONDS", "31536001"),
        ("DJANGO_TRUST_PROXY_TLS", "maybe"),
    ],
)
def test_contradictory_or_unsupported_private_values_stop(private, tmp_path, name, value):
    private[name] = value
    with pytest.raises(ImproperlyConfigured) as error:
        load_runtime(tmp_path, DEV_KEY, private)
    assert private["DECLARAI_DB_PASSWORD"] not in str(error.value)
    assert KEY not in str(error.value)


@pytest.mark.parametrize("root", ["", "/", "relative", "/missing-p16-artifact-directory"])
def test_invalid_private_artifact_directory_blocks(private, tmp_path, root):
    private["DECLARAI_MEDIA_ROOT"] = root
    with pytest.raises(ImproperlyConfigured, match="DECLARAI_MEDIA_ROOT"):
        load_runtime(tmp_path, DEV_KEY, private)


def test_secret_file_support_and_no_credential_echo(private, tmp_path):
    for name in ["DJANGO_SECRET_KEY", "DECLARAI_DB_PASSWORD"]:
        value = private.pop(name)
        secret = tmp_path / name
        secret.write_text(value + "\n")
        private[name + "_FILE"] = str(secret)
    result = load_runtime(tmp_path, DEV_KEY, private)
    assert result["SECRET_KEY"] == KEY
    assert result["DATABASES"]["default"]["PASSWORD"] == "synthetic-db-password"
    private["DJANGO_SECRET_KEY"] = "a credential that must never appear in an exception"
    with pytest.raises(ImproperlyConfigured) as error:
        load_runtime(tmp_path, DEV_KEY, private)
    assert private["DJANGO_SECRET_KEY"] not in str(error.value)


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "oversized", "binary", "empty", "multiline"])
def test_invalid_secret_files_fail_closed(private, tmp_path, kind):
    path = tmp_path / "secret"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(Path(private["DECLARAI_DB_SSLROOTCERT"]))
    elif kind == "oversized":
        path.write_text("x" * 4097)
    elif kind == "binary":
        path.write_bytes(b"\xff")
    elif kind == "empty":
        path.write_text("")
    elif kind == "multiline":
        path.write_text(KEY + "\nsecond-line")
    del private["DJANGO_SECRET_KEY"]
    private["DJANGO_SECRET_KEY_FILE"] = str(path)
    with pytest.raises(ImproperlyConfigured):
        load_runtime(tmp_path, DEV_KEY, private)


def test_private_artifact_symlink_is_not_an_implicit_storage_root(private, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(private["DECLARAI_MEDIA_ROOT"], target_is_directory=True)
    private["DECLARAI_MEDIA_ROOT"] = str(alias)
    with pytest.raises(ImproperlyConfigured):
        load_runtime(tmp_path, DEV_KEY, private)


def test_development_postgres_is_explicit_and_proxy_trust_is_opt_in(private, tmp_path):
    private["DECLARAI_RUNTIME_PROFILE"] = "development"
    private["DECLARAI_DB_ENGINE"] = "postgresql"
    private["DECLARAI_DB_SSLMODE"] = "disable"
    private["DJANGO_TRUST_PROXY_TLS"] = "true"
    result = load_runtime(tmp_path, DEV_KEY, private)
    assert result["DATABASES"]["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert result["SECURE_PROXY_SSL_HEADER"] == ("HTTP_X_FORWARDED_PROTO", "https")


def test_postgres_fields_cannot_silently_use_development_sqlite(tmp_path):
    with pytest.raises(ImproperlyConfigured, match="cannot silently select SQLite"):
        load_runtime(tmp_path, DEV_KEY, {"DECLARAI_DB_HOST": "postgres"})


def test_private_ipv6_host_is_normalized_for_libpq(private, tmp_path):
    private["DJANGO_ALLOWED_HOSTS"] = "[::1],api.private.test"
    private["DECLARAI_DB_HOST"] = "[::1]"
    result = load_runtime(tmp_path, DEV_KEY, private)
    assert result["ALLOWED_HOSTS"][0] == "[::1]"
    assert result["DATABASES"]["default"]["HOST"] == "::1"


@pytest.mark.parametrize("profile", ["private", "typo"])
def test_live_reload_entrypoint_blocks_before_any_python_command(profile, tmp_path):
    import os
    import subprocess

    entrypoint = Path(__file__).resolve().parents[3] / "docker/backend-entrypoint.sh"
    stub = tmp_path / "python"
    stub.write_text("#!/bin/sh\necho PYTHON_MUST_NOT_RUN\nexit 9\n")
    stub.chmod(0o755)
    result = subprocess.run(
        ["/bin/sh", str(entrypoint)],
        capture_output=True,
        text=True,
        env={**os.environ, "DECLARAI_RUNTIME_PROFILE": profile, "PATH": str(tmp_path)},
        timeout=5,
    )
    assert result.returncode == 1
    assert "development only" in result.stderr
    assert "PYTHON_MUST_NOT_RUN" not in result.stdout
