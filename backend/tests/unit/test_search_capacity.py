"""Cross-dataset search admission is bounded without replacing prior evidence."""
import copy
import json
import threading
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from modeling import search_admission as admission
from modeling.search_admission import (
    claim_search, fail_search_launch,
    request_search_stop, update_search_progress,
)

pytestmark = pytest.mark.unit


def owner(status="running", **extra):
    return {"status": status, "operation_id": str(uuid.uuid4()), **extra}


@pytest.fixture(params=["sfs", "hyperparam"])
def api(request, monkeypatch, _use_tmp_media, settings):
    from rest_framework.test import APIRequestFactory
    from modeling import views
    from tests.unit.test_sfs_objective import data

    X, y, V, z, context = data()
    saved = {"X_train": X, "y_train": y, "X_valid": V, "y_valid": z,
             "task": "regression", "algorithm": "xgboost", "validation_context": context,
             "prediction_contract": context["prediction_contract"], "execution_id": "source-run"}
    monkeypatch.setattr(views, "load_development_data", lambda *args: saved)
    monkeypatch.setattr(views, "SFS_PROGRESS", {})
    monkeypatch.setattr(views, "HYPERPARAM_PROGRESS", {})
    is_sfs = request.param == "sfs"
    registry = views.SFS_PROGRESS if is_sfs else views.HYPERPARAM_PROGRESS
    other = views.HYPERPARAM_PROGRESS if is_sfs else views.SFS_PROGRESS
    root = Path(settings.MEDIA_ROOT)
    (root / "train_data").mkdir()
    (root / "train_data/1_train_data.pkl").touch()
    path = root / ("sfs_results/1_sfs_results.json" if is_sfs else "hyperparam_results/1_hyperparam.json")
    path.parent.mkdir()
    path.write_bytes(b'{"status":"completed","operation_id":"prior-evidence"}')
    registry[1] = owner("completed", sentinel="prior-owner")
    factory = APIRequestFactory()
    view = views.SFSStartView if is_sfs else views.HyperparamStartView
    threads = Mock()
    monkeypatch.setattr(views.threading, "Thread", threads)

    def submit():
        return view.as_view()(factory.post("/search/start/", {"file_id": "1", "cv_folds": 4}, format="json"))

    return registry, other, path, threads, submit


@pytest.mark.parametrize("distribution", ["same_kind", "other_kind", "mixed"])
def test_full_capacity_rejects_without_launch_or_evidence_change(api, distribution):
    registry, other, path, threads, submit = api
    first, second = owner(secret="OTHER_PROJECT_A"), owner(secret="OTHER_PROJECT_B")
    (other if distribution == "other_kind" else registry)[2] = first
    (registry if distribution == "same_kind" else other)[3] = second
    before, prior = copy.deepcopy((registry, other)), path.read_bytes()
    files = sorted(path.parent.iterdir())
    response = submit()
    assert response.status_code == 503
    assert response.data == {
        "status": "busy", "error_code": "search_capacity_exhausted",
        "error": "Search capacity is full. Wait for an operation to finish, then retry.",
        "file_id": 1, "active_search_limit": 2,
    }
    assert (registry, other) == before and path.read_bytes() == prior
    assert sorted(path.parent.iterdir()) == files
    assert "OTHER_PROJECT" not in json.dumps(response.data)
    assert "operation_id" not in response.data and "failure" not in response.data
    threads.assert_not_called()


def test_cooperative_stop_keeps_capacity_until_terminal_publication(api):
    registry, other, _, threads, submit = api
    first, second = owner(), owner()
    registry[2], other[3] = first, second
    assert request_search_stop(other, 3, {"operation_id": second["operation_id"]})["outcome"] == "stop_requested"
    assert second["status"] == "running" and submit().status_code == 503
    threads.assert_not_called()
    assert update_search_progress(other, 3, second, second["operation_id"], {"status": "stopped"})
    response = submit()
    assert response.status_code == 200 and response.data["status"] == "started"
    assert str(uuid.UUID(response.data["operation_id"])) == response.data["operation_id"]
    assert sum(item["status"] == "running" for values in (registry, other) for item in values.values()) == 2
    threads.assert_called_once()
    threads.return_value.start.assert_called_once()


def test_duplicate_current_search_remains_a_conflict_when_capacity_is_full(api):
    registry, other, path, threads, submit = api
    registry[1], other[2] = owner(), owner()
    before, prior = copy.deepcopy((registry, other)), path.read_bytes()
    response = submit()
    assert response.status_code == 409 and response.data["status"] == "already_running"
    assert (registry, other) == before and path.read_bytes() == prior
    threads.assert_not_called()


@pytest.mark.parametrize("uncertain", [False, True])
def test_known_failed_launch_releases_logical_capacity_but_uncertain_launch_does_not(uncertain):
    first, second = owner(), owner()
    a, b = {1: first}, {2: second}
    assert fail_search_launch(b, 2, second, second["operation_id"], {"stage": "worker_start"}, uncertain, "failed") is not uncertain
    if uncertain:
        with pytest.raises(admission.SearchCapacityExceeded):
            claim_search(a, 3, owner(), other_registries=(b,))
        assert 3 not in a and second["status"] == "running"
    else:
        assert claim_search(a, 3, owner(), other_registries=(b,))
        assert second["status"] == "error"


@pytest.mark.parametrize("terminal", ["completed", "stopped", "error"])
def test_terminal_history_does_not_consume_slots(terminal):
    a, b = {n: owner(terminal) for n in range(20)}, {n: owner(terminal) for n in range(20)}
    assert claim_search(a, 21, owner(), other_registries=(b,))
    assert claim_search(b, 21, owner(), other_registries=(a,))
    before = copy.deepcopy((a, b))
    with pytest.raises(admission.SearchCapacityExceeded):
        claim_search(a, 22, owner(), other_registries=(b,))
    assert (a, b) == before


def test_repeated_registry_arguments_do_not_double_count():
    a, b = {1: owner()}, {}
    assert claim_search(b, 2, owner(), other_registries=(a, b, a))
    assert not claim_search(b, 2, owner(), other_registries=(a,))
    with pytest.raises(admission.SearchCapacityExceeded):
        claim_search(b, 3, owner(), other_registries=(a,))


def test_simultaneous_mixed_searches_cannot_overbook_the_shared_limit():
    a, b = {}, {}
    barrier = threading.Barrier(12)
    outcomes = []

    def submit(file_id):
        registry, other = (a, b) if file_id % 2 else (b, a)
        barrier.wait(5)
        try:
            accepted = claim_search(registry, file_id, owner(), other_registries=(other,))
        except admission.SearchCapacityExceeded:
            accepted = False
        outcomes.append(accepted)

    threads = [threading.Thread(target=submit, args=(n,)) for n in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert not any(thread.is_alive() for thread in threads)
    assert len(outcomes) == 12 and sum(outcomes) == admission.ACTIVE_SEARCH_LIMIT == 2
    assert len(a) + len(b) == 2
