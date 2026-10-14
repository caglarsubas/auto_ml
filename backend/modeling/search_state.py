"""Strict recorded search state, with operation-specific public reason codes."""

import json


def read_recorded_search(path, operation, list_fields, unavailable):
    def invalid_constant(value):
        raise unavailable(f"{operation}_record_malformed")

    def unique_object(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise unavailable(f"{operation}_record_malformed")
        return result

    try:
        with open(path, encoding="utf-8") as stream:
            record = json.load(stream, parse_constant=invalid_constant, object_pairs_hook=unique_object)
    except unavailable:
        raise
    except (ValueError, OSError):
        raise unavailable(f"{operation}_record_unreadable") from None
    if not isinstance(record, dict) or record.get("status") not in (
        "completed", "running", "stopped", "error", "interrupted"
    ):
        raise unavailable(f"{operation}_record_state_invalid")
    if record["status"] == "completed" and (record.get("error") or record.get("failure")):
        raise unavailable(f"{operation}_record_contradictory")
    if any(record.get(field) is not None and not isinstance(record[field], list) for field in list_fields):
        raise unavailable(f"{operation}_record_shape_invalid")
    return record
