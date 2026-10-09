"""Server-side sessions and project-scoped artifact downloads."""
import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import DatabaseError
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, JsonResponse, Http404
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from access_control.session_authority import reserve_login, deny_login, complete_login, recorded_logout


def _session(request):
    user = request.user
    return {'authenticated': bool(user.is_authenticated), 'csrf_token': get_token(request),
            'user': {'id': user.pk, 'username': user.get_username()} if user.is_authenticated else None}


@require_http_methods(['GET'])
@ensure_csrf_cookie
def session_status(request):
    response = JsonResponse(_session(request))
    response['Cache-Control'] = 'no-store'
    return response


@require_http_methods(['POST'])
@csrf_protect
def session_login(request):
    try:
        if len(request.body) > 16384:
            raise ValueError()
        data = json.loads(request.body)
        username, password = data.get('username'), data.get('password')
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 254 or len(password) > 4096:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        return JsonResponse({'error': 'Supply username and password.'}, status=400)
    try:
        admitted, event = reserve_login(request, username)
        if not admitted:
            response = JsonResponse({'error': 'Too many attempts. Try again later.'}, status=429)
            response['Retry-After'] = str(settings.DECLARAI_AUTH_LOGIN_WINDOW_SECONDS)
            response['Cache-Control'] = 'no-store'
            return response
        request._declarai_login_event = event
        user = authenticate(request, username=username, password=password)
        if user is None:
            deny_login(event)
            return JsonResponse({'error': 'Invalid username or password.'}, status=401)
        if not complete_login(request, user, event):
            return JsonResponse({'error': 'Invalid username or password.'}, status=401)
    except (DatabaseError, RuntimeError, PermissionDenied):
        # Do not mint or save a browser login whose authority could not be recorded.
        request.session.clear()
        response = JsonResponse({'error': 'Authentication authority is unavailable. Try again when the service recovers.',
            'error_code': 'authentication_authority_unavailable'}, status=503)
        response['Cache-Control'] = 'no-store'
        return response
    response = JsonResponse(_session(request))
    response['Cache-Control'] = 'no-store'
    return response


@require_http_methods(['POST'])
@csrf_protect
def session_logout(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Sign in first.'}, status=401)
    try:
        recorded_logout(request)
    except DatabaseError:
        return JsonResponse({'error': 'Logout authority could not be recorded. Try again when the service recovers.',
            'error_code': 'authentication_authority_unavailable'}, status=503)
    return JsonResponse(_session(request))


@require_http_methods(['GET', 'HEAD'])
def protected_media(request, path):
    """No public artifact storage or native-pickle download endpoint."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Sign in to access artifacts.'}, status=403)
    from access_control import projects
    try:
        if projects.governed():
            scope = projects.path_authority(request.user.pk, path)
            event = projects.audit(request.user, 'media_access', {'scope': scope}, scope['project_id'], outcome='started')
            request._project_event = event.pk
            request._project_scopes = [scope]
    except projects.ProjectDenied as exc:
        try:
            projects.audit(request.user, 'media_access', {}, outcome='denied', reason=exc.code)
        except DatabaseError:
            return JsonResponse({'error_code': 'project_authority_unavailable'}, status=503)
        return JsonResponse({'error': str(exc), 'error_code': exc.code}, status=403)
    except DatabaseError:
        return JsonResponse({'error': 'Project authority is unavailable.', 'error_code': 'project_authority_unavailable'}, status=503)
    root = Path(settings.MEDIA_ROOT).resolve()
    artifact = (root / path).resolve()
    if (not artifact.is_relative_to(root) or not artifact.is_file()
            or any(part.startswith('.') for part in Path(path).parts)
            or artifact.suffix.lower() in ('.pkl', '.pickle', '.joblib', '.py')):
        raise Http404()
    response = FileResponse(artifact.open('rb'))
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
