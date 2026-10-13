"""Stable TLS inputs must reject inter-read changes despite coarse timestamps."""

import os
from pathlib import Path
import pytest
from django.core.exceptions import ImproperlyConfigured
from ai_assistant.cache_connection import connection_options
from execution_jobs.broker_transport import captured_tls
from tests.unit.test_private_cache import cache_env  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("route", ["cache_url", "cache_ca", "broker_ca"])
@pytest.mark.parametrize("fault", ["bytes", "mode", "link"])
def test_tls_capture_rejects_inconsistent_input_with_unchanged_timestamps(
    cache_env, tmp_path, monkeypatch, route, fault
):
    path = Path(cache_env["DECLARAI_CACHE_URL_FILE" if route == "cache_url" else "DECLARAI_CACHE_CA_FILE"])
    stamp = path.stat()
    actual_fstat = os.fstat
    actual_fdopen = os.fdopen

    class CoarseTimes:
        st_mtime_ns, st_ctime_ns = stamp.st_mtime_ns, stamp.st_ctime_ns

        def __init__(self, now):
            self.now = now

        def __getattr__(self, name):
            return getattr(self.now, name)

    def fstat(fd):
        now = actual_fstat(fd)
        return CoarseTimes(now) if (now.st_dev, now.st_ino) == (stamp.st_dev, stamp.st_ino) else now

    class ChangedRead:
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
            now = actual_fstat(self.fileno())
            if not self.changed and (now.st_dev, now.st_ino) == (stamp.st_dev, stamp.st_ino):
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
    with pytest.raises(
        ImproperlyConfigured,
        match="private_broker_ca_invalid" if route == "broker_ca" else "private_cache_configuration_invalid",
    ):
        if route == "broker_ca":
            captured_tls(path)
        else:
            connection_options(cache_env)


@pytest.mark.parametrize("fault", ["platform", "uid", "parent", "root"])
def test_tls_qualification_rejects_nonfixture_scope_before_effects(monkeypatch, fault):
    import sys

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    import private_dependency_start as startup
    import qualify_private_tls_capture as qualifier

    monkeypatch.setattr(sys, "platform", "darwin" if fault == "platform" else "linux")
    monkeypatch.setattr(os, "geteuid", lambda: 10001 if fault == "uid" else 0)
    parent = Path("/srv/declarai-p37-" + "a" * 32)
    if fault == "parent":
        parent = Path("/srv/customer-installation")
    root = parent / ("installation" if fault != "root" else "other")
    with pytest.raises(startup.checker.planner.PlanError, match="private_tls_capture_fixture_scope_required"):
        qualifier.qualify({"request": {"root": str(root)}}, {}, lambda *a: pytest.fail("invalid scope reached Docker"))
