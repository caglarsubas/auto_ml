"""Operator probe stdout stays in bounded memory and closes owned pipe resources."""

import errno
import importlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
RUN = subprocess.run
LIMIT = 131072
API = {"container_id": "a" * 64, "attention_required": False}
VALUE = {"schema": "native_queue_operator_snapshot_v1", "status": "observed"}


def module():
    return importlib.import_module("private_queue_incidents")


def no_spool(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("probe stdout was spooled to a temporary file")
    monkeypatch.setattr(tempfile, "TemporaryFile", forbidden)


def child(monkeypatch, program):
    m = module()
    def run(args, **kwargs):
        assert args == [*m.resources.PREFIX, "exec", "--user", "10001:10001", API["container_id"],
                        "python", "-m", "execution_jobs.operator_triage"]
        assert kwargs["timeout"] == 20 and kwargs["stderr"] == subprocess.DEVNULL and kwargs["check"] is False
        return RUN([sys.executable, "-c", program], **kwargs)
    monkeypatch.setattr(m.subprocess, "run", run)
    return m


def pipe_tracker(monkeypatch):
    opened = []
    pipe = os.pipe
    def tracked():
        pair = pipe()
        opened.extend(pair)
        return pair
    monkeypatch.setattr(os, "pipe", tracked)
    return opened


def closed(descriptors):
    assert descriptors
    for fd in descriptors:
        with pytest.raises(OSError) as exc:
            os.fstat(fd)
        assert exc.value.errno == errno.EBADF
    assert not any(t.name == "declarai-operator-probe-reader" for t in threading.enumerate())


@pytest.mark.parametrize("size", [128, 4096, 65536, LIMIT])
def test_real_transport_never_spools_output_and_accepts_exact_byte_limit(monkeypatch, size):
    value = {**VALUE, "padding": ""}
    raw = json.dumps(value, separators=(",", ":")).encode()
    value["padding"] = "x" * (size - len(raw))
    raw = json.dumps(value, separators=(",", ":")).encode()
    assert len(raw) == size
    m = child(monkeypatch, f"import json,sys; value=json.loads({json.dumps(VALUE)!r}); "
              f"value['padding']='x'*{len(value['padding'])}; "
              "sys.stdout.write(json.dumps(value,separators=(',',':')))")
    no_spool(monkeypatch)
    assert m.probe(API) == value


@pytest.mark.parametrize("raw", [b"", b"private-secret", b"[]", b"null", b"\xff", b"{}", b"[" * 2000 + b"]" * 2000],
                         ids=["empty", "text", "array", "null", "utf8", "schema", "nesting"])
def test_real_malformed_transport_output_is_rejected_without_disclosing_it(monkeypatch, raw):
    m = child(monkeypatch, f"import sys; sys.stdout.buffer.write({raw!r})")
    no_spool(monkeypatch)
    with pytest.raises(m.checker.planner.PlanError, match="^queue_incident_probe_output_invalid$"):
        m.probe(API)


@pytest.mark.parametrize("size", [LIMIT + 1, LIMIT + 8192, 4 * 1024**2])
def test_real_oversized_stdout_is_drained_and_rejected_without_disk_capture(monkeypatch, size):
    m = child(monkeypatch, f"import sys; sys.stdout.buffer.write(b'x' * {size})")
    no_spool(monkeypatch)
    with pytest.raises(m.checker.planner.PlanError, match="^queue_incident_probe_output_invalid$"):
        m.probe(API)


@pytest.mark.parametrize("size", [0, 1, 8191, 8192, LIMIT - 1, LIMIT, LIMIT + 1, 524288])
def test_pipe_capture_retains_only_the_bounded_prefix_and_closes_descriptors(monkeypatch, size):
    m = module()
    opened = pipe_tracker(monkeypatch)
    raw = (bytes(range(256)) * ((size + 255) // 256))[:size]
    with m._probe_capture() as (output, captured):
        assert output.write(raw) == size
    assert bytes(captured) == raw[:LIMIT + 1]
    closed(opened)


def test_inherited_writer_does_not_hold_capture_cleanup_open(monkeypatch):
    m = module()
    opened = pipe_tracker(monkeypatch)
    duplicate = None
    released = threading.Event()
    timer = None
    try:
        started = time.monotonic()
        with m._probe_capture() as (output, captured):
            duplicate = os.dup(output.fileno())
            def release():
                os.close(duplicate)
                released.set()
            timer = threading.Timer(5, release)
            timer.start()
            output.write(json.dumps(VALUE).encode())
        assert time.monotonic() - started < 2
        assert not released.is_set() and json.loads(captured) == VALUE
        closed(opened)
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        if duplicate is not None and not released.is_set():
            os.close(duplicate)


@pytest.mark.parametrize("fault", ["os_error", "timeout", "interrupt"])
def test_transport_exceptions_close_pipes_and_keep_sanitized_failure_semantics(monkeypatch, fault):
    m = module()
    opened = pipe_tracker(monkeypatch)
    def run(*args, **kwargs):
        if fault == "interrupt":
            raise KeyboardInterrupt
        if fault == "timeout":
            raise subprocess.TimeoutExpired(args, 20, stderr="private-secret")
        raise OSError("private-secret")
    monkeypatch.setattr(m.subprocess, "run", run)
    no_spool(monkeypatch)
    if fault == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            m.probe(API)
    else:
        assert m.probe(API) == {"status": "unavailable", "reason": "probe_transport_unavailable"}
    closed(opened)


@pytest.mark.parametrize("error", [OSError, MemoryError, RuntimeError, SystemExit])
def test_reader_failure_cannot_publish_partial_observation(monkeypatch, error):
    m = module()
    opened = pipe_tracker(monkeypatch)
    reads = iter([json.dumps(VALUE).encode()])
    def failed_read(*args):
        try:
            return next(reads)
        except StopIteration:
            raise error("private-secret") from None
    monkeypatch.setattr(os, "read", failed_read)
    monkeypatch.setattr(m.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    assert m.probe(API) == {"status": "unavailable", "reason": "probe_transport_unavailable"}
    closed(opened)


def test_thread_start_failure_closes_both_pipe_descriptors(monkeypatch):
    m = module()
    opened = pipe_tracker(monkeypatch)
    def unavailable(*args):
        raise RuntimeError("private-secret")
    monkeypatch.setattr(threading.Thread, "start", unavailable)
    monkeypatch.setattr(m.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    assert m.probe(API) == {"status": "unavailable", "reason": "probe_transport_unavailable"}
    closed(opened)


def test_pipe_allocation_failure_is_sanitized_before_child_launch(monkeypatch):
    m = module()
    def unavailable():
        raise OSError("private-secret")
    monkeypatch.setattr(os, "pipe", unavailable)
    monkeypatch.setattr(m.subprocess, "run", lambda *args, **kwargs: pytest.fail("child launched without capture"))
    assert m.probe(API) == {"status": "unavailable", "reason": "probe_transport_unavailable"}


@pytest.mark.parametrize("raw", [b"", json.dumps(VALUE).encode()], ids=["empty", "json"])
def test_nonzero_real_child_remains_an_unavailable_probe(monkeypatch, raw):
    m = child(monkeypatch, f"import sys; sys.stdout.buffer.write({raw!r}); sys.exit(1)")
    no_spool(monkeypatch)
    assert m.probe(API) == {"status": "unavailable", "reason": "probe_unavailable"}


def test_real_stderr_is_discarded_and_never_mixed_with_stdout(monkeypatch):
    m = child(monkeypatch, f"import sys; sys.stderr.write('private-secret' * 10000); print({json.dumps(VALUE)!r})")
    no_spool(monkeypatch)
    assert m.probe(API) == VALUE


def test_real_child_retains_the_existing_twenty_second_timeout(monkeypatch):
    m = child(monkeypatch, "import time; time.sleep(30)")
    no_spool(monkeypatch)
    started = time.monotonic()
    assert m.probe(API) == {"status": "unavailable", "reason": "probe_transport_unavailable"}
    assert 19 <= time.monotonic() - started < 24


def test_capture_state_initialization_failure_closes_any_owned_descriptors(monkeypatch):
    m = module()
    opened = pipe_tracker(monkeypatch)
    def unavailable():
        raise OSError("private-secret")
    monkeypatch.setattr(threading, "Event", unavailable)
    monkeypatch.setattr(m.subprocess, "run", lambda *args, **kwargs: pytest.fail("child launched without capture state"))
    try:
        assert m.probe(API) == {"status": "unavailable", "reason": "probe_transport_unavailable"}
        if opened:
            closed(opened)
        assert not any(t.name == "declarai-operator-probe-reader" for t in threading.enumerate())
    finally:
        # Keep a deliberately failing implementation from leaking into the suite.
        for fd in opened:
            try:
                os.close(fd)
            except OSError as exc:
                assert exc.errno == errno.EBADF
