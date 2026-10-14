"""Serialize process-local search registration after request validation."""

import threading

_lock = threading.Lock()


def claim_search(registry, file_id, progress):
    with _lock:
        if registry.get(file_id, {}).get("status") == "running":
            return False
        registry[file_id] = progress
        return True
