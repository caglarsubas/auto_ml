"""Read the frozen previous-source fixture without trusting archive paths."""

import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import PurePosixPath

MAX_ARCHIVE = 2 * 1024**2
MAX_EXPANDED = 8 * 1024**2
MAX_FILE = 2_000_000


class ReferenceError(ValueError):
    pass


def sources(archive, reference, pin):
    if (
        len(archive) > MAX_ARCHIVE
        or pin.get("schema") != "private_reference_archive_v1"
        or pin.get("qualification_reconstruction_only") is not True
        or pin.get("customer_release_qualified") is not False
        or hashlib.sha256(archive).hexdigest() != pin.get("archive_sha256")
        or pin.get("reference_sha256") != hashlib.sha256(reference).hexdigest()
    ):
        raise ReferenceError("reference_archive_binding")
    spec = json.loads(reference)
    if (
        spec.get("schema") != "private_reference_source_v1"
        or spec.get("qualification_reconstruction_only") is not True
        or spec.get("customer_release_qualified") is not False
        or not re.fullmatch("[0-9a-f]{40}", spec.get("source_commit", ""))
    ):
        raise ReferenceError("reference_source_scope")
    expected = spec["source_sha256"]
    if not isinstance(expected, dict) or not 1 <= len(expected) <= 1024:
        raise ReferenceError("reference_source_inventory")
    for name, digest in expected.items():
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or path.as_posix() != name
            or any(p in (".", "..") for p in path.parts)
            or path.parts[0] not in {"backend", "scripts", "docker", "docs"}
            or not re.fullmatch("[0-9a-f]{64}", digest)
        ):
            raise ReferenceError("reference_source_path")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(archive)) as stream:
            raw = stream.read(MAX_EXPANDED + 1)
        if len(raw) > MAX_EXPANDED:
            raise ReferenceError("reference_archive_expansion")
        result = {}
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as stream:
            for item in stream:
                if (
                    item.name not in expected
                    or item.name in result
                    or not item.isfile()
                    or item.size > MAX_FILE
                    or item.size < 0
                ):
                    raise ReferenceError("reference_archive_member")
                data = stream.extractfile(item).read(MAX_FILE + 1)
                if (
                    len(data) != item.size
                    or hashlib.sha256(data).hexdigest() != expected[item.name]
                ):
                    raise ReferenceError("reference_archive_content")
                result[item.name] = data
        if set(result) != set(expected) or len(result) != pin.get("files"):
            raise ReferenceError("reference_archive_inventory")
        return spec, result
    except (OSError, EOFError, tarfile.TarError):
        raise ReferenceError("reference_archive_invalid") from None
