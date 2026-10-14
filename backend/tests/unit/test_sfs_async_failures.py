"""Failure evidence survives swallowed search errors and background boundaries."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.unit.test_sfs_objective import data, run

pytestmark = pytest.mark.unit


def test_search_failure_is_correlated_and_callback_preserves_it(monkeypatch, caplog):
    from modeling import sfs_utils

    def broken(*args, **kwargs):
        raise ValueError("synthetic-secret-that-must-not-enter-service-logs")

    monkeypatch.setattr(sfs_utils, "_run_forward_step", broken)
    updates = []
    context = {"operation_id": "operation-1", "file_id": 17, "execution_id": "run-1"}
    result = run(data(), status_callback=updates.append, failure_context=context)
    assert result["status"] == updates[-1]["status"] == "error"
    assert result["failure"] == updates[-1]["failure"]
    assert result["failure"]["stage"] == "search"
    assert result["failure"]["exception_type"] == "ValueError"
    assert all(result["failure"][key] == value for key, value in context.items())
    assert result["failure"]["trace_frames"][-1]["function"] == "broken"
    assert "synthetic-secret-that-must-not-enter-service-logs" not in caplog.text
    assert "native_async_failure" in caplog.text


@pytest.mark.parametrize("stage", ["search", "candidate_refit", "candidate_publication", "final_evidence_write"])
def test_api_background_failure_never_claims_completion_and_preserves_stage(monkeypatch, _use_tmp_media, settings, stage):
    from rest_framework.test import APIRequestFactory
    from modeling import views, sfs_utils

    X, y, V, z, context = data()
    saved = {"X_train": X, "y_train": y, "X_valid": V, "y_valid": z,
             "task": "regression", "algorithm": "xgboost", "validation_context": context,
             "prediction_contract": context["prediction_contract"], "execution_id": "source-run"}
    root = Path(settings.MEDIA_ROOT)
    (root / "train_data").mkdir()
    (root / "train_data" / "1_train_data.pkl").touch()
    monkeypatch.setattr(views, "load_development_data", lambda *args: saved)

    def fail(*args, **kwargs):
        raise RuntimeError("deliberate async fault")

    success = {"status": "completed", "forward": [{"selected_features": ["x"]}], "backward": []}
    if stage == "search":
        monkeypatch.setattr(sfs_utils, "_run_forward_step", fail)
    else:
        monkeypatch.setattr(views, "run_sfs_with_progress", lambda **kwargs: success)
    monkeypatch.setattr(sfs_utils, "_sfs_fit", fail if stage == "candidate_refit" else lambda *args, **kwargs: object())
    publication = Mock(side_effect=fail) if stage == "candidate_publication" else Mock(
        return_value={"model": {"model_path": "synthetic-model"}, "execution_id": "candidate-run"})
    monkeypatch.setattr(views, "publish_candidate", publication)
    if stage == "final_evidence_write":
        monkeypatch.setattr(views, "write_sfs_record", fail)

    class InlineThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(views.threading, "Thread", InlineThread)
    factory = APIRequestFactory()
    response = views.SFSStartView.as_view()(factory.post("/sfs/start/", {"file_id": 1, "cv_folds": 4}, format="json"))
    try:
        assert response.status_code == 200
        progress = views.SFSStatusView.as_view()(factory.get("/sfs/status/1/"), file_id=1)
        assert progress.data["status"] == "error"
        assert progress.data["failure"]["stage"] == stage
        assert progress.data["failure"]["operation_id"] == response.data["operation_id"]
        assert progress.data["failure"]["execution_id"] == "source-run"
        if stage != "final_evidence_write":
            evidence = views.SFSResultsView.as_view()(factory.get("/sfs/results/1/"), file_id=1)
            assert evidence.data["sfs_completed"] is False
            assert evidence.data["failure"] == progress.data["failure"]
        if stage in {"search", "candidate_refit"}:
            publication.assert_not_called()
    finally:
        views.SFS_PROGRESS.pop(1, None)
