"""Native package reads reject late special files and bound metadata allocation."""

import hashlib
import json
import multiprocessing
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from execution_jobs import service

pytestmark = pytest.mark.unit


@pytest.fixture
def package(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path / "media"
    out = settings.MEDIA_ROOT / "bundle"
    out.mkdir(parents=True)
    identity = dict(file_id=7, **{key: str(uuid.uuid4()) for key in ["bundle_id", "execution_id", "assessment_id"]})
    manifest = {**identity, "handoff_schema_version": 1, "artifact_integrity": {"native.bin": {"bytes": 5}}}
    raw = json.dumps(manifest).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (out / "manifest.json").write_bytes(raw)
    (out / "publication.json").write_text(json.dumps({**identity, "manifest_sha256": sha}))
    for name in ["evaluation.json", "model_card.json"]:
        (out / name).write_text("{}")
    (out / "native.bin").write_bytes(b"model")
    monkeypatch.setattr(service, "bundle_dir", lambda *args: out)
    return SimpleNamespace(out=out, identity=identity, manifest=manifest, sha=sha)


@pytest.fixture
def worker(package, monkeypatch):
    spec = {**package.identity, "kind": service.KIND, "manifest_sha256": package.sha, "runtime": {"fixture": "pinned"}}
    package.spec = spec
    job = SimpleNamespace(specification=spec, dataset_id=7)
    receipts, hashes = [], []
    monkeypatch.setattr(service, "claim", lambda identifier: (job, "owned-token"))
    monkeypatch.setattr(service, "checkpoint", lambda *args: None)
    monkeypatch.setattr(service, "header", lambda *args: (package.manifest, package.identity))
    monkeypatch.setattr(service.projects, "assert_evidence_scope", lambda *args: None)

    def verify(out, file_id, bundle_id, *, artifact_digest, metadata_bytes=None):
        hashes.append(artifact_digest(out / "native.bin"))
        return package.manifest, package.sha

    def finish(identifier, token, state, reason="", result=None):
        receipts.append({"state": state, "reason": reason, "result": result})

    monkeypatch.setattr(service, "verify_bundle", verify)
    monkeypatch.setattr(service, "finish", finish)
    return receipts, hashes


def late_replacement(monkeypatch, path, fault, tmp_path):
    """Mutate only the owned final component after the existing path/stat checks."""
    original_open, original_path_open = os.open, Path.open
    outside = tmp_path / "outside"
    outside.write_bytes(path.read_bytes())
    replaced = False

    def replace(candidate):
        nonlocal replaced
        if Path(candidate) == path and not replaced:
            replaced = True
            path.unlink()
            if fault == "fifo":
                os.mkfifo(path)
            elif fault == "symlink":
                path.symlink_to(outside)
            else:
                path.mkdir()

    def opened(candidate, *args, **kwargs):
        replace(candidate)
        return original_open(candidate, *args, **kwargs)

    def path_opened(candidate, *args, **kwargs):
        replace(candidate)
        return original_path_open(candidate, *args, **kwargs)

    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(Path, "open", path_opened)


def bounded_child(probe):
    # Controlled metadata/worker seams only; the forked child never uses a DB.
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)

    def run():
        try:
            send.send(probe())
        except Exception as error:
            send.send(type(error).__name__)
        finally:
            send.close()

    child = context.Process(target=run, daemon=True)
    child.start()
    send.close()
    try:
        child.join(3)
        assert not child.is_alive(), "native package read blocked on an owned FIFO"
        assert child.exitcode == 0 and receive.poll()
        return receive.recv()
    finally:
        if child.is_alive():
            child.terminate()
            child.join(3)
        child.close()
        receive.close()


@pytest.mark.parametrize("name", ["manifest.json", "publication.json"])
@pytest.mark.parametrize("fault", ["fifo", "symlink", "directory"])
def test_header_rejects_late_special_files(package, tmp_path, monkeypatch, name, fault):
    late_replacement(monkeypatch, package.out / name, fault, tmp_path)

    def probe():
        try:
            service.header(7, package.identity["bundle_id"], package.sha)
            return "accepted"
        except OSError:
            return "io_refused"

    assert bounded_child(probe) == "io_refused"


@pytest.mark.parametrize("name", ["evaluation.json", "model_card.json", "native.bin"])
@pytest.mark.parametrize("fault", ["fifo", "symlink", "directory"])
def test_worker_rejects_late_special_files_without_a_result(package, worker, tmp_path, monkeypatch, name, fault):
    late_replacement(monkeypatch, package.out / name, fault, tmp_path)

    def probe():
        service.execute("owned-job")
        return worker[0]

    assert bounded_child(probe) == [{"state": "blocked", "reason": "job_package_or_budget_invalid", "result": None}]


def grow_during_read(monkeypatch, path, bound):
    """Record allocations and grow valid JSON after stat, just before its read."""
    original_path_open, original_fdopen = Path.open, os.fdopen
    requested = []

    def wrap(stream):
        original_read = stream.read

        def read(size=-1):
            requested.append(size)
            with original_path_open(path, "ab") as output:
                output.write(b" " * (bound + 1))
            return original_read(size)

        stream.read = read
        return stream

    def opened(candidate, *args, **kwargs):
        stream = original_path_open(candidate, *args, **kwargs)
        return wrap(stream) if Path(candidate) == path else stream

    def fdopened(fd, *args, **kwargs):
        stream = original_fdopen(fd, *args, **kwargs)
        return wrap(stream) if Path(os.readlink(f"/proc/self/fd/{fd}")) == path else stream

    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(os, "fdopen", fdopened)
    return requested


@pytest.mark.parametrize("name,bound", [("manifest.json", 1024**2), ("publication.json", 65536)])
def test_header_growth_is_rejected_with_a_bounded_read(package, monkeypatch, name, bound):
    requested = grow_during_read(monkeypatch, package.out / name, bound)
    with pytest.raises(service.JobConflict, match="^job_package_budget_exceeded$"):
        service.header(7, package.identity["bundle_id"], package.sha)
    assert requested and all(0 <= size <= bound + 1 for size in requested)


@pytest.mark.parametrize("name", ["evaluation.json", "model_card.json"])
def test_evidence_growth_never_adopts_a_result(package, worker, monkeypatch, name):
    bound = 8 * 1024**2
    requested = grow_during_read(monkeypatch, package.out / name, bound)
    service.execute("owned-job")
    assert worker[0] == [{"state": "blocked", "reason": "job_evidence_budget_exceeded", "result": None}]
    assert requested and all(0 <= size <= bound + 1 for size in requested)


@pytest.mark.parametrize("name", ["manifest.json", "publication.json"])
def test_header_missing_and_initial_oversize_keep_existing_diagnostics(package, name):
    path = package.out / name
    path.unlink()
    with pytest.raises(service.JobConflict, match="^job_package_unavailable$"):
        service.header(7, package.identity["bundle_id"], package.sha)
    path.write_bytes(b" " * (1024**2 + 1))
    with pytest.raises(service.JobConflict, match="^job_package_unavailable$"):
        service.header(7, package.identity["bundle_id"], package.sha)


@pytest.mark.parametrize("name", ["evaluation.json", "model_card.json", "native.bin"])
def test_worker_missing_files_keep_existing_failure_receipts(package, worker, name):
    (package.out / name).unlink()
    service.execute("owned-job")
    assert worker[0] == [{"state": "blocked", "reason": "job_package_or_budget_invalid", "result": None}]


def test_regular_metadata_and_hash_receipts_are_unchanged(package, worker):
    # Worker fixture substitutes header only; call the original module function
    # through a separately captured reference below for actual header bytes.
    assert ORIGINAL_HEADER(7, package.identity["bundle_id"], package.sha) == (package.manifest, package.identity)
    service.execute("owned-job")
    receipt = worker[0][0]
    assert receipt["state"] == "succeeded" and receipt["reason"] == ""
    assert receipt["result"]["verified_bytes"] == 5
    assert receipt["result"]["manifest_sha256"] == package.sha
    assert worker[1] == [hashlib.sha256(b"model").hexdigest()]
    assert receipt["result"]["production_use_approved"] is False


ORIGINAL_HEADER = service.header


@pytest.mark.parametrize("failure", ["read", "wrapper", "checkpoint", "budget"])
def test_worker_closes_owned_artifact_descriptor_on_failure(package, worker, monkeypatch, failure):
    descriptors = []
    original_open, original_fdopen = os.open, os.fdopen

    def opened(path, *args, **kwargs):
        fd = original_open(path, *args, **kwargs)
        if Path(path) == package.out / "native.bin":
            descriptors.append(fd)
        return fd

    def wrapped(fd, *args, **kwargs):
        if descriptors and fd == descriptors[-1] and failure == "wrapper":
            raise OSError("private-io-sentinel")
        stream = original_fdopen(fd, *args, **kwargs)
        if descriptors and fd == descriptors[-1] and failure == "read":
            def fail(*args):
                raise OSError("private-io-sentinel")
            stream.read = fail
        return stream

    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(os, "fdopen", wrapped)
    if failure == "checkpoint":
        def check(*args):
            if descriptors:
                raise service.JobStopped
        monkeypatch.setattr(service, "checkpoint", check)
    if failure == "budget":
        monkeypatch.setitem(service.LIMITS, "max_bytes", 4)
    service.execute("owned-job")
    expected = ("cancelled", "job_stopped") if failure == "checkpoint" else (
        "blocked", "job_package_budget_exceeded" if failure == "budget" else "job_package_or_budget_invalid"
    )
    assert worker[0] == [{"state": expected[0], "reason": expected[1], "result": None}]
    assert len(descriptors) == 1, "worker must pin its artifact with an owned descriptor"
    with pytest.raises(OSError):
        os.fstat(descriptors[0])


@pytest.mark.parametrize("name", ["manifest.json", "publication.json"])
def test_real_verifier_rejects_late_fifo_after_header(package, worker, monkeypatch, tmp_path, name):
    from deployment.evidence import verify_bundle

    def verifying(*args, **kwargs):
        late_replacement(monkeypatch, package.out / name, "fifo", tmp_path)
        return verify_bundle(*args, **kwargs)

    monkeypatch.setattr(service, "verify_bundle", verifying)

    def probe():
        service.execute("owned-job")
        return worker[0]

    assert bounded_child(probe) == [{"state": "blocked", "reason": "job_package_or_budget_invalid", "result": None}]


@pytest.mark.parametrize("name,bound", [("manifest.json", 1024**2), ("publication.json", 65536)])
def test_real_verifier_bounds_growth_after_header(package, worker, monkeypatch, name, bound):
    from deployment.evidence import verify_bundle

    requested = grow_during_read(monkeypatch, package.out / name, bound)
    monkeypatch.setattr(service, "verify_bundle", verify_bundle)
    service.execute("owned-job")
    assert worker[0] == [{"state": "blocked", "reason": "job_package_budget_exceeded", "result": None}]
    assert requested and all(0 <= size <= bound + 1 for size in requested)


def test_manifest_change_during_verification_preserves_the_existing_fence(package, worker, monkeypatch):
    from deployment.evidence import verify_bundle

    # A minimal legacy bundle lets the real verifier reach its final digest.
    # Header/lease seams are controlled; the file mutation and hashing are real.
    manifest = {"file_id": 7, "bundle_id": package.identity["bundle_id"],
                "artifact_integrity": {"native.bin": {"bytes": 5, "sha256": hashlib.sha256(b"model").hexdigest()}}}
    raw = json.dumps(manifest).encode()
    (package.out / "manifest.json").write_bytes(raw)
    (package.out / "publication.json").write_text("{}")
    package.spec["manifest_sha256"] = hashlib.sha256(raw).hexdigest()

    def verifying(*args, artifact_digest, **kwargs):
        def changed(path):
            result = artifact_digest(path)
            (package.out / "manifest.json").write_bytes(raw + b" ")
            return result
        return verify_bundle(*args, artifact_digest=changed, **kwargs)

    monkeypatch.setattr(service, "verify_bundle", verifying)
    service.execute("owned-job")
    assert worker[0] == [{"state": "blocked", "reason": "job_manifest_changed", "result": None}]
