"""Explicit installation-operator ordinary-account and project enrollment."""

import hashlib
import json
import re
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from access_control.authority import actor_snapshot
from access_control.models import AuthenticationEvent, ProjectMembership, ProjectPolicy, SessionAuthority
from access_control.projects import operator_change, ProjectDenied


class EnrollmentDenied(Exception):
    pass


def specification(username, operator_label, role, project_id=None, new_project=None):
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.@+-]{1,150}", username):
        raise EnrollmentDenied("enrollment_username_invalid")
    if not isinstance(operator_label, str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,100}", operator_label):
        raise EnrollmentDenied("enrollment_operator_assertion_required")
    if role not in {"developer", "reviewer", "admin"} or (project_id is None) == (new_project is None):
        raise EnrollmentDenied("enrollment_project_scope_required")
    value = {
        "schema": "ordinary_project_account_v1",
        "username": username,
        "operator_label": operator_label,
        "role": role,
        "project_isolation": True,
    }
    if new_project is not None:
        if (
            role != "admin"
            or not isinstance(new_project, str)
            or not 0 < len(new_project.strip()) <= 200
            or not new_project.isprintable()
        ):
            raise EnrollmentDenied("enrollment_new_project_admin_required")
        value["new_project"] = new_project.strip()
    else:
        try:
            value["project_id"] = str(uuid.UUID(str(project_id)))
        except (ValueError, TypeError, AttributeError):
            raise EnrollmentDenied("enrollment_project_scope_required") from None
    return value


def enroll(spec, request_id, password):
    """Input password is never included in request/evidence digests or diagnostics."""
    try:
        identifier = uuid.UUID(str(request_id))
    except (ValueError, TypeError, AttributeError):
        raise EnrollmentDenied("enrollment_request_uuid_required") from None
    if (
        not isinstance(password, str)
        or not 16 <= len(password) <= 4096
        or len(set(password)) < 8
        or any(ord(c) < 32 or ord(c) == 127 for c in password)
    ):
        raise EnrollmentDenied("enrollment_password_policy_failed")
    wanted = specification(
        spec["username"], spec["operator_label"], spec["role"], spec.get("project_id"), spec.get("new_project")
    )
    if spec != wanted:
        raise EnrollmentDenied("enrollment_scope_invalid")
    digest = hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    started = timezone.now()
    with transaction.atomic():
        if (
            not ProjectPolicy.objects.filter(pk=1).exists()
            and AuthenticationEvent.objects.filter(pk=identifier).exists()
        ):
            raise EnrollmentDenied("enrollment_policy_state_changed")
        ProjectPolicy.objects.get_or_create(pk=1)
        ProjectPolicy.objects.select_for_update().get(pk=1)
        previous = AuthenticationEvent.objects.filter(pk=identifier).first()
        if previous:
            if (
                previous.request_sha256 != digest
                or previous.authority_source != "installation_operator"
                or previous.event_type != "account_enrolled"
                or previous.outcome != "completed"
                or previous.operator_label != spec["operator_label"]
                or previous.details.get("scope") != spec
            ):
                raise EnrollmentDenied("enrollment_request_changed")
            user = get_user_model().objects.select_for_update().filter(pk=previous.subject_snapshot.get("id")).first()
            authority = SessionAuthority.objects.filter(user=user).first() if user else None
            member = (
                ProjectMembership.objects.filter(project_id=previous.details.get("project_id"), actor=user).first()
                if user
                else None
            )
            if (
                not user
                or user.username != spec["username"]
                or not user.is_active
                or user.is_staff
                or user.is_superuser
                or user.groups.exists()
                or user.user_permissions.exists()
                or not check_password(password, user.password)
            ):
                raise EnrollmentDenied("enrollment_account_state_changed")
            if (
                not authority
                or authority.revision != previous.session_revision
                or not member
                or not member.active
                or member.role != spec["role"]
                or str(member.revision) != previous.details.get("membership_revision")
            ):
                raise EnrollmentDenied("enrollment_authority_changed")
            return previous, True
        if get_user_model().objects.filter(username=spec["username"]).exists():
            raise EnrollmentDenied("enrollment_username_exists")
        user = get_user_model()(username=spec["username"], is_active=True, is_staff=False, is_superuser=False)
        try:
            validate_password(password, user)
        except ValidationError:
            raise EnrollmentDenied("enrollment_password_policy_failed") from None
        user.set_password(password)
        user.save()
        authority = SessionAuthority.objects.create(user=user)
        project_request = uuid.uuid5(identifier, "declarai-enrollment-project-v1")
        change = (
            {"operation": "create", "name": spec["new_project"], "user": user.username}
            if "new_project" in spec
            else {"operation": "member", "project_id": spec["project_id"], "user": user.username, "role": spec["role"]}
        )
        try:
            project_event, replayed_project = operator_change(change, project_request, spec["operator_label"])
            if replayed_project:
                raise EnrollmentDenied("enrollment_project_request_collision")
        except (ObjectDoesNotExist, ProjectDenied, ValueError):
            raise EnrollmentDenied("enrollment_project_unavailable") from None
        membership = ProjectMembership.objects.get(project=project_event.project, actor=user)
        now = timezone.now()
        event = AuthenticationEvent.objects.create(
            id=identifier,
            subject_snapshot=actor_snapshot(user),
            authority_source="installation_operator",
            event_type="account_enrolled",
            outcome="completed",
            operator_label=spec["operator_label"],
            request_sha256=digest,
            session_revision=authority.revision,
            started_at=started,
            finished_at=now,
            details={
                "scope": spec,
                "project_id": str(project_event.project_id),
                "project_event_id": str(project_event.pk),
                "membership_revision": str(membership.revision),
                "global_privileges_granted": False,
            },
        )
        return event, False
