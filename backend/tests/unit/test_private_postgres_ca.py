"""Selected public PostgreSQL anchors must pass bounded preflight."""

import os
import traceback
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from backend.runtime_config import private_postgres_tls_options, load_runtime
from tests.unit.test_private_cache import cache_env  # noqa: F401
from tests.unit.test_runtime_config import private, DEV_KEY  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("mode", [0o400, 0o600, 0o444, 0o644])
def test_public_ca_permissions_are_compatible(cache_env, mode):
    path = Path(cache_env["DECLARAI_CACHE_CA_FILE"])
    path.chmod(mode)
    options = private_postgres_tls_options(path)
    assert options["sslrootcert"] == str(path)
    assert options["sslmode"] == "verify-full"


@pytest.mark.parametrize("fault", [
    "relative", "symlink", "hardlink", "fifo", "directory", "missing",
    "mode_622", "mode_666", "empty", "oversized", "binary", "malformed",
])
def test_unsafe_ca_is_rejected_without_path_or_driver_diagnostics(cache_env, tmp_path, monkeypatch, fault):
    path = Path(cache_env["DECLARAI_CACHE_CA_FILE"])
    selected = path
    if fault == "relative":
        monkeypatch.chdir(tmp_path)
        selected = Path(path.name)
    elif fault == "symlink":
        selected = tmp_path / "alias"
        selected.symlink_to(path)
    elif fault == "hardlink":
        os.link(path, tmp_path / "alias")
    elif fault.startswith("mode_"):
        path.chmod(int(fault.removeprefix("mode_"), 8))
    elif fault in {"fifo", "directory", "missing"}:
        path.unlink()
        if fault == "fifo":
            os.mkfifo(path)
        elif fault == "directory":
            path.mkdir()
    else:
        path.chmod(0o600)
        path.write_bytes({"empty": b"", "oversized": b"X" * 65537,
                          "binary": b"\xff", "malformed": b"not a certificate"}[fault])
    with pytest.raises(ImproperlyConfigured) as error:
        private_postgres_tls_options(selected)
    assert str(error.value).startswith("DECLARAI_DB_SSLROOTCERT: use a stable absolute regular single-link PEM CA file")
    assert str(tmp_path) not in "".join(traceback.format_exception(error.value))
    assert "not a certificate" not in str(error.value)


@pytest.mark.parametrize("fault", ["bytes", "mode", "link"])
def test_interread_change_rejected_even_with_coarse_timestamps(cache_env, tmp_path, monkeypatch, fault):
    path = Path(cache_env["DECLARAI_CACHE_CA_FILE"])
    before = path.stat()
    actual_fstat, actual_fdopen = os.fstat, os.fdopen

    class CoarseTimes:
        st_mtime_ns, st_ctime_ns = before.st_mtime_ns, before.st_ctime_ns

        def __init__(self, current):
            self.current = current

        def __getattr__(self, name):
            return getattr(self.current, name)

    def fstat(fd):
        current = actual_fstat(fd)
        return CoarseTimes(current) if (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino) else current

    class ChangedRead:
        def __init__(self, stream):
            self.stream, self.changed = stream, False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def seek(self, offset):
            return self.stream.seek(offset)

        def read(self, limit):
            data = self.stream.read(limit)
            current = actual_fstat(self.fileno())
            if not self.changed and (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino):
                self.changed = True
                if fault == "bytes":
                    path.chmod(0o600)
                    path.write_bytes(b"X" + data[1:])
                    path.chmod(0o400)
                elif fault == "mode":
                    path.chmod(0o666)
                else:
                    os.link(path, tmp_path / "alias")
            return data

    monkeypatch.setattr(os, "fstat", fstat)
    monkeypatch.setattr(os, "fdopen", lambda *a, **k: ChangedRead(actual_fdopen(*a, **k)))
    with pytest.raises(ImproperlyConfigured, match="DECLARAI_DB_SSLROOTCERT"):
        private_postgres_tls_options(path)


@pytest.mark.parametrize("fault", ["symlink", "malformed"])
def test_runtime_blocks_unsafe_selected_ca_before_database_start(private, cache_env, tmp_path, fault):
    path = Path(cache_env["DECLARAI_CACHE_CA_FILE"])
    if fault == "symlink":
        alias = tmp_path / "selected-alias"
        alias.symlink_to(path)
        path = alias
    else:
        path.chmod(0o600)
        path.write_text("malformed certificate")
    private["DECLARAI_DB_SSLROOTCERT"] = str(path)
    with pytest.raises(ImproperlyConfigured, match="DECLARAI_DB_SSLROOTCERT"):
        load_runtime(tmp_path, DEV_KEY, private)


def test_development_verified_tls_preserves_existing_path_configuration(private, tmp_path):
    private["DECLARAI_RUNTIME_PROFILE"] = "development"
    private["DECLARAI_DB_ENGINE"] = "postgresql"
    private["DECLARAI_DB_SSLMODE"] = "verify-full"
    assert load_runtime(tmp_path, DEV_KEY, private)["DATABASES"]["default"]["OPTIONS"] == {
        "sslmode": "verify-full", "connect_timeout": 10,
        "sslrootcert": private["DECLARAI_DB_SSLROOTCERT"],
    }


@pytest.mark.parametrize("fault", ["platform", "uid", "root", "name"])
def test_ca_qualification_refuses_nonfixture_scope_before_effects(monkeypatch, fault):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    import qualify_private_postgres_ca as qualifier
    import private_dependency_start as startup

    monkeypatch.setattr(sys, "platform", "darwin" if fault == "platform" else "linux")
    monkeypatch.setattr(startup.os, "geteuid", lambda: 1 if fault == "uid" else 0)
    parent = "/tmp" if fault == "root" else "/srv"
    name = "customer" if fault == "name" else "declarai-p37-" + "a" * 32
    with pytest.raises(startup.checker.planner.PlanError, match="private_postgres_ca_fixture_scope_required"):
        qualifier.qualify({"request": {"root": f"{parent}/{name}/installation"}}, {}, lambda _: pytest.fail("out of scope Docker call"))
