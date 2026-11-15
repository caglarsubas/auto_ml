"""Preprocessing receipts preserve exact evidence under concurrency and retry."""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pandas as pd
import pytest
from django.db import connections
from django.test import Client
from rest_framework.test import APIRequestFactory

from access_control import projects
from access_control.models import Project, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from modeling.split_contract import split_path
from preprocessing import stage_publication as stages
from preprocessing.views import PreprocessingDatqDetailView, PreprocessingRunView, PreprocessingStatusView


pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def stage_dataset(_use_tmp_media, settings):
    source = Path(settings.MEDIA_ROOT) / 'data_files' / 'stage.csv'
    pd.DataFrame({'x': range(48), 'Target': [0, 1] * 24,
                  'date': pd.date_range('2024-01-01', periods=48)}).to_csv(source, index=False)
    return Declaration.objects.create(name='stages', original_name=source.name, file='data_files/stage.csv')


def _run(file_id, identifier, *, options=None, percent=25):
    request = APIRequestFactory().post('/api/preprocessing/run/', {
        'file_id': file_id, 'request_id': str(identifier), 'options': options or [],
        'split': {'strategy': 'random', 'percent': percent},
    }, format='json')
    return PreprocessingRunView.as_view()(request)


def _status(file_id, **selectors):
    request = APIRequestFactory().get(f'/api/preprocessing/status/{file_id}/', selectors)
    return PreprocessingStatusView.as_view()(request, file_id=file_id)


def test_concurrent_preprocessing_versions_keep_disjoint_result_and_fitted_state(stage_dataset, monkeypatch):
    before_publish = Barrier(2)
    original = stages._write_json

    def synchronize(path, payload):
        if path.name.endswith('.result.json'):
            before_publish.wait(timeout=15)
        return original(path, payload)

    def run(identifier, options, percent):
        try:
            response = _run(stage_dataset.pk, identifier, options=options, percent=percent)
            assert response.status_code == 200, response.data
            return response.data
        finally:
            connections.close_all()

    monkeypatch.setattr(stages, '_write_json', synchronize)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(run, uuid.uuid4(), [28], 25)
        b = pool.submit(run, uuid.uuid4(), [30], 50)
        results = [a.result(timeout=25), b.result(timeout=25)]

    assert results[0]['processed_file'] != results[1]['processed_file']
    assert _status(stage_dataset.pk).data['result'] in results
    sizes = []
    for result in results:
        stage = stages.stage_path(stage_dataset.pk, result['preprocessing_version_id'])
        verified, _, purifier = stages.load_stage(stage, stage_dataset.pk)
        assert verified['recipe_id'] == result['purifier_recipe_id']
        assert purifier['path'] == result['purifier_artifact']
        sizes.append(purifier['n_fit'])
        assert _status(stage_dataset.pk, processed_file=result['processed_file']).data['result'] == result
        detail = PreprocessingDatqDetailView.as_view()(APIRequestFactory().post('/api/preprocessing/datq_detail/', {
            'file_id': stage_dataset.pk, 'processed_file': result['processed_file'], 'column': 'x',
            'split': {'strategy': 'oot', 'date_column': 'date', 'cutoff': '2024-01-03'},
        }, format='json'))
        assert detail.status_code == 200, detail.data
        assert detail.data['train_count'] == purifier['n_fit']
    assert sizes[0] != sizes[1]


def test_interrupted_projection_replays_same_request_without_readopting_older_version(stage_dataset, monkeypatch):
    file_id = stage_dataset.pk
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    prior = _run(file_id, a).data
    assert _status(file_id, request_id=str(b)).data == {'status': 'not_started'}
    original = stages.replace_projection

    def interrupt(source, destination):
        if Path(destination) == stages.result_path(file_id):
            raise OSError('synthetic interruption before latest pointer')
        return original(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(stages, 'replace_projection', interrupt)
        assert _run(file_id, b, percent=50).status_code == 500
    assert _status(file_id).data['result'] == prior
    completed = _status(file_id, request_id=str(b)).data['result']
    pin = stages.stage_paths(stages.stage_path(file_id, b))['receipt'].read_bytes()
    assert _run(file_id, b, percent=50).data == completed
    assert _status(file_id).data['result'] == completed
    def interrupt_alias(source, destination):
        if Path(destination) == Path(split_path(file_id)):
            raise OSError('synthetic interruption refreshing a compatibility file')
        return original(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(stages, 'replace_projection', interrupt_alias)
        assert _run(file_id, c).status_code == 500
    newer = _status(file_id).data['result']
    assert newer['preprocessing_version_id'] == c.hex
    assert _run(file_id, c).data == newer
    assert Path(split_path(file_id)).read_bytes() == stages.stage_paths(stages.stage_path(file_id, c))['split'].read_bytes()
    assert _run(file_id, b, percent=50).data == completed
    assert stages.stage_paths(stages.stage_path(file_id, b))['receipt'].read_bytes() == pin
    assert _status(file_id).data['result'] == newer
    assert _run(file_id, b, percent=25).status_code == 409


@pytest.mark.auth_boundary
def test_exact_status_rejects_corruption_and_keeps_old_provenance_unverified(stage_dataset, django_user_model):
    file_id, identifier = stage_dataset.pk, uuid.uuid4()
    ProjectPolicy.objects.create()
    owning, foreign = Project.objects.create(name='owner'), Project.objects.create(name='foreign')
    projects.bind_dataset(stage_dataset, owning.pk)
    owner, outsider = (django_user_model.objects.create_user(name) for name in ('owner', 'outsider'))
    ProjectMembership.objects.create(actor=owner, project=owning, role='developer')
    ProjectMembership.objects.create(actor=outsider, project=foreign, role='developer')
    client, denied = Client(), Client()
    client.force_login(owner)
    denied.force_login(outsider)
    path = f'/api/preprocessing/status/{file_id}/'
    finished = client.post('/api/preprocessing/run/', {
        'file_id': file_id, 'request_id': str(identifier), 'options': [29],
    }, content_type='application/json')
    assert finished.status_code == 200, finished.content
    result = finished.json()
    assert client.get(path, {'request_id': str(identifier)}).json()['result'] == result
    assert denied.get(path, {'processed_file': result['processed_file']}).status_code == 403
    assert denied.get(path, {'request_id': str(identifier)}).status_code == 403
    parts = stages.stage_paths(stages.stage_path(file_id, identifier))
    parts['datq'].write_text('[] ', encoding='utf-8')
    assert client.get(path).status_code == 409
    assert client.get(path, {'processed_file': result['processed_file']}).status_code == 409

    historical = {'file_id': file_id, 'processed_file': 'data_files/stage.csv'}
    stages.result_path(file_id).write_text(json.dumps(historical), encoding='utf-8')
    assert client.get(path).json()['result'] == {**historical, 'preprocessing_provenance': 'historical_unverified'}
    assert client.get(path, {'processed_file': result['processed_file']}).status_code == 409
