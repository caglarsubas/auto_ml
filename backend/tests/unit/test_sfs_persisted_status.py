"""UI, result and assistant readers agree after process-local state is lost."""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def recorded(_use_tmp_media, settings):
    from modeling.views import SFS_PROGRESS

    SFS_PROGRESS.clear()
    path = Path(settings.MEDIA_ROOT) / "sfs_results" / "41_sfs_results.json"
    path.parent.mkdir()
    yield path
    SFS_PROGRESS.clear()


def readers():
    from rest_framework.test import APIRequestFactory
    from modeling.views import SFSStatusView, SFSResultsView
    from ai_assistant.tool_executor import read_sfs_status

    factory = APIRequestFactory()
    return (SFSStatusView.as_view()(factory.get("/sfs/status/41/"), file_id=41),
            SFSResultsView.as_view()(factory.get("/sfs/results/41/"), file_id=41),
            read_sfs_status(41))


def test_failed_record_retains_exact_diagnostic_across_all_readers(recorded):
    failure = {"schema_version": 1, "operation_id": "operation-41", "stage": "candidate_publication",
               "exception_type": "OperationalError", "trace_frames": []}
    recorded.write_text(json.dumps({"status": "error", "error": "database is locked", "failure": failure,
                                    "operation_id": "operation-41", "forward": [], "backward": []}))
    before = recorded.read_bytes()
    progress, results, assistant = readers()
    assert progress.status_code == results.status_code == 200
    for payload in (progress.data, results.data, assistant):
        assert payload["status"] == "error"
        assert payload["failure"] == failure
        assert payload["operation_id"] == "operation-41"
        assert payload["error"] == "database is locked"
    assert results.data["sfs_completed"] is False
    assert progress.data["progress"] == assistant["progress"] == 0
    assert recorded.read_bytes() == before


@pytest.mark.parametrize("content", [
    "{", "[]", "null", "{}", '{"status":"unknown"}', '{"status":null}',
    '{"status":"completed","error":"failed"}',
    '{"status":"completed","failure":{"stage":"search"}}',
    '{"status":"error","status":"completed"}',
    '{"status":"completed","forward":NaN}',
    '{"status":"completed","forward":{}}',
])
def test_invalid_saved_evidence_is_unavailable_never_success_or_absence(recorded, content):
    recorded.write_text(content)
    before = recorded.read_bytes()
    progress, results, assistant = readers()
    assert progress.status_code == results.status_code == 503
    for payload in (progress.data, results.data, assistant):
        assert payload["status"] == "unavailable"
        assert payload.get("progress", 0) == 0
    assert progress.data["sfs_completed"] is results.data["sfs_completed"] is False
    assert assistant["source"] == "disk"
    from ai_assistant.tool_executor import _format_sfs_status_line
    assert "UNAVAILABLE" in _format_sfs_status_line(assistant)
    assert "Inspect" in _format_sfs_status_line(assistant)
    assert recorded.read_bytes() == before


@pytest.mark.parametrize("state,expected", [("completed", "completed"), ("running", "interrupted"),
                                           ("stopped", "stopped"), ("interrupted", "interrupted")])
def test_supported_records_keep_explicit_state_and_no_owner_is_not_live(recorded, state, expected):
    recorded.write_text(json.dumps({"status": state, "forward": [{"step": 1}], "backward": []}))
    progress, results, assistant = readers()
    assert progress.status_code == results.status_code == 200
    assert progress.data["status"] == assistant["status"] == expected
    assert results.data["status"] == state
    assert results.data["sfs_completed"] is (state in {"completed", "stopped"})
    assert progress.data["progress"] == assistant["progress"] == int(state == "completed")


def test_live_progress_keeps_precedence_over_old_failed_record(recorded):
    from modeling.views import SFS_PROGRESS

    recorded.write_text('{"status":"error","error":"older attempt"}')
    SFS_PROGRESS[41] = {"status": "running", "progress": 0.25, "operation_id": "new-attempt"}
    progress, _, assistant = readers()
    assert progress.data["status"] == assistant["status"] == "running"
    assert progress.data["operation_id"] == assistant["operation_id"] == "new-attempt"


def test_unreadable_record_has_safe_unavailable_state(recorded, monkeypatch):
    import builtins

    recorded.write_text('{"status":"completed"}')
    actual_open = builtins.open

    def open_file(path, *args, **kwargs):
        if str(path) == str(recorded):
            raise PermissionError("synthetic sensitive path")
        return actual_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", open_file)
    progress, results, assistant = readers()
    assert progress.status_code == results.status_code == 503
    for payload in (progress.data, results.data, assistant):
        assert payload["status"] == "unavailable"
        assert "synthetic sensitive path" not in str(payload)


def test_absent_file_keeps_no_run_semantics(recorded):
    progress, results, assistant = readers()
    assert progress.status_code == 200 and progress.data["status"] == "not_started"
    assert results.status_code == 404 and results.data["sfs_completed"] is False
    assert assistant["status"] == "not_started" and assistant["source"] == "absent"
