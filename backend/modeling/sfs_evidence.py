"""Publish complete SFS records without exposing a partially written checkpoint."""

import json
import os
import tempfile
from pathlib import Path


def write_sfs_record(path, record):
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
        os.replace(staged, destination)
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
