"""Store the extra SFS fits outside legacy progress and result payloads."""

import hashlib
import json
from pathlib import Path

from django.conf import settings

from execution_jobs import legacy_context

NAME = "development_evidence/selection-fits.jsonl"
MAX_BYTES = 8 * 1024**2


def record(value):
    """Return a content reference, with a bounded gap if the evidence is too large."""
    if legacy_context.active() is None:
        return None
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    path = Path(settings.MEDIA_ROOT) / NAME
    offset = path.stat().st_size if path.exists() else 0
    if offset + len(raw) + 1 > MAX_BYTES:
        return {"status": "evidence_budget_exceeded"}
    path.parent.mkdir(exist_ok=True)
    with path.open("ab") as stream:
        stream.write(raw + b"\n")
    return {"offset": offset, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(raw, reference):
    offset, size = reference["offset"], reference["bytes"]
    if type(offset) is not int or type(size) is not int or offset < 0 or size <= 0:
        raise ValueError("Selection fit evidence has an invalid extent.")
    end = offset + size
    if (end >= len(raw) or raw[end:end + 1] != b"\n" or offset and raw[offset - 1:offset] != b"\n"):
        raise ValueError("Selection fit evidence exceeds its recorded extent.")
    value = raw[offset:end]
    if hashlib.sha256(value).hexdigest() != reference["sha256"]:
        raise ValueError("Selection fit evidence digest does not match.")
    return json.loads(value)
