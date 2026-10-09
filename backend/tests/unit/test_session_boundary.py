"""Exercise actual session middleware, permissions and CSRF on HTTP routes."""
import pytest
from rest_framework.test import APIClient

pytestmark = [pytest.mark.unit, pytest.mark.django_db, pytest.mark.auth_boundary]


@pytest.fixture
def csrf_session_client(django_user_model):
    django_user_model.objects.create_user(username='mutation-test', password='synthetic-session-test-pass')
    client = APIClient(enforce_csrf_checks=True)
    csrf = client.get('/api/auth/session/').json()['csrf_token']
    login = client.post('/api/auth/login/', {
        'username': 'mutation-test', 'password': 'synthetic-session-test-pass',
    }, format='json', HTTP_X_CSRFTOKEN=csrf)
    assert login.status_code == 200
    client.credentials(HTTP_X_CSRFTOKEN=login.json()['csrf_token'])
    return client


@pytest.mark.parametrize('path', ['/api/modeling/sfs/start/', '/api/modeling/hyperparam/start/'])
@pytest.mark.parametrize('request_format', ['json', 'multipart'])
def test_session_csrf_parsing_preserves_modeling_payload(csrf_session_client, path, request_format):
    response = csrf_session_client.post(path, {}, format=request_format)
    assert response.status_code == 400
    assert response.json()['error'] == 'file_id is required'
    response = csrf_session_client.post(path, {'file_id': 999999999}, format=request_format)
    assert response.status_code == 404
    assert 'Training data not found' in response.json()['error']


@pytest.mark.parametrize('method,path', [
    ('post', '/api/modeling/sfs/start/'), ('post', '/api/modeling/hyperparam/start/'),
    ('post', '/api/pipeline/create/'), ('put', '/api/pipeline/999999999/'),
])
@pytest.mark.parametrize('payload', ['{"broken":', '[]'])
def test_session_mutations_reject_malformed_or_non_object_json(csrf_session_client, method, path, payload):
    response = getattr(csrf_session_client, method)(path, payload, content_type='application/json')
    assert response.status_code == 400
    if payload == '[]':
        assert response.json()['error'] == 'Request payload must be an object'
    else:
        assert 'JSON parse error' in response.json()['detail']


def test_pipeline_lifecycle_uses_session_parsed_json(csrf_session_client):
    created = csrf_session_client.post('/api/pipeline/create/', {
        'name': 'session-pipeline', 'state': {'modeling': {'substep': 'encoding_completed'}},
    }, format='json')
    assert created.status_code == 201
    path = f'/api/pipeline/{created.json()["id"]}/'
    changed = csrf_session_client.put(path, {
        'current_step': 'modeling', 'state': {'modeling': {'substep': 'modeling_started'}},
    }, format='json')
    assert changed.status_code == 200
    assert changed.json()['current_step'] == 'modeling'
    assert csrf_session_client.get(path).json()['state']['modeling']['substep'] == 'modeling_started'
    assert csrf_session_client.delete(path).status_code == 200
    assert csrf_session_client.get(path).status_code == 404


@pytest.mark.parametrize('method,path', [
    ('get', '/api/declaration/'), ('get', '/api/pipeline/'),
    ('get', '/api/modeling/status/1/'), ('get', '/api/evaluation/status/1/'),
    ('get', '/api/deployment/status/1/'), ('get', '/api/ai-assistant/models/'),
    ('post', '/api/modeling/start/'), ('post', '/api/preprocessing/run/'),
    ('post', '/api/evaluation/run/'), ('post', '/api/deployment/score/'),
    ('post', '/api/ai-assistant/execute-action/'), ('post', '/api/evaluation/pack/'),
])
def test_anonymous_requests_are_blocked(method, path):
    response = getattr(APIClient(), method)(path, {}, format='json')
    assert response.status_code == 403


def test_signin_csrf_session_rotation_and_logout(django_user_model):
    django_user_model.objects.create_user(username='developer-test', password='synthetic-session-test-pass')
    client = APIClient(enforce_csrf_checks=True)
    credentials = {'username': 'developer-test', 'password': 'synthetic-session-test-pass'}
    assert client.post('/api/auth/login/', credentials, format='json').status_code == 403
    session = client.get('/api/auth/session/').json()
    assert session['authenticated'] is False
    login = client.post('/api/auth/login/', credentials, format='json', HTTP_X_CSRFTOKEN=session['csrf_token'])
    assert login.status_code == 200
    assert login.json()['authenticated'] is True
    assert login.json()['csrf_token'] != session['csrf_token']
    assert client.get('/api/declaration/').status_code == 200
    assert client.post('/api/modeling/start/', {}, format='json').status_code == 403
    assert client.post('/api/modeling/start/', {}, format='json', HTTP_X_CSRFTOKEN=login.json()['csrf_token']).status_code == 400
    assert client.post('/api/auth/logout/', {}, format='json').status_code == 403
    assert client.post('/api/auth/logout/', {}, format='json', HTTP_X_CSRFTOKEN=login.json()['csrf_token']).status_code == 200
    assert client.get('/api/declaration/').status_code == 403


def test_invalid_and_inactive_credentials_cannot_authenticate(django_user_model):
    django_user_model.objects.create_user(username='inactive-test', password='synthetic-session-test-pass', is_active=False)
    client = APIClient(enforce_csrf_checks=True)
    csrf = client.get('/api/auth/session/').json()['csrf_token']
    for username in ('unknown-test', 'inactive-test'):
        response = client.post('/api/auth/login/', {'username': username, 'password': 'synthetic-session-test-pass'}, format='json', HTTP_X_CSRFTOKEN=csrf)
        assert response.status_code == 401
    assert client.get('/api/auth/session/').json()['authenticated'] is False


# FileResponse.close emits request_finished. Exercise real autocommit rather
# than closing PostgreSQL inside pytest-django's wrapping atomic transaction.
@pytest.mark.django_db(transaction=True)
def test_artifacts_require_session_and_block_internal_serialization(_use_tmp_media, settings, django_user_model):
    from pathlib import Path
    root = Path(settings.MEDIA_ROOT)
    (root / 'data_files' / 'public.csv').write_text('x\n1\n')
    (root / 'private.pkl').write_bytes(b'not a pickle')
    client = APIClient()
    assert client.get('/media/data_files/public.csv').status_code == 403
    user = django_user_model.objects.create_user(username='artifact-test', password='synthetic-session-test-pass')
    client.force_login(user)
    response = client.get('/media/data_files/public.csv')
    assert response.status_code == 200
    assert response['Cache-Control'] == 'private, no-store'
    response.close()
    assert client.get('/media/private.pkl').status_code == 404
    assert client.get('/media/../outside.csv').status_code == 404
