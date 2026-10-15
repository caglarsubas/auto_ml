"""Serialize process-local search registration after request validation."""

import threading
import uuid
from collections.abc import Mapping

_lock = threading.Lock()
ACTIVE_SEARCH_LIMIT = 2


class SearchCapacityExceeded(Exception):
    """All process-local active search slots are occupied."""


def claim_search(registry, file_id, progress, *, other_registries=()):
    with _lock:
        if registry.get(file_id, {}).get("status") == "running":
            return False
        # Count SFS and tuning together, including cooperative stops and launches
        # whose acknowledgement is uncertain. Terminal evidence is not a slot.
        registries = {id(item): item for item in (registry, *other_registries)}
        active = sum(owner.get("status") == "running"
                     for item in registries.values() for owner in item.values())
        if active >= ACTIVE_SEARCH_LIMIT:
            raise SearchCapacityExceeded
        registry[file_id] = progress
        return True


def request_search_stop(registry, file_id, parameters, *, message=None):
    """Validate optional operation identity and stop one owner atomically."""
    if not isinstance(parameters, Mapping):
        return {"outcome": "invalid"}
    expected = parameters.get("operation_id")
    if "operation_id" in parameters:
        try:
            if not isinstance(expected, str) or str(uuid.UUID(expected)) != expected:
                return {"outcome": "invalid"}
        except ValueError:
            return {"outcome": "invalid"}
    with _lock:
        owner = registry.get(file_id)
        operation = owner.get("operation_id") if owner is not None else None
        if expected is not None and operation != expected:
            return {"outcome": "conflict", "operation_id": operation}
        if owner is None:
            return {"outcome": "missing", "operation_id": None}
        current_status = owner.get("status")
        if current_status != "running":
            return {"outcome": "not_running", "operation_id": operation, "run_status": current_status}
        changes = {"stop_requested": True}
        if message is not None:
            changes["message"] = message
        owner.update(changes)
        return {"outcome": "stop_requested", "operation_id": operation}


def update_search_progress(registry, file_id, owner, operation_id, changes, *, running_only=False):
    """Publish only to the accepted owner, pinning identity and terminal callbacks."""
    with _lock:
        if registry.get(file_id) is not owner or owner is None or owner.get("operation_id") != operation_id:
            return False
        if running_only and owner.get("status") != "running":
            return False
        owner.update({**changes, "operation_id": operation_id})
        return True


def fail_search_launch(registry, file_id, owner, operation_id, failure, may_have_started, message):
    """Fail only a known unstarted current owner; retain uncertain/terminal owners."""
    with _lock:
        if registry.get(file_id) is not owner or owner is None or owner.get("operation_id") != operation_id:
            return False
        if may_have_started or owner.get("status") != "running":
            owner["launch_failure"] = failure
            return False
        owner.update(status="error", progress=0.0, message=message, error=message, failure=failure)
        return True
