"""Operation-bound archives survive retries, collisions and failed publication."""

import json
import os
import threading
import uuid
from pathlib import Path

import pytest

from modeling import sfs_evidence

pytestmark = pytest.mark.unit


def record():
    return {"operation_id": str(uuid.uuid4()), "status": "completed", "forward": [], "backward": []}


def test_same_operation_reuses_unchanged_archive_and_changed_evidence_is_refused(tmp_path):
    data = record()
    path = sfs_evidence.archive_sfs_record(tmp_path, data)
    original, stat = path.read_bytes(), path.stat()
    assert sfs_evidence.archive_sfs_record(tmp_path, dict(data)) == path
    assert path.read_bytes() == original
    assert path.stat().st_ino == stat.st_ino and path.stat().st_mtime_ns == stat.st_mtime_ns
    with pytest.raises(ValueError, match="different evidence"):
        sfs_evidence.archive_sfs_record(tmp_path, {**data, "status": "error", "error": "different"})
    assert path.read_bytes() == original and list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("same_operation", [False, True])
def test_concurrent_archive_publication_never_overwrites_evidence(tmp_path, monkeypatch, same_operation):
    first = record()
    second = dict(first) if same_operation else record()
    actual_link = os.link
    barrier = threading.Barrier(2)
    outcomes, failures = [], []

    def link(source, destination):
        barrier.wait(5)
        return actual_link(source, destination)

    def publish(data):
        try:
            outcomes.append(sfs_evidence.archive_sfs_record(tmp_path, data))
        except BaseException as error:
            failures.append(error)

    monkeypatch.setattr(sfs_evidence.os, "link", link)
    threads = [threading.Thread(target=publish, args=(data,)) for data in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert not any(thread.is_alive() for thread in threads) and not failures
    assert len(set(outcomes)) == (1 if same_operation else 2)
    assert {json.loads(path.read_bytes())["operation_id"] for path in outcomes} == {first["operation_id"], second["operation_id"]}
    assert not list(tmp_path.glob(".sfs-*"))


def test_failed_archive_link_leaves_no_partial_history(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("deliberate archive-link fault")

    monkeypatch.setattr(sfs_evidence.os, "link", fail)
    with pytest.raises(OSError):
        sfs_evidence.archive_sfs_record(tmp_path, record())
    assert list(tmp_path.iterdir()) == []


def test_directory_sync_uncertainty_reconciles_same_archive_without_republication(tmp_path, monkeypatch):
    data = record()
    actual_sync = sfs_evidence._sync_directory

    def fail(*args):
        raise OSError("directory sync failed")

    monkeypatch.setattr(sfs_evidence, "_sync_directory", fail)
    with pytest.raises(OSError):
        sfs_evidence.archive_sfs_record(tmp_path, data)
    path = next(tmp_path.glob("sfs_*.json"))
    before, inode = path.read_bytes(), path.stat().st_ino
    monkeypatch.setattr(sfs_evidence, "_sync_directory", actual_sync)
    assert sfs_evidence.archive_sfs_record(tmp_path, data) == path
    assert path.read_bytes() == before and path.stat().st_ino == inode
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("invalid", [None, "../escape", "not-a-uuid", "00000000000000000000000000000000"])
def test_invalid_archive_identity_never_creates_a_file(tmp_path, invalid):
    with pytest.raises(ValueError):
        sfs_evidence.archive_sfs_record(tmp_path, {**record(), "operation_id": invalid})
    assert list(tmp_path.iterdir()) == []


def test_malformed_existing_archive_is_preserved_and_refused(tmp_path):
    data = record()
    path = tmp_path / f"sfs_run_{data['operation_id']}.json"
    path.write_bytes(b'{"status":')
    with pytest.raises(ValueError):
        sfs_evidence.archive_sfs_record(tmp_path, data)
    assert path.read_bytes() == b'{"status":'


@pytest.mark.parametrize("archive_fails", [False, True])
def test_background_completion_requires_archive_before_current_result(monkeypatch, _use_tmp_media, settings, archive_fails):
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
        return {"status": "completed", "forward": [], "backward": []}

    actual_archive = views._archive_sfs_run
    events = []

    def archive(file_id, result):
        assert json.loads(path.read_bytes())["status"] == "running"
        events.append("archive")
        if archive_fails:
            raise OSError("synthetic history unavailable")
        return actual_archive(file_id, result)

    class InlineThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(views, "run_sfs_with_progress", search)
    monkeypatch.setattr(views, "_archive_sfs_run", archive)
    monkeypatch.setattr(views.threading, "Thread", InlineThread)
    factory = APIRequestFactory()
    try:
        response = views.SFSStartView.as_view()(factory.post("/sfs/start/", {"file_id": 1, "cv_folds": 4}, format="json"))
        assert response.status_code == 200 and events == ["archive"]
        progress = views.SFSStatusView.as_view()(factory.get("/sfs/status/1/"), file_id=1)
        if archive_fails:
            assert progress.data["status"] == "error"
            assert progress.data["failure"]["stage"] == "history_evidence_write"
            assert progress.data["failure"]["operation_id"] == response.data["operation_id"]
            assert path.read_bytes() == checkpoint[0]
            assert list((root / "modeling/1_runs").glob("sfs_*.json")) == []
            views.SFS_PROGRESS.pop(1)
            disk = views.SFSStatusView.as_view()(factory.get("/sfs/status/1/"), file_id=1)
            assert disk.data["status"] == "interrupted"
        else:
            assert progress.data["status"] == "completed"
            current = json.loads(path.read_bytes())
            archived = json.loads(next((root / "modeling/1_runs").glob("sfs_*.json")).read_bytes())
            archived.pop("archived_at")
            assert archived == current and current["operation_id"] == response.data["operation_id"]
    finally:
        views.SFS_PROGRESS.pop(1, None)


def test_history_keeps_legacy_files_and_lists_new_operations_in_recent_order(_use_tmp_media, settings):
    from rest_framework.test import APIRequestFactory
    from modeling import views

    root = Path(settings.MEDIA_ROOT) / "modeling/1_runs"
    root.mkdir(parents=True)
    legacy = root / "sfs_run_1_20200101T000000Z.json"
    legacy.write_text(json.dumps({"status": "completed", "forward": [], "archived_at": "2020-01-01T00:00:00+00:00", "run_index": 1}))
    original = legacy.read_bytes()
    os.utime(legacy, (1, 1))
    data = record()
    views._archive_sfs_run(1, data)
    (root / ".sfs-hidden.tmp").write_bytes(b'partial')
    factory = APIRequestFactory()
    result = views.SFSHistoryView.as_view()(factory.get("/sfs/history/1/"), file_id=1)
    assert result.status_code == 200
    assert len(result.data["history"]) == 2
    newest, old = result.data["history"]
    assert newest["operation_id"] == newest["id"] == data["operation_id"]
    assert newest["created_at"] == newest["archived_at"]
    assert old["filename"] == legacy.name and old["run_index"] == 1
    assert legacy.read_bytes() == original
