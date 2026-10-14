"""Correlatable native async failures without logging data or exception values."""

import json
import logging
import traceback
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def record_failure(error, stage, context=None):
    context = context or {}
    record = {
        "schema_version": 1,
        "operation": context.get("operation", "sfs"),
        "operation_id": context.get("operation_id") or str(uuid.uuid4()),
        "file_id": context.get("file_id"),
        "execution_id": context.get("execution_id"),
        "stage": stage,
        "exception_type": type(error).__name__,
        "trace_frames": [
            {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
            for frame in traceback.extract_tb(error.__traceback__)[-32:]
        ],
    }
    # Messages/locals/rows/parameters are deliberately excluded from service
    # logs. The existing authorized error response retains actionable detail.
    logger.error("native_async_failure %s", json.dumps(record, sort_keys=True))
    return record
