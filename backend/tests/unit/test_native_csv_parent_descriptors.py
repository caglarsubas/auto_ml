"""Native CSV capture cannot follow a replaced parent outside managed storage."""

import errno
import os
import socket
import time
from pathlib import Path

import pytest

from access_control import projects
from execution_jobs import csv_scoring, service
from tests.unit.test_native_csv_input_files import capture, input_file  # noqa: F401

pytestmark = pytest.mark.unit
ORIGINAL = b"x,other\n1,2\n"
OUTSIDE = b"x,other\n99,100\n"


def nested(input_file, depth):
    root = input_file.parent
    parents = []
    parent = root
    for i in range(depth):
        parent = parent / ("p" + str(i))
        parent.mkdir()
        parents.append(parent)
    path = parent / input_file.name
    input_file.rename(path)
    csv_scoring.Declaration.objects.get(pk=7).file.name = str(path.relative_to(root))
    return root, parents, path


def redirect(parent, path, outside):
    remainder = path.relative_to(parent)
    target = outside / remainder
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(OUTSIDE)
    parent.rename(parent.with_name(parent.name + "-retained"))
    parent.symlink_to(outside, target_is_directory=True)


def actual_receipt(entrypoint):
    result = capture(entrypoint)
    return result if entrypoint == "prepare" else result[1]


def assert_closed(opened):
    for descriptor in opened:
        with pytest.raises(OSError) as exc:
            os.fstat(descriptor)
        assert exc.value.errno == errno.EBADF


@pytest.mark.parametrize("depth,index", [(1, 0), (2, 0), (2, 1), (3, 0), (3, 2)])
@pytest.mark.parametrize("entrypoint", ["prepare", "worker"])
def test_parent_symlink_inserted_after_authority_never_supplies_csv_bytes(input_file, tmp_path, monkeypatch, depth, index, entrypoint):
    _, parents, path = nested(input_file, depth)
    def replace(*args, **kwargs):
        redirect(parents[index], path, tmp_path / "outside")
    monkeypatch.setattr(csv_scoring.projects, "path_authority", replace)
    with pytest.raises(service.JobConflict, match="^job_input_unavailable$"):
        capture(entrypoint)


@pytest.mark.parametrize("depth", [1, 2, 3])
@pytest.mark.parametrize("entrypoint", ["prepare", "worker"])
def test_parent_replaced_at_file_open_keeps_the_pinned_original_directory(input_file, tmp_path, monkeypatch, depth, entrypoint):
    _, parents, path = nested(input_file, depth)
    original_open = os.open
    changed = False
    opened = []
    def racing_open(name, flags, *args, **kwargs):
        nonlocal changed
        if Path(name).name == path.name and not changed:
            changed = True
            redirect(parents[-1], path, tmp_path / "outside")
        descriptor = original_open(name, flags, *args, **kwargs)
        opened.append(descriptor)
        return descriptor
    monkeypatch.setattr(csv_scoring.os, "open", racing_open)
    receipt = actual_receipt(entrypoint)
    assert changed and receipt["sha256"] == csv_scoring.csv_input(ORIGINAL)["sha256"]
    assert receipt["sha256"] != csv_scoring.csv_input(OUTSIDE)["sha256"]
    assert_closed(opened)


@pytest.mark.parametrize("entrypoint", ["prepare", "worker"])
def test_root_symlink_inserted_after_authority_is_rejected(input_file, tmp_path, monkeypatch, entrypoint):
    root, _, path = nested(input_file, 2)
    def replace(*args, **kwargs):
        redirect(root, path, tmp_path / "outside")
    monkeypatch.setattr(csv_scoring.projects, "path_authority", replace)
    with pytest.raises(service.JobConflict, match="^job_input_unavailable$"):
        capture(entrypoint)


@pytest.mark.parametrize("kind", ["fifo", "socket", "regular", "missing"])
@pytest.mark.parametrize("entrypoint", ["prepare", "worker"])
def test_changed_parent_types_fail_promptly_with_existing_diagnostics(input_file, monkeypatch, kind, entrypoint):
    _, parents, _ = nested(input_file, 2)
    parent = parents[-1]
    endpoint = socket.socket(socket.AF_UNIX)
    def replace(*args, **kwargs):
        parent.rename(parent.with_name(parent.name + "-retained"))
        if kind == "fifo":
            os.mkfifo(parent)
        elif kind == "socket":
            endpoint.bind(str(parent))
        elif kind == "regular":
            parent.write_bytes(b"owned fixture")
    monkeypatch.setattr(csv_scoring.projects, "path_authority", replace)
    started = time.monotonic()
    try:
        error = FileNotFoundError if kind == "missing" else service.JobConflict
        with pytest.raises(error) as exc:
            capture(entrypoint)
        if kind != "missing":
            assert exc.value.code == "job_input_unavailable"
        assert time.monotonic() - started < 2
    finally:
        endpoint.close()


@pytest.mark.parametrize("depth", [1, 3])
@pytest.mark.parametrize("fault", ["success", "budget", "read", "checkpoint", "wrapper", "root_open", "parent_open", "file_open"])
def test_all_owned_directory_and_file_descriptors_close(input_file, monkeypatch, depth, fault):
    root, parents, path = nested(input_file, depth)
    if fault == "budget":
        path.write_bytes(b"x" * (csv_scoring.BUDGET["max_input_bytes"] + 1))
    opened = []
    original_open, original_fdopen = os.open, os.fdopen
    def tracked(name, flags, *args, **kwargs):
        fail = fault == "root_open" and Path(name) == root
        fail |= fault == "parent_open" and str(name) == parents[-1].name
        fail |= fault == "file_open" and Path(name).name == path.name
        if fail:
            raise OSError("private-io-sentinel")
        descriptor = original_open(name, flags, *args, **kwargs)
        opened.append(descriptor)
        return descriptor
    def wrapped(descriptor, *args, **kwargs):
        if fault == "wrapper":
            raise OSError("private-io-sentinel")
        stream = original_fdopen(descriptor, *args, **kwargs)
        if fault == "read":
            stream.read = lambda *a: (_ for _ in ()).throw(OSError("private-io-sentinel"))
        return stream
    def check():
        if fault == "checkpoint":
            raise service.JobStopped
    monkeypatch.setattr(csv_scoring.os, "open", tracked)
    monkeypatch.setattr(csv_scoring.os, "fdopen", wrapped)
    if fault == "success":
        assert csv_scoring.input_bytes(1, 7, check)[0] == ORIGINAL
    else:
        error = service.JobStopped if fault == "checkpoint" else service.JobConflict
        with pytest.raises(error) as exc:
            csv_scoring.input_bytes(1, 7, check)
        if fault != "checkpoint":
            assert exc.value.code == ("job_input_budget_exceeded" if fault == "budget" else "job_input_unavailable")
            assert "private-io-sentinel" not in str(exc.value)
    if fault == "root_open":
        assert opened == []
    else:
        assert opened
    assert_closed(opened)


@pytest.mark.parametrize("depth", [1, 2, 3])
@pytest.mark.parametrize("raw", [ORIGINAL, b"\xef\xbb\xbfx,other\r\n1,2\r\n"])
def test_nested_regular_capture_and_expected_receipt_remain_exact(input_file, depth, raw):
    _, _, path = nested(input_file, depth)
    path.write_bytes(raw)
    actual, receipt, authority = csv_scoring.input_bytes(1, 7)
    assert actual == raw and receipt["sha256"] == csv_scoring.csv_input(raw)["sha256"]
    assert receipt["bytes"] == len(raw) and authority == {"fixture": "read-authority"}
    again, pinned, _ = csv_scoring.input_bytes(1, 7, expected=receipt)
    assert again == raw and pinned == receipt


@pytest.mark.parametrize("depth", [1, 3])
def test_path_authority_denial_precedes_all_descriptor_opens(input_file, monkeypatch, depth):
    nested(input_file, depth)
    def denied(*args, **kwargs):
        raise projects.ProjectDenied("project_access_denied")
    monkeypatch.setattr(csv_scoring.projects, "path_authority", denied)
    monkeypatch.setattr(csv_scoring.os, "open", lambda *a, **k: pytest.fail("denied path reached descriptor open"))
    with pytest.raises(projects.ProjectDenied):
        csv_scoring.input_bytes(1, 7)
