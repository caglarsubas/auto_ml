"""Private configuration cannot silently adopt unsafe or changing secrets."""

import os
import traceback

import pytest
from django.core.exceptions import ImproperlyConfigured

from backend.runtime_config import _secret, load_runtime
from execution_jobs.config import load_job_config
from tests.unit.test_runtime_config import private, DEV_KEY  # noqa: F401
from tests.unit.test_private_cache import cache_env  # noqa: F401

pytestmark = pytest.mark.unit
VALUE = "synthetic-private-secret-0123456789-abcdefghijklmnopqrstuvwxyz"
NAMES = ["DJANGO_SECRET_KEY", "DECLARAI_DB_PASSWORD", "DECLARAI_JOB_BROKER_URL"]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("mode", [0o400, 0o600])
def test_private_file_captures_exact_single_line(tmp_path, name, mode):
    path = tmp_path / "secret"
    path.write_text(VALUE + "\r\n")
    path.chmod(mode)
    captured = _secret({name + "_FILE": str(path)}, name, private=True)
    assert captured == VALUE
    path.chmod(0o600)
    path.write_text("later replacement cannot alter captured value")
    assert captured == VALUE


@pytest.mark.parametrize("fault", ["relative", "mode_644", "mode_640", "mode_444", "mode_700", "hardlink", "symlink", "fifo", "directory", "empty", "oversized", "binary", "multiline"])
def test_private_invalid_delivery_fails_with_static_error(tmp_path, monkeypatch, fault):
    path = tmp_path / VALUE
    path.write_text(VALUE)
    path.chmod(0o600)
    selected = str(path)
    if fault == "relative":
        monkeypatch.chdir(tmp_path)
        selected = path.name
    elif fault.startswith("mode_"):
        path.chmod(int(fault.removeprefix("mode_"), 8))
    elif fault == "hardlink":
        os.link(path, tmp_path / "alias")
    elif fault in {"symlink", "fifo", "directory"}:
        path.unlink()
        if fault == "symlink":
            path.symlink_to(tmp_path / "unavailable")
        elif fault == "fifo":
            os.mkfifo(path, 0o600)
        else:
            path.mkdir()
    else:
        path.write_bytes({"empty": b"", "oversized": b"x" * 4097, "binary": b"\xff", "multiline": VALUE.encode() + b"\nsecond-line"}[fault])
    with pytest.raises(ImproperlyConfigured) as error:
        _secret({"DJANGO_SECRET_KEY_FILE": selected}, "DJANGO_SECRET_KEY", private=True)
    assert VALUE not in str(error.value)
    assert str(tmp_path) not in str(error.value)
    assert VALUE not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("fault,coarse_timestamps", [
    ("same_size", False), ("truncate", False), ("grow", False), ("mode", False), ("link", False), ("replace", False),
    ("same_size", True),
])
def test_change_during_capture_cannot_become_accepted_configuration(tmp_path, monkeypatch, fault, coarse_timestamps):
    path = tmp_path / "secret"
    path.write_text(VALUE)
    path.chmod(0o600)
    original = os.fdopen
    if coarse_timestamps:
        actual_fstat, stamp = os.fstat, path.stat()

        class CoarseTimes:
            st_mtime_ns, st_ctime_ns = stamp.st_mtime_ns, stamp.st_ctime_ns

            def __init__(self, current):
                self.current = current

            def __getattr__(self, name):
                return getattr(self.current, name)

        monkeypatch.setattr(os, "fstat", lambda fd: CoarseTimes(actual_fstat(fd)))

    class ChangingRead:
        def __init__(self, stream):
            self.stream = stream
            self.changed = False

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
            if self.changed:
                return data
            self.changed = True
            if fault == "same_size":
                path.write_text("Z" * len(VALUE))
            elif fault == "truncate":
                path.write_text("short")
            elif fault == "grow":
                path.write_text(VALUE + "longer")
            elif fault == "mode":
                path.chmod(0o640)
            elif fault == "link":
                os.link(path, tmp_path / "alias")
            else:
                replacement = tmp_path / "replacement"
                replacement.write_text("new credential")
                replacement.chmod(0o600)
                os.replace(replacement, path)
            return data

    monkeypatch.setattr(os, "fdopen", lambda *a, **k: ChangingRead(original(*a, **k)))
    with pytest.raises(ImproperlyConfigured, match="stable absolute single-link"):
        _secret({"DECLARAI_DB_PASSWORD_FILE": str(path)}, "DECLARAI_DB_PASSWORD", private=True)


@pytest.mark.parametrize("name", ["DJANGO_SECRET_KEY", "DECLARAI_DB_PASSWORD"])
def test_private_runtime_applies_capture_boundary(private, tmp_path, name):
    path = tmp_path / "credential"
    path.write_text(private.pop(name))
    path.chmod(0o644)
    private[name + "_FILE"] = str(path)
    with pytest.raises(ImproperlyConfigured, match="mode 0400 or 0600"):
        load_runtime(tmp_path, DEV_KEY, private)
    path.chmod(0o600)
    assert load_runtime(tmp_path, DEV_KEY, private)["DECLARAI_RUNTIME_PROFILE"] == "private"


def test_private_broker_uses_the_same_file_boundary(cache_env, tmp_path):
    path = tmp_path / "job-broker-url"
    value = "rediss://:" + VALUE + "@job-broker:6379/1"
    path.write_text(value)
    path.chmod(0o644)
    env = {"DECLARAI_JOB_BROKER_URL_FILE": str(path), "DECLARAI_JOB_BROKER_CA_FILE": cache_env["DECLARAI_CACHE_CA_FILE"]}
    with pytest.raises(ImproperlyConfigured, match="mode 0400 or 0600"):
        load_job_config("private", env)
    path.chmod(0o400)
    assert load_job_config("private", env)["CELERY_BROKER_URL"] == value


def test_explicit_development_and_direct_values_keep_existing_contract(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "secret"
    path.write_text(VALUE)
    path.chmod(0o644)
    os.link(path, tmp_path / "alias")
    assert _secret({"DJANGO_SECRET_KEY_FILE": "secret"}, "DJANGO_SECRET_KEY") == VALUE
    assert _secret({"DJANGO_SECRET_KEY": VALUE}, "DJANGO_SECRET_KEY", private=True) == VALUE


@pytest.mark.parametrize("fault", ["platform", "uid", "parent", "root"])
def test_native_qualification_refuses_nonfixture_scope_before_effects(monkeypatch, fault):
    import sys
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    import private_dependency_start as startup
    import qualify_private_secret_capture as qualifier

    monkeypatch.setattr(sys, "platform", "darwin" if fault == "platform" else "linux")
    monkeypatch.setattr(os, "geteuid", lambda: 10001 if fault == "uid" else 0)
    parent = Path("/srv/declarai-p37-" + "a" * 32)
    if fault == "parent":
        parent = Path("/srv/customer-installation")
    root = parent / ("installation" if fault != "root" else "other")
    with pytest.raises(startup.checker.planner.PlanError, match="private_secret_fixture_scope_required"):
        qualifier.qualify({"request": {"root": str(root)}}, {}, lambda *a: pytest.fail("invalid scope touched Docker"))
