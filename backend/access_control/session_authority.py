"""Durable login admission, recorded authentication and bounded web revocation."""

import hashlib
import json
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from access_control.authority import actor_snapshot
from access_control.models import AuthenticationEvent, LoginThrottleBucket, SessionAuthority, AssistantActionApproval

SESSION_REVISION_KEY = "declarai_session_revision"


def authority_for(user):
    return SessionAuthority.objects.get_or_create(user_id=user.pk)[0]


def bind_login_session(sender, request, user, **kwargs):
    """Django login (including admin) binds new sessions; legacy sessions are not adopted."""
    with transaction.atomic():
        current = get_user_model().objects.select_for_update().get(pk=user.pk)
        if not current.is_active:
            raise PermissionDenied("Account authority unavailable.")
        authority = authority_for(current)
        request.session[SESSION_REVISION_KEY] = str(authority.revision)
        if not getattr(request, "_declarai_api_login_owned", False):
            AuthenticationEvent.objects.create(
                actor=current,
                actor_snapshot=actor_snapshot(current),
                authority_source="django_login_signal",
                event_type="session_bound",
                outcome="completed",
                session_revision=authority.revision,
                finished_at=timezone.now(),
            )


def _key(purpose, value):
    return salted_hmac("declarai.auth." + purpose, value, secret=settings.SECRET_KEY, algorithm="sha256").hexdigest()


def _take(key, limit, now):
    # PostgreSQL serializes reservations across processes. SQLite is development-only.
    bucket = LoginThrottleBucket.objects.select_for_update().get_or_create(
        key=key, defaults={"window_started_at": now}
    )[0]
    if bucket.window_started_at <= now - timedelta(seconds=settings.DECLARAI_AUTH_LOGIN_WINDOW_SECONDS):
        bucket.window_started_at, bucket.attempts = now, 0
        bucket.blocked_attempts, bucket.denial_recorded = 0, False
    admitted = bucket.attempts < limit
    first_denial = not admitted and not bucket.denial_recorded
    if admitted:
        bucket.attempts += 1
    else:
        bucket.blocked_attempts = min(bucket.blocked_attempts + 1, 2**63 - 1)
        bucket.denial_recorded = True
    bucket.save()
    return admitted, first_denial


def reserve_login(request, username, *, authority_source="browser_password"):
    """Reserve counters and audit before password work. Source blocks allocate no new principals."""
    source = str(request.META.get("REMOTE_ADDR", ""))[:128]
    source_key = _key("source", source)
    principal_key = _key("principal", json.dumps([source, username], separators=(",", ":")))
    now = timezone.now()
    with transaction.atomic():
        admitted, first_denial = _take(source_key, settings.DECLARAI_AUTH_LOGIN_SOURCE_LIMIT, now)
        reason = "login_source_rate_limited"
        if admitted:
            admitted, first_denial = _take(principal_key, settings.DECLARAI_AUTH_LOGIN_PAIR_LIMIT, now)
            reason = "login_principal_rate_limited"
        event = None
        if admitted or first_denial:
            event = AuthenticationEvent.objects.create(
                authority_source=authority_source,
                event_type="login",
                source_key=source_key,
                principal_key=principal_key,
                outcome="pending" if admitted else "denied",
                reason_code="" if admitted else reason,
                finished_at=None if admitted else now,
            )
    return admitted, event


def deny_login(event, reason="invalid_credentials"):
    if (
        AuthenticationEvent.objects.filter(pk=event.pk, outcome="pending").update(
            outcome="denied", reason_code=reason, finished_at=timezone.now()
        )
        != 1
    ):
        raise RuntimeError("Authentication receipt unavailable.")


def complete_login(request, actor, event):
    with transaction.atomic():
        current = get_user_model().objects.select_for_update().get(pk=actor.pk)
        # Password/deactivation changes between authenticate and admission cannot inherit success.
        if not current.is_active or current.password != actor.password:
            deny_login(event, "credentials_changed_during_login")
            return False
        current.backend = actor.backend
        request._declarai_api_login_owned = True
        login(request, current)
        request.session.save()
        revision = authority_for(current).revision
        if (
            AuthenticationEvent.objects.filter(pk=event.pk, outcome="pending").update(
                actor=current,
                actor_snapshot=actor_snapshot(current),
                session_revision=revision,
                outcome="completed",
                finished_at=timezone.now(),
            )
            != 1
        ):
            raise RuntimeError("Authentication receipt unavailable.")
        # Preserve legitimate successful-login retry behavior; the source budget remains bounded.
        LoginThrottleBucket.objects.filter(pk=event.principal_key).update(attempts=0, denial_recorded=False)
    return True


def recorded_logout(request, reason="user_logout", *, event_type="logout"):
    user = request.user if request.user.is_authenticated else None
    previous_id = request.session.get("_auth_user_id")
    subject = (
        {"previous_session_user_id": previous_id}
        if isinstance(previous_id, str) and previous_id.isdecimal() and len(previous_id) <= 19
        else {}
    )
    with transaction.atomic():
        AuthenticationEvent.objects.create(
            actor=user,
            actor_snapshot=actor_snapshot(user),
            subject_snapshot=subject,
            authority_source="browser_session",
            event_type=event_type,
            outcome="completed",
            reason_code=reason,
            finished_at=timezone.now(),
        )
        logout(request)


def revoke_sessions(user, *, request_id, operator_label, deactivate=False):
    """Installation-operator action. An asserted label is not an authenticated human actor."""
    identifier = uuid.UUID(str(request_id))
    specification = {"user_id": user.pk, "operator_label": operator_label, "deactivate": deactivate}
    fingerprint = hashlib.sha256(json.dumps(specification, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def replay(event):
        if event.event_type != "sessions_revoked" or event.request_sha256 != fingerprint:
            raise ValueError("The request identifier is already bound to another operation.")
        return event, True

    try:
        with transaction.atomic():
            current = get_user_model().objects.select_for_update().get(pk=user.pk)
            previous = AuthenticationEvent.objects.filter(pk=identifier).first()
            if previous:
                return replay(previous)
            authority = SessionAuthority.objects.select_for_update().get_or_create(user=current)[0]
            authority.revision, authority.updated_at = uuid.uuid4(), timezone.now()
            authority.save(update_fields=["revision", "updated_at"])
            if deactivate:
                current.is_active = False
                current.save(update_fields=["is_active"])
            cancelled = AssistantActionApproval.objects.filter(
                actor=current, state__in=["prepared", "approved"]
            ).update(state="cancelled", reason_code="operator_sessions_revoked", finished_at=timezone.now())
            event = AuthenticationEvent.objects.create(
                id=identifier,
                subject_snapshot=actor_snapshot(current),
                authority_source="installation_operator",
                operator_label=operator_label,
                event_type="sessions_revoked",
                outcome="completed",
                request_sha256=fingerprint,
                session_revision=authority.revision,
                details={"deactivated": deactivate, "cancelled_actions": cancelled},
                finished_at=timezone.now(),
            )
            return event, False
    except IntegrityError:
        previous = AuthenticationEvent.objects.filter(pk=identifier).first()
        if previous:
            return replay(previous)
        raise
