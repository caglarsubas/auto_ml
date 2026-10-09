"""Recorded project authority. Installation operators are assertions, not users."""

import hashlib
import json
import uuid
from contextvars import ContextVar
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from access_control.authority import actor_snapshot
from access_control.models import (
    Project,
    ProjectPolicy,
    ProjectMembership,
    ProjectDataset,
    ProjectPipeline,
    ProjectArtifact,
    ProjectAuthorityEvent,
    AssistantActionApproval,
)
from access_control.storage import managed_path, positive_file_id

current_actor = ContextVar("project_request_actor", default=None)


class ProjectDenied(PermissionError):
    def __init__(self, code="project_access_denied"):
        self.code = code
        super().__init__("Project authority is unavailable. Ask a project administrator to review your access.")


def governed():
    return settings.DECLARAI_RUNTIME_PROFILE == "private" or ProjectPolicy.objects.exists()


def membership(actor_id, project_id, operation="read"):
    member = ProjectMembership.objects.filter(
        actor_id=actor_id, actor__is_active=True, project_id=project_id, active=True
    ).first()
    roles = {"read": {"developer", "reviewer", "admin"}, "write": {"developer"}, "admin": {"admin"}}
    if not member or member.role not in roles.get(operation, set()):
        raise ProjectDenied()
    return {
        "project_id": str(member.project_id),
        "actor_id": member.actor_id,
        "membership_revision": str(member.revision),
        "role": member.role,
        "operation": operation,
    }


def dataset_authority(actor_id, file_id, operation="read"):
    binding = ProjectDataset.objects.filter(dataset_id=positive_file_id(file_id)).first()
    if not binding:
        raise ProjectDenied("dataset_project_assignment_required")
    return {
        **membership(actor_id, binding.project_id, operation),
        "file_id": binding.dataset_id,
        "binding_revision": str(binding.revision),
    }


def choose_project(actor_id, explicit=None, operation="write"):
    if explicit:
        try:
            return membership(actor_id, uuid.UUID(str(explicit)), operation)
        except (ValueError, TypeError):
            raise ProjectDenied("project_identifier_invalid") from None
    allowed = list(
        ProjectMembership.objects.filter(
            actor_id=actor_id, actor__is_active=True, active=True, role="developer"
        ).values_list("project_id", flat=True)[:2]
    )
    if len(allowed) != 1:
        raise ProjectDenied("project_selection_required")
    return membership(actor_id, allowed[0], operation)


def allowed_projects(actor_id):
    return ProjectMembership.objects.filter(
        actor_id=actor_id, actor__is_active=True, active=True, role__in=["developer", "reviewer", "admin"]
    ).values_list("project_id", flat=True)


def allowed_datasets(actor_id):
    return ProjectDataset.objects.filter(project_id__in=allowed_projects(actor_id)).values_list("dataset_id", flat=True)


def audit(actor, operation, resource, project_id=None, *, source="browser_session", outcome="completed", reason=""):
    return ProjectAuthorityEvent.objects.create(
        actor=actor,
        actor_snapshot=actor_snapshot(actor),
        project_id=project_id,
        authority_source=source,
        operation=operation,
        resource=resource,
        outcome=outcome,
        reason_code=reason,
    )


def bind_dataset(dataset, project_id, actor=None, source="native_declaration"):
    with transaction.atomic():
        binding, created = ProjectDataset.objects.get_or_create(dataset=dataset, defaults={"project_id": project_id})
        if str(binding.project_id) != str(project_id):
            raise ProjectDenied("dataset_project_reassignment_unsupported")
        if created:
            audit(
                actor,
                "dataset_assigned",
                {"file_id": dataset.pk, "binding_revision": str(binding.revision)},
                project_id,
                source=source,
            )
        return binding


def bind_pipeline(pipeline, project_id, actor=None, source="native_pipeline"):
    with transaction.atomic():
        binding, created = ProjectPipeline.objects.get_or_create(pipeline=pipeline, defaults={"project_id": project_id})
        if str(binding.project_id) != str(project_id):
            raise ProjectDenied("pipeline_project_reassignment_unsupported")
        if created:
            audit(
                actor,
                "pipeline_assigned",
                {"pipeline_id": pipeline.pk, "binding_revision": str(binding.revision)},
                project_id,
                source=source,
            )
        return binding


def canonical_path(path):
    return Path(managed_path(str(path) if isinstance(path, Path) else path)).relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()


def register_artifact(path, *, file_id=None, project_id=None):
    if not governed():
        return
    if file_id is not None:
        file_id = positive_file_id(file_id)
        binding = ProjectDataset.objects.filter(dataset_id=file_id).first()
        if binding is None:
            raise ProjectDenied("dataset_project_assignment_required")
        project_id = binding.project_id
    if project_id is None:
        raise ProjectDenied("artifact_project_assignment_required")
    relative = canonical_path(path)
    digest = hashlib.sha256(relative.encode()).hexdigest()
    with transaction.atomic():
        record, created = ProjectArtifact.objects.get_or_create(
            path_sha256=digest, defaults={"relative_path": relative, "project_id": project_id, "dataset_id": file_id}
        )
        if (
            record.relative_path != relative
            or str(record.project_id) != str(project_id)
            or record.dataset_id != file_id
        ):
            raise ProjectDenied("artifact_owner_conflict")
        if created:
            audit(
                None,
                "artifact_registered",
                {"path_sha256": digest, "file_id": file_id},
                project_id,
                source="native_artifact_writer",
            )


def path_authority(actor_id, path, *, file_id=None, operation="read"):
    from declaration.models import Declaration

    relative = canonical_path(path)
    datasets = list(Declaration.objects.filter(file=relative).values_list("pk", flat=True))
    if datasets:
        if len(datasets) != 1:
            raise ProjectDenied("artifact_owner_ambiguous")
        scopes = [dataset_authority(actor_id, item, operation) for item in datasets]
        if file_id is not None and file_id not in datasets:
            raise ProjectDenied("artifact_dataset_mismatch")
        return scopes[0]
    record = ProjectArtifact.objects.filter(
        path_sha256=hashlib.sha256(relative.encode()).hexdigest(), relative_path=relative
    ).first()
    if not record or file_id is not None and record.dataset_id != file_id:
        raise ProjectDenied("artifact_project_assignment_required")
    scope = membership(actor_id, record.project_id, operation)
    if record.dataset_id:
        scope = dataset_authority(actor_id, record.dataset_id, operation)
    return scope


def validate_paths(actor_id, file_id, values, operation="read"):
    for key in ["processed_file", "file_override"]:
        if values.get(key):
            path_authority(actor_id, values[key], file_id=file_id, operation=operation)
    if values.get("model_path"):
        raise ProjectDenied("use_immutable_execution_identifier")


def recheck(scope, *, allow_deleted=False):
    if allow_deleted:
        from declaration.models import Declaration
        from modeling.models import PipelineRun

        deleted = (
            scope.get("file_id") is not None
            and not Declaration.objects.filter(pk=scope["file_id"]).exists()
            or scope.get("pipeline_id") is not None
            and not PipelineRun.objects.filter(pk=scope["pipeline_id"]).exists()
        )
        if deleted:
            current = membership(scope["actor_id"], scope["project_id"], scope["operation"])
            expected = {k: v for k, v in scope.items() if k not in {"file_id", "pipeline_id", "binding_revision"}}
            if current != expected:
                raise ProjectDenied("project_authority_changed")
            return
    if scope.get("pipeline_id") is not None:
        current = pipeline_authority(scope["actor_id"], scope["pipeline_id"], scope["operation"])
    elif scope.get("file_id") is not None:
        current = dataset_authority(scope["actor_id"], scope["file_id"], scope["operation"])
    else:
        current = membership(scope["actor_id"], scope["project_id"], scope["operation"])
    if current != scope:
        raise ProjectDenied("project_authority_changed")


def pipeline_authority(actor_id, pipeline_id, operation="read"):
    binding = (
        ProjectPipeline.objects.select_related("pipeline").filter(pipeline_id=positive_file_id(pipeline_id)).first()
    )
    if not binding:
        raise ProjectDenied("pipeline_project_assignment_required")
    scope = {
        **membership(actor_id, binding.project_id, operation),
        "pipeline_id": binding.pipeline_id,
        "binding_revision": str(binding.revision),
    }
    state = binding.pipeline.state
    references = [binding.pipeline.file_id]
    if isinstance(state, dict):
        references.extend([state.get("file_id"), state.get("fileId")])
    for file_id in references:
        if file_id is not None:
            related = dataset_authority(actor_id, file_id, operation)
            if related["project_id"] != scope["project_id"]:
                raise ProjectDenied("pipeline_dataset_project_mismatch")
    return scope


def change_member(project, user, role):
    if role not in {"developer", "reviewer", "admin", "none"}:
        raise ValueError("Select developer, reviewer, admin or none.")
    member, _ = ProjectMembership.objects.get_or_create(
        project=project, actor=user, defaults={"role": "reviewer", "active": False}
    )
    member.active, member.revision, member.updated_at = role != "none", uuid.uuid4(), timezone.now()
    if member.active:
        member.role = role
    member.save()
    cancelled = AssistantActionApproval.objects.filter(
        actor=user,
        state__in=["prepared", "approved"],
        file_id__in=ProjectDataset.objects.filter(project=project).values("dataset_id"),
    ).update(state="cancelled", reason_code="project_membership_changed", finished_at=timezone.now())
    return {"subject_user_id": user.pk, "membership_revision": str(member.revision), "cancelled_actions": cancelled}


def admin_change(actor, project_id, username, role, request_id):
    identifier = uuid.UUID(str(request_id))
    spec = {"project_id": str(project_id), "user": username, "role": role, "actor_id": actor.pk}
    digest = hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id)
        membership(actor.pk, project.pk, "admin")
        previous = ProjectAuthorityEvent.objects.filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != digest or previous.authority_source != "browser_session":
                raise ValueError("Request UUID is bound to a different operation.")
            return previous, True
        user = get_user_model().objects.get(username=username)
        if user.pk == actor.pk:
            raise ValueError("Use the installation operator command to change your own administrator role.")
        resource = {**spec, **change_member(project, user, role)}
        event = ProjectAuthorityEvent.objects.create(
            id=identifier,
            project=project,
            actor=actor,
            actor_snapshot=actor_snapshot(actor),
            authority_source="browser_session",
            operation="member",
            resource=resource,
            outcome="completed",
            request_sha256=digest,
        )
        return event, False


def operator_change(spec, request_id, operator_label):
    """Exact-request retry receipt, serialized by the durable installation policy row."""
    from declaration.models import Declaration
    from modeling.models import PipelineRun

    identifier = uuid.UUID(str(request_id))
    digest = hashlib.sha256(
        json.dumps(
            {"spec": spec, "operator_label": operator_label}, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    with transaction.atomic():
        ProjectPolicy.objects.get_or_create(pk=1)
        ProjectPolicy.objects.select_for_update().get(pk=1)
        previous = ProjectAuthorityEvent.objects.filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != digest or previous.authority_source != "installation_operator":
                raise ValueError("Request UUID is bound to a different operation.")
            return previous, True
        resource = dict(spec)
        if spec["operation"] == "create":
            user = get_user_model().objects.get(username=spec["user"], is_active=True)
            project = Project.objects.create(name=spec["name"])
            member = ProjectMembership.objects.create(project=project, actor=user, role="admin")
            resource.update(
                project_id=str(project.pk), subject_user_id=user.pk, membership_revision=str(member.revision)
            )
        else:
            project = Project.objects.select_for_update().get(pk=uuid.UUID(spec["project_id"]))
            if spec["operation"] == "member":
                user = get_user_model().objects.get(username=spec["user"])
                resource.update(change_member(project, user, spec["role"]))
            elif spec["operation"] == "dataset":
                binding = bind_dataset(
                    Declaration.objects.get(pk=spec["file_id"]), project.pk, source="installation_operator_assertion"
                )
                resource["binding_revision"] = str(binding.revision)
            elif spec["operation"] == "pipeline":
                run = PipelineRun.objects.get(pk=spec["pipeline_id"])
                refs = [run.file_id] + (
                    [run.state.get("file_id"), run.state.get("fileId")] if isinstance(run.state, dict) else []
                )
                for reference in refs:
                    if reference is not None and str(
                        ProjectDataset.objects.get(dataset_id=positive_file_id(reference)).project_id
                    ) != str(project.pk):
                        raise ValueError("Pipeline and dataset projects must agree.")
                binding = bind_pipeline(run, project.pk, source="installation_operator_assertion")
                resource["binding_revision"] = str(binding.revision)
            else:
                raise ValueError("Select a supported project operation.")
        event = ProjectAuthorityEvent.objects.create(
            id=identifier,
            project=project,
            authority_source="installation_operator",
            operator_label=operator_label,
            operation=spec["operation"],
            resource=resource,
            outcome="completed",
            request_sha256=digest,
        )
        return event, False


def assert_evidence_scope(value, file_id):
    """Withhold legacy cross-project history; never rewrite frozen evidence."""
    from access_control.models import ProjectDataset

    project_id = ProjectDataset.objects.filter(dataset_id=file_id).values_list("project_id", flat=True).first()
    allowed = (
        set(ProjectDataset.objects.filter(project_id=project_id).values_list("dataset_id", flat=True))
        if project_id
        else {file_id}
    )

    def inspect(item):
        if isinstance(item, dict):
            if item.get("relation") in {"same_final_rows", "overlapping_final_rows", "historical_identity_unknown"}:
                if item.get("file_id") is not None and item["file_id"] not in allowed:
                    raise ProjectDenied("cross_project_evidence_requires_new_assessment")
            for child in item.values():
                inspect(child)
        elif isinstance(item, list):
            for child in item:
                inspect(child)

    inspect(value)
