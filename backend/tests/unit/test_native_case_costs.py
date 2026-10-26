"""Partial case-cost metadata is bounded and independent of tested operations."""
import hashlib
import json
import os
import signal
import subprocess
import sys
import warnings
from types import SimpleNamespace

import pytest

from tests import native_case_costs
from tests.native_case_costs import NativeCaseCosts
from tests.native_worker_diagnostics import NativeWorkerDiagnostics

pytestmark = pytest.mark.unit
IDENTITY = hashlib.sha256(b'synthetic-node').hexdigest()
CASE = 'tests/unit/test_owned.py::test_owned'


def rows(journal):
    return [json.loads(line) for line in journal.path.read_text().splitlines()]


def journal(tmp_path, worker='gw0'):
    return NativeCaseCosts(tmp_path / 'workers' / 'progress.json', worker)


def complete(value, outcome='passed'):
    value.start(CASE, IDENTITY)
    for phase in ['setup', 'call', 'teardown']:
        value.phase(phase, outcome if phase == 'call' else 'passed', .125)
    value.finish_case()


def test_completed_cases_record_full_protocol_costs_without_payloads(tmp_path):
    value = journal(tmp_path)
    wall, cpu = iter([10., 12.5]), iter([20., 20.75])
    value._wall, value._cpu = lambda: next(wall), lambda: next(cpu)
    complete(value)
    value.finish(0)
    data = rows(value)
    assert [r['kind'] for r in data] == ['session_start', 'case_start', 'case_finish', 'session_finish']
    assert data[1]['case'] == CASE and data[1]['case_id_sha256'] == IDENTITY
    assert data[2]['wall_seconds'] == 2.5 and data[2]['process_cpu_seconds'] == .75
    assert data[2]['phases'] == {p: {'outcome': 'passed', 'wall_seconds': .125} for p in ['setup', 'call', 'teardown']}
    assert data[-1]['started_cases'] == data[-1]['finished_cases'] == 1
    assert data[-1]['incomplete_case'] is None and data[-1]['exitstatus'] == 0
    assert not data[0]['arguments_parameters_reports_locals_or_source_retained']
    assert not list(value.path.parent.rglob('gw*.json'))
    assert value.path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('worker', ['gw2', 'gw-1', '../gw0', None, 0])
def test_unknown_worker_identity_is_refused(tmp_path, worker):
    with pytest.raises(ValueError):
        journal(tmp_path, worker)


@pytest.mark.parametrize('outcome', ['passed', 'failed', 'skipped', 'unrecognized'])
def test_phase_outcomes_remain_metadata_and_do_not_change_the_caller(tmp_path, outcome):
    value = journal(tmp_path)
    complete(value, outcome)
    value.finish(1 if outcome == 'failed' else 0)
    assert rows(value)[2]['phases']['call']['outcome'] == (outcome if outcome != 'unrecognized' else 'unknown')
    assert rows(value)[-1]['finished_cases'] == 1


@pytest.mark.parametrize('duration', [None, float('nan'), float('inf'), -1., 'private-value'])
def test_invalid_duration_is_explicitly_unknown_without_serializing_its_value(tmp_path, duration):
    value = journal(tmp_path)
    value.start(CASE, IDENTITY)
    value.phase('setup', 'passed', duration)
    value.finish_case()
    value.finish(0)
    assert rows(value)[2]['phases']['setup']['wall_seconds'] is None
    assert 'private-value' not in value.path.read_text()


def test_incomplete_case_is_never_counted_as_finished_on_interrupted_exit(tmp_path):
    value = journal(tmp_path)
    value.start(CASE, IDENTITY)
    value.phase('setup', 'passed', .5)
    value.finish(3)
    assert [r['kind'] for r in rows(value)] == ['session_start', 'case_start', 'session_finish']
    assert rows(value)[-1]['finished_cases'] == 0 and rows(value)[-1]['incomplete_case'] == 1


def test_replaced_incomplete_case_is_retained_and_not_converted_to_success(tmp_path):
    value = journal(tmp_path)
    value.start(CASE, IDENTITY)
    complete(value)
    value.finish(3)
    data = rows(value)
    assert data[2] == {'kind': 'incomplete', 'index': 1}
    assert data[-1]['started_cases'] == 2 and data[-1]['finished_cases'] == 1


def test_record_bound_does_not_stop_later_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(NativeCaseCosts, 'MAX_CASES', 2)
    value = journal(tmp_path)
    for _ in range(5):
        complete(value)
    value.finish(0)
    data = rows(value)
    assert sum(r['kind'] == 'case_finish' for r in data) == 2
    assert sum(r['kind'] == 'limit' for r in data) == 1
    assert data[-1]['truncated'] and data[-1]['started_cases'] == 5


def test_repeated_teardown_and_shutdown_cannot_duplicate_completion(tmp_path):
    value = journal(tmp_path)
    complete(value)
    value.finish_case()
    value.finish(0)
    value.finish(0)
    complete(value)
    assert sum(r['kind'] == 'case_finish' for r in rows(value)) == 1
    assert sum(r['kind'] == 'session_finish' for r in rows(value)) == 1


def test_unrecognized_phase_and_identity_do_not_retain_untrusted_values(tmp_path):
    value = journal(tmp_path)
    value.start('tests/a.py::test_x[private-value]', 'private-value')
    value.phase('private-value', 'passed', 1.)
    value.finish_case()
    value.finish(0)
    assert rows(value)[1]['case'] is rows(value)[1]['case_id_sha256'] is None
    assert rows(value)[2]['phases'] == {} and 'private-value' not in value.path.read_text()


def test_short_writes_preserve_complete_records(tmp_path):
    value = journal(tmp_path)
    original = value._write
    value._write = lambda descriptor, raw: original(descriptor, raw[:7])
    complete(value)
    value.finish(0)
    assert len(rows(value)) == 4 and not value.failed


@pytest.mark.parametrize('operation', ['write', 'close'])
def test_output_fault_warns_once_without_replacing_test_outcomes(tmp_path, operation):
    value = journal(tmp_path)
    original_close = value._close

    def refused(*args):
        raise OSError('private-value')

    setattr(value, '_' + operation, refused)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        complete(value)
        complete(value)
        value.finish(0)
    assert value.failed and len(caught) == 1 and 'private-value' not in str(caught[0].message)
    if operation == 'close':
        original_close(value.descriptor)


def test_existing_journal_is_preserved_and_unavailable_state_is_explicit(tmp_path):
    first = journal(tmp_path)
    complete(first)
    first.finish(0)
    original = first.path.read_bytes()
    with pytest.warns(pytest.PytestWarning, match='could not be retained'):
        second = journal(tmp_path)
    complete(second)
    second.finish(0)
    assert second.failed and first.path.read_bytes() == original


def test_warning_as_error_cannot_turn_optional_diagnostic_failure_into_test_failure(tmp_path):
    value = journal(tmp_path)
    value._write = lambda *args: 0
    with warnings.catch_warnings():
        warnings.simplefilter('error', pytest.PytestWarning)
        complete(value)
        value.finish(0)
    assert value.failed and value.closed


def test_captured_operations_survive_fault_injection_and_working_directory_changes(tmp_path, monkeypatch):
    value = journal(tmp_path)
    monkeypatch.chdir(tmp_path)

    def refused(*args, **kwargs):
        raise AssertionError('Test fault injection must not replace captured operations')

    for name in ['open', 'write', 'close']:
        monkeypatch.setattr(native_case_costs.os, name, refused)
    monkeypatch.setattr(native_case_costs.time, 'monotonic', refused)
    monkeypatch.setattr(native_case_costs.time, 'process_time', refused)
    monkeypatch.setattr(native_case_costs.json, 'dumps', refused)
    complete(value)
    value.finish(0)
    assert not value.failed and len(rows(value)) == 4


def test_original_progress_retains_its_counts_and_parameter_privacy(tmp_path):
    observer = NativeWorkerDiagnostics(tmp_path / 'isolation.json', 'gw0')
    observer.pytest_sessionstart(None)
    node = CASE + '[private-value]'
    observer.pytest_runtest_logstart(node, None)
    for phase in ['setup', 'call', 'teardown']:
        observer.pytest_runtest_logreport(SimpleNamespace(nodeid=node, when=phase, outcome='passed', duration=.125))
    observer.pytest_sessionfinish(None, 0)
    assert observer.state['started_cases'] == observer.state['finished_cases'] == 1
    data = rows(observer._costs)
    assert data[-1]['started_cases'] == data[-1]['finished_cases'] == 1
    assert data[1]['case_id_sha256'] == hashlib.sha256(node.encode()).hexdigest()
    assert 'private-value' not in observer._costs.path.read_text()


def test_actual_killed_process_keeps_partial_case_journal_without_payloads(tmp_path):
    script = """from tests.native_case_costs import NativeCaseCosts
import sys,time
v=NativeCaseCosts(sys.argv[1],'gw0')
v.start('tests/a.py::test_owned','a'*64)
print(v.path,flush=True)
time.sleep(20)
"""
    child = subprocess.Popen([sys.executable, '-c', script, str(tmp_path / 'workers' / 'gw0.json')],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        from pathlib import Path
        path = Path(child.stdout.readline().strip())
        os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
        data = [json.loads(line) for line in path.read_text().splitlines()]
        assert [r['kind'] for r in data] == ['session_start', 'case_start']
        assert data[-1]['case'] == 'tests/a.py::test_owned' and 'private-value' not in path.read_text()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_record_byte_bound_is_explicit_without_interfering_with_case_execution(tmp_path):
    value = journal(tmp_path)
    value._record_limit = 16
    with pytest.warns(pytest.PytestWarning, match='could not be retained'):
        complete(value)
    value.finish(0)
    assert value.failed and value.finished == 1
    assert [r['kind'] for r in rows(value)] == ['session_start']


def test_worker_journals_remain_independent(tmp_path):
    first, second = journal(tmp_path, 'gw0'), journal(tmp_path, 'gw1')
    complete(first)
    second.start(CASE, IDENTITY)
    first.finish(0)
    second.finish(3)
    assert first.path != second.path
    assert rows(first)[-1]['finished_cases'] == 1
    assert rows(second)[-1]['finished_cases'] == 0
    assert rows(first)[0]['worker'] == 'gw0' and rows(second)[0]['worker'] == 'gw1'


def test_complete_reader_validates_counts_costs_and_static_attribution(tmp_path):
    value = journal(tmp_path)
    complete(value)
    value.finish(0)
    summary = native_case_costs.read_case_costs(value.path)
    assert summary['complete'] and summary['started_cases'] == summary['finished_cases'] == 1
    assert summary['skipped_cases'] == summary['failed_cases'] == 0
    assert summary['files']['tests/unit/test_owned.py']['cases'] == 1
    assert summary['slowest_wall'][0]['case_id_sha256'] == IDENTITY
    assert not summary['arguments_parameters_reports_locals_or_source_retained']


def test_partial_reader_never_qualifies_an_interrupted_case(tmp_path):
    value = journal(tmp_path)
    value.start(CASE, IDENTITY)
    value.finish(3)
    summary = native_case_costs.read_case_costs(value.path, require_complete=False)
    assert not summary['complete'] and summary['finished_cases'] == 0
    assert summary['active_case']['index'] == 1 and summary['session_exitstatus'] == 3
    with pytest.raises(ValueError, match='native_case_cost_metadata_invalid'):
        native_case_costs.read_case_costs(value.path)


@pytest.mark.parametrize('corruption', ['schema', 'worker', 'index', 'hash', 'extra_field', 'nonfinite', 'massive_integer',
                                       'phase_keys', 'outcome', 'missing_call', 'footer_count', 'exit', 'duplicate'])
def test_reader_rejects_malformed_or_inconsistent_evidence_without_echoing_values(tmp_path, corruption):
    value = journal(tmp_path)
    complete(value)
    value.finish(0)
    data = rows(value)
    if corruption == 'schema':
        data[0]['schema'] = 'private-value'
    elif corruption == 'worker':
        data[0]['worker'] = []
    elif corruption == 'index':
        data[1]['index'] = True
    elif corruption == 'hash':
        data[2]['case_id_sha256'] = 'private-value'
    elif corruption == 'extra_field':
        data[1]['private-value'] = 'private-value'
    elif corruption == 'nonfinite':
        data[2]['wall_seconds'] = float('inf')
    elif corruption == 'massive_integer':
        data[2]['wall_seconds'] = 10 ** 1000
    elif corruption == 'phase_keys':
        data[2]['phases']['private-value'] = {}
    elif corruption == 'outcome':
        data[2]['phases']['call']['outcome'] = []
    elif corruption == 'missing_call':
        del data[2]['phases']['call']
    elif corruption == 'footer_count':
        data[-1]['finished_cases'] = 2
    elif corruption == 'exit':
        data[-1]['exitstatus'] = 1
    else:
        data.insert(-1, data[2].copy())
    path = tmp_path / 'corrupted.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in data))
    with pytest.raises(ValueError) as error:
        native_case_costs.read_case_costs(path)
    assert str(error.value) == 'native_case_cost_metadata_invalid'


def test_reader_refuses_stale_sessions(tmp_path):
    from datetime import datetime, timedelta

    value = journal(tmp_path)
    complete(value)
    value.finish(0)
    after = (datetime.fromisoformat(rows(value)[0]['observed_at']) + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match='native_case_cost_metadata_invalid'):
        native_case_costs.read_case_costs(value.path, not_before=after)


def test_reader_bounds_individual_input_records(tmp_path):
    path = tmp_path / 'oversized.jsonl'
    path.write_bytes(b'x' * (NativeCaseCosts.MAX_RECORD_BYTES + 1) + b'\n')
    with pytest.raises(ValueError, match='native_case_cost_metadata_invalid'):
        native_case_costs.read_case_costs(path, require_complete=False)


def test_partial_reader_exposes_a_truncated_tail_without_qualifying_it(tmp_path):
    value = journal(tmp_path)
    complete(value)
    value.finish(0)
    path = tmp_path / 'truncated.jsonl'
    lines = value.path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b''.join(lines[:-1]) + b'{"kind":')
    summary = native_case_costs.read_case_costs(path, require_complete=False)
    assert summary['truncated_tail'] and not summary['session_finished'] and not summary['complete']
    assert summary['finished_cases'] == 1
    with pytest.raises(ValueError, match='native_case_cost_metadata_invalid'):
        native_case_costs.read_case_costs(path)


def test_partial_mode_still_rejects_malformed_complete_records(tmp_path):
    path = tmp_path / 'malformed.jsonl'
    path.write_bytes(b'private-value\n')
    with pytest.raises(ValueError) as error:
        native_case_costs.read_case_costs(path, require_complete=False)
    assert str(error.value) == 'native_case_cost_metadata_invalid'
