"""The native suite uses the fixed app image and an explicit test-only overlay."""

import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit
SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
IMAGE = "sha256:" + "a" * 64


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    module = importlib.import_module("private_native_suite")
    installed = tmp_path / "installed"
    distributions = {}
    for name, (package, version) in module.TOOLS.items():
        members = [Path(package) / "__init__.py", Path(name.replace("-", "_") + "-" + version + ".dist-info") / "METADATA"]
        for member in members:
            path = installed / member
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Name: " + name + "\nVersion: " + version + "\n")
        distributions[name] = SimpleNamespace(version=version, files=members, locate_file=lambda path: installed / path)
    monkeypatch.setattr(module.metadata, "distribution", distributions.__getitem__)
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(module.os, "sched_getaffinity", lambda pid: {0, 1, 2, 3}, raising=False)
    info = {"Id": IMAGE, "Config": {"User": "10001:10001"}}
    runtime = {"schema": "private_native_runtime_v1", "machine": "aarch64", "system": "Linux",
               "implementation": "CPython", "python": "3.12.16",
               "source_sha256": {"backend/manage.py": hashlib.sha256(b"fixed application").hexdigest()}}
    monkeypatch.setattr(module, "inspect_image", lambda image: info)
    monkeypatch.setattr(module, "native_manifest", lambda image: runtime)
    root, fixture = tmp_path / "repo", tmp_path / "fixture"
    root.mkdir()
    (root / "backend").mkdir()
    (root / "backend/manage.py").write_bytes(b"fixed application")
    fixture.mkdir()
    return SimpleNamespace(module=module, installed=installed, distributions=distributions,
                           info=info, runtime=runtime, root=root, fixture=fixture)


def prepare(w, **kwargs):
    return w.module.prepare(IMAGE, root=w.root, fixture=w.fixture, name="owned-native-suite", environment=kwargs)


def test_exact_application_runtime_preserves_workers_affinity_and_all_test_limits(world):
    argv, receipt = prepare(world, DECLARAI_DB_NAME="synthetic")
    assert argv[-1] == IMAGE and argv[-3:-1] == ["--entrypoint", "python"]
    assert argv[argv.index("--cpuset-cpus") + 1] == "0,1,2,3"
    assert argv[argv.index("--network") + 1] == "host"
    assert "--pull" in argv and "never" in argv and "no-new-privileges:true" in argv
    assert receipt["workers"] == 2 and receipt["scheduling"] == "loadfile"
    assert receipt["timeout_seconds"] == 900 and receipt["worker_restarts"] == 0
    assert receipt["python"] == world.runtime["python"]
    assert receipt["application_runtime_manifest_sha256"] == hashlib.sha256(json.dumps(world.runtime, sort_keys=True).encode()).hexdigest()
    assert receipt["application_source_sha256"] == hashlib.sha256(json.dumps(world.runtime["source_sha256"], sort_keys=True).encode()).hexdigest()
    assert receipt["application_dependencies_replaced"] is receipt["host_site_packages_mounted"] is False
    for path, digest in receipt["qualification_tools"]["files_sha256"].items():
        assert hashlib.sha256((world.fixture / "native-suite-tools" / path).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("name", ["execnet", "pytest-xdist"])
def test_tool_version_drift_is_refused(world, name):
    world.distributions[name].version = "99.0"
    with pytest.raises(ValueError, match="native_suite_tool_version"):
        prepare(world)


@pytest.mark.parametrize("path", ["/private/customer", "../credential", "other_package/plugin.py"])
def test_overlay_never_copies_paths_outside_the_two_declared_packages(world, path):
    world.distributions["execnet"].files = [Path(path)]
    with pytest.raises(ValueError, match="native_suite_tool_path"):
        prepare(world)


def test_symlink_tool_file_is_refused(world):
    member = world.distributions["execnet"].files[0]
    path = world.installed / member
    path.unlink()
    path.symlink_to(world.installed / world.distributions["execnet"].files[1])
    with pytest.raises(ValueError, match="native_suite_tool_file"):
        prepare(world)


def test_host_credentials_and_python_paths_are_excluded_from_the_controller(world):
    argv, receipt = prepare(world, GITHUB_TOKEN="private-marker", PYTHONPATH="/private/host",
                            DECLARAI_DB_PASSWORD_FILE="/fixture/test-password")
    raw = (world.fixture / "native-suite.env").read_text()
    assert "private-marker" not in raw and "/private/host" not in raw
    assert "PYTHONPATH=/opt/declarai-qualification\n" in raw
    assert "DECLARAI_DB_PASSWORD_FILE=/fixture/test-password\n" in raw
    assert "private-marker" not in json.dumps(receipt) and "private-marker" not in str(argv)
    assert (world.fixture / "native-suite.env").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("fault", ["changed", "empty"])
def test_tests_cannot_run_against_different_or_unverified_application_sources(world, fault):
    if fault == "changed":
        (world.root / "backend/manage.py").write_bytes(b"different application")
    else:
        world.runtime["source_sha256"] = {}
    with pytest.raises(ValueError, match="native_suite_application_source_changed"):
        prepare(world)
    assert not (world.fixture / "native-suite-tools").exists()


@pytest.mark.parametrize("fault", ["mac", "architecture", "image", "user"])
def test_unverified_or_cross_architecture_runtime_is_refused(world, monkeypatch, fault):
    if fault == "mac":
        monkeypatch.setattr(world.module.platform, "system", lambda: "Darwin")
    elif fault == "architecture":
        world.runtime["machine"] = "x86_64"
    elif fault == "image":
        world.info["Id"] = "sha256:" + "b" * 64
    else:
        world.info["Config"]["User"] = "0:0"
    with pytest.raises(ValueError, match="native_suite_"):
        prepare(world)
