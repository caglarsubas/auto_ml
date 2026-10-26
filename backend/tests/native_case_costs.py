"""Bounded metadata-only case costs survive incomplete native qualification.

No arguments, parameter values, reports, exceptions, locals or source text.
CPU is this worker process (including its threads), excluding child processes.
Observations never change test outcomes, execution, resource limits or retries.
"""
import json
import math
import os
import re
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path



class NativeCaseCosts:
    MAX_CASES = 10_000
    MAX_RECORD_BYTES = 2048

    def __init__(self, progress_path, worker):
        if worker not in {'gw0', 'gw1'}:
            raise ValueError('Unsupported native worker identity')
        from pytest import PytestWarning

        self._warning_type = PytestWarning
        progress = Path(progress_path).absolute()
        self.path = progress.parent.with_name(progress.parent.name + '-costs') / ('cost-' + worker + '.jsonl')
        self._open, self._write, self._close = os.open, os.write, os.close
        self._wall, self._cpu, self._now, self._dumps = time.monotonic, time.process_time, datetime.now, json.dumps
        self._warn = warnings.warn
        self._flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | os.O_NOFOLLOW
        self._prefix = re.compile(r'tests/[A-Za-z0-9_./-]+\.py(?:::[A-Za-z_][A-Za-z0-9_]*)+')
        self._hash = re.compile(r'[0-9a-f]{64}')
        self._maximum, self._record_limit = self.MAX_CASES, self.MAX_RECORD_BYTES
        self.descriptor = None
        self.failed = self.closed = self.truncated = self._warned = False
        self.started = self.finished = 0
        self.active = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.descriptor = self._open(str(self.path), self._flags, 0o600)
        except OSError:
            self._failure()
        self._record(dict(kind='session_start', schema='native_test_case_costs_v1', worker=worker,
                          observed_at=self._timestamp(), maximum_cases=self._maximum,
                          cpu_mode='worker_process_including_threads_excluding_children',
                          arguments_parameters_reports_locals_or_source_retained=False))

    def _timestamp(self):
        return self._now(timezone.utc).isoformat()

    def _failure(self):
        self.failed = True
        if not self._warned:
            self._warned = True
            try:
                self._warn('Native case-cost diagnostics could not be retained', self._warning_type)
            except Warning:
                pass

    def _record(self, value):
        if self.failed or self.closed or self.descriptor is None:
            return
        try:
            raw = (self._dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()
            if len(raw) > self._record_limit:
                raise ValueError('Diagnostic record exceeds its bound')
            offset = 0
            while offset < len(raw):
                written = self._write(self.descriptor, raw[offset:])
                if written <= 0:
                    raise OSError('Diagnostic write made no progress')
                offset += written
        except (OSError, ValueError, TypeError):
            self._failure()

    @staticmethod
    def _elapsed(clock, started):
        try:
            value = float(clock() - started)
            return max(0., value) if math.isfinite(value) else None
        except (TypeError, ValueError, OSError, OverflowError):
            return None

    def start(self, prefix, identity):
        if self.closed:
            return
        self.started += 1
        if self.active is not None:
            self._record(dict(kind='incomplete', index=self.active['index']))
            self.active = None
        if self.started > self._maximum:
            if not self.truncated:
                self.truncated = True
                self._record(dict(kind='limit', completed_cases=self.finished))
            return
        label = prefix if isinstance(prefix, str) and len(prefix) <= 512 and self._prefix.fullmatch(prefix) else None
        identity = identity if isinstance(identity, str) and self._hash.fullmatch(identity) else None
        self.active = dict(index=self.started, case=label, case_id_sha256=identity,
                           wall=self._wall(), cpu=self._cpu(), phases={})
        self._record(dict(kind='case_start', index=self.started, case=label, case_id_sha256=identity))

    def phase(self, when, outcome, duration):
        if self.active is None or when not in {'setup', 'call', 'teardown'}:
            return
        try:
            duration = float(duration)
            duration = duration if math.isfinite(duration) and duration >= 0 else None
        except (TypeError, ValueError, OverflowError):
            duration = None
        self.active['phases'][when] = dict(outcome=outcome if outcome in {'passed', 'failed', 'skipped'} else 'unknown',
                                          wall_seconds=duration)

    def finish_case(self):
        if self.active is None or self.closed:
            return
        value, self.active = self.active, None
        self.finished += 1
        self._record(dict(kind='case_finish', index=value['index'], case_id_sha256=value['case_id_sha256'],
                          wall_seconds=self._elapsed(self._wall, value['wall']),
                          process_cpu_seconds=self._elapsed(self._cpu, value['cpu']), phases=value['phases']))

    def finish(self, exitstatus):
        if self.closed:
            return
        self._record(dict(kind='session_finish', observed_at=self._timestamp(), exitstatus=int(exitstatus),
                          started_cases=self.started, finished_cases=self.finished, truncated=self.truncated,
                          incomplete_case=self.active['index'] if self.active is not None else None))
        if self.descriptor is not None:
            try:
                self._close(self.descriptor)
            except OSError:
                self._failure()
        self.closed = True


def read_case_costs(path, *, require_complete=True, not_before=None):
    """Validate bounded untrusted metadata; partial observations never imply success."""
    def invalid():
        raise ValueError('native_case_cost_metadata_invalid')

    def fields(row, expected):
        if not isinstance(row, dict) or set(row) != set(expected.split()):
            invalid()

    def integer(value):
        return type(value) is int and value >= 0

    def finite(value):
        try:
            return type(value) in {int, float} and math.isfinite(value) and value >= 0
        except OverflowError:
            return False

    def timestamp(value):
        try:
            if not isinstance(value, str) or len(value) > 64:
                invalid()
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                invalid()
            return parsed
        except (TypeError, ValueError):
            invalid()

    starts, completed, active, abandoned, limited, footer, header = {}, [], None, [], False, None, None
    tail_truncated = False
    with Path(path).open('rb') as stream:
        for number, raw in enumerate(iter(lambda: stream.readline(NativeCaseCosts.MAX_RECORD_BYTES + 1), b''), 1):
            if number > 2 * NativeCaseCosts.MAX_CASES + 3 or len(raw) > NativeCaseCosts.MAX_RECORD_BYTES:
                invalid()
            if not raw.endswith(b'\n'):
                tail_truncated = True
                if require_complete:
                    invalid()
                break
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                invalid()
            if header is None:
                fields(row, 'kind schema worker observed_at maximum_cases cpu_mode arguments_parameters_reports_locals_or_source_retained')
                if (row['kind'] != 'session_start' or row['schema'] != 'native_test_case_costs_v1'
                        or row['worker'] not in ('gw0', 'gw1') or not integer(row['maximum_cases'])
                        or not 0 < row['maximum_cases'] <= NativeCaseCosts.MAX_CASES
                        or row['cpu_mode'] != 'worker_process_including_threads_excluding_children'
                        or row['arguments_parameters_reports_locals_or_source_retained'] is not False):
                    invalid()
                started_at = timestamp(row['observed_at'])
                if not_before is not None and started_at < timestamp(not_before):
                    invalid()
                header = row
                continue
            if footer is not None or not isinstance(row, dict):
                invalid()
            kind = row.get('kind')
            if kind == 'case_start':
                fields(row, 'kind index case case_id_sha256')
                if (active is not None or limited or not integer(row['index']) or row['index'] != len(starts) + 1
                        or row['index'] > header['maximum_cases']
                        or not isinstance(row['case_id_sha256'], str)
                        or not re.fullmatch(r'[0-9a-f]{64}', row['case_id_sha256'])
                        or (row['case'] is not None and (not isinstance(row['case'], str) or len(row['case']) > 512
                            or not re.fullmatch(r'tests/[A-Za-z0-9_./-]+\.py(?:::[A-Za-z_][A-Za-z0-9_]*)+', row['case'])))):
                    invalid()
                starts[row['index']] = row
                active = row['index']
            elif kind == 'case_finish':
                fields(row, 'kind index case_id_sha256 wall_seconds process_cpu_seconds phases')
                if (not integer(row['index']) or row['index'] != active
                        or row['case_id_sha256'] != starts[active]['case_id_sha256']
                        or not finite(row['wall_seconds']) or not finite(row['process_cpu_seconds'])
                        or not isinstance(row['phases'], dict) or not {'setup', 'teardown'} <= row['phases'].keys()
                        or not row['phases'].keys() <= {'setup', 'call', 'teardown'}):
                    invalid()
                for phase in row['phases'].values():
                    fields(phase, 'outcome wall_seconds')
                    if phase['outcome'] not in ('passed', 'failed', 'skipped') or not finite(phase['wall_seconds']):
                        invalid()
                if row['phases']['setup']['outcome'] == 'passed' and 'call' not in row['phases']:
                    invalid()
                completed.append({**row, 'case': starts[active]['case']})
                active = None
            elif kind == 'incomplete':
                fields(row, 'kind index')
                if not integer(row['index']) or row['index'] != active:
                    invalid()
                abandoned.append(starts[active])
                active = None
            elif kind == 'limit':
                fields(row, 'kind completed_cases')
                if (limited or active is not None or len(starts) != header['maximum_cases']
                        or not integer(row['completed_cases']) or row['completed_cases'] != len(completed)):
                    invalid()
                limited = True
            elif kind == 'session_finish':
                fields(row, 'kind observed_at exitstatus started_cases finished_cases truncated incomplete_case')
                if (not integer(row['started_cases']) or not integer(row['finished_cases']) or not integer(row['exitstatus'])
                        or row['finished_cases'] != len(completed) or row['incomplete_case'] != active
                        or (row['incomplete_case'] is not None and not integer(row['incomplete_case']))
                        or row['truncated'] is not limited or row['started_cases'] < len(starts)
                        or (not limited and row['started_cases'] != len(starts))
                        or timestamp(row['observed_at']) < started_at):
                    invalid()
                footer = row
            else:
                invalid()
    if header is None:
        invalid()
    failed = sum(any(phase['outcome'] == 'failed' for phase in row['phases'].values()) for row in completed)
    skipped = sum(any(phase['outcome'] == 'skipped' for phase in row['phases'].values()) for row in completed)
    complete = bool(footer and footer['exitstatus'] == 0 and active is None and not abandoned
                    and not limited and not tail_truncated and len(starts) == len(completed) and failed == 0)
    if require_complete and not complete:
        invalid()
    by_file = {}
    for row in completed:
        file = row['case'].split('::')[0] if row['case'] else '<unlabeled>'
        entry = by_file.setdefault(file, dict(cases=0, wall_seconds=0., process_cpu_seconds=0.))
        entry['cases'] += 1
        entry['wall_seconds'] += row['wall_seconds']
        entry['process_cpu_seconds'] += row['process_cpu_seconds']
        if not finite(entry['wall_seconds']) or not finite(entry['process_cpu_seconds']):
            invalid()
    def slowest(key):
        return [{name: row[name] for name in ['index', 'case', 'case_id_sha256', 'wall_seconds', 'process_cpu_seconds']}
                for row in sorted(completed, key=lambda row: row[key], reverse=True)[:20]]
    return dict(schema='native_test_case_cost_summary_v1', worker=header['worker'], complete=complete,
                started_cases=len(starts), finished_cases=len(completed), failed_cases=failed, skipped_cases=skipped,
                active_case=starts.get(active), abandoned_cases=abandoned, limited=limited, truncated_tail=tail_truncated,
                session_finished=footer is not None, session_exitstatus=footer['exitstatus'] if footer else None,
                files=by_file, slowest_wall=slowest('wall_seconds'), slowest_cpu=slowest('process_cpu_seconds'),
                arguments_parameters_reports_locals_or_source_retained=False)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    parser.add_argument('--partial', action='store_true', help='Inspect incomplete evidence without claiming qualification')
    parser.add_argument('--not-before', help='Refuse stale sessions before this timezone-aware ISO timestamp')
    arguments = parser.parse_args()
    try:
        print(json.dumps(read_case_costs(arguments.path, require_complete=not arguments.partial,
                                         not_before=arguments.not_before), sort_keys=True, indent=2))
    except (ValueError, OSError):
        raise SystemExit('native_case_cost_metadata_invalid_or_unavailable') from None
