"""The default password backend shares admission with Django admin logins."""

from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from access_control.authority import actor_snapshot
from access_control.models import AuthenticationEvent, LoginThrottleBucket
from access_control.session_authority import reserve_login, deny_login


class GovernedModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Non-HTTP callers do not establish a browser session. Django login still
        # requires a recorded binding through its signal before session storage.
        if request is None or getattr(request, "_declarai_login_event", None):
            return super().authenticate(request, username=username, password=password, **kwargs)
        admitted, event = reserve_login(request, username, authority_source="django_password_backend")
        if not admitted:
            raise PermissionDenied("Login admission denied.")
        actor = super().authenticate(request, username=username, password=password, **kwargs)
        if actor is None:
            deny_login(event)
        else:
            # Credential validation is distinct from staff permission and session binding.
            with transaction.atomic():
                if (
                    AuthenticationEvent.objects.filter(pk=event.pk, outcome="pending").update(
                        actor=actor,
                        actor_snapshot=actor_snapshot(actor),
                        event_type="credentials_validated",
                        outcome="completed",
                        finished_at=timezone.now(),
                    )
                    != 1
                ):
                    raise RuntimeError("Authentication receipt unavailable.")
                LoginThrottleBucket.objects.filter(pk=event.principal_key).update(attempts=0, denial_recorded=False)
        return actor
