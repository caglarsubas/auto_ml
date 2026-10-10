"""One bounded read-only job kind. DB leases fence every result publication."""

import hashlib
import json
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from access_control import projects
from access_control.authority import actor_snapshot
from deployment.deploy_utils import bundle_dir
from deployment.evidence import verify_bundle
from deployment.reviews import digest, lock_authority
from deployment.scoring_receipts import require_digest
from execution_jobs.models import QueueLock, NativeJob, JobEvent
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


class JobConflict(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class JobStopped(Exception):
    pass


def runtime():
    sources = [
        "execution_jobs/service.py",
        "execution_jobs/models.py",
        "execution_jobs/tasks.py",
        "execution_jobs/config.py",
        "backend/celery.py",
        "deployment/evidence.py",
        "deployment/deploy_utils.py",
        "access_control/projects.py",
    ]
    return {
        "python": sys.version.split()[0],
        "packages": {p: version(p) for p in ["Django", "celery", "kombu", "redis"]},
        "sources": {p: hashlib.sha256((Path(settings.BASE_DIR) / p).read_bytes()).hexdigest() for p in sources},
    }


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
            QueueLock.objects.get_or_create(pk=1)
            QueueLock.objects.select_for_update().get(pk=1)
            yield


def record(job, kind, *, actor=None, detail=None):
    job.revision += 1
    JobEvent.objects.create(
        job=job,
        revision=job.revision,
        event_type=kind,
        actor_snapshot=actor_snapshot(actor) if actor else {},
        detail=detail or {},
    )
    job.save()


def scope(actor, file_id):
    if not projects.governed():
        raise projects.ProjectDenied("job_requires_project_governance")
    return projects.dataset_authority(actor.pk, file_id, "read")


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
        raw = path.read_bytes()
        if len(raw) > bound:
            raise JobConflict("job_package_budget_exceeded")
        values[name] = json.loads(raw)
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
    if (
        not isinstance(data, dict)
        or set(data) != {"request_id", "kind", "bundle_id", "manifest_sha256"}
        or data["kind"] != KIND
    ):
        raise ValueError("Supply exactly request_id, package_integrity_v1, bundle_id and manifest_sha256.")
    identifier, bundle_id = uuid.UUID(str(data["request_id"])), uuid.UUID(str(data["bundle_id"]))
    sha = require_digest(data["manifest_sha256"])
    current = scope(actor, file_id)
    if current["role"] not in {"developer", "reviewer"}:
        raise projects.ProjectDenied("job_submit_role_required")
    request_sha = digest({"actor_id": actor.pk, "file_id": file_id, "request": data})
    with locked():
        current = lock_authority(actor, file_id, None)
        if current["role"] not in {"developer", "reviewer"}:
            raise projects.ProjectDenied("job_submit_role_required")
        previous = NativeJob.objects.filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != request_sha:
                raise JobConflict("job_request_reused")
            return serialize(previous, replayed=True)
        if NativeJob.objects.filter(state__in=ACTIVE | {"queued"}).count() >= LIMITS["max_pending"]:
            raise JobConflict("job_queue_full")
        _, identity = header(file_id, bundle_id, sha)
        specification = {
            "schema_version": 1,
            "kind": KIND,
            **identity,
            "manifest_sha256": sha,
            "runtime": runtime(),
            "limits": LIMITS,
        }
        job = NativeJob.objects.create(
            id=identifier,
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
        return serialize(job)


def serialize(job, *, replayed=False):
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
        "result": job.result,
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


def read(actor, identifier):
    with locked():
        job = NativeJob.objects.get(pk=identifier)
        current = scope(actor, job.dataset_id)
        if str(job.project_id) != current["project_id"]:
            raise projects.ProjectDenied("job_project_mismatch")
        result = serialize(job)
        projects.recheck(current)
        return result


def cancel(actor, identifier, data):
    if data != {"action": "cancel"}:
        raise ValueError("Supply exactly action: cancel.")
    with locked():
        job = NativeJob.objects.select_for_update().get(pk=identifier)
        current = lock_authority(actor, job.dataset_id, None)
        if actor.pk != job.authority["actor_id"] or current["role"] not in {"developer", "reviewer"}:
            raise projects.ProjectDenied("job_cancel_submitter_required")
        if job.state not in TERMINAL and job.state != "cancel_requested":
            job.state = "cancel_requested" if job.state == "running" else "cancelled"
            job.reason_code = "actor_cancelled"
            if job.state == "cancelled":
                job.finished_at = timezone.now()
            record(job, job.state, actor=actor)
        projects.recheck(current)
        return serialize(job)


def close(job, state, reason):
    job.state, job.reason_code, job.finished_at = state, reason, timezone.now()
    job.lease_token = job.lease_until = None
    record(job, state, detail={"reason_code": reason})


def claim(identifier):
    with locked():
        job = NativeJob.objects.select_for_update().get(pk=identifier)
        if job.state != "queued" or NativeJob.objects.filter(state__in=ACTIVE).count() >= LIMITS["max_active"]:
            return None
        if timezone.now() >= job.expires_at:
            close(job, "failed", "job_expired")
            return None
        try:
            projects.recheck(job.authority)
        except (projects.ProjectDenied, ObjectDoesNotExist):
            close(job, "blocked", "job_authority_changed")
            return None
        if (
            job.specification.get("runtime") != runtime()
            or job.specification.get("kind") != KIND
            or job.specification.get("limits") != LIMITS
        ):
            close(job, "blocked", "job_runtime_changed")
            return None
        job.state, job.lease_token = "running", uuid.uuid4()
        job.lease_until = timezone.now() + timedelta(seconds=LIMITS["lease_seconds"])
        job.attempts += 1
        record(job, "started", detail={"attempt": job.attempts})
        return job, job.lease_token


def checkpoint(identifier, token, deadline):
    job = NativeJob.objects.get(pk=identifier)
    if job.state != "running" or job.lease_token != token or timezone.now() >= job.lease_until:
        raise JobStopped
    if timezone.now() >= job.expires_at:
        raise JobConflict("job_expired")
    if time.monotonic() >= deadline:
        raise JobConflict("job_time_budget_exceeded")
    projects.recheck(job.authority)


def finish(identifier, token, state, reason="", result=None):
    with locked():
        job = NativeJob.objects.select_for_update().get(pk=identifier)
        if job.lease_token != token or job.state not in ACTIVE or timezone.now() >= job.lease_until:
            return
        if job.state == "cancel_requested":
            close(job, "cancelled", "actor_cancelled")
            return
        if timezone.now() >= job.expires_at:
            close(job, "failed", "job_expired")
            return
        try:
            # Same project/binding/member locks as authoritative membership edits.
            from django.contrib.auth import get_user_model

            lock_authority(get_user_model().objects.get(pk=job.authority["actor_id"]), job.dataset_id, None)
            projects.recheck(job.authority)
        except (projects.ProjectDenied, ObjectDoesNotExist):
            close(job, "blocked", "job_authority_changed")
            return
        job.result = result if state == "succeeded" else None
        job.result_sha256 = digest(result) if job.result else ""
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

    def hashed(path):
        nonlocal total
        check()
        sha = hashlib.sha256()
        with Path(path).open("rb") as stream:
            while chunk := stream.read(1024**2):
                total += len(chunk)
                if total > LIMITS["max_bytes"]:
                    raise JobConflict("job_package_budget_exceeded")
                check()
                sha.update(chunk)
        return sha.hexdigest()

    try:
        check()
        _, identity = header(job.dataset_id, spec["bundle_id"], spec["manifest_sha256"])
        if any(spec[k] != v for k, v in identity.items()):
            raise JobConflict("job_package_identity_changed")
        out = Path(bundle_dir(job.dataset_id, spec["bundle_id"]))
        manifest, sha = verify_bundle(out, job.dataset_id, spec["bundle_id"], artifact_digest=hashed)
        if sha != spec["manifest_sha256"]:
            raise JobConflict("job_manifest_changed")
        for name in ["evaluation.json", "model_card.json"]:
            if (out / name).stat().st_size > 8 * 1024**2:
                raise JobConflict("job_evidence_budget_exceeded")
            projects.assert_evidence_scope(json.loads((out / name).read_text()), job.dataset_id)
        check()
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
        finish(identifier, token, "succeeded", result=result)
    except JobStopped:
        finish(identifier, token, "cancelled", "job_stopped")
    except projects.ProjectDenied:
        finish(identifier, token, "blocked", "job_authority_changed")
    except JobConflict as exc:
        finish(identifier, token, "blocked", exc.code)
    except (ValueError, OSError, TypeError, KeyError):
        finish(identifier, token, "blocked", "job_package_or_budget_invalid")
    # Unexpected/storage failures leave a leased attempt for reconciliation;
    # do not turn uncertain publication into a successful or retryable receipt.


def reconcile():
    now = timezone.now()
    with locked():
        for job in NativeJob.objects.select_for_update().filter(state__in=ACTIVE, lease_until__lte=now):
            if job.state == "cancel_requested":
                close(job, "cancelled", "actor_cancelled_after_lease")
            elif job.attempts >= LIMITS["attempts"] or job.expires_at <= now:
                close(job, "failed", "job_attempts_exhausted")
            else:
                job.state, job.lease_token, job.lease_until, job.next_dispatch = "queued", None, None, now
                record(job, "requeued", detail={"reason_code": "worker_lease_expired"})
        for job in NativeJob.objects.select_for_update().filter(state="queued", expires_at__lte=now):
            close(job, "failed", "job_expired")
        return list(
            NativeJob.objects.filter(state="queued", next_dispatch__lte=now)
            .order_by("created_at")
            .values_list("pk", flat=True)[:100]
        )


def dispatch_once():
    if not settings.DECLARAI_JOBS_ENABLED:
        raise JobConflict("job_service_disabled")
    from execution_jobs.tasks import run_native_job

    delivered, unavailable = 0, 0
    for identifier in reconcile():
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
