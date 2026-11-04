"""Private scratch state of one fixed native child, never execution authority.

This is not an expert-code sandbox. Only platform-generated native artifacts
and registered implementations enter this process; D08 remains separate.
"""

import json
import os
import uuid
from pathlib import Path

_context = None


def active():
    return _context


def operation_id():
    if active():
        return json.loads((active().directory / "request.json").read_bytes())["job_id"]
    return str(uuid.uuid4())


def native_threads(requested):
    return 1 if active() else requested


class ChildContext:
    def __init__(self, directory):
        self.directory = Path(directory)

    def failure(self, error, stage):
        from modeling.async_failures import record_failure

        request = json.loads((self.directory / "request.json").read_bytes())
        record = record_failure(
            error,
            stage,
            {
                "operation": request["operation"],
                "operation_id": request["job_id"],
                "file_id": request["options"]["file_id"],
            },
        )
        (self.directory / "failure.json").write_text(json.dumps(record, allow_nan=False))
        return record

    def progress(self, owner, changes):
        if (self.directory / "stop").exists():
            owner["stop_requested"] = True
        allowed = {
            "status",
            "message",
            "progress",
            "completed_trials",
            "total_trials",
            "current_step",
            "completed_step_count",
            "duration_seconds",
            "operation_id",
            "failure",
        }
        combined = {**owner, **changes}
        value = {k: v for k, v in combined.items() if k in allowed}
        if isinstance(combined.get("completed_steps"), list):
            value["completed_step_count"] = len(combined["completed_steps"])
        raw = json.dumps(value, allow_nan=False, default=str).encode()
        if len(raw) > 16384:
            value = {"status": owner.get("status"), "operation_id": owner.get("operation_id")}
            raw = json.dumps(value).encode()
        staged = self.directory / "progress.tmp"
        staged.write_bytes(raw)
        os.replace(staged, self.directory / "progress.json")


def activate(directory):
    global _context
    if _context is not None:
        raise RuntimeError("One native execution per child is required.")
    _context = ChildContext(directory)
