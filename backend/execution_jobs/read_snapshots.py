"""Opt-in, read-committed observations; never an execution or approval authority.

Two complete collections fence the public bytes, including out-of-band changes
that forgot to advance a revision. This is an optimistic observation, not a
promise of latest state after the response or a cryptographic event history.
Legacy serialized read routes remain available and unchanged.
"""

import hashlib
import json
import re
import time
import uuid
from datetime import date, datetime
from typing import NamedTuple

from django.db import connection
from django.utils import timezone

from access_control import projects
from execution_jobs import csv_scoring, history, service, training_search
from execution_jobs.models import JobEvent, NativeJob

MAX_EVENTS = 256
MAX_SECONDS = 5
REPRESENTATIONS = {"receipt", "candidate", "scores"}


class Snapshot(NamedTuple):
    raw: bytes
    representation: str
    revision: int
    result_sha256: str


def parameters(params):
    if (set(params) - {"representation", "revision", "sha256", "project_id"}
            or any(len(params.getlist(k)) != 1 for k in params)):
        raise ValueError("Unsupported or repeated snapshot parameter.")
    representation = params.get("representation", "receipt")
    revision = params.get("revision")
    if representation not in REPRESENTATIONS:
        raise ValueError("Unsupported snapshot representation.")
    if revision is not None:
        if not re.fullmatch(r"0|[1-9][0-9]{0,9}", revision) or int(revision) > 2**31 - 1:
            raise ValueError("Supply one canonical nonnegative revision.")
        revision = int(revision)
    expected = params.get("sha256")
    if representation == "receipt":
        if expected is not None:
            raise ValueError("Receipt snapshots use revision, not a result digest.")
    else:
        expected = service.require_digest(expected)
    return representation, revision, expected


def _canonical(value):
    def scalar(v):
        if isinstance(v, (datetime, date)):
            return v.isoformat()  # Keep full timestamp precision in private fences.
        if isinstance(v, uuid.UUID):
            return str(v)
        raise TypeError("Unsupported snapshot value.")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False, default=scalar).encode("utf-8")


def _fence(job, events):
    # Never return this private fingerprint: it includes lease/authority fields.
    def fields(row):
        return {f.attname: getattr(row, f.attname) for f in row._meta.concrete_fields}
    return hashlib.sha256(_canonical([fields(job), [fields(e) for e in events]])).digest()


def _budget(started):
    if time.monotonic() - started > MAX_SECONDS:
        raise service.JobConflict("job_snapshot_budget_exceeded")


def _events(job):
    rows = list(JobEvent.objects.filter(job_id=job.pk).order_by("revision")[:MAX_EVENTS + 1])
    if len(rows) > MAX_EVENTS:
        raise service.JobConflict("job_snapshot_budget_exceeded")
    if (type(job.revision) is not int or job.revision < 0 or len(rows) != job.revision
            or any(e.revision != index or not isinstance(e.detail, dict)
                   or not isinstance(e.actor_snapshot, dict) for index, e in enumerate(rows, 1))):
        raise service.JobConflict("job_snapshot_history_invalid")
    return rows


def _materialize(job, events, representation, expected):
    if representation == "receipt":
        # Reuse the public serializer without an unbounded related-manager read.
        job._prefetched_objects_cache = {"events": events}
        return _canonical({"schema": "native_job_snapshot_v1", "read_only": True,
                           "observed_at": timezone.now().isoformat(), "revision": job.revision,
                           "receipt": service.serialize(job)})
    if representation == "scores":
        if (job.state != "succeeded" or service._saved_kind(job) not in
                (csv_scoring.KIND, service.training_scoring.KIND)
                or job.result_sha256 != expected or not isinstance(job.result, dict)
                or not isinstance(job.result.get("scores"), list)):
            raise service.JobConflict("job_scoring_result_unavailable")
        return csv_scoring.canonical_bytes(job.result)
    if (job.state != "succeeded" or service._saved_kind(job) != training_search.KIND
            or job.result_sha256 != expected):
        raise service.JobConflict("job_training_result_unavailable")
    from deployment import native_candidate
    return native_candidate.export_candidate(job.pk, job.dataset_id, job.project_id, job.result, expected)


def read(actor, identifier, params):
    representation, revision, expected = parameters(params)
    if connection.vendor != "postgresql":
        raise service.JobConflict("job_snapshot_backend_unsupported")
    started = time.monotonic()
    with history._bounded_read():
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_isolation")
            if cursor.fetchone()[0] != "read committed":
                # A repeatable snapshot could conceal late authority revocation.
                raise service.JobConflict("job_snapshot_isolation_unsupported")
        metadata = NativeJob.objects.values("dataset_id", "source_dataset_id", "project_id").get(pk=identifier)
        first_scope = service.scope(actor, metadata["dataset_id"])
        if first_scope["project_id"] != str(metadata["project_id"]):
            raise projects.ProjectDenied("job_project_mismatch")
        selector_scope = None
        if params.get("project_id") is not None:
            selector_scope = projects.membership(actor.pk, params["project_id"], "read")
            if selector_scope["project_id"] != first_scope["project_id"]:
                raise projects.ProjectDenied("job_project_mismatch")
        if metadata["source_dataset_id"] is not None:
            source_scope = service.scope(actor, metadata["source_dataset_id"])
            if source_scope["project_id"] != first_scope["project_id"]:
                raise projects.ProjectDenied("job_input_project_mismatch")
        _budget(started)
        job = NativeJob.objects.get(pk=identifier)
        if any(getattr(job, name) != value for name, value in metadata.items()):
            raise service.JobConflict("job_snapshot_stale")
        scopes = service.read_authority(actor, job)
        if revision is not None and job.revision != revision:
            raise service.JobConflict("job_snapshot_stale")
        events = _events(job)
        before = _fence(job, events)
        raw = _materialize(job, events, representation, expected)
        _budget(started)
        observed = NativeJob.objects.get(pk=identifier)
        # Collect the second history without assuming its coherence: a normal
        # concurrent transition is stale, not a corrupt-history diagnosis.
        later_events = list(JobEvent.objects.filter(job_id=identifier).order_by("revision")[:MAX_EVENTS + 1])
        if before != _fence(observed, later_events):
            raise service.JobConflict("job_snapshot_stale")
        for current in [first_scope, *scopes]:
            projects.recheck(current)
        if selector_scope is not None:
            projects.recheck(selector_scope)
        if metadata["source_dataset_id"] is not None:
            projects.recheck(source_scope)
        _budget(started)
        return Snapshot(raw, representation, job.revision, job.result_sha256)
