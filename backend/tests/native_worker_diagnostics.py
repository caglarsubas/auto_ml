"""Bounded test-worker progress, retained even when its controller times out.

Never changes outcomes or execution. Records only static case names and a hash
of the complete node ID, excluding parameter values, reports and local data.
"""

import hashlib
import json
import os
import re
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pytest


class NativeWorkerDiagnostics:
    def __init__(self, isolation_report, worker):
        if worker not in {"gw0", "gw1"}:
            raise ValueError("Unsupported native worker identity")
        self.path = Path(isolation_report).absolute().with_suffix("").with_name(
            Path(isolation_report).stem + "-workers"
        ) / (worker + ".json")
        self.started = None
        self.complete = False
        self.write_failed = False
        self._cpu = None
        # Observe independently of artifact/clock faults deliberately injected
        # by the tests. These are operation references, never cached test data.
        self._open, self._write, self._close, self._replace = os.open, os.write, os.close, os.replace
        self._clock, self._now, self._hash, self._dumps = time.monotonic, datetime.now, hashlib.sha256, json.dumps
        self._flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        self._case = re.compile(r"[A-Za-z0-9_./:-]{1,512}")
        self.filename = str(self.path)
        self.temporary = self.filename + ".tmp"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError:
            # publish() records the unavailable destination without changing
            # the test or session outcome.
            pass
        self.state = {
            "schema": "native_test_worker_diagnostic_v1",
            "worker": worker,
            "started_cases": 0,
            "finished_cases": 0,
            "case": None,
            "case_id_sha256": None,
            "phase": "configured",
            "last_report_phase": None,
            "outcome": None,
            "session_finished": False,
            "session_exitstatus": None,
            "diagnostic_write_failed": False,
        }
        self.publish()

    def pytest_sessionstart(self, session):
        from tests.native_cpu_diagnostics import NativeCPUDiagnostics

        self._cpu = NativeCPUDiagnostics(self.path, self.state["worker"])
        self._cpu.start()

    def publish(self):
        self.state["observed_at"] = self._now(timezone.utc).isoformat()
        self.state["elapsed_seconds"] = None if self.started is None else max(0.0, self._clock() - self.started)
        try:
            raw = (self._dumps(self.state, sort_keys=True) + "\n").encode()
            descriptor = self._open(self.temporary, self._flags, 0o600)
            try:
                offset = 0
                while offset < len(raw):
                    written = self._write(descriptor, raw[offset:])
                    if written <= 0:
                        raise OSError("Diagnostic write made no progress")
                    offset += written
            finally:
                self._close(descriptor)
            self._replace(self.temporary, self.filename)
        except OSError:
            self.state["diagnostic_write_failed"] = True
            if not self.write_failed:
                try:
                    warnings.warn("Native worker diagnostics could not be retained", pytest.PytestWarning)
                except Warning:
                    # A caller's -W error must not turn optional diagnostics into
                    # a different test outcome.
                    pass
                self.write_failed = True

    def pytest_runtest_logstart(self, nodeid, location):
        prefix = nodeid.split("[", 1)[0]
        self.state.update(
            case=prefix if self._case.fullmatch(prefix) else None,
            case_id_sha256=self._hash(nodeid.encode()).hexdigest(),
            started_cases=self.state["started_cases"] + 1,
            phase="setup",
            last_report_phase=None,
            outcome=None,
        )
        self.complete = False
        self.started = self._clock()
        self.publish()

    def pytest_runtest_logreport(self, report):
        if self._hash(report.nodeid.encode()).hexdigest() != self.state["case_id_sha256"]:
            return
        if report.when not in {"setup", "call", "teardown"}:
            return
        phase = ("call" if report.outcome == "passed" else "teardown") if report.when == "setup" else (
            "teardown" if report.when == "call" else "finished"
        )
        self.state.update(phase=phase, last_report_phase=report.when,
                          outcome=report.outcome if report.outcome in {"passed", "failed", "skipped"} else "unknown")
        if report.when == "teardown" and not self.complete:
            self.state["finished_cases"] += 1
            self.complete = True
        self.publish()
        if self._cpu is not None:
            self._cpu.publish()

    def pytest_sessionfinish(self, session, exitstatus):
        # Preserve the last phase. Session shutdown can follow an interrupted
        # test or a broken worker transport and does not prove case completion.
        self.state.update(session_finished=True, session_exitstatus=int(exitstatus))
        self.publish()
        if self._cpu is not None:
            self._cpu.finish(exitstatus)
