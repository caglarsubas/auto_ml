"""Native input capture must reject special files without waiting for a writer."""

import multiprocessing
import os
import socket
from types import SimpleNamespace

import pytest

from execution_jobs import csv_scoring, service

pytestmark = pytest.mark.unit


@pytest.fixture
def input_file(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.MEDIA_ROOT.mkdir()
    path = settings.MEDIA_ROOT / "batch.csv"
    path.write_bytes(b"x,other\n1,2\n")
    dataset = SimpleNamespace(has_header=True, file=SimpleNamespace(name="batch.csv"), original_name="batch.csv")
    authority = {"fixture": "read-authority"}
    monkeypatch.setattr(csv_scoring, "Declaration", SimpleNamespace(objects=SimpleNamespace(get=lambda **kwargs: dataset)))
    monkeypatch.setattr(csv_scoring.projects, "dataset_authority", lambda *args: authority)
    monkeypatch.setattr(csv_scoring.projects, "path_authority", lambda *args, **kwargs: authority)
    monkeypatch.setattr(csv_scoring.projects, "recheck", lambda scope: None)
    monkeypatch.setattr(csv_scoring.projects, "governed", lambda: True)
    return path


def capture(entrypoint):
    if entrypoint == "prepare":
        return csv_scoring.prepare(SimpleNamespace(pk=1), 7)
    return csv_scoring.input_bytes(1, 7)


@pytest.mark.parametrize("entrypoint", ["prepare", "worker"])
@pytest.mark.parametrize("replacement", [False, True])
def test_real_fifo_is_rejected_without_waiting_for_a_writer(input_file, monkeypatch, entrypoint, replacement):
    def replace(*args, **kwargs):
        input_file.unlink()
        os.mkfifo(input_file)

    if replacement:
        monkeypatch.setattr(csv_scoring.projects, "path_authority", replace)
    else:
        replace()
    # Fork inherits only controlled authority/metadata seams. The child performs
    # no database work; its actual FIFO open is the operation under test.
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)

    def probe():
        try:
            capture(entrypoint)
            send.send("accepted")
        except service.JobConflict as error:
            send.send(error.code)
        except Exception as error:
            send.send(type(error).__name__)
        finally:
            send.close()

    child = context.Process(target=probe, daemon=True)
    child.start()
    send.close()
    try:
        child.join(3)
        assert not child.is_alive(), "native input capture blocked on an owned FIFO"
        assert child.exitcode == 0 and receive.poll()
        assert receive.recv() == "job_input_unavailable"
    finally:
        if child.is_alive():
            child.terminate()
            child.join(3)
        child.close()
        receive.close()


@pytest.mark.parametrize("entrypoint", ["prepare", "worker"])
@pytest.mark.parametrize("fault", ["directory", "socket", "late_symlink", "late_directory"])
def test_special_or_replaced_inputs_never_become_csv_bytes(input_file, tmp_path, monkeypatch, entrypoint, fault):
    target = tmp_path / "outside.csv"
    target.write_bytes(b"private-outside-sentinel")
    endpoint = socket.socket(socket.AF_UNIX)

    def replace(*args, **kwargs):
        input_file.unlink()
        if fault == "late_symlink":
            input_file.symlink_to(target)
        elif fault == "socket":
            endpoint.bind(str(input_file))
        else:
            input_file.mkdir()

    if fault.startswith("late_"):
        monkeypatch.setattr(csv_scoring.projects, "path_authority", replace)
    else:
        replace()
    try:
        with pytest.raises(service.JobConflict, match="^job_input_unavailable$"):
            capture(entrypoint)
    finally:
        endpoint.close()


@pytest.mark.parametrize("raw", [b"x\n1\n", b"\xef\xbb\xbfx\r\n1\r\n", "x\né\n".encode(), b"x\n\"one,two\"\n"])
def test_regular_csv_bytes_and_receipts_remain_exact(input_file, raw):
    input_file.write_bytes(raw)
    actual, receipt, authority = csv_scoring.input_bytes(1, 7)
    assert actual == raw and receipt["sha256"] == csv_scoring.csv_input(raw)["sha256"]
    assert receipt["bytes"] == len(raw) and authority == {"fixture": "read-authority"}
    assert csv_scoring.prepare(SimpleNamespace(pk=1), 7)["sha256"] == receipt["sha256"]


@pytest.mark.parametrize("failure", ["budget", "read", "checkpoint", "wrapper"])
def test_owned_descriptor_is_closed_on_failed_capture(input_file, monkeypatch, failure):
    descriptor = None
    original_open, original_fdopen = os.open, os.fdopen

    def opened(path, flags, *args, **kwargs):
        nonlocal descriptor
        descriptor = original_open(path, flags, *args, **kwargs)
        return descriptor

    def wrapped(fd, *args, **kwargs):
        if failure == "wrapper":
            raise OSError("private-io-sentinel")
        stream = original_fdopen(fd, *args, **kwargs)
        if failure == "read":
            stream.read = lambda *args: (_ for _ in ()).throw(OSError("private-io-sentinel"))
        return stream

    monkeypatch.setattr(csv_scoring.os, "open", opened)
    monkeypatch.setattr(csv_scoring.os, "fdopen", wrapped)
    if failure == "budget":
        input_file.write_bytes(b"x" * (csv_scoring.BUDGET["max_input_bytes"] + 1))

    def check():
        if failure == "checkpoint":
            raise service.JobStopped

    expected = service.JobStopped if failure == "checkpoint" else service.JobConflict
    with pytest.raises(expected) as caught:
        csv_scoring.input_bytes(1, 7, check)
    if expected is service.JobConflict:
        assert caught.value.code == ("job_input_budget_exceeded" if failure == "budget" else "job_input_unavailable")
        assert "private-io-sentinel" not in str(caught.value)
    assert descriptor is not None, "capture must pin its input with a descriptor"
    with pytest.raises(OSError):
        os.fstat(descriptor)
