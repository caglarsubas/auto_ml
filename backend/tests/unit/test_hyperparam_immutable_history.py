"""Terminal tuning history survives later runs, retries and publication failures."""
import json
import os
import threading
import uuid

import pytest

from modeling import hyperparam_state, sfs_evidence
from tests.unit.test_hyperparam_failure_recovery import api_operation  # noqa: F401
from tests.unit.test_project_authority import world  # noqa: F401

pytestmark = pytest.mark.unit


def record(status="completed"):
    return {"operation_id": str(uuid.uuid4()), "status": status, "trials": [], "trial_attempts": []}


@pytest.mark.parametrize("status", ["completed", "stopped", "error"])
def test_terminal_archive_is_immutable_and_identical_retry_reuses_bytes(tmp_path, status):
    data = record(status)
    path = hyperparam_state.archive_hyperparam_record(tmp_path, data)
    before, stat = path.read_bytes(), path.stat()
    assert path.name == f"hyperparam_run_{data['operation_id']}.json"
    assert hyperparam_state.archive_hyperparam_record(tmp_path, dict(data)) == path
    assert path.read_bytes() == before
    assert (path.stat().st_ino, path.stat().st_mtime_ns) == (stat.st_ino, stat.st_mtime_ns)
    with pytest.raises(ValueError, match="different evidence"):
        hyperparam_state.archive_hyperparam_record(tmp_path, {**data, "trials": [{"metric": 0.1}]})
    assert path.read_bytes() == before and list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("same,changed", [(False, False), (True, False), (True, True)])
def test_concurrent_publication_preserves_one_record_per_operation(tmp_path, monkeypatch, same, changed):
    first = record()
    second = dict(first) if same else record()
    if changed:
        second["trials"] = [{"metric": 0.2}]
    link, barrier = os.link, threading.Barrier(2)
    outcomes, failures = [], []

    def synchronized_link(source, destination):
        barrier.wait(5)
        return link(source, destination)

    def publish(data):
        try:
            outcomes.append(hyperparam_state.archive_hyperparam_record(tmp_path, data))
        except BaseException as error:
            failures.append(error)

    monkeypatch.setattr(sfs_evidence.os, "link", synchronized_link)
    threads = [threading.Thread(target=publish, args=(data,)) for data in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert not any(thread.is_alive() for thread in threads)
    assert len(failures) == int(changed)
    assert all(isinstance(error, ValueError) for error in failures)
    assert len(set(outcomes)) == (1 if same else 2)
    for path in set(outcomes):
        saved = json.loads(path.read_bytes())
        saved.pop("archived_at")
        assert saved in (first, second)
    assert not list(tmp_path.glob(".sfs-*"))


def test_link_failure_cannot_publish_a_partial_archive(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("archive link failure")

    monkeypatch.setattr(sfs_evidence.os, "link", fail)
    with pytest.raises(OSError):
        hyperparam_state.archive_hyperparam_record(tmp_path, record())
    assert list(tmp_path.iterdir()) == []


def test_directory_sync_failure_reconciles_without_republication(tmp_path, monkeypatch):
    data, sync = record(), sfs_evidence._sync_directory

    def fail(*args):
        raise OSError("directory sync uncertainty")

    monkeypatch.setattr(sfs_evidence, "_sync_directory", fail)
    with pytest.raises(OSError):
        hyperparam_state.archive_hyperparam_record(tmp_path, data)
    path = next(tmp_path.glob("hyperparam_*.json"))
    before, inode = path.read_bytes(), path.stat().st_ino
    monkeypatch.setattr(sfs_evidence, "_sync_directory", sync)
    assert hyperparam_state.archive_hyperparam_record(tmp_path, data) == path
    assert path.read_bytes() == before and path.stat().st_ino == inode


@pytest.mark.parametrize("identity", [None, 41, "../escape", "not-a-uuid", "00000000000000000000000000000000"])
def test_invalid_operation_identity_never_creates_a_file(tmp_path, identity):
    with pytest.raises(ValueError):
        hyperparam_state.archive_hyperparam_record(tmp_path, {**record(), "operation_id": identity})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("override", [
    {"status": "running"}, {"status": "interrupted"}, {"status": None},
    {"error": "contradictory completion"}, {"failure": {"stage": "search"}},
    {"trials": {}}, {"trial_attempts": {}}, {"validation_curves": {}},
    {"archived_at": "invented timestamp"}, {"value": float("nan")},
])
def test_invalid_or_nonterminal_evidence_is_refused_before_publication(tmp_path, override):
    with pytest.raises(ValueError):
        hyperparam_state.archive_hyperparam_record(tmp_path, {**record(), **override})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("content", ['{"status":', '{"status":"completed","status":"error"}',
                                     '{"status":"completed","trials":NaN}'])
def test_invalid_existing_archive_is_preserved_and_refused(tmp_path, content):
    data = record()
    path = tmp_path / f"hyperparam_run_{data['operation_id']}.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        hyperparam_state.archive_hyperparam_record(tmp_path, data)
    assert path.read_text() == content


@pytest.mark.parametrize("terminal", ["completed", "stopped", "error"])
def test_current_result_follows_exact_terminal_archive(api_operation, monkeypatch, terminal):
    views, factory, path, prior, _ = api_operation
    if terminal != "completed":
        monkeypatch.setattr(views, "run_hyperparam_search_with_progress", lambda **kwargs: {
            "status": terminal, "trial_attempts": [{"status": "failed"}], "trials": []})
    archive, write, events = views._archive_hyperparam_run, views.write_hyperparam_record, []

    def save_archive(file_id, data):
        assert path.read_bytes() == prior
        events.append("archive")
        return archive(file_id, data)

    def save_current(destination, data):
        assert events == ["archive"]
        assert (path.parents[1] / data["archive_path"]).is_file()
        events.append("current")
        return write(destination, data)

    monkeypatch.setattr(views, "_archive_hyperparam_run", save_archive)
    monkeypatch.setattr(views, "write_hyperparam_record", save_current)
    response = views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    progress = views.HYPERPARAM_PROGRESS[1]
    assert response.status_code == 200 and events == ["archive", "current"]
    assert progress["status"] == terminal
    saved = json.loads(path.read_bytes())
    archived = json.loads((path.parents[1] / saved["archive_path"]).read_bytes())
    assert archived.pop("archived_at") and archived == saved
    assert saved["operation_id"] == response.data["operation_id"]
    views.HYPERPARAM_PROGRESS.pop(1)
    disk = views.HyperparamStatusView.as_view()(factory.get("/hp/status/1/"), file_id=1)
    assert disk.data["archive_path"] == saved["archive_path"]


def test_history_failure_preserves_current_and_blocks_live_completion(api_operation, monkeypatch):
    views, factory, path, prior, _ = api_operation

    def fail(*args):
        raise OSError("terminal history unavailable")

    monkeypatch.setattr(views, "_archive_hyperparam_run", fail)
    response = views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    progress = views.HYPERPARAM_PROGRESS[1]
    assert response.status_code == 200 and progress["status"] == "error"
    assert progress["failure"]["stage"] == "history_evidence_write"
    assert progress["failure"]["operation_id"] == response.data["operation_id"]
    assert "archive_path" not in progress and path.read_bytes() == prior


@pytest.mark.parametrize("archive_fails", [False, True])
def test_search_exception_preserves_original_failure_and_requires_history(api_operation, monkeypatch, archive_fails):
    views, factory, path, prior, _ = api_operation

    def search(**kwargs):
        raise ValueError("search failed")

    def fail_archive(*args):
        raise OSError("history failed")

    monkeypatch.setattr(views, "run_hyperparam_search_with_progress", search)
    if archive_fails:
        monkeypatch.setattr(views, "_archive_hyperparam_run", fail_archive)
    response = views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    progress = views.HYPERPARAM_PROGRESS[1]
    assert response.status_code == 200 and progress["failure"]["stage"] == "search"
    if archive_fails:
        assert progress["storage_failure"]["stage"] == "failure_history_write"
        assert progress["storage_failure"]["operation_id"] == progress["failure"]["operation_id"]
        assert path.read_bytes() == prior
    else:
        saved = json.loads(path.read_bytes())
        assert saved["status"] == "error" and saved["failure"] == progress["failure"]
        archive = json.loads((path.parents[1] / saved["archive_path"]).read_bytes())
        assert archive["failure"] == saved["failure"]


def test_failed_current_publication_retains_archive_without_overwriting_prior(api_operation, monkeypatch):
    views, factory, path, prior, _ = api_operation

    def fail(*args):
        raise OSError("current pointer unavailable")

    monkeypatch.setattr(views, "write_hyperparam_record", fail)
    views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    progress = views.HYPERPARAM_PROGRESS[1]
    assert progress["status"] == "error" and progress["failure"]["stage"] == "final_evidence_write"
    archive = json.loads((path.parents[1] / progress["archive_path"]).read_bytes())
    assert archive["operation_id"] == progress["operation_id"] and archive["status"] == "completed"
    assert path.read_bytes() == prior


def test_later_iteration_keeps_prior_archive_and_legacy_history(api_operation):
    views, factory, path, _, _ = api_operation
    root = path.parents[1] / "modeling/1_runs"
    root.mkdir(parents=True)
    legacy = root / "sfs_run_1_20200101T000000Z.json"
    legacy.write_bytes(b'{"legacy":true}')
    first = views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    archive = path.parents[1] / views.HYPERPARAM_PROGRESS[1]["archive_path"]
    before = archive.read_bytes()
    second = views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    assert first.data["operation_id"] != second.data["operation_id"]
    assert archive.read_bytes() == before and legacy.read_bytes() == b'{"legacy":true}'
    assert len(list(root.glob("hyperparam_*.json"))) == 2


def test_registration_failure_blocks_current_and_retry_keeps_archive_bytes(api_operation, monkeypatch):
    from access_control import projects

    views, factory, path, prior, _ = api_operation
    registration = projects.register_artifact

    def fail(*args, **kwargs):
        raise projects.ProjectDenied("artifact_registration_unavailable")

    monkeypatch.setattr(projects, "register_artifact", fail)
    views.HyperparamStartView.as_view()(factory.post("/hp/start/", {"file_id": 1}, format="json"))
    progress = views.HYPERPARAM_PROGRESS[1]
    assert progress["status"] == "error" and progress["failure"]["stage"] == "history_evidence_write"
    archive = next((path.parents[1] / "modeling/1_runs").glob("hyperparam_*.json"))
    original, inode = archive.read_bytes(), archive.stat().st_ino
    saved = json.loads(original)
    saved.pop("archived_at")
    assert path.read_bytes() == prior
    monkeypatch.setattr(projects, "register_artifact", registration)
    assert views._archive_hyperparam_run(1, saved) == saved["archive_path"]
    assert archive.read_bytes() == original and archive.stat().st_ino == inode


@pytest.mark.auth_boundary
@pytest.mark.django_db(transaction=True)
def test_archived_tuning_download_preserves_project_authority(world):
    from modeling import views

    _, _, _, clients, files, _ = world
    owned, foreign = [views._archive_hyperparam_run(dataset.pk, record()) for dataset in files]
    for role in ("developer", "reviewer", "admin", "outsider"):
        response = clients[role].get("/media/" + owned)
        assert response.status_code == (403 if role == "outsider" else 200)
        if role != "outsider":
            assert json.loads(b"".join(response.streaming_content))["status"] == "completed"
            response.close()
        assert clients[role].get("/media/" + foreign).status_code == 403
