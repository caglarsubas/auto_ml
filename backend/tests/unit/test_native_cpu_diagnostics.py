"""Qualification CPU evidence is bounded and cannot rewrite test outcomes."""

import gc
import inspect
import json
import os
import select
import signal
import subprocess
import sys
import warnings
import weakref
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests import native_cpu_diagnostics
from tests.native_cpu_diagnostics import NativeCPUDiagnostics
from tests.native_worker_diagnostics import NativeWorkerDiagnostics

pytestmark = pytest.mark.unit


class Signals:
    SIGPROF, ITIMER_PROF, SIG_DFL = 27, 2, 0

    def __init__(self):
        self.handler, self.timer, self.calls, self.fail_start = 0, (0., 0.), [], False

    def getsignal(self, number):
        return self.handler

    def getitimer(self, number):
        return self.timer

    def signal(self, number, handler):
        previous = self.handler
        self.calls.append(('signal', handler))
        self.handler = handler
        return previous

    def setitimer(self, number, seconds, interval=0.):
        self.calls.append(('timer', seconds, interval))
        if seconds and self.fail_start:
            raise OSError('private timer details')
        previous = self.timer
        self.timer = seconds, interval
        return previous


@pytest.fixture
def probe(tmp_path, monkeypatch):
    signals = Signals()
    clock = SimpleNamespace(wall=50., cpu=20.)
    monkeypatch.setattr(native_cpu_diagnostics, 'signal', signals)
    monkeypatch.setattr(native_cpu_diagnostics, 'time', SimpleNamespace(
        monotonic=lambda: clock.wall, process_time=lambda: clock.cpu))
    return NativeCPUDiagnostics(tmp_path / 'isolation-workers/gw0.json', 'gw0'), signals, clock


def value(probe):
    return json.loads(probe.path.read_text())


def frame(filename, back=None):
    code = compile("private_constant = 'private source text'", filename, 'exec')
    return SimpleNamespace(f_code=code, f_back=back, f_locals={'private argument': 'private payload'})


def test_only_normalized_static_code_labels_are_retained(probe):
    d, _, _ = probe
    d.start()
    known = frame(d._repo + 'modeling/example.py')
    generated = frame('<private filename>', known)
    d.sample(None, generated)
    d.publish(force=True)
    record = value(d)
    assert record['samples'] == record['accepted_samples'] == 1
    assert any(k.startswith('repo/modeling/example.py:') for k in record['stack_samples'])
    text = d.path.read_text()
    for private in ['private argument', 'private payload', 'private source text', 'private filename', d._repo]:
        assert private not in text
    assert record['arguments_locals_parameters_or_source_retained'] is False
    assert record['additional_threads'] == 0
    d.finish(0)


def test_recursive_code_is_counted_once_per_stack(probe):
    d, _, _ = probe
    leaf = frame(d._repo + 'modeling/example.py')
    leaf.f_back = SimpleNamespace(f_code=leaf.f_code, f_back=None)
    d.sample(None, leaf)
    assert list(d._leaf.values()) == [1] and list(d._stack.values()) == [1]


def test_label_cache_does_not_keep_generated_code_or_constants_alive(probe):
    d, _, _ = probe
    current = frame('<private generated source>')
    reference = weakref.ref(current.f_code)
    d.sample(None, current)
    del current
    gc.collect()
    assert reference() is None
    assert d._codes and all(entry[0]() is None for entry in d._codes.values())


def test_entry_and_code_caches_have_fixed_bounds(probe):
    d, _, _ = probe
    d._entries = 1
    d.sample(None, frame(d._repo + 'first.py'))
    d.sample(None, frame(d._repo + 'second.py'))
    assert len(d._codes) == len(d._leaf) == len(d._stack) == 1
    assert d.state['dropped_labels'] > 0


def test_sample_and_depth_limits_are_explicit(probe):
    d, _, _ = probe
    d._maximum, d._depth = 1, 1
    chain = frame(d._repo + 'first.py', frame(d._repo + 'second.py'))
    d.sample(None, chain)
    d.sample(None, chain)
    assert d.state['samples'] == 2 and d.state['accepted_samples'] == 1
    assert d.state['dropped_samples'] == d.state['truncated_stacks'] == 1


def test_periodic_snapshot_keeps_the_last_complete_observation(probe):
    d, _, clock = probe
    d.start()
    first = d.path.read_bytes()
    d.sample(None, frame(d._repo + 'first.py'))
    clock.wall += 29.
    d.publish()
    assert d.path.read_bytes() == first
    clock.wall += 2.
    clock.cpu += 3.
    d.publish()
    assert value(d)['samples'] == 1
    assert value(d)['wall_seconds'] == 31. and value(d)['process_cpu_seconds'] == 3.
    d.finish(3)
    assert value(d)['session_finished'] and value(d)['session_exitstatus'] == 3


def test_owned_timer_and_handler_are_restored(probe):
    d, signals, _ = probe
    d.start()
    assert signals.handler is d._callback and signals.timer == (.04, .04)
    d.finish(1)
    assert signals.handler == signals.SIG_DFL and signals.timer == (0., 0.)
    assert value(d)['session_exitstatus'] == 1


@pytest.mark.parametrize('busy', ['timer', 'handler'])
def test_preexisting_timer_or_handler_is_never_replaced(probe, busy):
    d, signals, _ = probe
    if busy == 'timer':
        signals.timer = (1., 1.)
    else:
        signals.handler = lambda *args: None
    before = signals.handler, signals.timer
    d.start()
    d.finish(0)
    assert (signals.handler, signals.timer) == before and signals.calls == []
    assert not value(d)['available']
    assert value(d)['unavailable_reason'] == 'existing_timer_or_handler'


def test_unsupported_timer_is_explicit_and_does_not_raise(probe):
    d, signals, _ = probe
    d._signal = None
    d.start()
    assert not signals.calls and value(d)['unavailable_reason'] == 'unsupported_timer'


def test_failed_timer_start_rolls_back_the_installed_handler(probe):
    d, signals, _ = probe
    signals.fail_start = True
    d.start()
    assert signals.handler == signals.SIG_DFL and signals.timer == (0., 0.)
    assert value(d)['unavailable_reason'] == 'timer_start_failed'
    assert 'private timer details' not in d.path.read_text()


def test_changed_handler_ownership_is_preserved(probe):
    d, signals, _ = probe
    d.start()
    external = lambda *args: None
    signals.handler = external
    timer = signals.timer
    d.finish(0)
    assert signals.handler is external and signals.timer == timer
    assert value(d)['unavailable_reason'] == 'timer_ownership_changed'


@pytest.mark.parametrize('warning_error', [False, True])
def test_output_failure_cannot_change_control_flow_or_expose_exception_details(probe, monkeypatch, warning_error):
    d, _, _ = probe
    d.publish(force=True)
    before = d.path.read_bytes()

    def unavailable(*args):
        raise OSError('private filesystem details')

    monkeypatch.setattr(d, '_replace', unavailable)
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter('error' if warning_error else 'always')
        d.publish(force=True)
        d.publish(force=True)
    assert d.state['diagnostic_write_failed'] and d.path.read_bytes() == before
    assert len(emitted) == (0 if warning_error else 1)
    assert all('private filesystem details' not in str(w.message) for w in emitted)


def test_short_writes_produce_a_complete_atomic_snapshot(probe, monkeypatch):
    d, _, _ = probe
    original = d._write
    monkeypatch.setattr(d, '_write', lambda descriptor, raw: original(descriptor, raw[:7]))
    d.publish(force=True)
    assert value(d)['schema'] == 'native_test_cpu_diagnostic_v1'
    assert not Path(str(d.path) + '.tmp').exists()


def test_workers_use_separate_paths_that_do_not_match_progress_snapshot_names(probe):
    d, _, _ = probe
    other = NativeCPUDiagnostics(d.path.parent.parent / 'isolation-workers/gw1.json', 'gw1')
    d.publish(force=True)
    other.publish(force=True)
    assert value(d)['worker'] == 'gw0' and value(other)['worker'] == 'gw1'
    assert not list(d.path.parent.rglob('gw*.json'))


@pytest.mark.parametrize('module', ['os', 'time', 'json', 'signal'])
def test_operation_references_survive_injected_module_bindings(probe, monkeypatch, module):
    d, _, _ = probe
    monkeypatch.setattr(native_cpu_diagnostics, module, SimpleNamespace())
    d.start()
    d.sample(None, frame(d._repo + 'first.py'))
    d.finish(0)
    assert value(d)['samples'] == 1 and not value(d)['diagnostic_write_failed']


@pytest.mark.parametrize('worker', ['gw2', '../other', ''])
def test_invalid_worker_cannot_select_a_destination(tmp_path, worker):
    with pytest.raises(ValueError):
        NativeCPUDiagnostics(tmp_path / 'isolation-workers/gw0.json', worker)
    assert not list(tmp_path.iterdir())


def test_progress_observer_preserves_case_outcome_with_cpu_sidecar(tmp_path, monkeypatch):
    cpu = SimpleNamespace(start=Mock(), publish=Mock(), finish=Mock())
    monkeypatch.setattr(native_cpu_diagnostics, 'NativeCPUDiagnostics', Mock(return_value=cpu))
    diagnostic = NativeWorkerDiagnostics(tmp_path / 'isolation.json', 'gw0')
    session = SimpleNamespace(exitstatus=3)
    node = 'tests/unit/example.py::test_case[private parameter]'
    diagnostic.pytest_sessionstart(session)
    diagnostic.pytest_runtest_logstart(node, None)
    report = SimpleNamespace(nodeid=node, when='setup', outcome='passed')
    diagnostic.pytest_runtest_logreport(report)
    diagnostic.pytest_sessionfinish(session, 3)
    cpu.start.assert_called_once_with()
    cpu.publish.assert_called_once_with()
    cpu.finish.assert_called_once_with(3)
    record = json.loads(diagnostic.path.read_text())
    assert session.exitstatus == record['session_exitstatus'] == 3
    assert record['started_cases'] == 1 and record['finished_cases'] == 0 and record['phase'] == 'call'
    assert report.outcome == 'passed'


def test_killed_real_sampler_keeps_a_partial_snapshot_without_payloads(tmp_path):
    program = """
import sys,time
from tests.native_cpu_diagnostics import NativeCPUDiagnostics
diagnostic=NativeCPUDiagnostics(sys.argv[1], 'gw0')
diagnostic.start()
until=time.process_time()+.3
private_payload='private fixture payload'
while time.process_time()<until:
    pass
diagnostic.publish(force=True)
print('ready',flush=True)
time.sleep(60)
"""
    progress = tmp_path / 'isolation-workers/gw0.json'
    child = subprocess.Popen(
        [sys.executable, '-c', program, str(progress)],
        cwd=Path(inspect.getfile(NativeCPUDiagnostics)).parents[1],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
    )
    try:
        assert select.select([child.stdout], [], [], 5)[0]
        assert child.stdout.readline() == b'ready\n'
        os.killpg(child.pid, signal.SIGKILL)
        assert child.wait(timeout=5) == -signal.SIGKILL
        path = tmp_path / 'isolation-workers-cpu/cpu-gw0.json'
        record = json.loads(path.read_text())
        assert record['available'] and record['samples'] > 0 and record['leaf_samples']
        assert record['session_finished'] is False and record['session_exitstatus'] is None
        assert record['process_cpu_seconds'] > 0
        assert 'private fixture payload' not in path.read_text()
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
        child.stdout.close()
        child.stderr.close()
