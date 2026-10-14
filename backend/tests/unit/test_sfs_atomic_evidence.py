"""Checkpoint readers see complete records; failed replacement preserves evidence."""

import json
import os
import threading
from pathlib import Path

import pytest

from modeling import sfs_evidence
from modeling.sfs_state import read_recorded_sfs

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("fault", ["nonfinite", "unserializable", "write", "flush", "file_sync", "replace"])
def test_failed_checkpoint_keeps_previous_record_and_cleans_staging(tmp_path, monkeypatch, fault):
    path = tmp_path / "checkpoint.json"
    previous = b'{"status":"running","operation_id":"previous","forward":[]}'
    path.write_bytes(previous)
    record = {"status": "completed", "operation_id": "next", "forward": []}

    def fail(*args):
        raise OSError("deliberate storage fault")

    if fault in {"nonfinite", "unserializable"}:
        record["invalid"] = float("nan") if fault == "nonfinite" else object()
    elif fault in {"write", "flush"}:
        actual = sfs_evidence.tempfile.NamedTemporaryFile

        class FaultyStream:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def __getattr__(self, key):
                return getattr(self.stream, key)

            def write(self, payload):
                if fault == "write":
                    self.stream.write(payload[:10])
                    fail()
                return self.stream.write(payload)

            def flush(self):
                if fault == "flush":
                    fail()
                return self.stream.flush()

        monkeypatch.setattr(sfs_evidence.tempfile, "NamedTemporaryFile", lambda **kwargs: FaultyStream(actual(**kwargs)))
    else:
        monkeypatch.setattr(sfs_evidence.os, "fsync" if fault == "file_sync" else "replace", fail)
    with pytest.raises((ValueError, TypeError, OSError)):
        sfs_evidence.write_sfs_record(path, record)
    assert path.read_bytes() == previous
    assert read_recorded_sfs(path)["operation_id"] == "previous"
    assert list(tmp_path.iterdir()) == [path]


def test_reader_sees_old_then_complete_new_record_during_replacement(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    old = {"status": "running", "operation_id": "old", "forward": []}
    new = {"status": "completed", "operation_id": "new", "forward": [{"selected_features": ["x"]}] * 10000}
    sfs_evidence.write_sfs_record(path, old)
    staged, release = threading.Event(), threading.Event()
    actual_replace = os.replace
    failures = []

    def replace(source, destination):
        staged.set()
        assert release.wait(5)
        actual_replace(source, destination)

    def writer():
        try:
            sfs_evidence.write_sfs_record(path, new)
        except BaseException as error:
            failures.append(error)

    monkeypatch.setattr(sfs_evidence.os, "replace", replace)
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        assert staged.wait(5)
        for _ in range(20):
            assert read_recorded_sfs(path) == old
        release.set()
        while thread.is_alive():
            assert read_recorded_sfs(path) in (old, new)
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not failures
    assert read_recorded_sfs(path) == new
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_directory_sync_failure_reports_uncertain_durability_with_complete_visible_record(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    actual_sync = os.fsync
    calls = []

    def sync(fd):
        calls.append(fd)
        if len(calls) == 2:
            raise OSError("directory sync failed")
        return actual_sync(fd)

    monkeypatch.setattr(sfs_evidence.os, "fsync", sync)
    with pytest.raises(OSError, match="directory sync failed"):
        sfs_evidence.write_sfs_record(path, {"status": "completed", "forward": []})
    assert read_recorded_sfs(path)["status"] == "completed"
    assert list(tmp_path.iterdir()) == [path]


def test_first_failed_serialization_does_not_create_a_result(tmp_path):
    path = tmp_path / "checkpoint.json"
    with pytest.raises(ValueError):
        sfs_evidence.write_sfs_record(path, {"status": "completed", "value": float("inf")})
    assert list(tmp_path.iterdir()) == []


def test_background_final_write_failure_preserves_correlated_checkpoint(monkeypatch, _use_tmp_media, settings):
    from rest_framework.test import APIRequestFactory
    from modeling import views
    from tests.unit.test_sfs_objective import data

    X, y, V, z, context = data()
    saved = {"X_train": X, "y_train": y, "X_valid": V, "y_valid": z,
             "task": "regression", "algorithm": "xgboost", "validation_context": context,
             "prediction_contract": context["prediction_contract"], "execution_id": "source-run"}
    root = Path(settings.MEDIA_ROOT)
    (root / "train_data").mkdir()
    (root / "train_data" / "1_train_data.pkl").touch()
    monkeypatch.setattr(views, "load_development_data", lambda *args: saved)
    path = root / "sfs_results/1_sfs_results.json"
    checkpoint = []

    def search(**kwargs):
        kwargs["status_callback"]({"status": "running", "completed_steps": [
            {"direction": "forward", "step": 1, "selected_features": ["x"]}]})
        checkpoint.append(path.read_bytes())
        return {"status": "completed", "forward": [], "invalid": None, "baselines": {"score": float("nan")}}

    class InlineThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(views, "run_sfs_with_progress", search)
    monkeypatch.setattr(views.threading, "Thread", InlineThread)
    factory = APIRequestFactory()
    try:
        response = views.SFSStartView.as_view()(factory.post("/sfs/start/", {"file_id": 1, "cv_folds": 4}, format="json"))
        assert response.status_code == 200
        progress = views.SFSStatusView.as_view()(factory.get("/sfs/status/1/"), file_id=1)
        assert progress.data["status"] == "error"
        assert progress.data["failure"]["stage"] == "final_evidence_write"
        assert path.read_bytes() == checkpoint[0]
        assert json.loads(checkpoint[0])["operation_id"] == response.data["operation_id"]
        views.SFS_PROGRESS.pop(1)
        disk = views.SFSStatusView.as_view()(factory.get("/sfs/status/1/"), file_id=1)
        assert disk.data["status"] == "interrupted"
        assert disk.data["operation_id"] == response.data["operation_id"]
        assert not list(path.parent.glob(".sfs-*"))
    finally:
        views.SFS_PROGRESS.pop(1, None)
