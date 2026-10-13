"""Private PostgreSQL transport does not inherit weaker libpq defaults."""

import sys
from pathlib import Path

import pytest
from django.db.backends.postgresql.base import DatabaseWrapper

from backend.runtime_config import load_runtime
from tests.unit.test_runtime_config import private, DEV_KEY  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("name,value", [
    ("PGGSSENCMODE", "require"), ("PGSSLMODE", "disable"),
    ("PGSSLMINPROTOCOLVERSION", "TLSv1"), ("PGSSLROOTCERT", "/unselected/ca.pem"),
])
def test_django_connection_explicitly_overrides_ambient_defaults(private, tmp_path, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    runtime = load_runtime(tmp_path, DEV_KEY, private)
    params = DatabaseWrapper({**runtime["DATABASES"]["default"], "TIME_ZONE": None}).get_connection_params()
    assert params["sslmode"] == "verify-full"
    assert params["gssencmode"] == "disable"
    assert params["ssl_min_protocol_version"] == "TLSv1.2"
    assert params["sslrootcert"] == private["DECLARAI_DB_SSLROOTCERT"]


def test_development_postgres_preserves_driver_default_policy(private, tmp_path):
    private["DECLARAI_RUNTIME_PROFILE"] = "development"
    private["DECLARAI_DB_ENGINE"] = "postgresql"
    assert load_runtime(tmp_path, DEV_KEY, private)["DATABASES"]["default"]["OPTIONS"] == {
        "sslmode": "disable", "connect_timeout": 10,
    }


@pytest.mark.parametrize("fault", ["platform", "uid", "root", "name"])
def test_postgres_qualification_rejects_nonfixture_scope_before_effects(monkeypatch, fault):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    import qualify_private_postgres_tls as qualifier
    import private_dependency_start as startup

    monkeypatch.setattr(sys, "platform", "darwin" if fault == "platform" else "linux")
    monkeypatch.setattr(startup.os, "geteuid", lambda: 1 if fault == "uid" else 0)
    parent = "/tmp" if fault == "root" else "/srv"
    name = "customer" if fault == "name" else "declarai-p37-" + "a" * 32
    value = {"request": {"root": f"{parent}/{name}/installation"}}
    with pytest.raises(startup.checker.planner.PlanError, match="private_postgres_tls_fixture_scope_required"):
        qualifier.qualify(value, {}, lambda _: pytest.fail("out of scope Docker call"))
