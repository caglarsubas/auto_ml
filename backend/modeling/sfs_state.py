"""Recorded SFS state never infers completion from missing or invalid evidence."""

import json


class SFSStateUnavailable(ValueError):
    pass


def read_recorded_sfs(path):
    def invalid_constant(value):
        raise SFSStateUnavailable("sfs_record_malformed")

    def unique_object(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise SFSStateUnavailable("sfs_record_malformed")
        return result

    try:
        with open(path, encoding="utf-8") as stream:
            record = json.load(stream, parse_constant=invalid_constant, object_pairs_hook=unique_object)
    except SFSStateUnavailable:
        raise
    except (ValueError, OSError):
        raise SFSStateUnavailable("sfs_record_unreadable") from None
    if not isinstance(record, dict) or record.get("status") not in (
        "completed", "running", "stopped", "error", "interrupted"
    ):
        raise SFSStateUnavailable("sfs_record_state_invalid")
    if record["status"] == "completed" and (record.get("error") or record.get("failure")):
        raise SFSStateUnavailable("sfs_record_contradictory")
    if any(record.get(direction) is not None and not isinstance(record[direction], list)
           for direction in ("forward", "backward", "forward_from_backward")):
        raise SFSStateUnavailable("sfs_record_shape_invalid")
    return record


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
