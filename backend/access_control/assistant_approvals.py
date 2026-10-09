"""Exact browser-session authority for one existing native typed dispatch.

Downstream frontend handoffs are not job completion/authority. Expert code and
MCP execution remain blocked by their independent boundaries.
"""

import hashlib
import json
import platform
import uuid
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from access_control.authority import actor_snapshot
from access_control.models import AssistantActionApproval, SessionAuthority
from access_control.storage import managed_path, positive_file_id
from declaration.models import Declaration, DataDictionary
from modeling.execution_artifacts import digest_file, projection_lock
from modeling.models import PipelineRun

BUDGET = {
    "typed_dispatches": 1,
    "max_payload_bytes": 32768,
    "max_collection_items": 100,
    "expert_code": False,
    "downstream_job_authority": False,
}


class ApprovalError(Exception):
    def __init__(self, code, message, status=409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError):
        raise ApprovalError("invalid_action_payload", "Supply a finite JSON action payload.", 400) from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _actor(actor):
    if (
        not actor
        or not actor.is_authenticated
        or not get_user_model().objects.filter(pk=actor.pk, is_active=True).exists()
    ):
        raise ApprovalError("action_actor_unavailable", "Sign in with an active account.", 403)
    bound = getattr(actor, '_declarai_session_revision', None)
    if bound is not None:
        current = SessionAuthority.objects.filter(user_id=actor.pk).values_list('revision', flat=True).first()
        if bound != str(current):
            raise ApprovalError('action_actor_authority_changed', 'Your session authority changed. Sign in and review the action again.', 403)


def action_request(data):
    from ai_assistant.action_executor import HANDLERS

    if not isinstance(data, dict):
        raise ApprovalError("invalid_action_payload", "Supply a JSON action object.", 400)
    if data.get("file_id") is None:
        raise ApprovalError("file_id_required", "file_id is required", 400)
    file_id = positive_file_id(data.get("file_id"))
    action_type = data.get("action_type")
    if not isinstance(action_type, str) or action_type not in HANDLERS:
        raise ApprovalError("unsupported_action", "Unknown action type. Select a supported typed action.", 400)
    if action_type == "execute_code":
        raise ApprovalError(
            "expert_isolation_unavailable",
            "Sandboxed Python is unavailable. Exact code approval and qualified Linux isolation are required.",
            400,
        )
    payload = data.get("payload")
    if not isinstance(payload, dict) or len(canonical(payload)) > BUDGET["max_payload_bytes"]:
        raise ApprovalError("invalid_action_payload", "Supply an action object within the 32 KiB payload budget.", 400)

    def bound(value, depth=0):
        if depth > 10 or isinstance(value, (dict, list)) and len(value) > BUDGET["max_collection_items"]:
            raise ApprovalError("invalid_action_payload", "The action exceeds its collection or nesting budget.", 400)
        for child in value.values() if isinstance(value, dict) else value if isinstance(value, list) else []:
            bound(child, depth + 1)

    bound(payload)
    source = data.get("source") or "panel"
    if source not in ("panel", "codeline"):
        raise ApprovalError("invalid_action_payload", "Select a valid action source.", 400)
    parent = data.get("parent_span_id")
    parent = parent if isinstance(parent, str) and 0 < len(parent) <= 256 else ""
    return {
        "file_id": file_id,
        "action_type": action_type,
        "payload": payload,
        "source": source,
        "parent_span_id": parent,
    }


def recorded_context(file_id, action_type):
    """Hash recorded inputs only; never deserialize fitted state or final outcomes."""
    try:
        dataset = Declaration.objects.get(pk=file_id)
        path = dataset.get_file_path()
        if path is None:
            raise ValueError("missing dataset")
        context = {
            "dataset_sha256": digest_file(path),
            "declaration_sha256": digest(
                {
                    "id": dataset.pk,
                    "file": dataset.file.name,
                    "name": dataset.name,
                    "original_name": dataset.original_name,
                    "has_header": dataset.has_header,
                }
            ),
            "dictionary_sha256": digest(
                list(
                    DataDictionary.objects.filter(data_file_id=file_id)
                    .order_by("column_name")
                    .values("column_name", "description")
                )
            ),
            "pipeline_sha256": digest(
                list(
                    PipelineRun.objects.filter(file_id=file_id)
                    .order_by("id")
                    .values("id", "name", "current_step", "status", "state")
                )
            ),
            "artifact_pointers": {},
        }
        for relative in (
            f"modeling/{file_id}_status.json",
            f"evaluation/{file_id}_evaluation.json",
            f"splits/{file_id}_split.json",
            f"configs/preprocess_{file_id}.json",
            f"sfs_results/{file_id}_sfs_results.json",
            f"hyperparam_results/{file_id}_hyperparam.json",
            f"deployment_bundles/{file_id}/current.json",
        ):
            artifact = Path(managed_path(relative))
            context["artifact_pointers"][relative] = digest_file(artifact) if artifact.is_file() else None
        if action_type == "set_ordinal_ranking":
            from ai_assistant.cache import _get_redis, _key

            cache = _get_redis()
            if cache is None:
                raise ValueError("required cache unavailable")
            names = ["encoding_plan", "data_dictionary"]
            context["cache_inputs"] = {
                name: hashlib.sha256(raw.encode()).hexdigest() if raw is not None else None
                for name, raw in zip(names, cache.mget([_key(file_id, name) for name in names]), strict=True)
            }
        return context
    except Declaration.DoesNotExist:
        raise ApprovalError("action_dataset_unavailable", "The selected dataset is unavailable.", 404) from None
    except Exception:
        raise ApprovalError(
            "action_context_unavailable", "Recorded inputs cannot be verified. Restore them before preparing an action."
        ) from None


def environment():
    return {
        "schema_version": 1,
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("Django", "djangorestframework", "pandas", "numpy")},
        "dispatcher_sha256": digest_file(Path(__file__).parents[1] / "ai_assistant/action_executor.py"),
        "authority_sha256": digest_file(__file__),
    }


def envelope(record):
    return {
        "id": str(record.pk),
        "actor": record.actor_snapshot,
        "file_id": record.file_id,
        "action_type": record.action_type,
        "payload": record.payload,
        "source": record.source,
        "parent_span_id": record.parent_span_id,
        "context": record.context,
        "environment": record.environment,
        "budget": record.budget,
        "expires_at": record.expires_at.isoformat(),
    }


def receipt(record, *, replay=False):
    return {
        "approval_id": str(record.pk),
        "proposal_sha256": record.proposal_sha256,
        "file_id": record.file_id,
        "action_type": record.action_type,
        "actor": record.actor_snapshot,
        "state": record.state,
        "approved_at": record.approved_at.isoformat() if record.approved_at else None,
        "dispatched_at": record.dispatched_at.isoformat() if record.dispatched_at else None,
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
        "reason_code": record.reason_code,
        "replayed_receipt": replay,
        "scope": "one_native_typed_dispatch",
        "downstream_job_authority": False,
        "expert_code_authority": False,
    }


def project_snapshot(actor_id, file_id):
    from access_control import projects
    try:
        return projects.dataset_authority(actor_id, file_id, 'write') if projects.governed() else None
    except projects.ProjectDenied as exc:
        raise ApprovalError(exc.code, str(exc), 403) from None


def prepare(actor, data):
    _actor(actor)
    requested = action_request(data)
    project_scope = project_snapshot(actor.pk, requested["file_id"])
    with projection_lock(requested["file_id"]):
        revision = SessionAuthority.objects.get_or_create(user_id=actor.pk)[0].revision
        if AssistantActionApproval.objects.filter(file_id=requested["file_id"], state="dispatching").exists():
            raise ApprovalError(
                "action_dispatch_unresolved",
                "A dispatch outcome is unconfirmed. Reconcile its receipt before preparing another action.",
            )
        record = AssistantActionApproval(
            actor=actor,
            actor_snapshot={**actor_snapshot(actor), **({'project_authority': project_scope} if project_scope else {}), 'session_revision': getattr(actor, '_declarai_session_revision', str(revision))},
            **requested,
            context=recorded_context(requested["file_id"], requested["action_type"]),
            environment=environment(),
            budget=BUDGET.copy(),
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        _actor(actor)
        if project_snapshot(actor.pk, requested["file_id"]) != project_scope:
            raise ApprovalError("project_authority_changed", "Project authority changed. Prepare the action again.", 403)
        record.proposal_sha256 = digest(envelope(record))
        record.save(force_insert=True)
    return {
        **receipt(record),
        "payload": record.payload,
        "source": record.source,
        "parent_span_id": record.parent_span_id,
        "expires_at": record.expires_at.isoformat(),
        "budget": record.budget,
        "context_sha256": digest(record.context),
        "effect": "Dictionary descriptions are saved here. Other actions send settings to the pipeline. Check pipeline status to see whether a job ran. This approval does not cover expert Python or independent review.",
    }


def _load(actor, data):
    _actor(actor)
    try:
        identifier = uuid.UUID(str(data.get("approval_id")))
        record = AssistantActionApproval.objects.get(pk=identifier, actor_id=actor.pk)
    except (ValueError, TypeError, AssistantActionApproval.DoesNotExist):
        raise ApprovalError("action_approval_unavailable", "Select your prepared action approval.", 403) from None
    if digest(envelope(record)) != record.proposal_sha256 or data.get("proposal_sha256") != record.proposal_sha256:
        raise ApprovalError("action_approval_mismatch", "The prepared action changed. Prepare and review it again.")
    return record


def _fresh(record):
    code = None
    try:
        project_scope = project_snapshot(record.actor_id, record.file_id)
    except ApprovalError:
        project_scope = {"unavailable": True}
    if project_scope != record.actor_snapshot.get("project_authority"):
        code = "project_authority_changed"
    elif record.expires_at <= timezone.now():
        code = "action_approval_expired"
    elif record.actor_snapshot.get('session_revision') != str(SessionAuthority.objects.filter(
        user_id=record.actor_id).values_list('revision', flat=True).first()):
        code = 'action_actor_authority_changed'
    elif environment() != record.environment or recorded_context(record.file_id, record.action_type) != record.context:
        code = "action_approval_stale"
    if code:
        AssistantActionApproval.objects.filter(pk=record.pk, state__in=["prepared", "approved"]).update(
            state="stale", reason_code=code, finished_at=timezone.now()
        )
        raise ApprovalError(
            code, "The approval expired or its recorded inputs changed. Prepare and review a new action."
        )


def approve(actor, data):
    record = _load(actor, data)
    with projection_lock(record.file_id):
        _fresh(record)
        if (
            AssistantActionApproval.objects.filter(pk=record.pk, state="prepared").update(
                state="approved", approved_at=timezone.now()
            )
            != 1
        ):
            raise ApprovalError("action_approval_not_prepared", "This action is no longer awaiting approval.")
        record.refresh_from_db()
        return receipt(record)


def cancel(actor, data):
    record = _load(actor, data)
    with projection_lock(record.file_id):
        if (
            AssistantActionApproval.objects.filter(pk=record.pk, state__in=["prepared", "approved"]).update(
                state="cancelled", reason_code="actor_cancelled", finished_at=timezone.now()
            )
            != 1
        ):
            raise ApprovalError("action_approval_not_cancellable", "This action has already been consumed or closed.")
        record.refresh_from_db()
        return receipt(record)


def execute(actor, data, dispatch):
    requested = action_request(data)
    record = _load(actor, data)
    if requested != {key: getattr(record, key) for key in requested}:
        raise ApprovalError(
            "action_approval_mismatch", "The action payload or dataset changed. Prepare and review it again."
        )
    with projection_lock(record.file_id):
        record.refresh_from_db()
        if record.state in ("completed", "failed"):
            return {**record.result, "approval_receipt": receipt(record, replay=True)}
        if record.state != "approved":
            raise ApprovalError(
                "action_approval_required", "Review and approve the exact prepared action before dispatch."
            )
        _fresh(record)
        _actor(actor)
        if (
            AssistantActionApproval.objects.filter(pk=record.pk, state="approved").update(
                state="dispatching", dispatched_at=timezone.now()
            )
            != 1
        ):
            raise ApprovalError("action_approval_consumed", "This approval has already been consumed.")
        # Reservation commits before dispatch. Failed completion must not allow retry.
        try:
            result = dispatch(
                record.file_id,
                record.action_type,
                record.payload,
                parent_span_id=record.parent_span_id or None,
                source=record.source,
            )
            if not isinstance(result, dict) or result.get("status") not in ("success", "error"):
                raise ValueError("invalid dispatch result")
            canonical(result)
        except Exception:
            result = {
                "status": "error",
                "error_code": "action_dispatch_failed",
                "error": "The typed action failed. Inspect its receipt before preparing a new action.",
            }
        state = "completed" if result["status"] == "success" else "failed"
        if (
            AssistantActionApproval.objects.filter(pk=record.pk, state="dispatching").update(
                state=state, result=result, reason_code=result.get("error_code", ""), finished_at=timezone.now()
            )
            != 1
        ):
            raise ApprovalError(
                "action_receipt_unavailable",
                "Dispatch may have occurred, but its completion receipt is unavailable. Do not repeat it.",
                503,
            )
        record.refresh_from_db()
        return {**result, "approval_receipt": receipt(record)}


def status(actor, data):
    record = _load(actor, data)
    return {**receipt(record), "expires_at": record.expires_at.isoformat(), "result": record.result}
