"""Bounded CPU samples for owned qualification workers, never model evidence.

Only static code labels and counters are retained. Arguments, locals, reports,
parameters and source text are excluded. Sampling creates no extra threads and
never changes test outcomes, limits, worker allocation or declared workloads.
"""

import collections
import json
import os
import re
import signal
import time
import warnings
import weakref
from datetime import datetime, timezone
from pathlib import Path

import pytest


class NativeCPUDiagnostics:
    INTERVAL = .04
    SNAPSHOT_SECONDS = 30.
    MAX_ENTRIES = 8192
    MAX_DEPTH = 128
    MAX_SAMPLES = 200_000

    def __init__(self, progress_path, worker):
        if worker not in {"gw0", "gw1"}:
            raise ValueError("Unsupported native worker identity")
        progress = Path(progress_path).absolute()
        self.path = progress.parent.with_name(progress.parent.name + "-cpu") / ("cpu-" + worker + ".json")
        self._open, self._write, self._close, self._replace = os.open, os.write, os.close, os.replace
        self._clock, self._cpu, self._now, self._dumps = time.monotonic, time.process_time, datetime.now, json.dumps
        self._flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        self._normalize = os.path.normpath
        self._getsignal = getattr(signal, "getsignal", None)
        self._gettimer = getattr(signal, "getitimer", None)
        self._setsignal = getattr(signal, "signal", None)
        self._settimer = getattr(signal, "setitimer", None)
        self._signal, self._timer = getattr(signal, "SIGPROF", None), getattr(signal, "ITIMER_PROF", None)
        self._default = getattr(signal, "SIG_DFL", None)
        self._interval, self._period = self.INTERVAL, self.SNAPSHOT_SECONDS
        self._entries, self._depth, self._maximum = self.MAX_ENTRIES, self.MAX_DEPTH, self.MAX_SAMPLES
        self._callback = self.sample
        self._old_handler = None
        self._active = False
        self._warned = False
        self._codes, self._leaf, self._stack = {}, collections.Counter(), collections.Counter()
        self._repo = str(Path(__file__).absolute().parents[1]).replace("\\", "/") + "/"
        self._stdlib = str(Path(os.__file__).absolute().parent).replace("\\", "/") + "/"
        self._safe = re.compile(r"[A-Za-z0-9_./-]{1,384}")
        self._name = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
        self._started_wall, self._started_cpu = self._clock(), self._cpu()
        self._last_publish = None
        self.state = dict(schema="native_test_cpu_diagnostic_v1", worker=worker,
                          sample_mode="process_cpu_timer_main_python_frame", interval_seconds=self._interval,
                          available=False, status="configured", unavailable_reason=None,
                          samples=0, accepted_samples=0, dropped_samples=0, dropped_labels=0,
                          truncated_stacks=0, sample_errors=0, diagnostic_write_failed=False,
                          session_finished=False, session_exitstatus=None,
                          arguments_locals_parameters_or_source_retained=False, additional_threads=0)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError:
            pass

    def start(self):
        if self._active:
            return
        if None in (self._signal, self._timer, self._getsignal, self._gettimer, self._setsignal, self._settimer):
            self.state.update(status="unavailable", unavailable_reason="unsupported_timer")
            self.publish(force=True)
            return
        installed = False
        try:
            self._old_handler = self._getsignal(self._signal)
            if self._old_handler != self._default or self._gettimer(self._timer) != (0., 0.):
                self.state.update(status="unavailable", unavailable_reason="existing_timer_or_handler")
            else:
                self._setsignal(self._signal, self._callback)
                installed = True
                self._settimer(self._timer, self._interval, self._interval)
                self._active = True
                self.state.update(status="collecting", available=True)
        except Exception:
            if installed:
                try:
                    self._setsignal(self._signal, self._old_handler)
                except Exception:
                    pass
            self.state.update(status="unavailable", unavailable_reason="timer_start_failed")
        self.publish(force=True)

    def label(self, code):
        identity = id(code)
        cached = self._codes.get(identity)
        if cached is not None and cached[0]() is code:
            return cached[1]
        filename = self._normalize(code.co_filename).replace("\\", "/")
        if filename.startswith(self._repo):
            location = "repo/" + filename[len(self._repo):]
        elif "/site-packages/" in filename:
            location = "package/" + filename.split("/site-packages/", 1)[1]
        elif filename.startswith(self._stdlib):
            location = "stdlib/" + filename[len(self._stdlib):]
        else:
            location = "<generated>"
        if location != "<generated>" and not self._safe.fullmatch(location):
            location = "<generated>"
        name = code.co_name if location != "<generated>" and (
            self._name.fullmatch(code.co_name) or code.co_name in {"<lambda>", "<module>"}
        ) else "<generated>"
        label = location + ":" + str(code.co_firstlineno) + ":" + name
        if identity in self._codes or len(self._codes) < self._entries:
            self._codes[identity] = weakref.ref(code), label
        return label

    def increment(self, counts, label):
        if label in counts or len(counts) < self._entries:
            counts[label] += 1
        else:
            self.state["dropped_labels"] += 1

    def sample(self, signum, frame):
        try:
            self.state["samples"] += 1
            if self.state["accepted_samples"] >= self._maximum:
                self.state["dropped_samples"] += 1
                return
            self.state["accepted_samples"] += 1
            labels = []
            for _ in range(self._depth):
                if frame is None:
                    break
                labels.append(self.label(frame.f_code))
                frame = frame.f_back
            if frame is not None:
                self.state["truncated_stacks"] += 1
            if labels:
                self.increment(self._leaf, labels[0])
                for label in set(labels):
                    self.increment(self._stack, label)
        except Exception:
            self.state["sample_errors"] += 1

    def publish(self, *, force=False):
        now = self._clock()
        if not force and self._last_publish is not None and now - self._last_publish < self._period:
            return
        self._last_publish = now
        snapshot = {**self.state, "observed_at": self._now(timezone.utc).isoformat(),
                    "wall_seconds": max(0., now - self._started_wall),
                    "process_cpu_seconds": max(0., self._cpu() - self._started_cpu),
                    "leaf_samples": dict(self._leaf), "stack_samples": dict(self._stack)}
        temporary = str(self.path) + ".tmp"
        try:
            raw = (self._dumps(snapshot, sort_keys=True) + "\n").encode()
            descriptor = self._open(temporary, self._flags, 0o600)
            try:
                offset = 0
                while offset < len(raw):
                    written = self._write(descriptor, raw[offset:])
                    if written <= 0:
                        raise OSError("Diagnostic write made no progress")
                    offset += written
            finally:
                self._close(descriptor)
            self._replace(temporary, str(self.path))
        except OSError:
            self.state["diagnostic_write_failed"] = True
            if not self._warned:
                try:
                    warnings.warn("Native CPU diagnostics could not be retained", pytest.PytestWarning)
                except Warning:
                    pass
                self._warned = True

    def finish(self, exitstatus):
        if self._active:
            try:
                if self._getsignal(self._signal) is self._callback:
                    self._settimer(self._timer, 0.)
                    self._setsignal(self._signal, self._old_handler)
                else:
                    self.state.update(available=False, unavailable_reason="timer_ownership_changed")
            except Exception:
                self.state.update(available=False, unavailable_reason="timer_stop_failed")
            self._active = False
        self.state.update(status="finished", session_finished=True, session_exitstatus=int(exitstatus))
        self.publish(force=True)
