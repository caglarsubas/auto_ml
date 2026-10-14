"""Recorded tuning results disclose unavailable evidence and retain failures."""

from modeling.search_state import read_recorded_search, validate_recorded_search
from modeling.sfs_evidence import write_sfs_record as write_hyperparam_record
from modeling.sfs_evidence import _archive_search_record

__all__ = ["write_hyperparam_record", "read_recorded_hyperparam", "HyperparamStateUnavailable",
           "unavailable_hyperparam", "recorded_hyperparam_progress", "archive_hyperparam_record"]


class HyperparamStateUnavailable(ValueError):
    pass


def read_recorded_hyperparam(path):
    return read_recorded_search(path, "hyperparam", ("trials", "trial_attempts", "validation_curves"),
                                HyperparamStateUnavailable)


def archive_hyperparam_record(directory, record):
    """Retain terminal tuning evidence once per operation, including failures/stops."""
    validate_recorded_search(record, "hyperparam", ("trials", "trial_attempts", "validation_curves"),
                             HyperparamStateUnavailable)
    if record.get("status") not in ("completed", "stopped", "error"):
        raise ValueError("Tuning archives require explicit terminal evidence.")
    return _archive_search_record(directory, record, "hyperparam", read_recorded_hyperparam, "tuning")


def unavailable_hyperparam(error):
    return {
        "status": "unavailable", "hyperparam_completed": False, "progress": 0.0,
        "error_code": str(error),
        "error": "Recorded tuning state is unavailable. Inspect the saved evidence before continuing.",
    }


def recorded_hyperparam_progress(record, file_id):
    state = "interrupted" if record["status"] == "running" else record["status"]
    return {
        "file_id": file_id, "status": state, "progress": 1.0 if state == "completed" else 0.0,
        "message": ("Tuning has no live owner in this process. Inspect the recorded evidence."
                    if state == "interrupted" else f"Recorded hyperparameter tuning {state}"),
        **{key: record.get(key) for key in ("error", "failure", "operation_id", "duration_seconds", "archive_path")},
    }
