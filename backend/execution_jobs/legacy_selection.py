"""Select an exact immutable native result for development; never approve use."""

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from django.conf import settings

from access_control import projects
from deployment.reviews import digest, lock_authority
from deployment.scoring_receipts import require_digest
from execution_jobs import legacy_execution as legacy, service
from execution_jobs.models import NativeJob
from modeling.execution_artifacts import projection_lock, replace_projection


def bound_job(actor, identifier, expected=None):
    job = NativeJob.objects.get(pk=identifier)
    scopes = service.read_authority(actor, job)
    if (
        job.state != "succeeded"
        or job.specification.get("kind") != legacy.KIND
        or not isinstance(job.result, dict)
        or digest(job.result) != job.result_sha256
        or digest(job.result.get("files")) != job.result.get("files_sha256")
        or expected is not None
        and job.result_sha256 != expected
    ):
        legacy.conflict("selection_candidate_changed")
    return job, scopes


def member(job, name):
    entry = job.result["files"].get(legacy.relative(name))
    if not isinstance(entry, dict):
        legacy.conflict("selection_artifact_missing")
    raw = legacy.read(legacy.output_root(job) / name, legacy.BUDGET["max_output_bytes"])
    if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        legacy.conflict("selection_artifact_changed")
    return raw


def candidate(job, execution):
    execution = str(uuid.UUID(str(execution)))
    prefix = f"execution_runs/{execution}/"
    payload = json.loads(member(job, prefix + "modeling_status.json"))
    if payload.get("file_id") != job.dataset_id or payload.get("execution_id") != execution:
        legacy.conflict("selection_execution_changed")
    return payload, prefix


def current(file_id):
    path = Path(settings.MEDIA_ROOT) / "modeling" / f"{file_id}_status.json"
    if not os.path.lexists(path):
        return None, None
    raw = legacy.read(path, legacy.BUDGET["max_result_bytes"])
    return hashlib.sha256(raw).hexdigest(), json.loads(raw)


def preview(actor, identifier):
    with service.locked():
        job, scopes = bound_job(actor, identifier)
        choices = []
        for name in job.result["files"]:
            if name.startswith("execution_runs/") and name.endswith("/modeling_status.json"):
                payload, _ = candidate(job, name.split("/")[1])
                m = payload.get("model", {})
                choices.append(
                    {
                        "execution_id": payload["execution_id"],
                        "algorithm": payload.get("algorithm"),
                        "task": m.get("task"),
                        "features": m.get("feature_count"),
                        "model_adopted": False,
                    }
                )
        pin, _ = current(job.dataset_id)
        for scope in scopes:
            projects.recheck(scope)
        return {
            "job_id": str(job.pk),
            "file_id": job.dataset_id,
            "result_sha256": job.result_sha256,
            "candidates": choices,
            "expected_projection_sha256": pin,
            "purpose": "development_selection_only",
            "review_approved": False,
            "production_use_approved": False,
        }


def select(actor, identifier, data):
    if not isinstance(data, dict) or set(data) != {
        "request_id",
        "result_sha256",
        "execution_id",
        "expected_projection_sha256",
    }:
        raise ValueError("Bind the exact candidate and previous development selection.")
    request_id = str(uuid.UUID(str(data["request_id"])))
    pin = require_digest(data["result_sha256"])
    execution = str(uuid.UUID(str(data["execution_id"])))
    expected = data["expected_projection_sha256"]
    if expected is not None:
        require_digest(expected)
    request_sha = digest({"actor_id": actor.pk, "job_id": str(identifier), "request": data})
    routing = NativeJob.objects.only("dataset_id").get(pk=identifier)
    with projection_lock(routing.dataset_id):
        with service.locked():
            job, scopes = bound_job(actor, identifier, pin)
            authority = lock_authority(actor, job.dataset_id, None)
            if authority["role"] != "developer":
                raise projects.ProjectDenied("job_submit_role_required")
            previous = [
                e
                for e in job.events.filter(event_type__in=["legacy_selection_requested", "legacy_selection_completed"])
                if e.detail.get("request_id") == request_id
            ]
            if any(e.detail.get("request_sha256") != request_sha for e in previous):
                legacy.conflict("selection_request_reused")
            completed = next((e for e in previous if e.event_type == "legacy_selection_completed"), None)
            if completed:
                for scope in scopes:
                    projects.recheck(scope)
                return {
                    **completed.detail["receipt"],
                    "replayed": True,
                    "currently_selected": (current(job.dataset_id)[1] or {})
                    .get("native_job_selection", {})
                    .get("request_id")
                    == request_id,
                }
            payload, prefix = candidate(job, execution)
            stamp = {"job_id": str(job.pk), "result_sha256": pin, "request_id": request_id, "execution_id": execution}
            actual, existing = current(job.dataset_id)
            if actual != expected and (existing or {}).get("native_job_selection") != stamp:
                legacy.conflict("selection_base_changed")
            if not previous:
                service.record(
                    job,
                    "legacy_selection_requested",
                    actor=actor,
                    detail={
                        "request_id": request_id,
                        "request_sha256": request_sha,
                        "execution_id": execution,
                        "expected_projection_sha256": expected,
                    },
                    update_fields=["revision"],
                )
        # The committed intent survives a lost publication acknowledgement. All
        # following state remains under live authority and the projection fence.
        with service.locked():
            job, scopes = bound_job(actor, identifier, pin)
            authority = lock_authority(actor, job.dataset_id, None)
            if authority["role"] != "developer":
                raise projects.ProjectDenied("job_submit_role_required")
            actual, existing = current(job.dataset_id)
            already = (existing or {}).get("native_job_selection") == stamp
            if actual != expected and not already:
                legacy.conflict("selection_base_changed")
            destination = Path(settings.MEDIA_ROOT) / prefix
            entries = {name: entry for name, entry in job.result["files"].items() if name.startswith(prefix)}
            if not entries:
                legacy.conflict("selection_artifact_missing")
            if destination.is_symlink() or destination.parent.is_symlink():
                legacy.conflict("selection_target_invalid")
            if destination.exists():
                actual_files = {str(p.relative_to(settings.MEDIA_ROOT)) for p in destination.rglob("*") if p.is_file()}
                if actual_files != set(entries):
                    legacy.conflict("selection_target_occupied")
                for name, entry in entries.items():
                    raw = legacy.read(Path(settings.MEDIA_ROOT) / name)
                    if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                        legacy.conflict("selection_target_occupied")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                staged = destination.with_name("." + destination.name + "-" + uuid.uuid4().hex)
                staged.mkdir()
                try:
                    for name in entries:
                        raw = member(job, name)
                        path = staged / name[len(prefix) :]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(raw)
                        path.chmod(0o400)
                    staged.rename(destination)
                finally:
                    if staged.exists():
                        shutil.rmtree(staged)
            model = payload["model"]
            root = Path(settings.MEDIA_ROOT)
            for key in ("train_data_path", "lineage_path"):
                name = legacy.relative(model[key])
                if name not in entries:
                    legacy.conflict("selection_artifact_missing")
            encoded = payload.get("encoded_file")
            if encoded and encoded not in entries:
                member(job, encoded)
                payload["encoded_file"] = str((legacy.output_root(job) / encoded).relative_to(root))
                projects.register_artifact(root / payload["encoded_file"], file_id=job.dataset_id)
            payload.update(
                native_job_selection=stamp,
                selected_for_development=True,
                review_approved=False,
                production_use_approved=False,
            )
            if already and digest(existing) != digest(payload):
                legacy.conflict("selection_pointer_changed")
            if not already:
                replace_projection(
                    root / model["train_data_path"], root / "train_data" / f"{job.dataset_id}_train_data.pkl"
                )
                replace_projection(root / model["lineage_path"], root / "lineage" / f"{job.dataset_id}_lineage.json")
                status_path = root / "modeling" / f"{job.dataset_id}_status.json"
                status_path.parent.mkdir(parents=True, exist_ok=True)
                stage = status_path.with_name(status_path.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    stage.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")))
                    for scope in scopes:
                        projects.recheck(scope)
                    os.replace(stage, status_path)
                finally:
                    stage.unlink(missing_ok=True)
            for name in entries:
                if Path(name).suffix.lower() in {".json", ".csv", ".png", ".svg", ".pdf"}:
                    projects.register_artifact(root / name, file_id=job.dataset_id)
            projects.register_artifact(root / "modeling" / f"{job.dataset_id}_status.json", file_id=job.dataset_id)
            receipt = {
                "request_id": request_id,
                "job_id": str(job.pk),
                "result_sha256": pin,
                "execution_id": execution,
                "development_selected": True,
                "review_approved": False,
                "production_use_approved": False,
            }
            service.record(
                job,
                "legacy_selection_completed",
                actor=actor,
                detail={"request_id": request_id, "request_sha256": request_sha, "receipt": receipt},
                update_fields=["revision"],
            )
            for scope in scopes:
                projects.recheck(scope)
            return {**receipt, "replayed": False, "currently_selected": True}
