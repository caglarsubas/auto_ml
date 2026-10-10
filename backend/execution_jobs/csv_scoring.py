"""Bounded native scoring of a pinned governed CSV; no expert execution."""

import io
import csv
import json
import os
from pathlib import Path
import pandas as pd
from django.conf import settings
from declaration.models import Declaration
from access_control import projects
from deployment.scoring_receipts import csv_input, scoring_runtime

KIND = "native_csv_scoring_v1"
BUDGET = {"max_input_bytes": 5 * 1024**2, "max_rows": 10000, "max_columns": 256, "max_output_bytes": 16 * 1024**2}


def canonical_bytes(result):
    return json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def input_bytes(actor_id, file_id, check=lambda: None, expected=None):
    from execution_jobs.service import JobConflict

    authority = projects.dataset_authority(actor_id, file_id, "read")
    dataset = Declaration.objects.get(pk=file_id)
    if not dataset.has_header:
        raise JobConflict("job_csv_header_required")
    relative = dataset.file.name
    path = Path(settings.MEDIA_ROOT) / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts or path.suffix.lower() != ".csv":
        raise JobConflict("job_csv_input_required")
    current = Path(settings.MEDIA_ROOT)
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise JobConflict("job_input_unavailable")
    if expected and relative != expected["relative_path"]:
        raise JobConflict("job_input_changed")
    projects.path_authority(actor_id, str(path), file_id=file_id)
    # Bound reads using the opened descriptor, including a concurrently enlarged
    # file. The job consumes these exact bytes, never a mutable path after parsing.
    with path.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size > BUDGET["max_input_bytes"]:
            raise JobConflict("job_input_budget_exceeded")
        raw = bytearray()
        while chunk := stream.read(min(1024**2, BUDGET["max_input_bytes"] + 1 - len(raw))):
            check()
            raw.extend(chunk)
            if len(raw) > BUDGET["max_input_bytes"]:
                raise JobConflict("job_input_budget_exceeded")
    check()
    projects.recheck(authority)
    receipt = {"file_id": file_id, "name": dataset.original_name, "relative_path": relative, **csv_input(raw)}
    if not raw or expected and any(receipt[k] != expected[k] for k in ["sha256", "bytes", "parser", "pandas_version"]):
        raise JobConflict("job_input_changed")
    return bytes(raw), receipt, authority


def prepare(actor, file_id):
    if not projects.governed():
        raise projects.ProjectDenied("job_requires_project_governance")
    _, receipt, _ = input_bytes(actor.pk, file_id)
    return {k: v for k, v in receipt.items() if k != "relative_path"} | {"budget": BUDGET}


def score(job, manifest, out, hashed, check):
    from execution_jobs.service import JobConflict
    from deployment.offline_verify import NATIVE_ALGORITHMS
    from deployment.deploy_utils import score_bundle_directory

    if manifest.get("algorithm") not in NATIVE_ALGORITHMS:
        raise JobConflict("job_native_package_required")
    raw, receipt, _ = input_bytes(job.authority["actor_id"], job.source_dataset_id, check, job.specification["source"])
    # Reject pathological width/record counts before pandas allocates a frame.
    # This bounded UTF-8 profile uses the default CSV dialect and field limit.
    try:
        text = io.StringIO(raw.decode("utf-8-sig"))
        records = csv.reader(text, strict=True)
        header = next(row for row in records if row)
        if len(header) > BUDGET["max_columns"] or len(set(header)) != len(header):
            raise JobConflict("job_csv_schema_invalid")
        count = 0
        checked_at = text.tell()
        for row in records:
            # Poll by bounded parsed text instead of issuing authority queries
            # for every tiny record. Every schema/row check still executes.
            if text.tell() - checked_at >= 65536:
                check()
                checked_at = text.tell()
            if row:
                count += 1
                if count > BUDGET["max_rows"] or len(row) > len(header):
                    raise JobConflict("job_input_budget_exceeded")
    except (csv.Error, UnicodeError, StopIteration):
        raise JobConflict("job_csv_input_invalid") from None
    check()
    frame = pd.read_csv(io.BytesIO(raw), nrows=BUDGET["max_rows"] + 1)
    if frame.empty or len(frame) > BUDGET["max_rows"] or len(frame.columns) > BUDGET["max_columns"]:
        raise JobConflict("job_input_budget_exceeded")
    check()
    result = score_bundle_directory(out, job.dataset_id, frame, job.specification["bundle_id"], artifact_digest=hashed)
    check()
    if result["manifest_sha256"] != job.specification["manifest_sha256"]:
        raise JobConflict("job_manifest_changed")
    result.update(
        {
            "scope": KIND,
            "batch_id": str(job.pk),
            "job_id": str(job.pk),
            "receipt_schema_version": 1,
            "input": {k: v for k, v in receipt.items() if k not in {"file_id", "name", "relative_path"}},
            "scoring_runtime": scoring_runtime(),
            "offline_verification_scope": "native_csv_batch_score_parity",
            "review_approved": False,
        }
    )
    if len(canonical_bytes(result)) > BUDGET["max_output_bytes"]:
        raise JobConflict("job_output_budget_exceeded")
    check()
    return result
