"""Reject stale/unbound browser authority before protected handlers run."""

from django.db import DatabaseError
from django.http import JsonResponse

from access_control.models import SessionAuthority
from access_control.session_authority import SESSION_REVISION_KEY, recorded_logout


class SessionAuthorityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            if request.user.is_authenticated:
                revision = request.session.get(SESSION_REVISION_KEY)
                current = (
                    SessionAuthority.objects.filter(user_id=request.user.pk).values_list("revision", flat=True).first()
                )
                if not revision or not current or revision != str(current):
                    recorded_logout(
                        request,
                        "session_revision_unavailable" if not revision else "session_revision_revoked",
                        event_type="session_rejected",
                    )
                else:
                    request.user._declarai_session_revision = revision
            elif request.session.get("_auth_user_id"):
                recorded_logout(request, "session_authentication_invalidated", event_type="session_rejected")
        except DatabaseError:
            response = JsonResponse(
                {
                    "error": "Authentication authority is unavailable. Try again when the service recovers.",
                    "error_code": "authentication_authority_unavailable",
                },
                status=503,
            )
            response["Cache-Control"] = "no-store"
            return response
        return self.get_response(request)
