"""Bounded native jobs. DB leases fence every result publication."""

import hashlib
import os
import stat
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from deployment.runtime_metadata import package_version as version
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from access_control import projects
from access_control.authority import actor_snapshot
from deployment.deploy_utils import bundle_dir
from deployment.evidence import parse_metadata, verify_bundle
from deployment.reviews import digest, lock_authority
from deployment.scoring_receipts import require_digest
from execution_jobs.models import QueueLock, NativeJob, JobEvent
from execution_jobs import csv_scoring, training_search, training_scoring, native_assessment
from modeling.execution_artifacts import projection_lock

ACTIVE = {"running", "cancel_requested"}
TERMINAL = {"succeeded", "blocked", "failed", "cancelled"}
LIMITS = {
    "max_active": 2,
    "max_pending": 100,
    "max_bytes": 1024**3,
    "max_files": 256,
    "seconds": 120,
    "attempts": 3,
    "lease_seconds": 180,
}
KIND = "package_integrity_v1"
LOCK_WAIT_MILLISECONDS = 5_000


class JobConflict(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class JobStopped(Exception):
    pass


def limits(kind):
    if kind == native_assessment.KIND:
        return {**LIMITS, **native_assessment.BUDGET}
    if kind == training_scoring.KIND:
        return {**LIMITS, **training_scoring.BUDGET}
    if kind == training_search.KIND:
        return {**LIMITS, **training_search.BUDGET}
    return {**LIMITS, **csv_scoring.BUDGET} if kind == csv_scoring.KIND else dict(LIMITS)


def runtime(kind=KIND):
    sources = [
        "execution_jobs/service.py",
        "execution_jobs/models.py",
        "execution_jobs/tasks.py",
        "execution_jobs/config.py",
        "execution_jobs/csv_scoring.py",
        "backend/celery.py",
        "deployment/evidence.py",
        "deployment/runtime_metadata.py",
        "deployment/deploy_utils.py",
        "access_control/projects.py",
    ]
    result = {
        "python": sys.version.split()[0],
        "packages": {p: version(p) for p in ["Django", "celery", "kombu", "redis"]},
        "sources": {p: hashlib.sha256((Path(settings.BASE_DIR) / p).read_bytes()).hexdigest() for p in sources},
    }

    if kind == csv_scoring.KIND:
        from deployment.scoring_receipts import scoring_runtime

        result["scoring"] = scoring_runtime()
    if kind in {training_search.KIND, training_scoring.KIND, native_assessment.KIND}:
        result["packages"].update({p: version(p) for p in ["numpy", "pandas", "scipy", "scikit-learn", "xgboost"]})
        for name in ["execution_jobs/native_assessment.py", "modeling/holdout_evidence.py", "modeling/execution_artifacts.py", "execution_jobs/training_search.py", "execution_jobs/training_scoring.py", "deployment/native_candidate.py", "modeling/booster_adapters.py", "modeling/prediction_contract.py",
                     "modeling/declared_metric.py", "modeling/development_validation.py", "modeling/development_assessment.py", "modeling/rank_metrics.py",
                     "modeling/fit_receipts.py", "modeling/split_contract.py", "modeling/sfs_objective.py", "evaluation/eval_utils.py",
                     "preprocessing/purifier_contract.py", "deployment/scoring_receipts.py", "access_control/project_http.py"]:
            result["sources"][name] = hashlib.sha256((Path(settings.BASE_DIR) / name).read_bytes()).hexdigest()
    return result


@contextmanager
def locked():
    # Development SQLite has no SELECT FOR UPDATE; use the existing cross-process
    # local projection lock. Private installations always require PostgreSQL.
    if connection.vendor == "sqlite":
        with projection_lock(0), transaction.atomic():
            QueueLock.objects.get_or_create(pk=1)
            QueueLock.objects.select_for_update().get(pk=1)
            yield
    else:
        with transaction.atomic():
            previous_lock_timeout = None
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT current_setting('lock_timeout'), setting::bigint "
                        "FROM pg_settings WHERE name = 'lock_timeout'"
                    )
                    previous_lock_timeout, configured = cursor.fetchone()
                    bounded = min(configured or LOCK_WAIT_MILLISECONDS, LOCK_WAIT_MILLISECONDS)
                    cursor.execute("SELECT set_config('lock_timeout', %s, true)", [f"{bounded}ms"])
            QueueLock.objects.get_or_create(pk=1)
            QueueLock.objects.select_for_update().get(pk=1)
            yield
            # Exceptions/explicit rollback revert SET LOCAL with this atomic
            # block. Successful nested callers need their original setting back
            # before their outer transaction continues.
            if previous_lock_timeout is not None and not transaction.get_rollback():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('lock_timeout', %s, true)", [previous_lock_timeout])


def record(job, kind, *, actor=None, detail=None, update_fields=None):
    job.revision += 1
    JobEvent.objects.create(
        job=job,
        revision=job.revision,
        event_type=kind,
        actor_snapshot=actor_snapshot(actor) if actor else {},
        detail=detail or {},
    )
    if update_fields is None:
        job.save()
    else:
        job.save(update_fields=update_fields)


def scope(actor, file_id):
    if not projects.governed():
        raise projects.ProjectDenied("job_requires_project_governance")
    return projects.dataset_authority(actor.pk, file_id, "read")


@contextmanager
def _regular_artifact(path):
    """Pin storage parents and the regular file without following replacement links."""
    try:
        parts = Path(path).absolute().relative_to(Path(settings.MEDIA_ROOT).absolute()).parts
    except ValueError:
        raise OSError("artifact outside storage root") from None
    if not parts or ".." in parts:
        raise OSError("artifact outside storage root")
    descriptor = csv_scoring._input_descriptor(settings.MEDIA_ROOT, parts)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("regular artifact required")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(descriptor)


def _artifact_bytes(path, bound, initial_reason, growth_reason=None):
    with _regular_artifact(path) as stream:
        if os.fstat(stream.fileno()).st_size > bound:
            raise JobConflict(initial_reason)
        raw = stream.read(bound + 1)
        if len(raw) > bound:
            raise JobConflict(growth_reason or initial_reason)
        return raw


def _package_metadata(path):
    bound = 1024**2 if Path(path).name == "manifest.json" else 65536
    return _artifact_bytes(path, bound, "job_package_unavailable", "job_package_budget_exceeded")


def header(file_id, bundle_id, expected_sha):
    """Cheap admission pins small metadata; expensive artifact hashes run only in worker."""
    out = Path(bundle_dir(file_id, bundle_id))
    raw_root = Path(settings.MEDIA_ROOT).absolute()
    current = raw_root
    for part in out.absolute().relative_to(raw_root).parts:
        current = current / part
        if current.is_symlink():
            raise JobConflict("job_package_unavailable")
    values = {}
    for name, bound in [("manifest.json", 1024**2), ("publication.json", 65536)]:
        path = out / name
        if out.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size > bound:
            raise JobConflict("job_package_unavailable")
        raw = _artifact_bytes(path, bound, "job_package_unavailable", "job_package_budget_exceeded")
        values[name] = parse_metadata(raw)
        if name == "manifest.json" and hashlib.sha256(raw).hexdigest() != expected_sha:
            raise JobConflict("job_manifest_changed")
    manifest, publication = values["manifest.json"], values["publication.json"]
    if not isinstance(manifest, dict) or not isinstance(publication, dict):
        raise JobConflict("job_package_invalid")
    identity = {k: manifest.get(k) for k in ["file_id", "bundle_id", "execution_id", "assessment_id"]}
    if (
        identity["file_id"] != file_id
        or identity["bundle_id"] != str(bundle_id)
        or manifest.get("handoff_schema_version") != 1
        or any(publication.get(k) != v for k, v in identity.items())
        or publication.get("manifest_sha256") != expected_sha
    ):
        raise JobConflict("job_package_invalid")
    for key in ["bundle_id", "execution_id", "assessment_id"]:
        if str(uuid.UUID(str(identity[key]))) != identity[key]:
            raise JobConflict("job_package_invalid")
    files = manifest.get("artifact_integrity")
    if not isinstance(files, dict) or not 1 <= len(files) <= LIMITS["max_files"]:
        raise JobConflict("job_package_budget_exceeded")
    sizes = [v.get("bytes") for v in files.values() if isinstance(v, dict)]
    if len(sizes) != len(files) or any(type(n) is not int or n < 0 for n in sizes) or sum(sizes) > LIMITS["max_bytes"]:
        raise JobConflict("job_package_budget_exceeded")
    return manifest, identity


def submit(actor, file_id, data):
    if not settings.DECLARAI_JOBS_ENABLED:
        raise JobConflict("job_service_disabled")
    if not isinstance(data, dict) or data.get("kind") not in {KIND, csv_scoring.KIND, training_search.KIND, training_scoring.KIND, native_assessment.KIND}:
        raise ValueError("Select a supported native job kind.")
    kind = data["kind"]
    if kind == training_search.KIND:
        return training_search.submit(actor, file_id, data)
    if kind == training_scoring.KIND:
        return training_scoring.submit(actor, file_id, data)
    if kind == native_assessment.KIND:
        return native_assessment.submit(actor, file_id, data)
    fields = {"request_id", "kind", "bundle_id", "manifest_sha256"}
    if kind == csv_scoring.KIND:
        fields |= {"input_file_id", "input_sha256"}
    if set(data) != fields:
        raise ValueError("Supply exactly the displayed native job fields.")
    identifier, bundle_id = uuid.UUID(str(data["request_id"])), uuid.UUID(str(data["bundle_id"]))
    sha = require_digest(data["manifest_sha256"])
    current = scope(actor, file_id)
    roles = {"developer"} if kind == csv_scoring.KIND else {"developer", "reviewer"}
    if current["role"] not in roles:
        raise projects.ProjectDenied("job_submit_role_required")
    request_sha = digest({"actor_id": actor.pk, "file_id": file_id, "request": data})
    with locked():
        current = lock_authority(actor, file_id, None)
        if current["role"] not in roles:
            raise projects.ProjectDenied("job_submit_role_required")
        previous = NativeJob.objects.filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != request_sha:
                raise JobConflict("job_request_reused")
            scopes = read_authority(actor, previous)
            for authority in scopes:
                projects.recheck(authority)
            return authorized_receipt(previous, scopes, replayed=True)
        if NativeJob.objects.filter(state__in=ACTIVE | {"queued"}).count() >= LIMITS["max_pending"]:
            raise JobConflict("job_queue_full")
        manifest, identity = header(file_id, bundle_id, sha)
        source, input_scope, input_id = None, None, None
        if kind == csv_scoring.KIND:
            from deployment.offline_verify import NATIVE_ALGORITHMS

            if manifest.get("algorithm") not in NATIVE_ALGORITHMS:
                raise JobConflict("job_native_package_required")
            input_id = data["input_file_id"]
            if type(input_id) is not int or not 0 < input_id <= 2**63 - 1:
                raise ValueError("Supply a positive input dataset ID.")
            input_scope = lock_authority(actor, input_id, None)
            if input_scope["project_id"] != current["project_id"]:
                raise projects.ProjectDenied("job_input_project_mismatch")
            _, source, input_scope = csv_scoring.input_bytes(actor.pk, input_id)
            if input_scope["project_id"] != current["project_id"]:
                raise projects.ProjectDenied("job_input_project_mismatch")
            if source["sha256"] != require_digest(data["input_sha256"]):
                raise JobConflict("job_input_changed")
        specification = {
            "schema_version": 1,
            "kind": kind,
            **identity,
            "manifest_sha256": sha,
            "runtime": runtime(kind),
            "limits": limits(kind),
        }
        if source:
            specification.update(source=source, source_authority=input_scope)
        job = NativeJob.objects.create(
            id=identifier,
            source_dataset_id=input_id,
            actor=actor,
            actor_snapshot=actor_snapshot(actor),
            project_id=current["project_id"],
            dataset_id=file_id,
            authority=current,
            specification=specification,
            request_sha256=request_sha,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        projects.recheck(current)
        record(job, "submitted", actor=actor)
        return authorized_receipt(job, [current, *([input_scope] if input_scope is not None else [])])


def _saved_kind(job):
    value = job.specification.get("kind") if isinstance(job.specification, dict) else None
    return value if isinstance(value, str) else None


def serialize(job, *, replayed=False):
    result = job.result
    scores = result.get("scores") if isinstance(result, dict) else None
    if _saved_kind(job) in (csv_scoring.KIND, training_scoring.KIND) and isinstance(scores, list) and len(scores) > 500:
        result = {k: v for k, v in result.items() if k != "scores"} | {
            "scores_preview": scores[:500],
            "scores_truncated": True,
        }
    return {
        "id": str(job.pk),
        "file_id": job.dataset_id,
        "project_id": str(job.project_id),
        "state": job.state,
        "revision": job.revision,
        "attempts": job.attempts,
        "specification": job.specification,
        "submitted_by": job.actor_snapshot,
        "created_at": job.created_at.isoformat(),
        "expires_at": job.expires_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "result": result,
        "result_sha256": job.result_sha256,
        "reason_code": job.reason_code,
        "replayed": replayed,
        "review_approved": False,
        "production_use_approved": False,
        "events": [
            {
                "revision": e.revision,
                "event_type": e.event_type,
                "actor": e.actor_snapshot,
                "detail": e.detail,
                "created_at": e.created_at.isoformat(),
            }
            for e in job.events.all()
        ],
    }



def authorized_receipt(job, scopes, *, replayed=False):
    """Prepare a receipt before the final live authority checks, inside its transaction."""
    result = serialize(job, replayed=replayed)
    for current in scopes:
        projects.recheck(current)
    return result


def execution_scope_bindings(job):
    """A current scope for another resource is not this job's authority."""
    def bound(value, file_id, actor_id=None):
        if (not isinstance(value, dict) or type(value.get("file_id")) is not int
                or value["file_id"] != file_id or value.get("project_id") != str(job.project_id)
                or value.get("operation") != "read" or "pipeline_id" in value
                or type(value.get("actor_id")) is not int or value["actor_id"] <= 0
                or actor_id is not None and value["actor_id"] != actor_id):
            raise projects.ProjectDenied("job_authority_binding_changed")
    bound(job.authority, job.dataset_id)
    if job.source_dataset_id is not None:
        source = job.specification.get("source_authority") if isinstance(job.specification, dict) else None
        bound(source, job.source_dataset_id, job.authority["actor_id"])


def execution_specification(job):
    spec = job.specification
    if not isinstance(spec, dict) or not isinstance(spec.get("kind"), str):
        raise JobConflict("job_specification_invalid")
    return spec


def execution_reference(spec, identifier, checksum):
    """Validate persisted reference syntax before ORM conversion or protected reads."""
    value = spec.get(identifier)
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
        require_digest(spec.get(checksum))
    except ValueError:
        raise JobConflict("job_specification_invalid") from None


def recheck_execution(job):
    spec = execution_specification(job)
    execution_scope_bindings(job)
    if spec["kind"] == native_assessment.KIND:
        execution_reference(spec, "protected_input_id", "assessment_sha256")
        native_assessment.recheck(job)
    if spec["kind"] == training_scoring.KIND:
        execution_reference(spec, "training_job_id", "training_result_sha256")
        trained = NativeJob.objects.get(pk=spec["training_job_id"])
        if (trained.state != "succeeded" or trained.dataset_id != job.dataset_id
                or trained.project_id != job.project_id
                or _saved_kind(trained) != training_search.KIND
                or trained.result_sha256 != job.specification["training_result_sha256"]
                or digest(trained.result) != trained.result_sha256):
            raise JobConflict("job_training_result_changed")
    projects.recheck(job.authority)
    if job.source_dataset_id is not None:
        projects.recheck(job.specification["source_authority"])
    if spec["kind"] not in {KIND, csv_scoring.KIND, training_search.KIND, training_scoring.KIND, native_assessment.KIND}:
        raise JobConflict("job_runtime_changed")


def read_authority(actor, job):
    current = scope(actor, job.dataset_id)
    if str(job.project_id) != current["project_id"]:
        raise projects.ProjectDenied("job_project_mismatch")
    scopes = [current]
    if job.source_dataset_id is not None:
        source = scope(actor, job.source_dataset_id)
        if source["project_id"] != current["project_id"]:
            raise projects.ProjectDenied("job_input_project_mismatch")
        scopes.append(source)
    if job.result is not None and digest(job.result) != job.result_sha256:
        raise JobConflict("job_result_changed")
    return scopes


def scoring_receipt(actor, identifier, expected):
    expected = require_digest(expected)
    with locked():
        job = NativeJob.objects.get(pk=identifier)
        scopes = read_authority(actor, job)
        if (job.state != "succeeded" or _saved_kind(job) not in (csv_scoring.KIND, training_scoring.KIND)
                or job.result_sha256 != expected or not isinstance(job.result, dict)
                or not isinstance(job.result.get("scores"), list)):
            raise JobConflict("job_scoring_result_unavailable")
        raw = csv_scoring.canonical_bytes(job.result)
        for current in scopes:
            projects.recheck(current)
        return raw


def read(actor, identifier):
    with locked():
        job = NativeJob.objects.get(pk=identifier)
        return authorized_receipt(job, read_authority(actor, job))


def cancel(actor, identifier, data):
    if data != {"action": "cancel"}:
        raise ValueError("Supply exactly action: cancel.")
    with locked():
        job = NativeJob.objects.select_for_update().get(pk=identifier)
        current = lock_authority(actor, job.dataset_id, None)
        saved_actor = job.authority.get("actor_id") if isinstance(job.authority, dict) else None
        if type(saved_actor) is not int or saved_actor <= 0 or actor.pk != saved_actor or current["role"] not in {"developer", "reviewer"}:
            raise projects.ProjectDenied("job_cancel_submitter_required")
        if job.state not in TERMINAL and job.state != "cancel_requested":
            job.state = "cancel_requested" if job.state == "running" else "cancelled"
            job.reason_code = "actor_cancelled"
            if job.state == "cancelled":
                job.finished_at = timezone.now()
            record(job, job.state, actor=actor, update_fields=["state", "reason_code", "finished_at", "revision"])
        return authorized_receipt(job, read_authority(actor, job))


def close(job, state, reason, *, metadata_only=False):
    job.state, job.reason_code, job.finished_at = state, reason, timezone.now()
    job.lease_token = job.lease_until = None
    fields = ["state", "reason_code", "finished_at", "lease_token", "lease_until", "revision"] if metadata_only else None
    record(job, state, detail={"reason_code": reason}, update_fields=fields)


def claim(identifier):
    with locked():
        job = NativeJob.objects.select_for_update().get(pk=identifier)
        if job.state != "queued" or NativeJob.objects.filter(state__in=ACTIVE).count() >= LIMITS["max_active"]:
            return None
        if timezone.now() >= job.expires_at:
            close(job, "failed", "job_expired", metadata_only=True)
            return None
        # A restored/inconsistent queued row must not bypass the retry ceiling
        # just because delivery arrives without an expired-lease reconciliation.
        if job.attempts >= LIMITS["attempts"]:
            close(job, "failed", "job_attempts_exhausted", metadata_only=True)
            return None
        # Malformed restored metadata must not remain a poison queued request
        # that raises before claiming a lease on every duplicate delivery.
        if not isinstance(job.specification, dict) or not isinstance(job.specification.get("kind"), str):
            close(job, "blocked", "job_specification_invalid", metadata_only=True)
            return None
        try:
            recheck_execution(job)
        except (projects.ProjectDenied, ObjectDoesNotExist):
            close(job, "blocked", "job_authority_changed", metadata_only=True)
            return None
        except JobConflict as exc:
            close(job, "blocked", exc.code, metadata_only=True)
            return None
        if (
            job.specification.get("kind") not in {KIND, csv_scoring.KIND, training_search.KIND, training_scoring.KIND, native_assessment.KIND}
            or job.specification.get("runtime") != runtime(job.specification.get("kind"))
            or job.specification.get("limits") != limits(job.specification.get("kind"))
        ):
            close(job, "blocked", "job_runtime_changed", metadata_only=True)
            return None
        now = timezone.now()
        if now >= job.expires_at:
            close(job, "failed", "job_expired", metadata_only=True)
            return None
        job.state, job.lease_token = "running", uuid.uuid4()
        job.lease_until = now + timedelta(seconds=LIMITS["lease_seconds"])
        job.attempts += 1
        record(job, "started", detail={"attempt": job.attempts})
        return job, job.lease_token


def _checkpoint_guards(job, token, deadline):
    if (job.state != "running" or token is None or job.lease_token != token
            or job.lease_until is None or timezone.now() >= job.lease_until):
        raise JobStopped
    if timezone.now() >= job.expires_at:
        raise JobConflict("job_expired")
    if time.monotonic() >= deadline:
        raise JobConflict("job_time_budget_exceeded")


def _checkpoint_row(identifier, fields):
    # Keep model conversion/fault boundaries while avoiding compilation of the
    # same projection on every numerical-work checkpoint. All values stay bound.
    from django.db import connections

    alias = NativeJob.objects.db
    db = connections[alias]
    meta, quote = NativeJob._meta, db.ops.quote_name
    columns = ", ".join(quote(meta.get_field(name).column) for name in fields)
    sql = f"SELECT {columns} FROM {quote(meta.db_table)} WHERE {quote(meta.pk.column)} = %s LIMIT 21"
    # Use the same backend/field conversion order and model materialization as
    # Django's raw reader, without constructing a RawQuerySet for each fence.
    selected = [meta.get_field(name) for name in fields]
    with db.cursor() as cursor:
        cursor.execute(sql, [meta.pk.get_db_prep_value(identifier, db)])
        values = cursor.fetchall()
    if meta.pk.attname not in {field.attname for field in selected}:
        from django.core.exceptions import FieldDoesNotExist
        raise FieldDoesNotExist("Raw query must include the primary key")
    converted = []
    for row in values:
        if len(row) != len(selected):
            from django.db import DatabaseError
            raise DatabaseError("Checkpoint projection shape changed")
        data = {}
        for field, value in zip(selected, row):
            expression = field.get_col(meta.db_table)
            for convert in db.ops.get_db_converters(expression) + expression.get_db_converters(db):
                value = convert(value, expression, db)
            data[field.attname] = value
        names = [field.attname for field in meta.concrete_fields if field.attname in data]
        converted.append(NativeJob.from_db(alias, names, [data[name] for name in names]))
    rows = converted
    if not rows:
        raise NativeJob.DoesNotExist("NativeJob matching query does not exist.")
    if len(rows) != 1:
        raise NativeJob.MultipleObjectsReturned("Checkpoint identifier is not unique.")
    return rows[0]


def checkpoint(identifier, token, deadline):
    # Checkpoints need guards and execution authority, never stored outputs or
    # publication history. Keep referenced training-result validation explicit
    # in recheck_execution rather than loading this job's unrelated payloads.
    job = _checkpoint_row(identifier, (
        "id", "state", "lease_token", "lease_until", "expires_at", "authority",
        "specification", "project", "dataset", "source_dataset",
    ))
    _checkpoint_guards(job, token, deadline)
    recheck_execution(job)
    # Authority reads can outlast a lease or work deadline, or overlap a
    # cancellation/requeue. Refresh only the guards before returning to work.
    current = _checkpoint_row(identifier, ("id", "state", "lease_token", "lease_until", "expires_at"))
    _checkpoint_guards(current, token, deadline)


def _owns_live_lease(job, token, now):
    # Missing metadata is not proof of ownership; leave it for operator review.
    return (token is not None and job.lease_token == token and job.state in ACTIVE
            and job.lease_until is not None and now < job.lease_until)


def finish(identifier, token, state, reason="", result=None, *, deadline=None):
    with locked():
        job = NativeJob.objects.select_for_update().get(pk=identifier)
        now = timezone.now()
        if not _owns_live_lease(job, token, now):
            return
        if job.state == "cancel_requested":
            close(job, "cancelled", "actor_cancelled", metadata_only=True)
            return
        if now >= job.expires_at:
            close(job, "failed", "job_expired", metadata_only=True)
            return
        if state == "succeeded" and deadline is not None and time.monotonic() >= deadline:
            close(job, "blocked", "job_time_budget_exceeded", metadata_only=True)
            return
        try:
            # Same project/binding/member locks as authoritative membership edits.
            from django.contrib.auth import get_user_model

            execution_specification(job)
            execution_scope_bindings(job)
            actor = get_user_model().objects.get(pk=job.authority["actor_id"])
            lock_authority(actor, job.dataset_id, None)
            if job.source_dataset_id is not None:
                lock_authority(actor, job.source_dataset_id, None)
            recheck_execution(job)
        except (projects.ProjectDenied, ObjectDoesNotExist):
            if _owns_live_lease(job, token, timezone.now()):
                close(job, "blocked", "job_authority_changed", metadata_only=True)
            return
        except JobConflict as exc:
            if _owns_live_lease(job, token, timezone.now()):
                close(job, "blocked", exc.code, metadata_only=True)
            return
        prepared_result = result if state == "succeeded" else None
        prepared_digest = digest(prepared_result) if prepared_result else ""
        # Authority locks and result preparation can outlast the first check.
        # Fence again, including the work deadline, before adopting a result.
        now = timezone.now()
        if not _owns_live_lease(job, token, now):
            return
        if now >= job.expires_at:
            close(job, "failed", "job_expired", metadata_only=True)
            return
        if state == "succeeded" and deadline is not None and time.monotonic() >= deadline:
            close(job, "blocked", "job_time_budget_exceeded", metadata_only=True)
            return
        job.result, job.result_sha256 = prepared_result, prepared_digest
        close(job, state, reason)


def execute(identifier):
    selected = claim(identifier)
    if not selected:
        return
    job, token = selected
    spec, total = job.specification, 0
    deadline = time.monotonic() + LIMITS["seconds"]

    def check():
        checkpoint(identifier, token, deadline)

    def metadata(path):
        check()
        raw = _package_metadata(path)
        if Path(path).name == "manifest.json" and hashlib.sha256(raw).hexdigest() != spec["manifest_sha256"]:
            raise JobConflict("job_manifest_changed")
        return raw

    def hashed(path):
        nonlocal total
        check()
        sha = hashlib.sha256()
        with _regular_artifact(path) as stream:
            while chunk := stream.read(1024**2):
                total += len(chunk)
                if total > LIMITS["max_bytes"]:
                    raise JobConflict("job_package_budget_exceeded")
                check()
                sha.update(chunk)
        return sha.hexdigest()

    try:
        check()
        if spec["kind"] == training_search.KIND:
            result = training_search.train(job, check)
            finish(identifier, token, "succeeded", result=result, deadline=deadline)
            return
        if spec["kind"] == native_assessment.KIND:
            result = native_assessment.assess(job, check)
            finish(identifier, token, "succeeded", result=result, deadline=deadline)
            return
        if spec["kind"] == training_scoring.KIND:
            result = training_scoring.score(job, check)
            finish(identifier, token, "succeeded", result=result, deadline=deadline)
            return
        manifest, identity = header(job.dataset_id, spec["bundle_id"], spec["manifest_sha256"])
        if any(spec[k] != v for k, v in identity.items()):
            raise JobConflict("job_package_identity_changed")
        out = Path(bundle_dir(job.dataset_id, spec["bundle_id"]))
        for name in ["evaluation.json", "model_card.json"]:
            raw = _artifact_bytes(out / name, 8 * 1024**2, "job_evidence_budget_exceeded")
            projects.assert_evidence_scope(parse_metadata(raw.decode("utf-8")), job.dataset_id)
        check()
        if spec["kind"] == csv_scoring.KIND:
            result = csv_scoring.score(job, manifest, out, hashed, check, metadata_bytes=metadata)
            finish(identifier, token, "succeeded", result=result, deadline=deadline)
            return
        manifest, sha = verify_bundle(
            out, job.dataset_id, spec["bundle_id"], artifact_digest=hashed, metadata_bytes=metadata
        )
        if sha != spec["manifest_sha256"]:
            raise JobConflict("job_manifest_changed")
        result = {
            "schema_version": 1,
            "scope": KIND,
            **identity,
            "manifest_sha256": sha,
            "artifact_count": len(manifest["artifact_integrity"]),
            "verified_bytes": total,
            "runtime": spec["runtime"],
            "model_state_loaded": False,
            "score_parity_verified": False,
            "refit_verified": False,
            "review_approved": False,
            "production_use_approved": False,
        }
        finish(identifier, token, "succeeded", result=result, deadline=deadline)
    except JobStopped:
        finish(identifier, token, "cancelled", "job_stopped")
    except projects.ProjectDenied:
        finish(identifier, token, "blocked", "job_authority_changed")
    except JobConflict as exc:
        finish(identifier, token, "blocked", exc.code)
    except (ValueError, OSError, TypeError, KeyError):
        finish(identifier, token, "blocked", "job_assessment_or_budget_invalid" if spec["kind"] == native_assessment.KIND else "job_training_or_budget_invalid" if spec["kind"] == training_search.KIND else "job_package_or_budget_invalid")
    # Unexpected/storage failures leave a leased attempt for reconciliation;
    # do not turn uncertain publication into a successful or retryable receipt.


def reconcile():
    with locked():
        now = timezone.now()
        # Recovery needs transition metadata only. Deferred saves in record()
        # retain opaque inputs/results without fetching or rewriting them.
        jobs = NativeJob.objects.only(
            "id", "state", "revision", "attempts", "lease_token", "lease_until",
            "next_dispatch", "expires_at", "reason_code", "finished_at",
        )
        for job in jobs.select_for_update().filter(state__in=ACTIVE, lease_until__lte=now):
            if job.state == "cancel_requested":
                close(job, "cancelled", "actor_cancelled_after_lease")
            elif job.attempts >= LIMITS["attempts"] or job.expires_at <= now:
                close(job, "failed", "job_attempts_exhausted")
            else:
                job.state, job.lease_token, job.lease_until, job.next_dispatch = "queued", None, None, now
                record(job, "requeued", detail={"reason_code": "worker_lease_expired"})
        for job in jobs.select_for_update().filter(state="queued", expires_at__lte=now):
            close(job, "failed", "job_expired")
        return list(
            NativeJob.objects.filter(state="queued", next_dispatch__lte=now)
            .order_by("created_at", "pk")
            .values_list("pk", flat=True)[:100]
        )


def dispatch_once(*, should_stop=None):
    def stopped():
        return should_stop is not None and should_stop()

    if stopped():
        return {"delivered": 0, "broker_unavailable": 0}
    if not settings.DECLARAI_JOBS_ENABLED:
        raise JobConflict("job_service_disabled")
    from execution_jobs.tasks import run_native_job

    delivered, unavailable = 0, 0
    for identifier in reconcile():
        if stopped():
            break
        try:
            # Commit exists before publish. Duplicate delivery is intentional and
            # harmless; the metadata lease, not Celery task ID, controls execution.
            run_native_job.apply_async(args=[str(identifier)], retry=False)
        except Exception:
            unavailable += 1
            break  # Never surface connection strings in API, receipts or logs.
        with locked():
            NativeJob.objects.filter(pk=identifier, state="queued").update(
                next_dispatch=timezone.now() + timedelta(seconds=30)
            )
        delivered += 1
    return {"delivered": delivered, "broker_unavailable": unavailable}
