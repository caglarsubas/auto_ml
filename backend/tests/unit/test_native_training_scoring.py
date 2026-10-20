"""Candidate export, actual native prediction parity and durable authority fences."""

import copy
import json
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from django.utils import timezone

from access_control import projects
from access_control.models import Project, ProjectMembership, ProjectDataset
from declaration.models import Declaration
from deployment import native_candidate as portable
from execution_jobs import service, training_scoring
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import admission, post, queue, world  # noqa: F401
from tests.unit.test_governed_foundation import declaration

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def candidate(world):  # noqa: F811
    body, _ = admission(world)
    identifier = queue(world, body)
    service.execute(identifier)
    world.trained = NativeJob.objects.get(pk=identifier)
    assert world.trained.state == "succeeded"
    world.scoring_path = world.root / 'data_files/candidate-input.csv'
    frame = pd.DataFrame({'z': [np.nan, 10.0, -2.0, np.nan], 'x': [-2.0, 0.0, 3.0, 1.0]})
    frame.to_csv(world.scoring_path, index=False)
    dataset = Declaration.objects.create(name='Feature only', original_name='predict.csv', file='data_files/candidate-input.csv')
    projects.bind_dataset(dataset, world.project.pk)
    world.input_id = dataset.pk
    return world


def exported(w, role='developer'):
    response = w.clients[role].get(f'/api/jobs/{w.trained.pk}/candidate/?sha256={w.trained.result_sha256}')
    assert response.status_code == 200, response.content
    assert response['Cache-Control'] == 'no-store'
    assert response['Access-Control-Expose-Headers'] == 'X-DeclarAI-Export-SHA256'
    assert response['X-DeclarAI-Export-SHA256'] == portable.sha(response.content)
    return response.content, response['X-DeclarAI-Export-SHA256']


def preview(w):
    response = post(w.clients['developer'], f'/api/jobs/{w.trained.pk}/scoring-input/', {
        'input_file_id': w.input_id, 'training_result_sha256': w.trained.result_sha256,
    })
    assert response.status_code == 200, response.content
    p = response.json()
    return {**{k: p[k] for k in training_scoring.FIELDS}, 'kind': training_scoring.KIND, 'request_id': str(uuid.uuid4())}


def submit(w, body):
    response = post(w.clients['developer'], f'/api/jobs/datasets/{w.file_id}/', body)
    assert response.status_code == 202, response.content
    return response.json()['id']


@pytest.mark.parametrize('task,positive', [('classification', 'bad'), ('classification', 'good'), ('regression', None)])
def test_export_scoring_and_offline_cli_match_refit_with_frozen_means(world, task, positive):  # noqa: F811
    w = world
    options = copy.deepcopy(w.options)
    options['business_understanding'] = declaration(task, positive)
    if task == 'regression':
        w.frame['outcome'] = [10., 20.] * 60
        w.frame.to_csv(w.path, index=False)
    body, _ = admission(w, options)
    identifier = queue(w, body)
    service.execute(identifier)
    w.trained = NativeJob.objects.get(pk=identifier)
    raw, sha = exported(w)
    assert exported(w, 'reviewer') == (raw, sha) == exported(w, 'admin')
    feature_raw = w.frame[['z', 'x']].to_csv(index=False).encode()
    reference = portable.score(raw, sha, feature_raw, chunk_size=1)
    assert reference == portable.score(raw, sha, feature_raw, chunk_size=17) == portable.score(raw, sha, feature_raw, chunk_size=10000)
    import xgboost as xgb
    model = xgb.Booster(params={'nthread': 1})
    model.load_model(bytearray(w.trained.result['model_json'].encode()))
    values = w.frame[['x', 'z']].fillna(w.trained.result['refit_preprocessing']['impute_means'])
    assert reference['scores'] == pytest.approx(model.predict(xgb.DMatrix(values, nthread=1)).tolist(), abs=0)
    assert reference['prediction_contract']['positive_class'] == positive
    assert reference['score_semantics'] == ('target_prediction' if task == 'regression' else 'positive_class_probability')
    assert all(reference[k] is False for k in portable.FLAGS)
    export_path, input_path, output_path = [w.root / f for f in ['candidate.json', 'features.csv', 'scores.json']]
    export_path.write_bytes(raw); input_path.write_bytes(feature_raw)
    args = [sys.executable, str(Path(__file__).resolve().parents[3] / 'scripts/score_native_candidate.py'), str(export_path), str(input_path), '--export-sha256', sha, '--output', str(output_path), '--chunk-size', '7']
    with patch('pickle.load', side_effect=AssertionError('pickle')), patch('joblib.load', side_effect=AssertionError('joblib')):
        assert portable.score(raw, sha, feature_raw) == reference
        assert subprocess.run(args, capture_output=True, timeout=30).returncode == 0
    assert json.loads(output_path.read_bytes()) == reference
    assert subprocess.run(args, capture_output=True, timeout=30).returncode == 2  # no overwrite


def test_real_queued_scoring_is_pinned_replayable_and_does_not_adopt(candidate):
    w = candidate
    body = preview(w)
    identifier = submit(w, body)
    assert post(w.clients['developer'], f'/api/jobs/datasets/{w.file_id}/', body).status_code == 200
    service.execute(identifier); service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == 'succeeded' and job.attempts == 1
    raw, sha = exported(w)
    expected = portable.score(raw, sha, w.scoring_path.read_bytes())
    assert job.result['scores'] == expected['scores']
    assert job.result['export_sha256'] == sha and job.result['training_result_sha256'] == w.trained.result_sha256
    assert job.result_sha256 == service.digest(job.result)
    response = w.clients['reviewer'].get(f'/api/jobs/{identifier}/scores/?sha256={job.result_sha256}')
    assert response.status_code == 200 and json.loads(response.content) == job.result
    assert list(job.events.values_list('event_type', flat=True)) == ['submitted', 'started', 'succeeded']
    assert all(job.result[k] is False for k in portable.FLAGS)
    assert not (w.root / 'modeling').exists() and not (w.root / 'deployment_bundles').exists()
    changed = {**body, 'input_sha256': 'a' * 64}
    assert post(w.clients['developer'], f'/api/jobs/datasets/{w.file_id}/', changed).status_code == 409


@pytest.mark.parametrize('role', ['reviewer', 'admin', 'outsider', 'anonymous'])
def test_only_current_developer_can_prepare_or_submit(candidate, role):
    w = candidate
    body = preview(w)
    assert post(w.clients[role], f'/api/jobs/{w.trained.pk}/scoring-input/', {'input_file_id': w.input_id, 'training_result_sha256': w.trained.result_sha256}).status_code == 403
    assert post(w.clients[role], f'/api/jobs/datasets/{w.file_id}/', body).status_code == 403
    if role in {'outsider', 'anonymous'}:
        assert w.clients[role].get(f'/api/jobs/{w.trained.pk}/candidate/?sha256={w.trained.result_sha256}').status_code == 403


@pytest.mark.parametrize('csv', ['x\n1\n', 'x,z,extra\n1,2,3\n', 'x,x\n1,2\n', 'x,z\n1,2,3\n', 'x,z\n1\n', 'x,z\ninf,2\n', 'x,z\nword,2\n', 'x,z\n', 'x,z,outcome\n1,2,bad\n', 'x,z\n1,2\n' * 10001])
def test_invalid_schema_categories_labels_nonfinite_or_bounds_rejected(candidate, csv):
    w = candidate
    w.scoring_path.write_text(csv)
    response = post(w.clients['developer'], f'/api/jobs/{w.trained.pk}/scoring-input/', {'input_file_id': w.input_id, 'training_result_sha256': w.trained.result_sha256})
    assert response.status_code in {400, 409}
    assert NativeJob.objects.count() == 1


@pytest.mark.parametrize('fault', ['input', 'result', 'runtime', 'approval', 'cancel', 'authority', 'source_authority', 'source_project', 'holdout'])
def test_stale_or_unauthorized_execution_never_publishes(candidate, fault):
    w = candidate
    body = preview(w)
    identifier = submit(w, body)
    if fault == 'input':
        w.scoring_path.write_text('x,z\n99,3\n')
    elif fault == 'result':
        NativeJob.objects.filter(pk=w.trained.pk).update(result={**w.trained.result, 'model_json': '{}'})
    elif fault == 'approval':
        result = {**w.trained.result, 'production_use_approved': True}
        NativeJob.objects.filter(pk=w.trained.pk).update(result=result, result_sha256=service.digest(result))
    elif fault == 'runtime':
        job = NativeJob.objects.get(pk=identifier); job.specification['runtime']['python'] = 'changed'; job.save()
    elif fault == 'cancel':
        service.cancel(w.users['developer'], identifier, {'action': 'cancel'})
    elif fault == 'authority':
        ProjectMembership.objects.filter(actor=w.users['developer'], project=w.project).update(active=False)
    elif fault in {'source_authority', 'source_project'}:
        other = Project.objects.create(name='Different project')
        if fault == 'source_project':
            ProjectDataset.objects.filter(dataset_id=w.input_id).update(project_id=other.pk)
        else:
            ProjectDataset.objects.filter(dataset_id=w.input_id).update(revision=uuid.uuid4())
    else:
        path = w.root / 'splits' / f'{w.input_id}_split.json'; path.parent.mkdir(); path.write_text('{}')
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state in {'blocked', 'cancelled'} and job.result is None and job.result_sha256 == ''


def test_stale_lease_and_late_candidate_tampering_cannot_publish(candidate):
    w = candidate
    identifier = submit(w, preview(w))
    job, token = service.claim(identifier)
    result = training_scoring.score(job, lambda: None)
    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1))
    service.finish(identifier, token, 'succeeded', result=result)
    assert NativeJob.objects.get(pk=identifier).result is None
    service.reconcile()
    job, token = service.claim(identifier)
    NativeJob.objects.filter(pk=w.trained.pk).update(result={'tampered': True})
    service.finish(identifier, token, 'succeeded', result=result)
    job.refresh_from_db()
    assert job.state == 'blocked' and job.result is None


@pytest.mark.parametrize('fault', ['digest', 'model_format', 'features', 'means', 'objective', 'encoding', 'runtime', 'native_json'])
def test_export_or_runtime_tampering_blocks_offline_scoring(candidate, fault):
    raw, sha = exported(candidate)
    value = json.loads(raw)
    if fault == 'digest':
        raw += b' '; expected = sha
    else:
        r = value['result']
        if fault == 'model_format':
            r['model_format'] = 'pickle'
        elif fault == 'features':
            r['features'].reverse()
        elif fault == 'means':
            r['refit_preprocessing']['impute_means'].pop('z')
        elif fault == 'objective':
            r['prediction_contract']['task'] = 'regression'
        elif fault == 'encoding':
            r['refit_preprocessing']['encoding'] = ['unavailable']
        elif fault == 'runtime':
            r['runtime']['packages']['xgboost'] = 'different'
        else:
            r['model_json'] = '{}'
        value['result_sha256'] = portable.sha(portable.canonical(r))
        raw = portable.canonical(value); expected = portable.sha(raw)
    with pytest.raises(ValueError):
        portable.score(raw, expected, candidate.scoring_path.read_bytes())


def test_export_stale_digest_and_known_holdout_copy_block(candidate):
    w = candidate
    assert w.clients['developer'].get(f'/api/jobs/{w.trained.pk}/candidate/?sha256={"a" * 64}').status_code == 409
    HoldoutAccess.objects.create(file_id=w.file_id, dataset_sha256=portable.sha(w.scoring_path.read_bytes()), execution_id=uuid.uuid4(), evidence_status='exploratory')
    assert post(w.clients['developer'], f'/api/jobs/{w.trained.pk}/scoring-input/', {'input_file_id': w.input_id, 'training_result_sha256': w.trained.result_sha256}).status_code == 409


def test_changed_preview_budget_requires_new_explicit_review(candidate):
    w = candidate
    body = preview(w)
    with patch.dict(training_scoring.BUDGET, {'chunk_size': 123}):
        assert post(w.clients['developer'], f'/api/jobs/datasets/{w.file_id}/', body).status_code == 409
    assert NativeJob.objects.count() == 1


def test_large_receipt_preserves_every_row_and_scores_without_original_training_file(candidate):
    w = candidate
    frame = pd.DataFrame({'z': [np.nan] * 1301, 'x': np.linspace(-4, 4, 1301)})
    frame.to_csv(w.scoring_path, index=False)
    w.path.unlink()  # immutable native result, not a mutable source projection
    raw, sha = exported(w)
    identifier = submit(w, preview(w))
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == 'succeeded' and len(job.result['scores']) == 1301
    detail = w.clients['reviewer'].get(f'/api/jobs/{identifier}/').json()
    assert detail['result']['scores_truncated'] and len(detail['result']['scores_preview']) == 500
    receipt = w.clients['reviewer'].get(f'/api/jobs/{identifier}/scores/?sha256={job.result_sha256}')
    expected = portable.score(raw, sha, w.scoring_path.read_bytes(), chunk_size=10000)
    assert json.loads(receipt.content)['scores'] == expected['scores'] == job.result['scores']
