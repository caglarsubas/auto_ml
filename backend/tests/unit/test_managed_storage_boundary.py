"""Real HTTP storage checks; authentication and reference policy remain enabled."""
import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from declaration.models import Declaration

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db]


@pytest.fixture
def actor_client(django_user_model):
    django_user_model.objects.create_user(username='storage-actor', password='synthetic-storage-test-pass')
    client = APIClient(enforce_csrf_checks=True)
    token = client.get('/api/auth/session/').json()['csrf_token']
    login = client.post('/api/auth/login/', {'username': 'storage-actor', 'password': 'synthetic-storage-test-pass'},
        format='json', HTTP_X_CSRFTOKEN=token)
    assert login.status_code == 200
    client.credentials(HTTP_X_CSRFTOKEN=login.json()['csrf_token'])
    return client


def forbidden(*args, **kwargs):
    raise AssertionError('No table/model loader may inspect rejected input')


@pytest.mark.parametrize('endpoint', ['encoding/analyze/', 'encoding/apply/', 'preprocessing/datq_detail/',
    'preprocessing/datq_timeseries/', 'modeling/start/', 'modeling/feature-explainability/', 'feature-card'])
@pytest.mark.parametrize('reference', ['absolute', 'traversal', 'symlink', 'hidden', 'unsupported_type'])
def test_rejected_table_references_stop_before_read(actor_client, _use_tmp_media, media_root, tmp_path,
                                                   monkeypatch, endpoint, reference):
    external = tmp_path / 'private-host.csv'
    external.write_text('private-host-sentinel\n')
    if reference == 'absolute':
        value = str(external)
    elif reference == 'traversal':
        value = '../private-host.csv'
    elif reference == 'symlink':
        (media_root / 'escape.csv').symlink_to(external)
        value = 'escape.csv'
    elif reference == 'hidden':
        value = '.private/secret.csv'
    else:
        value = 'models/untrusted.pkl'
    monkeypatch.setattr('pandas.read_csv', forbidden)
    monkeypatch.setattr('pandas.read_excel', forbidden)
    if endpoint == 'feature-card':
        response = actor_client.get('/api/feature-card/42/get_feature_info/', {'column': 'x', 'file_override': value})
    else:
        response = actor_client.post('/api/'+endpoint, {'file_id': 42, 'processed_file': value,
            'column': 'x', 'date_column': 'date', 'feature_name': 'x'}, format='json')
    assert response.status_code == 400
    assert response.json()['error_code'] == 'managed_storage_reference_invalid'
    assert 'private-host-sentinel' not in response.content.decode()
    assert str(tmp_path) not in response.content.decode()


@pytest.mark.parametrize('value', [True, False, -1, 0, 1.5, '01', '../escape', '1/../../escape', 2**64, '9' * 5000])
def test_file_identifiers_cannot_control_generated_paths(actor_client, _use_tmp_media, media_root, value):
    response = actor_client.post('/api/encoding/apply/', {'file_id': value, 'processed_file': 'data_files/a.csv'}, format='json')
    assert response.status_code == 400
    assert response.json()['error_code'] == 'managed_storage_reference_invalid'
    assert not (media_root / 'encoded_files').exists()


@pytest.mark.parametrize('query', ['file_id=43', 'file_id=42&file_id=42'])
def test_conflicting_or_duplicate_ids_are_rejected(actor_client, _use_tmp_media, query):
    response = actor_client.get('/api/modeling/status/42/?'+query)
    assert response.status_code == 400
    assert response.json()['error_code'] == 'managed_storage_reference_invalid'


def test_query_and_body_identifiers_must_agree(actor_client, _use_tmp_media):
    response = actor_client.post('/api/encoding/analyze/?file_id=43', {'file_id': 42, 'processed_file': 'data_files/a.csv'}, format='json')
    assert response.status_code == 400


@pytest.mark.parametrize('path', ['models/custom.json', 'data_files/customer.csv'])
def test_unverified_model_overrides_cannot_load(actor_client, _use_tmp_media, media_root, monkeypatch, path):
    artifact = media_root / path
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text('unverified model')
    monkeypatch.setattr('xgboost.Booster.load_model', forbidden)
    monkeypatch.setattr('modeling.views.load_development_data', forbidden)
    response = actor_client.post('/api/modeling/feature-explainability/', {'file_id': 42,
        'feature_name': 'x', 'model_path': path}, format='json')
    assert response.status_code == 409
    assert response.json()['error_code'] == 'unverified_model_override'


def test_model_override_and_explicit_execution_cannot_disagree(actor_client, _use_tmp_media, monkeypatch):
    monkeypatch.setattr('modeling.views.load_execution', forbidden)
    response = actor_client.post('/api/modeling/feature-explainability/', {'file_id': 42, 'feature_name': 'x',
        'execution_id': '00000000-0000-0000-0000-000000000001',
        'model_path': 'execution_runs/00000000-0000-0000-0000-000000000002/models/model.json'}, format='json')
    assert response.status_code == 409
    assert response.json()['error_code'] == 'unverified_model_override'


@pytest.mark.parametrize('absolute', [False, True])
def test_managed_tables_and_encoding_remain_usable(actor_client, _use_tmp_media, media_root, absolute):
    table = media_root / 'data_files/encoding.csv'
    table.write_text('Value,Target\n1,0\n2,1\n3,0\n')
    value = str(table) if absolute else 'data_files/encoding.csv'
    payload = {'file_id': '42', 'processed_file': value, 'plan': []}
    assert actor_client.post('/api/encoding/analyze/', payload, format='json').status_code == 200
    first = actor_client.post('/api/encoding/apply/', payload, format='json')
    second = actor_client.post('/api/encoding/apply/', payload, format='json')
    assert first.status_code == second.status_code == 200
    assert first.json()['encoded_file'] != second.json()['encoded_file']
    assert (media_root / first.json()['encoded_file']).is_file()
    assert (media_root / second.json()['encoded_file']).is_file()


def upload(client, value):
    file = BytesIO(f'Value,Target\n{value},0\n{value+1},1\n{value+2},0\n'.encode())
    file.name = 'input.csv'
    return client.post('/api/declaration/', {'file': file, 'column_separator': 'comma'}, format='multipart')


def test_repeated_uploads_preserve_the_earlier_dataset(actor_client, _use_tmp_media, media_root):
    first = upload(actor_client, 10)
    assert first.status_code == 201
    declaration = Declaration.objects.get(pk=first.json()['id'])
    path = Path(declaration.get_file_path())
    original = path.read_bytes()
    second = upload(actor_client, 100)
    assert second.status_code == 201
    later = Declaration.objects.get(pk=second.json()['id'])
    assert declaration.file.name != later.file.name
    assert path.read_bytes() == original
    assert Path(later.get_file_path()).read_bytes() != original


def test_filename_collision_cannot_overwrite_upload(actor_client, _use_tmp_media, monkeypatch):
    monkeypatch.setattr('declaration.views.uuid.uuid4', lambda: SimpleNamespace(hex='fixed-collision'))
    first = upload(actor_client, 10)
    assert first.status_code == 201
    path = Path(Declaration.objects.get().get_file_path())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    response = upload(actor_client, 100)
    assert response.status_code == 409
    assert response.json()['error_code'] == 'file_publication_conflict'
    assert Declaration.objects.count() == 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_ambiguous_legacy_fallback_does_not_choose_another_dataset(_use_tmp_media, media_root):
    declaration = Declaration.objects.create(name='legacy', original_name='legacy.csv', file='data_files/missing.csv')
    for name in ['processed_a_legacy.csv', 'processed_b_legacy.csv']:
        (media_root / 'data_files' / name).write_text('Value\n1\n')
    assert declaration.get_file_path() is None


def test_declaration_metadata_cannot_escape_managed_storage(_use_tmp_media, tmp_path):
    from rest_framework.exceptions import ValidationError
    path = tmp_path / 'host.csv'
    path.write_text('private')
    declaration = Declaration.objects.create(name='unsafe', original_name='host.csv', file=str(path))
    with pytest.raises(ValidationError):
        declaration.get_file_path()


def encoding_payload(media_root):
    (media_root / 'data_files/encoding.csv').write_text('Value,Target\n1,0\n2,1\n3,0\n')
    return {'file_id': 42, 'processed_file': 'data_files/encoding.csv', 'plan': []}


def test_encoding_collision_preserves_csv_and_metadata(actor_client, _use_tmp_media, media_root, monkeypatch):
    monkeypatch.setattr('encoding.views.uuid.uuid4', lambda: SimpleNamespace(hex='fixed-collision'))
    payload = encoding_payload(media_root)
    first = actor_client.post('/api/encoding/apply/', payload, format='json')
    assert first.status_code == 200
    path = media_root / first.json()['encoded_file']
    metadata = path.with_suffix('.meta.json')
    before = (path.read_bytes(), metadata.read_bytes())
    response = actor_client.post('/api/encoding/apply/', payload, format='json')
    assert response.status_code == 409
    assert response.json()['error_code'] == 'file_publication_conflict'
    assert (path.read_bytes(), metadata.read_bytes()) == before


def test_encoding_metadata_failure_does_not_publish_csv(actor_client, _use_tmp_media, media_root, monkeypatch):
    payload = encoding_payload(media_root)
    def broken_metadata(*args, **kwargs):
        raise OSError('Synthetic metadata writer failure')
    monkeypatch.setattr('encoding.views.json.dump', broken_metadata)
    response = actor_client.post('/api/encoding/apply/', payload, format='json')
    assert response.status_code == 500
    assert 'encoded_file' not in response.json()
    assert not list((media_root / 'encoded_files').glob('*.csv'))


@pytest.mark.parametrize('operation', ['upload', 'encoding'])
def test_generated_outputs_cannot_follow_external_directory_symlinks(actor_client, _use_tmp_media,
                                                                    media_root, tmp_path, operation):
    external = tmp_path / 'external-output'
    external.mkdir()
    payload = encoding_payload(media_root)
    directory = media_root / ('data_files' if operation == 'upload' else 'encoded_files')
    if directory.exists():
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
    directory.symlink_to(external, target_is_directory=True)
    response = upload(actor_client, 10) if operation == 'upload' else actor_client.post(
        '/api/encoding/apply/', payload, format='json')
    assert response.status_code == 400
    assert response.json()['error_code'] == 'managed_storage_reference_invalid'
    assert not list(external.iterdir())


@pytest.mark.parametrize('kind', ['directory', 'fifo', 'nul', 'windows', 'hidden_alias'])
def test_nonregular_and_hidden_alias_inputs_do_not_reach_readers(actor_client, _use_tmp_media,
                                                               media_root, monkeypatch, kind):
    import os
    path = media_root / 'bad.csv'
    value = 'bad.csv'
    if kind == 'directory':
        path.mkdir()
    elif kind == 'fifo':
        os.mkfifo(path)
    elif kind == 'nul':
        value = 'bad\x00.csv'
    elif kind == 'windows':
        value = '..\\private.csv'
    else:
        hidden = media_root / '.hidden.csv'
        hidden.write_text('private')
        path.symlink_to(hidden)
    monkeypatch.setattr('pandas.read_csv', forbidden)
    response = actor_client.post('/api/encoding/analyze/', {'file_id': 42, 'processed_file': value}, format='json')
    assert response.status_code == 400
    assert response.json()['error_code'] == 'managed_storage_reference_invalid'
