"""Review and recover a single unused, platform-created upload purge."""

import hashlib
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q

from access_control.data_policy import canonical, policy_digest, private
from access_control.models import (
    AssistantActionApproval, MCPAccessEvent, MCPDatasetGrant, ProjectArtifact,
    ProjectAuthorityEvent, ProjectDataset,
)
from declaration.models import DataDictionary, Declaration
from deployment.models import PackageReview
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess, PipelineRun

UPLOAD = re.compile(r"data_files/(merged_data_[0-9a-f]{32}\.csv)")
MAX_BYTES = 64 * 1024**2


class RetentionError(ValueError):
    pass


def require_maintenance():
    if not private() or connection.vendor != "postgresql" or connection.in_atomic_block:
        raise RetentionError("private_postgresql_maintenance_required")
    # Require exclusive application custody as well as this observed DB check.
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM pg_catalog.pg_stat_activity
                WHERE datname = pg_catalog.current_database()
                  AND pid <> pg_catalog.pg_backend_pid()
            )
        """)
        if cursor.fetchone()[0]:
            raise RetentionError("stop_installation_services_before_retention")


def _identity(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_mode, info.st_nlink]


@contextmanager
def _upload_directory():
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root = os.open(Path(settings.MEDIA_ROOT), flags)
    try:
        directory = os.open("data_files", flags, dir_fd=root)
        try:
            yield directory
        finally:
            os.close(directory)
    finally:
        os.close(root)


def _read_upload(directory, name):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= MAX_BYTES:
            raise RetentionError("upload_storage_not_eligible")
        digest = hashlib.sha256()
        remaining = info.st_size
        while remaining and (chunk := stream.read(min(remaining, 1024**2))):
            digest.update(chunk)
            remaining -= len(chunk)
        identity = _identity(info)
        if remaining or _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != identity:
            raise RetentionError("upload_changed")
        return {"identity": identity, "sha256": digest.hexdigest()}


def _referenced(file_id, relative):
    paths = [relative, str(Path(settings.MEDIA_ROOT) / relative)]
    return (
        Declaration.objects.filter(file__in=paths).exclude(pk=file_id).exists()
        or ProjectArtifact.objects.filter(Q(relative_path__in=paths) | Q(dataset_id=file_id)).exists()
        or NativeJob.objects.filter(Q(dataset_id=file_id) | Q(source_dataset_id=file_id)).exists()
        or PipelineRun.objects.filter(Q(file_id=file_id) | Q(state__file_id=file_id) | Q(state__fileId=file_id)
                                      | Q(state__file_id=str(file_id)) | Q(state__fileId=str(file_id))).exists()
        or PackageReview.objects.filter(dataset_id=file_id).exists()
        or HoldoutAccess.objects.filter(file_id=file_id).exists()
        or DataDictionary.objects.filter(data_file_id=file_id).exists()
        or MCPDatasetGrant.objects.filter(dataset_id=file_id).exists()
        or MCPAccessEvent.objects.filter(file_id=file_id).exists()
        or AssistantActionApproval.objects.filter(file_id=file_id).exists()
    )


def _candidate(file_id, *, lock=False):
    bindings = ProjectDataset.objects.select_related("dataset")
    if lock:
        bindings = bindings.select_for_update()
    binding = bindings.filter(dataset_id=file_id).first()
    if binding is None:
        raise RetentionError("unclassified_upload_retained")
    dataset = binding.dataset
    relative = dataset.file.name
    match = UPLOAD.fullmatch(relative)
    if not match or dataset.name != match[1] or dataset.original_name != match[1]:
        raise RetentionError("unclassified_upload_retained")
    registered = {"file_id": file_id, "relative_path": relative, "binding_revision": str(binding.revision)}
    events = ProjectAuthorityEvent.objects.filter(project_id=binding.project_id)
    if not events.filter(operation="upload_registered", authority_source="native_declaration",
                         resource=registered).exists():
        raise RetentionError("unclassified_upload_retained")
    if (_referenced(file_id, relative) or events.exclude(operation__in=["dataset_assigned", "upload_registered"])
            .filter(resource__file_id=file_id).exists()):
        raise RetentionError("dataset_use_or_evidence_retained")
    # Scope-based admissions are reserved before opening bytes. A single scope
    # and a list of scopes are both used by the native authority entrypoints.
    admitted = events.exclude(operation__in=["dataset_assigned", "upload_registered"])
    if admitted.filter(resource__scope__file_id=file_id).exists():
        raise RetentionError("dataset_use_or_evidence_retained")
    for scopes in admitted.filter(resource__has_key="scopes").values_list("resource__scopes", flat=True).iterator():
        if any(scope.get("file_id") == file_id for scope in scopes):
            raise RetentionError("dataset_use_or_evidence_retained")
    with _upload_directory() as directory:
        storage = _read_upload(directory, match[1])
    return {**registered, "project_id": str(binding.project_id), "policy_sha256": policy_digest(), **storage}


def _digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def review(file_id):
    require_maintenance()
    candidate = _candidate(file_id)
    return {"file_id": file_id, "project_id": candidate["project_id"], "policy_sha256": policy_digest(),
            "bytes": candidate["identity"][2], "expected": _digest(candidate)}


def purge(file_id, expected, request_id, label):
    require_maintenance()
    request = _digest({"file_id": file_id, "expected": expected, "label": label, "policy_sha256": policy_digest()})
    with transaction.atomic():
        event = ProjectAuthorityEvent.objects.select_for_update().filter(pk=request_id).first()
        if event is None:
            candidate = _candidate(file_id, lock=True)
            if _digest(candidate) != expected:
                raise RetentionError("retention_review_changed")
            event = ProjectAuthorityEvent.objects.create(
                id=request_id, project_id=candidate["project_id"], authority_source="installation_operator",
                operator_label=label, operation="retention_purge", outcome="pending_files",
                resource=candidate, request_sha256=request,
            )
            Declaration.objects.get(pk=file_id).delete()
        elif (event.operation != "retention_purge" or event.authority_source != "installation_operator"
              or event.request_sha256 != request or _digest(event.resource) != expected):
            raise RetentionError("retention_request_conflict")

    # The metadata removal and pending intent are durable before unlink. A
    # crash before the terminal receipt can resume only this exact intent.
    require_maintenance()
    with transaction.atomic():
        event.refresh_from_db(from_queryset=ProjectAuthorityEvent.objects.select_for_update())
        if event.outcome == "pending_files":
            relative = event.resource["relative_path"]
            if Declaration.objects.filter(pk=file_id).exists() or _referenced(file_id, relative):
                raise RetentionError("dataset_use_or_evidence_retained")
            match = UPLOAD.fullmatch(relative)
            if not match:
                raise RetentionError("upload_storage_not_eligible")
            with _upload_directory() as directory:
                try:
                    storage = _read_upload(directory, match[1])
                except FileNotFoundError:
                    event.reason_code = "upload_absence_reconciled"
                else:
                    if any(storage[key] != event.resource[key] for key in storage):
                        raise RetentionError("upload_changed")
                    os.unlink(match[1], dir_fd=directory)
                    event.reason_code = "upload_removed"
                os.fsync(directory)
            event.outcome = "completed"
            event.save(update_fields=["outcome", "reason_code"])
        return {"event_id": str(event.pk), "file_id": file_id, "outcome": event.outcome,
                "reason_code": event.reason_code, "policy_sha256": policy_digest()}
