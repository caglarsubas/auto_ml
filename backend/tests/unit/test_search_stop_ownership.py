"""Cancellation cannot cross an operation boundary or race admission."""
import copy
import threading
import uuid

import pytest

from modeling.search_admission import claim_search, update_search_progress

pytestmark = pytest.mark.unit


@pytest.fixture(params=["sfs", "hyperparam"])
def stop_api(request):
    from rest_framework.test import APIRequestFactory
    from modeling import views

    sfs = request.param == "sfs"
    registry = views.SFS_PROGRESS if sfs else views.HYPERPARAM_PROGRESS
    view = views.SFSStopView if sfs else views.HyperparamStopView
    before = registry.copy()
    registry.clear()
    owner = {"status": "running", "operation_id": str(uuid.uuid4()), "stop_requested": False,
             "message": "Working", "progress": .25}
    other = {"status": "running", "operation_id": str(uuid.uuid4()), "stop_requested": False}
    registry.update({1: owner, 2: other})
    factory = APIRequestFactory()

    def stop(parameters):
        return view.as_view()(factory.post("/stop/1/", parameters, format="json"), file_id=1)

    def raw_stop(body, content_type):
        return view.as_view()(factory.generic("POST", "/stop/1/", body, content_type=content_type), file_id=1)

    yield {"registry": registry, "owner": owner, "other": other, "stop": stop, "raw_stop": raw_stop, "sfs": sfs}
    registry.clear()
    registry.update(before)


@pytest.mark.parametrize("bound", [False, True])
def test_matching_and_legacy_stop_are_correlated_idempotent_and_keep_admission_blocked(stop_api, bound):
    case = stop_api
    operation = case["owner"]["operation_id"]
    other = copy.deepcopy(case["other"])
    parameters = {"operation_id": operation} if bound else {}
    response = case["stop"](parameters)
    assert response.status_code == 200
    assert response.data["status"] == "stop_requested" and response.data["operation_id"] == operation
    assert case["owner"]["stop_requested"] is True and case["owner"]["status"] == "running"
    if not case["sfs"]:
        assert case["owner"]["message"] == "Stop requested — finishing current trial..."
    expected = copy.deepcopy(case["registry"])
    repeat = case["stop"](parameters)
    assert repeat.status_code == 200 and repeat.data == response.data
    assert case["registry"] == expected and case["other"] == other
    assert not claim_search(case["registry"], 1, {"status": "running", "operation_id": str(uuid.uuid4())})


@pytest.mark.parametrize("state", ["running", "stopped", "completed", "error"])
def test_stale_operation_is_rejected_without_changing_current_or_other_evidence(stop_api, state):
    case = stop_api
    case["owner"]["status"] = state
    before = copy.deepcopy(case["registry"])
    response = case["stop"]({"operation_id": str(uuid.uuid4())})
    assert response.status_code == 409 and response.data["error_code"] == "search_operation_changed"
    assert response.data["operation_id"] == case["owner"]["operation_id"]
    assert case["registry"] == before


@pytest.mark.parametrize("bound", [False, True])
def test_missing_live_owner_preserves_legacy_response_and_refuses_explicit_old_identity(stop_api, bound):
    case = stop_api
    operation = case["owner"]["operation_id"]
    case["registry"].pop(1)
    before = copy.deepcopy(case["registry"])
    response = case["stop"]({"operation_id": operation} if bound else {})
    assert response.status_code == (409 if bound else 404 if case["sfs"] else 200)
    if bound:
        assert response.data["error_code"] == "search_operation_changed" and response.data["operation_id"] is None
    elif not case["sfs"]:
        assert response.data["status"] == "not_running"
    assert case["registry"] == before


@pytest.mark.parametrize("value", [None, False, 1, "", "not-a-uuid", "ABCDEFAB-1234-1234-1234-ABCDEFABCDEF"])
def test_invalid_operation_values_do_not_fall_back_to_unbound_stop(stop_api, value):
    case = stop_api
    before = copy.deepcopy(case["registry"])
    response = case["stop"]({"operation_id": value})
    assert response.status_code == 400 and response.data["error_code"] == "invalid_stop_operation"
    assert case["registry"] == before


@pytest.mark.parametrize("body", [[], "invalid", 1])
def test_nonobject_body_is_rejected_without_mutation(stop_api, body):
    case = stop_api
    before = copy.deepcopy(case["registry"])
    response = case["stop"](body)
    assert response.status_code == 400 and response.data["error_code"] == "invalid_stop_operation"
    assert case["registry"] == before


@pytest.mark.parametrize("body,content_type,expected", [(b"{", "application/json", 400),
    (b"not-json", "application/json", 400), (b"stop", "text/plain", 415)])
def test_parser_and_media_errors_are_client_errors_without_signalling_a_stop(stop_api, body, content_type, expected):
    before = copy.deepcopy(stop_api["registry"])
    response = stop_api["raw_stop"](body, content_type)
    assert response.status_code == expected and stop_api["registry"] == before


@pytest.mark.parametrize("state", ["stopped", "completed", "error", "unavailable"])
def test_matching_terminal_owner_is_not_mutated(stop_api, state):
    case = stop_api
    case["owner"]["status"] = state
    before = copy.deepcopy(case["registry"])
    response = case["stop"]({"operation_id": case["owner"]["operation_id"]})
    assert response.status_code == 200
    assert response.data["status"] == (state if case["sfs"] else "not_running")
    assert response.data["operation_id"] == case["owner"]["operation_id"]
    assert case["registry"] == before


def test_stop_and_terminal_handover_are_serialized_for_real_threads(stop_api):
    case = stop_api
    entered, release, handover_entered, handed_over = [threading.Event() for _ in range(4)]
    errors, replies = [], []

    class PausedOwner(dict):
        def get(self, key, default=None):
            if key == "status" and threading.current_thread().name == "stop-request-proof":
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Stop proof was not released")
            return super().get(key, default)

    owner = PausedOwner(case["owner"])
    operation = owner["operation_id"]
    case["registry"][1] = owner
    newer = {"status": "running", "operation_id": str(uuid.uuid4()), "stop_requested": False}
    expected = copy.deepcopy(newer)

    def stop():
        try:
            replies.append(case["stop"]({"operation_id": operation}))
        except Exception as error:
            errors.append(error)

    def handover():
        try:
            handover_entered.set()
            assert update_search_progress(case["registry"], 1, owner, operation, {"status": "completed"})
            assert claim_search(case["registry"], 1, newer)
            handed_over.set()
        except Exception as error:
            errors.append(error)

    stop_thread = threading.Thread(target=stop, name="stop-request-proof")
    handover_thread = threading.Thread(target=handover)
    try:
        stop_thread.start()
        assert entered.wait(5)
        handover_thread.start()
        assert handover_entered.wait(5)
        # Handover reached the guarded publication while the stop is paused.
        assert not handed_over.wait(.1)
    finally:
        release.set()
        stop_thread.join(5)
        if handover_thread.ident is not None:
            handover_thread.join(5)
    assert not stop_thread.is_alive() and not handover_thread.is_alive() and not errors
    assert handed_over.is_set() and len(replies) == 1 and replies[0].status_code == 200
    assert replies[0].data["operation_id"] == operation and owner["stop_requested"] is True
    assert case["registry"][1] == expected
