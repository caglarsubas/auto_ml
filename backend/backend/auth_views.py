"""Server-side sessions. Project authorization is a separate release gate."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.http import FileResponse, JsonResponse, Http404
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods


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
        data = json.loads(request.body)
        username, password = data.get('username'), data.get('password')
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 254 or len(password) > 4096:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        return JsonResponse({'error': 'Supply username and password.'}, status=400)
    key = 'login-attempt:' + hashlib.sha256((request.META.get('REMOTE_ADDR', '') + ':' + username).encode()).hexdigest()
    cache.add(key, 0, timeout=60)
    if cache.incr(key) > 10:
        return JsonResponse({'error': 'Too many attempts. Try again later.'}, status=429)
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({'error': 'Invalid username or password.'}, status=401)
    login(request, user)
    cache.delete(key)
    response = JsonResponse(_session(request))
    response['Cache-Control'] = 'no-store'
    return response


@require_http_methods(['POST'])
@csrf_protect
def session_logout(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Sign in first.'}, status=401)
    logout(request)
    return JsonResponse(_session(request))


@require_http_methods(['GET', 'HEAD'])
def protected_media(request, path):
    """No public artifact storage or native-pickle download endpoint."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Sign in to access artifacts.'}, status=403)
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
