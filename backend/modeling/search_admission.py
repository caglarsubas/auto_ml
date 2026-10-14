"""Serialize process-local search registration after request validation."""

import threading

_lock = threading.Lock()


def claim_search(registry, file_id, progress):
    with _lock:
        if registry.get(file_id, {}).get("status") == "running":
            return False
        registry[file_id] = progress
        return True


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
