import importlib.util, sys, uuid, json
from pathlib import Path
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def enrollment(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    from access_control import enrollment as module

    return module


@pytest.fixture
def scope(enrollment):
    return enrollment.specification("alice", "operator-ticket", "admin", new_project="Credit models")


def test_enrollment_is_ordinary_atomic_and_idempotent(enrollment, scope):
    from django.contrib.auth import get_user_model
    from access_control.models import (
        AuthenticationEvent,
        ProjectPolicy,
        ProjectMembership,
        ProjectAuthorityEvent,
        SessionAuthority,
    )

    password = "Strong-fixture-secret-4901"
    request = uuid.uuid4()
    event, replay = enrollment.enroll(scope, request, password)
    user = get_user_model().objects.get(username="alice")
    hash = user.password
    revision = SessionAuthority.objects.get(user=user).revision
    assert user.is_active and not user.is_staff and not user.is_superuser and user.check_password(password)
    assert event.started_at <= event.finished_at
    assert ProjectPolicy.objects.filter(pk=1).exists()
    assert ProjectMembership.objects.get(actor=user).role == "admin" and ProjectAuthorityEvent.objects.count() == 1
    again, replay = enrollment.enroll(scope, request, password)
    user.refresh_from_db()
    assert replay and event.pk == again.pk and AuthenticationEvent.objects.count() == 1 and user.password == hash
    assert SessionAuthority.objects.get(user=user).revision == revision
    assert password not in json.dumps(event.details) and "password" not in json.dumps(event.details).lower()


@pytest.mark.parametrize("change", ["password", "inactive", "staff", "superuser", "revision", "membership"])
def test_replay_cannot_change_or_inherit_altered_authority(enrollment, scope, change):
    from django.contrib.auth import get_user_model
    from access_control.models import SessionAuthority, ProjectMembership, AuthenticationEvent

    request = uuid.uuid4()
    password = "Strong-fixture-secret-4901"
    event, _ = enrollment.enroll(scope, request, password)
    user = get_user_model().objects.get(username="alice")
    original = event.details
    if change == "password":
        password = "Different-fixture-secret-4901"
    elif change == "revision":
        SessionAuthority.objects.filter(user=user).update(revision=uuid.uuid4())
    elif change == "membership":
        member = ProjectMembership.objects.get(actor=user)
        member.role = "reviewer"
        member.save()
    else:
        setattr(
            user,
            {"inactive": "is_active", "staff": "is_staff", "superuser": "is_superuser"}[change],
            change != "inactive",
        )
        user.save()
    with pytest.raises(enrollment.EnrollmentDenied):
        enrollment.enroll(scope, request, password)
    assert AuthenticationEvent.objects.get(pk=request).details == original


def test_existing_user_and_request_collisions_preserve_prior_state(enrollment, scope):
    from django.contrib.auth import get_user_model

    request = uuid.uuid4()
    enrollment.enroll(scope, request, "Strong-fixture-secret-4901")
    with pytest.raises(enrollment.EnrollmentDenied, match="username_exists"):
        enrollment.enroll(scope, uuid.uuid4(), "Strong-fixture-secret-4901")
    altered = {**scope, "operator_label": "different-ticket"}
    with pytest.raises(enrollment.EnrollmentDenied, match="request_changed"):
        enrollment.enroll(altered, request, "Strong-fixture-secret-4901")
    assert get_user_model().objects.count() == 1


def test_project_failure_rolls_back_account_authority_and_audit(enrollment):
    from django.contrib.auth import get_user_model
    from access_control.models import AuthenticationEvent, SessionAuthority, ProjectPolicy

    scope = enrollment.specification("alice", "operator-ticket", "developer", project_id=uuid.uuid4())
    with pytest.raises(enrollment.EnrollmentDenied, match="project_unavailable"):
        enrollment.enroll(scope, uuid.uuid4(), "Strong-fixture-secret-4901")
    assert (
        not get_user_model().objects.exists()
        and not SessionAuthority.objects.exists()
        and not AuthenticationEvent.objects.exists()
        and not ProjectPolicy.objects.exists()
    )


@pytest.mark.parametrize(
    "password", ["short", "00000000000000000000", "alicealicealicealice", "line\nbreak-password4901"]
)
def test_invalid_password_has_no_durable_effect(enrollment, scope, password):
    from django.contrib.auth import get_user_model
    from access_control.models import ProjectPolicy, AuthenticationEvent

    with pytest.raises(enrollment.EnrollmentDenied, match="password_policy"):
        enrollment.enroll(scope, uuid.uuid4(), password)
    assert (
        not get_user_model().objects.exists()
        and not ProjectPolicy.objects.exists()
        and not AuthenticationEvent.objects.exists()
    )


def test_missing_recorded_policy_is_blocked_without_reactivation(enrollment, scope):
    from access_control.models import ProjectPolicy, AuthenticationEvent

    request = uuid.uuid4()
    enrollment.enroll(scope, request, "Strong-fixture-secret-4901")
    ProjectPolicy.objects.all().delete()
    with pytest.raises(enrollment.EnrollmentDenied, match="policy_state_changed"):
        enrollment.enroll(scope, request, "Strong-fixture-secret-4901")
    assert not ProjectPolicy.objects.exists() and AuthenticationEvent.objects.count() == 1


@pytest.mark.parametrize("fault", ["groups", "permissions", "request", "project_scope", "password_hash"])
def test_changed_enrollment_cannot_repair_global_or_request_state(enrollment, scope, fault, settings):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    from access_control.models import AuthenticationEvent

    request = uuid.uuid4()
    password = "Strong-fixture-secret-4901"
    enrollment.enroll(scope, request, password)
    user = get_user_model().objects.get(username="alice")
    prior = user.password
    altered = dict(scope)
    if fault == "groups":
        user.groups.add(Group.objects.create(name="foreign-global-group"))
    elif fault == "permissions":
        user.user_permissions.add(Permission.objects.first())
    elif fault == "request":
        altered["username"] = "bob"
    elif fault == "project_scope":
        altered["new_project"] = "Changed project"
    else:
        settings.PASSWORD_HASHERS = [
            "django.contrib.auth.hashers.PBKDF2PasswordHasher",
            "django.contrib.auth.hashers.MD5PasswordHasher",
        ]
        event, replayed = enrollment.enroll(scope, request, password)
        user.refresh_from_db()
        assert replayed and user.password == prior
        return
    with pytest.raises(enrollment.EnrollmentDenied):
        enrollment.enroll(altered, request, password)
    user.refresh_from_db()
    assert user.password == prior and AuthenticationEvent.objects.count() == 1


@pytest.mark.parametrize("fault", ["empty", "public", "symlink", "hardlink", "fifo", "large", "invalid_utf8"])
def test_private_credential_file_rejects_unsafe_inputs(tmp_path, fault):
    import os
    from access_control.management.commands.enroll_account import credential
    from access_control.enrollment import EnrollmentDenied

    file = tmp_path / "credential"
    file.write_bytes(b"Strong-fixture-secret-4901")
    file.chmod(0o600)
    if fault == "empty":
        file.write_bytes(b"")
    elif fault == "public":
        file.chmod(0o644)
    elif fault == "symlink":
        file.rename(tmp_path / "other")
        file.symlink_to(tmp_path / "other")
    elif fault == "hardlink":
        os.link(file, tmp_path / "other")
    elif fault == "fifo":
        file.unlink()
        os.mkfifo(file, 0o600)
    elif fault == "large":
        file.write_bytes(b"x" * 4097)
    else:
        file.write_bytes(b"\xff")
    with pytest.raises(EnrollmentDenied, match="private_credential_file"):
        credential(file)


def test_private_credential_file_is_read_without_mutation(tmp_path):
    from access_control.management.commands.enroll_account import credential

    file = tmp_path / "credential"
    data = b"Strong-fixture-secret-4901\n"
    file.write_bytes(data)
    file.chmod(0o400)
    assert credential(file) == "Strong-fixture-secret-4901" and file.read_bytes() == data


@pytest.mark.parametrize("stage", ["profile", "role", "runtime"])
def test_command_requires_private_actual_preflight_before_credential_read(
    enrollment, settings, monkeypatch, stage, tmp_path
):
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from access_control.management.commands import enroll_account as command
    from execution_jobs.preflight import RuntimeUnavailable

    calls = []
    settings.DECLARAI_RUNTIME_PROFILE = "development" if stage == "profile" else "private"

    def role():
        calls.append("role")
        if stage == "role":
            raise RuntimeUnavailable("job_application_role_elevated")

    def runtime():
        calls.append("runtime")
        raise RuntimeUnavailable("job_migrations_required")

    monkeypatch.setattr(command, "check_application_role", role)
    monkeypatch.setattr(command, "check_runtime", runtime)
    monkeypatch.setattr(command, "credential", lambda *a: pytest.fail("credential read before private preflight"))
    with pytest.raises(CommandError):
        call_command(
            "enroll_account",
            user="alice",
            request_id=str(uuid.uuid4()),
            operator_label="operator-ticket",
            password_file=str(tmp_path / "missing"),
            role="admin",
            new_project="Credit models",
        )
    assert calls == ([] if stage == "profile" else ["role"] if stage == "role" else ["role", "runtime"])


@pytest.mark.parametrize("fault", ["username", "operator", "role", "both", "neither", "new_project_reviewer", "uuid"])
def test_invalid_enrollment_scope_is_explicit(enrollment, fault):
    args = {"username": "alice", "operator_label": "operator-ticket", "role": "admin", "new_project": "Credit models"}
    if fault == "username":
        args["username"] = "bad\nprincipal"
    elif fault == "operator":
        args["operator_label"] = ""
    elif fault == "role":
        args["role"] = "superuser"
    elif fault == "both":
        args["project_id"] = uuid.uuid4()
    elif fault == "neither":
        args.pop("new_project")
    elif fault == "new_project_reviewer":
        args["role"] = "reviewer"
    else:
        args.pop("new_project")
        args["project_id"] = "bad-id"
    with pytest.raises(enrollment.EnrollmentDenied):
        enrollment.specification(**args)


@pytest.mark.parametrize("role", ["developer", "reviewer"])
def test_enrollment_assigns_only_the_requested_existing_project_role(enrollment, scope, role):
    from django.contrib.auth import get_user_model
    from access_control.models import ProjectMembership

    admin, _ = enrollment.enroll(scope, uuid.uuid4(), "Strong-fixture-secret-4901")
    requested = enrollment.specification(role, "operator-ticket", role, project_id=admin.details["project_id"])
    event, _ = enrollment.enroll(requested, uuid.uuid4(), "Other-strong-fixture-secret-4902")
    user = get_user_model().objects.get(username=role)
    assert (
        not user.is_staff and not user.is_superuser and not user.groups.exists() and not user.user_permissions.exists()
    )
    assert (
        ProjectMembership.objects.get(actor=user).role == role and event.details["global_privileges_granted"] is False
    )


def test_preexisting_derived_project_receipt_cannot_adopt_a_new_account(enrollment, scope):
    from django.contrib.auth import get_user_model
    from access_control.projects import operator_change
    from access_control.models import AuthenticationEvent, ProjectAuthorityEvent

    request = uuid.uuid4()
    user = get_user_model().objects.create_user(username="alice", password=None)
    prior, _ = operator_change(
        {"operation": "create", "name": "Credit models", "user": "alice"},
        uuid.uuid5(request, "declarai-enrollment-project-v1"),
        "operator-ticket",
    )
    original = prior.resource
    user.delete()
    with pytest.raises(enrollment.EnrollmentDenied, match="project_request_collision"):
        enrollment.enroll(scope, request, "Strong-fixture-secret-4901")
    assert not get_user_model().objects.exists() and not AuthenticationEvent.objects.exists()
    assert ProjectAuthorityEvent.objects.get(pk=prior.pk).resource == original


def test_tampered_scope_or_operator_metadata_does_not_replay(enrollment, scope):
    from access_control.models import AuthenticationEvent

    request = uuid.uuid4()
    event, _ = enrollment.enroll(scope, request, "Strong-fixture-secret-4901")
    event.details = {**event.details, "scope": {**scope, "new_project": "tampered"}}
    event.save(update_fields=["details"])
    with pytest.raises(enrollment.EnrollmentDenied, match="request_changed"):
        enrollment.enroll(scope, request, "Strong-fixture-secret-4901")
    assert AuthenticationEvent.objects.count() == 1
