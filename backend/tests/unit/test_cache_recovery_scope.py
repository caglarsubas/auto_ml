from pathlib import Path
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def recovery(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    import qualify_private_cache as module

    return module


@pytest.mark.parametrize("fault", ["platform", "uid", "parent", "request"])
def test_recovery_rejects_nonfixture_scope_before_effects(recovery, monkeypatch, fault):
    import sys, os, private_dependency_start as startup

    monkeypatch.setattr(sys, "platform", "darwin" if fault == "platform" else "linux")
    monkeypatch.setattr(os, "geteuid", lambda: 10001 if fault == "uid" else 0)
    parent = Path("/srv/declarai-p37-" + "a" * 32)
    if fault == "parent":
        parent = Path("/srv/customer-installation")
    value = {"request": {"root": str(parent / "installation") if fault != "request" else "/srv/customer/installation"}}
    monkeypatch.setattr(startup, "prepared", lambda *a: pytest.fail("invalid scope reached dependency files"))
    with pytest.raises(startup.checker.planner.PlanError, match="cache_recovery_fixture_scope_required"):
        recovery.recovery(value, {}, {}, parent, lambda *a: pytest.fail("invalid scope touched a container"))
