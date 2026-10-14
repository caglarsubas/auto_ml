"""Recorded SFS state never infers completion from missing or invalid evidence."""

from modeling.search_state import read_recorded_search


class SFSStateUnavailable(ValueError):
    pass


def read_recorded_sfs(path):
    return read_recorded_search(path, "sfs", ("forward", "backward", "forward_from_backward"), SFSStateUnavailable)


def unavailable_payload(error):
    return {
        "status": "unavailable",
        "sfs_completed": False,
        "error_code": str(error),
        "error": "Recorded SFS state is unavailable. Inspect the saved evidence before continuing.",
        "progress": 0.0,
    }


def recorded_progress(record, file_id):
    state = "interrupted" if record["status"] == "running" else record["status"]
    return {
        "file_id": file_id,
        "status": state,
        "progress": 1.0 if state == "completed" else 0.0,
        "message": {
            "completed": "SFS already completed",
            "interrupted": "SFS has no live owner in this process. Partial evidence is available for review.",
            "stopped": "SFS was stopped by user. Partial results available.",
            "error": "SFS failed. Inspect the recorded error and failure diagnostic.",
        }[state],
        "error": record.get("error"),
        "failure": record.get("failure"),
        "operation_id": record.get("operation_id"),
        "duration_seconds": record.get("duration_seconds"),
    }
