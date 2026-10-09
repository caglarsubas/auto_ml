"""Final-outcome reuse, audit failure and exact export regressions."""
import hashlib
import io
import json
import pickle
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from django.db import connections
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from declaration.models import Declaration
from evaluation.views import EvaluationPackView, EvaluationRunView, HoldoutHistoryView
from modeling.execution_artifacts import begin_execution, digest_file, execution_root, publish_execution
from modeling.holdout_evidence import holdout_history, holdout_spec, reserve_holdout_access, verify_holdout_spec
from modeling.models import HoldoutAccess
from modeling.views import ChampionPromoteView, ModelingStartView
from tests.unit.test_governed_foundation import declaration

pytestmark = pytest.mark.unit


def spec(rows=(1, 2, 3), source='a' * 64, target='outcome'):
    return holdout_spec(source, target, rows, 'raw_snapshot')


def test_identity_is_order_independent_and_does_not_include_model_choices():
    assert spec() == spec((3, 1, 2))
    assert spec()['sha256'] != spec((3, 2, 4))['sha256']
    assert spec()['sha256'] != spec(target='another_outcome')['sha256']
    assert spec()['sha256'] == holdout_spec('a' * 64, 'outcome', [1, 2, 3], 'processed_snapshot')['sha256']
    assert 'class_mapping' not in spec() and 'objective' not in spec()


@pytest.mark.parametrize('rows', [[], [1, 1], [False], [1.2], [None], [{'row': 1}]])
def test_invalid_membership_is_rejected(rows):
    with pytest.raises(ValueError):
        spec(rows)


@pytest.mark.parametrize('field,value', [('sha256', '0' * 64), ('rows', [9]),
    ('source_sha256', 'b' * 64), ('schema_version', 2)])
def test_modified_identity_is_rejected(field, value):
    changed = {**spec(), field: value}
    with pytest.raises(ValueError):
        verify_holdout_spec(changed)


@pytest.mark.django_db
def test_exact_overlap_unknown_and_different_source_target_are_distinct(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    actor = None
    reserve_holdout_access(spec(), 1, uuid.uuid4(), actor, {'threshold': .5})
    reserve_holdout_access(spec((2, 3, 4)), 2, uuid.uuid4(), actor, {'threshold': .7})
    reserve_holdout_access(spec((4, 5)), 1, uuid.uuid4(), actor, {})
    reserve_holdout_access(spec(target='other'), 1, uuid.uuid4(), actor, {})
    reserve_holdout_access(spec(source='b' * 64), 3, uuid.uuid4(), actor, {})
    old = HoldoutAccess.objects.create(file_id=1)
    history = holdout_history(spec(), 1, limit=2)
    assert history['same_final_rows_accesses'] == 1
    assert history['overlapping_final_rows_accesses'] == 1
    assert history['unknown_history_accesses'] == 1
    assert history['total_related_accesses'] == 3
    assert history['records'][1]['overlap_rows'] == 2
    assert history['next_offset'] == 2
    tail = holdout_history(spec(), 1, offset=2)
    assert tail['records'][0]['access_id'] == str(old.pk)
    assert tail['records'][0]['attempt_state'] == 'historical_unknown'
    assert holdout_history(None, 1)['identity_status'] == 'historical_unverified'


@pytest.mark.django_db(transaction=True)
def test_concurrent_reservations_cannot_both_report_no_previous_access(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    def reserve(index):
        try:
            _, history = reserve_holdout_access(spec(), index + 1, uuid.uuid4(), None, {})
            return history['same_final_rows_accesses']
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = list(pool.map(reserve, range(4)))
    assert sorted(counts) == [0, 1, 2, 3]
    assert HoldoutAccess.objects.count() == 4


@pytest.mark.django_db
def test_actor_identity_survives_account_deletion(settings, tmp_path, django_user_model):
    settings.MEDIA_ROOT = str(tmp_path)
    user = django_user_model.objects.create_user(username='independent-reviewer')
    receipt, _ = reserve_holdout_access(spec(), 1, uuid.uuid4(), user, {})
    actor_id = user.pk
    user.delete()
    receipt.refresh_from_db()
    assert receipt.actor is None
    assert receipt.actor_snapshot == {'id': actor_id, 'username': 'independent-reviewer'}


@pytest.fixture
def trained(_use_tmp_media, settings, db):
    frame = pd.DataFrame({'x': np.linspace(-2, 2, 160), 'other': np.random.normal(size=160),
                          'outcome': ['bad', 'good'] * 80})
    relative = 'data_files/holdout.csv'
    frame.to_csv(Path(settings.MEDIA_ROOT) / relative, index=False)
    file = Declaration.objects.create(name='holdout', original_name='holdout.csv', file=relative)
    request = APIRequestFactory().post('/modeling/start/', {'file_id': file.pk,
        'processed_file': relative, 'algorithm': 'logistic_regression',
        'business_understanding': declaration()}, format='json')
    response = ModelingStartView.as_view()(request)
    assert response.status_code == 200, response.data
    return file.pk, response.data


def assess(file_id, execution_id, **kwargs):
    return EvaluationRunView.as_view()(APIRequestFactory().post('/evaluation/run/',
        {'file_id': file_id, 'execution_id': execution_id, **kwargs}, format='json'))


def test_assessed_parent_cannot_reset_access_history_by_changing_candidate(trained, settings):
    file_id, parent = trained
    first = assess(file_id, parent['execution_id'])
    assert first.status_code == 200, first.data
    assert first.data['evaluation']['holdout_history']['same_final_rows_accesses'] == 0
    child = ChampionPromoteView.as_view()(APIRequestFactory().post('/modeling/champion/',
        {'file_id': file_id, 'execution_id': parent['execution_id'], 'features': ['x']}, format='json'))
    assert child.status_code == 200, child.data
    assert child.data['model']['holdout_spec'] == parent['model']['holdout_spec']
    # Candidate publication did not deserialize or assess final labels.
    assert HoldoutAccess.objects.count() == 1
    second = assess(file_id, child.data['execution_id'], threshold=.8)
    assert second.status_code == 200, second.data
    history = second.data['evaluation']['holdout_history']
    assert history['same_final_rows_accesses'] == 1
    assert history['records'][0]['execution_id'] == parent['execution_id']
    assert history['records'][0]['attempt_state'] == 'completed'
    assert second.data['model_card']['sections']['final_outcome_access']['evidence_status'] == 'exploratory'
    assert HoldoutAccess.objects.get(pk=second.data['evaluation']['holdout_access_id']).parameters['threshold'] == .8
    assert second.data['evaluation']['evidence_status'] == 'exploratory'


def test_receipt_failure_prevents_any_deserialization(trained, monkeypatch):
    file_id, parent = trained
    def fail(*args, **kwargs):
        raise RuntimeError('audit storage unavailable')
    def forbidden(*args, **kwargs):
        raise AssertionError('Outcome/development input cannot open without an access reservation')
    monkeypatch.setattr(HoldoutAccess.objects, 'create', fail)
    monkeypatch.setattr(pickle, 'load', forbidden)
    response = assess(file_id, parent['execution_id'])
    assert response.status_code == 500
    assert 'audit storage unavailable' in response.data['error']
    assert HoldoutAccess.objects.count() == 0


def test_failed_outcome_read_is_retained_and_counts_on_retry(trained, monkeypatch):
    file_id, parent = trained
    original = pickle.load
    def broken(stream, *args, **kwargs):
        if str(stream.name).endswith('final_holdout.pkl'):
            assert HoldoutAccess.objects.count() == 1  # receipt exists before access
            raise ValueError('simulated outcome read failure')
        return original(stream, *args, **kwargs)
    monkeypatch.setattr(pickle, 'load', broken)
    failed = assess(file_id, parent['execution_id'])
    assert failed.status_code == 500
    assert HoldoutAccess.objects.get().attempt_state == 'failed'
    monkeypatch.setattr(pickle, 'load', original)
    retry = assess(file_id, parent['execution_id'])
    assert retry.status_code == 200
    assert retry.data['evaluation']['holdout_history']['same_final_rows_accesses'] == 1
    assert retry.data['evaluation']['holdout_history']['records'][0]['attempt_state'] == 'failed'


def test_feature_override_is_blocked_before_outcome_access(trained):
    file_id, parent = trained
    response = assess(file_id, parent['execution_id'], features=['other'])
    assert response.status_code == 409
    assert HoldoutAccess.objects.count() == 0


def test_reversing_positive_label_does_not_reset_final_outcome_identity(trained):
    file_id, parent = trained
    assert assess(file_id, parent['execution_id']).status_code == 200
    from modeling.split_contract import save_split_artifact
    membership = parent['model']['split']['membership']
    save_split_artifact(file_id, membership['train'] + membership['valid'], membership['test'], {'strategy': 'random'})
    response = ModelingStartView.as_view()(APIRequestFactory().post('/modeling/start/', {
        'file_id': file_id, 'processed_file': 'data_files/holdout.csv',
        'algorithm': 'logistic_regression', 'business_understanding': declaration(positive='good')}, format='json'))
    assert response.status_code == 200
    assert response.data['model']['prediction_contract']['sha256'] != parent['model']['prediction_contract']['sha256']
    assert response.data['model']['holdout_spec'] == parent['model']['holdout_spec']
    result = assess(file_id, response.data['execution_id'])
    assert result.status_code == 200
    assert result.data['evaluation']['holdout_history']['same_final_rows_accesses'] == 1


def test_wrong_final_membership_blocks_metrics_and_retains_failed_access(trained, monkeypatch):
    file_id, parent = trained
    original = pickle.load
    def altered(stream, *args, **kwargs):
        value = original(stream, *args, **kwargs)
        if str(stream.name).endswith('final_holdout.pkl'):
            value['y_test'] = value['y_test'].iloc[::-1]
        return value
    monkeypatch.setattr(pickle, 'load', altered)
    result = assess(file_id, parent['execution_id'])
    assert result.status_code == 500
    assert 'rows/labels' in result.data['error']
    assert HoldoutAccess.objects.get().attempt_state == 'failed'


def test_history_never_deserializes_final_outcomes_and_validates_dataset_binding(trained, monkeypatch):
    file_id, parent = trained
    def forbidden(*args, **kwargs):
        raise AssertionError('History is receipt-only')
    monkeypatch.setattr(pickle, 'load', forbidden)
    factory = APIRequestFactory()
    view = HoldoutHistoryView.as_view()
    result = view(factory.get('/', {'file_id': file_id}), execution_id=parent['execution_id'])
    assert result.status_code == 200
    assert result.data['same_final_rows_accesses'] == 0
    assert HoldoutAccess.objects.count() == 0
    assert view(factory.get('/', {'file_id': file_id + 1}), execution_id=parent['execution_id']).status_code == 409
    assert view(factory.get('/', {'file_id': file_id, 'limit': 101}), execution_id=parent['execution_id']).status_code == 400


def test_export_selects_exact_assessment_and_preserves_manifest_bytes(trained):
    file_id, parent = trained
    first = assess(file_id, parent['execution_id'])
    second = assess(file_id, parent['execution_id'], threshold=.8)
    factory = APIRequestFactory()
    response = EvaluationPackView.as_view()(factory.post('/', {'file_id': file_id,
        'execution_id': parent['execution_id'],
        'assessment_id': first.data['evaluation']['holdout_access_id']}, format='json'))
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        evidence = json.loads(archive.read('evaluation.json'))
        assert evidence['evaluation']['holdout_access_id'] != second.data['evaluation']['holdout_access_id']
        assert evidence['evaluation']['holdout_history']['same_final_rows_accesses'] == 0
        live = json.loads(archive.read('holdout_history_at_export.json'))
        assert live['history']['same_final_rows_accesses'] == 2
        manifest = json.loads(archive.read('assessment_manifest.json'))
        for name, expected in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected['sha256']
        model = json.loads(archive.read('modeling_status.json'))
        assert model['execution_id'] == parent['execution_id']
    root = execution_root(parent['execution_id']) / 'assessments' / first.data['evaluation']['holdout_access_id']
    (root / 'evaluation.json').write_text('{}')
    tampered = EvaluationPackView.as_view()(factory.post('/', {'file_id': file_id,
        'execution_id': parent['execution_id'], 'assessment_id': str(root.name)}, format='json'))
    assert tampered.status_code == 409


@pytest.mark.auth_boundary
@pytest.mark.django_db
def test_history_requires_real_authentication_without_exposing_final_inputs(settings, tmp_path, django_user_model):
    settings.MEDIA_ROOT = str(tmp_path)
    source = tmp_path / 'source.csv'
    source.write_text('x,outcome\n1,bad\n2,good\n')
    execution, root, frozen = begin_execution(source)
    identity = holdout_spec(digest_file(frozen), 'outcome', [1], 'processed_snapshot')
    (root / 'final_holdout.pkl').write_bytes(b'not deserializable')
    publish_execution(execution, {'file_id': 42, 'model': {'holdout_spec': identity,
        'prediction_contract': {'target_column': 'outcome'}, 'split': {'membership': {'test': [1]}}}})
    client = APIClient(enforce_csrf_checks=True)
    path = f'/api/evaluation/holdout-history/{execution}/?file_id=42'
    assert client.get(path).status_code == 403
    user = django_user_model.objects.create_user(username='history-reader', password='disposable-test-password')
    client.force_login(user)
    assert client.get(path).status_code == 200
    assert HoldoutAccess.objects.count() == 0
    request = APIRequestFactory().get('/', {'file_id': 42})
    force_authenticate(request, user=user)
    assert HoldoutHistoryView.as_view()(request, execution_id=execution).status_code == 200
