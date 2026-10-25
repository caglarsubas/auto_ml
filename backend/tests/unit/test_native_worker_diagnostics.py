"""Worker evidence remains bounded, privacy-aware and independent of outcomes."""

import hashlib
import inspect
import json
import os
import select
import signal
import subprocess
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests import native_worker_diagnostics, postgresql_parallel
from tests.native_worker_diagnostics import NativeWorkerDiagnostics

pytestmark = pytest.mark.unit
NODE = "tests/unit/test_fixture.py::Fixture::test_case[private-fixture-value]"


def value(diagnostic):
    return json.loads(diagnostic.path.read_text())


def report(node=NODE, phase="call", outcome="passed"):
    return SimpleNamespace(nodeid=node, when=phase, outcome=outcome, longrepr="private failure detail")


def test_configured_snapshot_is_bounded_and_does_not_replace_isolation_report(tmp_path):
    isolation = tmp_path / "postgresql-isolation.json"
    isolation.write_text('original isolation evidence')
    d = NativeWorkerDiagnostics(isolation, "gw0")
    assert value(d)["schema"] == "native_test_worker_diagnostic_v1"
    assert value(d)["phase"] == "configured" and value(d)["started_cases"] == 0
    assert value(d)["session_exitstatus"] is None
    assert isolation.read_text() == 'original isolation evidence'
    assert d.path == tmp_path / "postgresql-isolation-workers/gw0.json"


def test_real_lifecycle_counts_and_active_phase_are_recorded_without_report_data(tmp_path):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    d.pytest_runtest_logstart(NODE, None)
    assert value(d)["phase"] == "setup"
    d.pytest_runtest_logreport(report(phase="setup"))
    assert value(d)["phase"] == "call"
    d.pytest_runtest_logreport(report())
    assert value(d)["phase"] == "teardown"
    d.pytest_runtest_logreport(report(phase="teardown"))
    d.pytest_sessionfinish(None, 0)
    v = value(d)
    assert v["phase"] == "finished" and v["last_report_phase"] == "teardown"
    assert v["started_cases"] == v["finished_cases"] == 1
    assert v["case"] == NODE.split("[", 1)[0]
    assert v["case_id_sha256"] == hashlib.sha256(NODE.encode()).hexdigest()
    assert v["elapsed_seconds"] >= 0 and v["session_exitstatus"] == 0 and v["session_finished"]
    assert "private-fixture-value" not in d.path.read_text() and "private failure detail" not in d.path.read_text()


@pytest.mark.parametrize("phase", ["setup", "call", "teardown"])
@pytest.mark.parametrize("outcome", ["passed", "failed", "skipped"])
def test_reports_are_observed_without_changing_their_outcome(tmp_path, phase, outcome):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    d.pytest_runtest_logstart(NODE, None)
    item = report(phase=phase, outcome=outcome)
    before = vars(item).copy()
    d.pytest_runtest_logreport(item)
    assert vars(item) == before and value(d)["outcome"] == outcome
    assert value(d)["finished_cases"] == (1 if phase == "teardown" else 0)
    assert value(d)["phase"] == ("finished" if phase == "teardown" else
                                  "call" if phase == "setup" and outcome == "passed" else "teardown")


@pytest.mark.parametrize("status", [0, 1, 2, 3, 4, 5])
def test_shutdown_does_not_turn_an_incomplete_case_into_a_completed_case(tmp_path, status):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    d.pytest_runtest_logstart(NODE, None)
    d.pytest_runtest_logreport(report(phase="setup"))
    session = SimpleNamespace(exitstatus=status)
    d.pytest_sessionfinish(session, status)
    v = value(d)
    assert v["session_exitstatus"] == status == session.exitstatus
    assert v["phase"] == "call" and v["started_cases"] == 1 and v["finished_cases"] == 0


@pytest.mark.parametrize("worker", ["gw2", "../../other", ""])
def test_unknown_worker_cannot_select_an_output_path(tmp_path, worker):
    with pytest.raises(ValueError):
        NativeWorkerDiagnostics(tmp_path / "isolation.json", worker)
    assert not list(tmp_path.iterdir())


def test_unrelated_or_unknown_phase_reports_do_not_replace_current_case(tmp_path):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    d.pytest_runtest_logstart(NODE, None)
    before = d.path.read_bytes()
    d.pytest_runtest_logreport(report(node="other.py::test_other"))
    d.pytest_runtest_logreport(report(phase="private-custom-phase"))
    assert d.path.read_bytes() == before


def test_duplicate_teardown_does_not_double_count(tmp_path):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    d.pytest_runtest_logstart(NODE, None)
    for _ in range(2):
        d.pytest_runtest_logreport(report(phase="teardown"))
    assert value(d)["finished_cases"] == 1


def test_next_case_replaces_only_the_bounded_current_snapshot(tmp_path):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    d.pytest_runtest_logstart(NODE, None)
    d.pytest_runtest_logreport(report(phase="teardown"))
    other = "tests/unit/test_other.py::test_next[private-new-value]"
    d.pytest_runtest_logstart(other, None)
    v = value(d)
    assert v["started_cases"] == 2 and v["finished_cases"] == 1 and v["phase"] == "setup"
    assert v["case"] == other.split("[", 1)[0] and v["last_report_phase"] is None
    assert "private-new-value" not in d.path.read_text()
    assert list(d.path.parent.iterdir()) == [d.path]


def test_workers_have_independent_snapshots(tmp_path):
    a = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    b = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw1")
    a.pytest_runtest_logstart(NODE, None)
    assert value(b)["started_cases"] == 0 and value(a)["started_cases"] == 1


def test_long_or_unsafe_case_metadata_and_parameter_values_are_not_published(tmp_path):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    node = "unsafe\ncase::test[" + "private-parameter" * 10000 + "]"
    d.pytest_runtest_logstart(node, None)
    assert value(d)["case"] is None and len(d.path.read_bytes()) < 1500
    assert "private-parameter" not in d.path.read_text() and "unsafe" not in d.path.read_text()


@pytest.mark.parametrize("warning_error", [False, True])
def test_storage_failure_does_not_raise_or_change_test_control_flow(tmp_path, warning_error, monkeypatch):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    # Affect this probe only, including when the real native-worker plugin is
    # concurrently observing this test's reports.
    def unavailable(*args, **kwargs):
        raise OSError("private filesystem details")
    monkeypatch.setattr(d, "_replace", unavailable)
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("error" if warning_error else "always")
        d.pytest_runtest_logstart(NODE, None)
        d.pytest_runtest_logreport(report())
    assert d.state["diagnostic_write_failed"] and len(emitted) == (0 if warning_error else 1)
    assert all("private filesystem details" not in str(w.message) for w in emitted)


def test_controller_configuration_keeps_original_worker_collection_without_diagnostics(tmp_path):
    config = SimpleNamespace()
    postgresql_parallel.pytest_configure(config)
    assert config._postgresql_workers == {} and not list(tmp_path.iterdir())


def test_worker_registration_preserves_existing_cache_selection(tmp_path, monkeypatch):
    import redis
    fake = Mock()
    fake.__enter__ = Mock(return_value=fake)
    fake.__exit__ = Mock(return_value=None)
    fake.client_info.return_value = {"db": 2}
    monkeypatch.setattr(redis.Redis, "from_url", Mock(return_value=fake))
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    config = SimpleNamespace(workerinput={"workerid": "gw0"}, pluginmanager=Mock(),
                             getoption=lambda name: str(tmp_path / "isolation.json"))
    postgresql_parallel.pytest_configure(config)
    plugin = config.pluginmanager.register.call_args.args[0]
    assert isinstance(plugin, NativeWorkerDiagnostics) and value(plugin)["phase"] == "configured"
    assert config._postgresql_identity == {"worker": "gw0", "cache_database": 2}
    fake.ping.assert_called_once_with()


def test_actual_killed_worker_leaves_the_unfinished_case_available(tmp_path):
    isolation = tmp_path / "isolation.json"
    program = """
import sys,time
from types import SimpleNamespace
from tests.native_worker_diagnostics import NativeWorkerDiagnostics
d=NativeWorkerDiagnostics(sys.argv[1], 'gw0')
node='tests/unit/synthetic.py::test_interrupted[private-value]'
d.pytest_runtest_logstart(node, None)
d.pytest_runtest_logreport(SimpleNamespace(nodeid=node,when='setup',outcome='passed'))
print('ready', flush=True)
time.sleep(60)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", program, str(isolation)],
        cwd=Path(inspect.getfile(NativeWorkerDiagnostics)).parents[1],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        assert select.select([child.stdout], [], [], 5)[0]
        assert child.stdout.readline() == b"ready\n"
        os.killpg(child.pid, signal.SIGKILL)
        assert child.wait(timeout=5) == -signal.SIGKILL
        snapshot = json.loads((tmp_path / "isolation-workers/gw0.json").read_text())
        assert snapshot["case"] == "tests/unit/synthetic.py::test_interrupted"
        assert snapshot["phase"] == "call" and snapshot["last_report_phase"] == "setup"
        assert snapshot["started_cases"] == 1 and snapshot["finished_cases"] == 0
        assert snapshot["session_finished"] is False and snapshot["session_exitstatus"] is None
        assert "private-value" not in json.dumps(snapshot)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
        child.stdout.close()
        child.stderr.close()


@pytest.mark.parametrize("module", ["os", "time", "hashlib", "json"])
def test_existing_observer_is_independent_of_injected_operation_bindings(tmp_path, monkeypatch, module):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    expected = hashlib.sha256(NODE.encode()).hexdigest()
    monkeypatch.setattr(native_worker_diagnostics, module, SimpleNamespace())
    d.pytest_runtest_logstart(NODE, None)
    d.pytest_runtest_logreport(report(phase="setup"))
    v = value(d)
    assert v["case_id_sha256"] == expected and v["phase"] == "call"
    assert v["diagnostic_write_failed"] is False and v["elapsed_seconds"] >= 0


def test_short_writes_publish_complete_atomic_json(tmp_path, monkeypatch):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    original = d._write
    monkeypatch.setattr(d, "_write", lambda descriptor, raw: original(descriptor, raw[:7]))
    d.pytest_runtest_logstart(NODE, None)
    assert value(d)["started_cases"] == 1 and not d.path.with_name(d.path.name + ".tmp").exists()


def test_zero_progress_preserves_last_complete_snapshot(tmp_path, monkeypatch):
    d = NativeWorkerDiagnostics(tmp_path / "isolation.json", "gw0")
    before = d.path.read_bytes()
    monkeypatch.setattr(d, "_write", lambda *args: 0)
    with pytest.warns(pytest.PytestWarning, match="could not be retained"):
        d.pytest_runtest_logstart(NODE, None)
    assert d.path.read_bytes() == before and d.state["diagnostic_write_failed"]


def test_relative_report_destination_remains_pinned_after_test_changes_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = NativeWorkerDiagnostics("reports/isolation.json", "gw0")
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    d.pytest_runtest_logstart(NODE, None)
    assert d.path == tmp_path / "reports/isolation-workers/gw0.json"
    assert value(d)["started_cases"] == 1 and value(d)["diagnostic_write_failed"] is False
    assert not list(other.iterdir())
