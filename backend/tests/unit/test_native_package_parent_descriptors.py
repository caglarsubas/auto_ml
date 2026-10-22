"""Owned package reads stay inside pinned storage parents without changing receipts."""

import errno
import hashlib
import os
import shutil
import socket
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from execution_jobs import service
from tests.unit.test_native_package_files import package, worker  # noqa: F401

pytestmark = pytest.mark.unit
NAMES = ["manifest.json", "publication.json", "evaluation.json", "model_card.json", "native.bin"]


def nested(package, monkeypatch, depth):
    root = package.out.parent
    parents = []
    parent = root
    for i in range(depth):
        parent = parent / ("p" + str(i))
        parent.mkdir()
        parents.append(parent)
    if depth:
        destination = parent / "bundle"
        package.out.rename(destination)
        package.out = destination
    parents.append(package.out)
    monkeypatch.setattr(service, "bundle_dir", lambda *args: package.out)
    return root, parents


def redirect(parent, outside, *, changed=None):
    shutil.copytree(parent, outside)
    if changed is not None:
        relative, raw = changed
        (outside / relative).write_bytes(raw)
    parent.rename(parent.with_name(parent.name + "-retained"))
    parent.symlink_to(outside, target_is_directory=True)


def read(path):
    if path.name in {"manifest.json", "publication.json"}:
        return service._package_metadata(path)
    if path.name in {"evaluation.json", "model_card.json"}:
        return service._artifact_bytes(path, 8 * 1024**2, "job_evidence_budget_exceeded")
    with service._regular_artifact(path) as stream:
        return stream.read(1024**2)


def closed(descriptors):
    for descriptor in descriptors:
        with pytest.raises(OSError) as error:
            os.fstat(descriptor)
        assert error.value.errno == errno.EBADF


@pytest.mark.parametrize("depth,index", [(0, 0), (1, 0), (1, 1), (2, 0), (2, 2)])
@pytest.mark.parametrize("name", NAMES)
def test_parent_replaced_before_pin_cannot_supply_package_bytes(package, monkeypatch, tmp_path, depth, index, name):
    _, parents = nested(package, monkeypatch, depth)
    target = package.out / name
    original_open = os.open
    replaced = False
    def opening(*args, **kwargs):
        nonlocal replaced
        if not replaced:
            replaced = True
            redirect(parents[index], tmp_path / "outside")
        return original_open(*args, **kwargs)
    monkeypatch.setattr(os, "open", opening)
    with pytest.raises(OSError):
        read(target)
    assert replaced


@pytest.mark.parametrize("depth", [0, 2])
@pytest.mark.parametrize("name", NAMES)
def test_parent_replaced_at_file_open_keeps_original_pinned_bytes(package, monkeypatch, tmp_path, depth, name):
    _, parents = nested(package, monkeypatch, depth)
    target = package.out / name
    expected = target.read_bytes()
    outside_bytes = b"other" if name == "native.bin" else b'{"outside":"owned"}'
    original_open = os.open
    descriptors = []
    changed = False
    def opening(candidate, *args, **kwargs):
        nonlocal changed
        if Path(candidate).name == name and not changed:
            changed = True
            redirect(parents[-1], tmp_path / "outside", changed=(name, outside_bytes))
        descriptor = original_open(candidate, *args, **kwargs)
        descriptors.append(descriptor)
        return descriptor
    monkeypatch.setattr(os, "open", opening)
    assert read(target) == expected and changed
    assert expected != outside_bytes
    closed(descriptors)


@pytest.mark.parametrize("suffix", ["", "/", "/."])
@pytest.mark.parametrize("name", NAMES)
def test_root_replacement_rejects_including_trailing_separators(package, settings, monkeypatch, tmp_path, suffix, name):
    root, _ = nested(package, monkeypatch, 2)
    settings.MEDIA_ROOT = str(root) + suffix
    target = package.out / name
    original_open = os.open
    changed = False
    def opening(*args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            redirect(root, tmp_path / "outside")
        return original_open(*args, **kwargs)
    monkeypatch.setattr(os, "open", opening)
    with pytest.raises(OSError):
        read(target)
    assert changed


@pytest.mark.parametrize("kind", ["fifo", "socket", "regular", "missing"])
@pytest.mark.parametrize("name", ["manifest.json", "evaluation.json"])
def test_changed_parent_types_fail_promptly(package, monkeypatch, kind, name):
    _, parents = nested(package, monkeypatch, 1)
    target, parent = package.out / name, parents[-1]
    parent.rename(parent.with_name(parent.name + "-retained"))
    endpoint = socket.socket(socket.AF_UNIX)
    try:
        if kind == "fifo":
            os.mkfifo(parent)
        elif kind == "socket":
            endpoint.bind(str(parent))
        elif kind == "regular":
            parent.write_bytes(b"owned")
        started = time.monotonic()
        with pytest.raises(OSError):
            read(target)
        assert time.monotonic() - started < 2
    finally:
        endpoint.close()


@pytest.mark.parametrize("fault", ["success", "read", "wrapper", "budget", "parent_open", "root_open", "file_open"])
@pytest.mark.parametrize("depth", [0, 2])
def test_all_directory_and_file_descriptors_close(package, monkeypatch, fault, depth):
    root, _ = nested(package, monkeypatch, depth)
    path = package.out / "native.bin"
    original_open, original_fdopen = os.open, os.fdopen
    descriptors = []
    def opening(candidate, flags, *args, **kwargs):
        fail = fault == "root_open" and Path(candidate) == root
        fail |= fault == "parent_open" and Path(candidate).name == "bundle"
        fail |= fault == "file_open" and Path(candidate).name == path.name
        if fail:
            raise OSError("private-io-sentinel")
        descriptor = original_open(candidate, flags, *args, **kwargs)
        descriptors.append(descriptor)
        return descriptor
    def wrapping(descriptor, *args, **kwargs):
        if fault == "wrapper":
            raise OSError("private-io-sentinel")
        stream = original_fdopen(descriptor, *args, **kwargs)
        if fault == "read":
            stream.read = lambda *a: (_ for _ in ()).throw(OSError("private-io-sentinel"))
        return stream
    monkeypatch.setattr(os, "open", opening)
    monkeypatch.setattr(os, "fdopen", wrapping)
    if fault == "success":
        assert service._artifact_bytes(path, 5, "owned_budget") == b"model"
    else:
        with pytest.raises(service.JobConflict if fault == "budget" else OSError):
            service._artifact_bytes(path, 4 if fault == "budget" else 5, "owned_budget")
    assert descriptors or fault == "root_open"
    closed(descriptors)


@pytest.mark.parametrize("name", ["manifest.json", "publication.json"])
@pytest.mark.parametrize("depth", [0, 2])
def test_header_late_parent_replacement_cannot_pass_on_identical_outside_metadata(package, monkeypatch, tmp_path, name, depth):
    nested(package, monkeypatch, depth)
    original_read = service._artifact_bytes
    changed = False
    def reading(path, *args, **kwargs):
        nonlocal changed
        if Path(path).name == name and not changed:
            changed = True
            redirect(package.out, tmp_path / "outside")
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(service, "_artifact_bytes", reading)
    with pytest.raises(OSError):
        service.header(7, package.identity["bundle_id"], package.sha)
    assert changed


@pytest.mark.parametrize("name", ["evaluation.json", "model_card.json", "native.bin"])
@pytest.mark.parametrize("depth", [0, 2])
def test_worker_never_publishes_when_parent_is_replaced(package, worker, monkeypatch, tmp_path, name, depth):
    nested(package, monkeypatch, depth)
    original = service._regular_artifact
    changed = False
    @contextmanager
    def opening(path):
        nonlocal changed
        if Path(path).name == name and not changed:
            changed = True
            redirect(package.out, tmp_path / "outside")
        with original(path) as stream:
            yield stream
    monkeypatch.setattr(service, "_regular_artifact", opening)
    service.execute("owned-job")
    assert changed and worker[0] == [{"state": "blocked", "reason": "job_package_or_budget_invalid", "result": None}]


@pytest.mark.parametrize("depth", [0, 2])
def test_worker_hashes_the_pinned_original_file_after_parent_replacement(package, worker, monkeypatch, tmp_path, depth):
    nested(package, monkeypatch, depth)
    original_open = os.open
    changed = False
    def opening(candidate, *args, **kwargs):
        nonlocal changed
        if Path(candidate).name == "native.bin" and not changed:
            changed = True
            redirect(package.out, tmp_path / "outside", changed=("native.bin", b"other"))
        return original_open(candidate, *args, **kwargs)
    monkeypatch.setattr(os, "open", opening)
    service.execute("owned-job")
    assert changed and worker[0][0]["state"] == "succeeded"
    assert worker[1] == [hashlib.sha256(b"model").hexdigest()]
    assert worker[0][0]["result"]["verified_bytes"] == 5


@pytest.mark.parametrize("kind", ["outside", "traversal"])
@pytest.mark.parametrize("name", ["manifest.json", "native.bin"])
def test_outside_or_traversing_paths_fail_before_any_open(package, monkeypatch, tmp_path, kind, name):
    root = package.out.parent
    outside = tmp_path / name
    outside.write_bytes(b"owned")
    path = outside if kind == "outside" else root / ".." / name
    monkeypatch.setattr(os, "open", lambda *a, **k: pytest.fail("invalid package path reached an open"))
    with pytest.raises(OSError):
        read(path)


@pytest.mark.parametrize("suffix", ["", "/", "/."])
@pytest.mark.parametrize("name", NAMES)
def test_regular_nested_reads_keep_exact_bytes_for_normalized_roots(package, settings, monkeypatch, suffix, name):
    root, _ = nested(package, monkeypatch, 2)
    settings.MEDIA_ROOT = str(root) + suffix
    path = package.out / name
    assert read(path) == path.read_bytes()
