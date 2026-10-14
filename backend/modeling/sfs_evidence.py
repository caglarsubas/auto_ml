"""Publish complete SFS records without exposing a partially written checkpoint."""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from modeling.sfs_state import read_recorded_sfs


def write_sfs_record(path, record, *, exclusive=False):
    """Replace a local-filesystem record after serialization and file synchronization.

    Failures before replacement leave the previous record intact. A directory-sync
    failure occurs after replacement: the complete new record is visible, but its
    crash durability is uncertain, so the caller must not claim successful saving.
    """
    payload = json.dumps(record, indent=2, allow_nan=False).encode("utf-8")
    destination = Path(path)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".sfs-", suffix=".tmp",
                                         delete=False) as stream:
            staged = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(staged, destination)
        else:
            os.replace(staged, destination)
        _sync_directory(destination.parent)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def _sync_directory(path):
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def archive_sfs_record(directory, record):
    """Publish one immutable archive per operation; identical retries reuse it."""
    operation_id = record.get("operation_id")
    if not isinstance(operation_id, str) or str(uuid.UUID(operation_id)) != operation_id:
        raise ValueError("SFS archive requires a canonical operation ID.")
    if "archived_at" in record:
        raise ValueError("Archive metadata cannot be supplied as search evidence.")
    expected = json.dumps(record, sort_keys=True, allow_nan=False)
    path = Path(directory) / f"sfs_run_{operation_id}.json"

    def verify_existing():
        existing = read_recorded_sfs(path)
        existing.pop("archived_at", None)
        if json.dumps(existing, sort_keys=True, allow_nan=False) != expected:
            raise ValueError("Recorded SFS operation has different evidence; archive preserved.")
        # Reconcile a prior directory-sync failure without republishing or changing bytes.
        _sync_directory(path.parent)

    if path.exists():
        verify_existing()
    else:
        payload = {**record, "archived_at": datetime.now(timezone.utc).isoformat()}
        try:
            write_sfs_record(path, payload, exclusive=True)
        except FileExistsError:
            verify_existing()
    return path
