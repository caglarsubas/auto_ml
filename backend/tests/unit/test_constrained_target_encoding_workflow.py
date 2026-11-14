"""Exercise declared encoder partitions through training, search, and evidence export."""

import copy

import numpy as np
import pandas as pd
import pytest

from encoding.fitted import apply_fitted_encoding
from execution_jobs import service
from execution_jobs.models import NativeJob
from modeling.development_validation import prepare_fold
from modeling.verify_fold_provenance import verify
from tests.unit.test_durable_legacy_execution import launch, options, post, world  # noqa: F401
from tests.unit.test_purifier_replay import recipe

pytestmark = pytest.mark.unit
TARGET_ENCODING = [{'feature': 'category', 'encoding_method': 'target_encoding'}]


def _expected_encoding(raw, rows, labels, smoothing, applied):
    y = labels.loc[rows]
    prior = float(y.mean())
    def keys(index):
        values = raw.loc[index, 'category'].astype('string')
        return ('s:' + values).fillna('n:')

    categories = keys(rows)
    probabilities = {
        category: (float(y.loc[ids].sum()) + smoothing * prior) / (len(ids) + smoothing)
        for category, ids in categories.groupby(categories).groups.items()
    }
    values = keys(applied)
    return prior, probabilities, values.map(lambda category: probabilities.get(category, prior))


def _assert_maps(frame, labels, report, parent_train, parent_valid, *, strategy, warmup_prior):
    spec = report['mapping']
    assert spec['type'] == 'target_encoding'
    assert spec['category_key_encoding'] == 'tagged_string_v1'
    assert spec['cross_fit_strategy'] == strategy
    assert spec['fit_rows'] == parent_train
    assert spec['fit_on_train_only'] is True
    assert spec['oof'] is True and spec['oof_fits']
    assert spec['warmup_prior'] == warmup_prior
    warmup = spec['warmup_rows']
    assert bool(warmup) == (strategy == 'oot')
    if strategy == 'oot':
        order = spec['chronological_rows']
        assert set(order) == set(parent_train)
        assert warmup == order[:len(warmup)]
        assert frame.loc[order, 'date'].is_monotonic_increasing
        assert frame.loc[warmup, 'date'].max() < frame.loc[order[len(warmup):], 'date'].min()
    else:
        assert spec['chronological_rows'] is None
    coverage = list(warmup)
    replay_train = pd.Series(warmup_prior, index=parent_train, dtype=float)
    for inner in spec['oof_fits']:
        train = inner['train_rows']
        valid = inner['validation_rows']
        assert len(train) >= 2 and valid
        assert set(train + valid) <= set(parent_train)
        assert set(train).isdisjoint(valid)
        assert set(frame.loc[train, 'entity']).isdisjoint(frame.loc[valid, 'entity'])
        if strategy == 'oot':
            assert frame.loc[train, 'date'].max() < frame.loc[valid, 'date'].min()
            assert frame.loc[train, 'end'].max() < frame.loc[valid, 'date'].min()
        else:
            assert set(train + valid) == set(parent_train)
        prior, mapping, values = _expected_encoding(frame, train, labels, spec['smoothing'], valid)
        assert inner['global_mean'] == pytest.approx(prior)
        assert inner['mapping'] == pytest.approx(mapping)
        replay_train.loc[valid] = values
        coverage.extend(valid)
    assert sorted(coverage) == sorted(parent_train)

    prior, mapping, expected = _expected_encoding(frame, parent_train, labels, spec['smoothing'], parent_valid)
    assert spec['global_mean'] == pytest.approx(prior)
    assert spec['mapping'] == pytest.approx(mapping, abs=5.1e-7)
    replay = apply_fitted_encoding(frame.loc[parent_valid, ['category']], [report])
    assert replay.category.tolist() == pytest.approx(expected.tolist(), abs=5.1e-7)
    chunks = [apply_fitted_encoding(chunk, [report]) for chunk in
              (frame.loc[parent_valid[::2], ['category']], frame.loc[parent_valid[1::2], ['category']])]
    pd.testing.assert_frame_equal(replay, pd.concat(chunks).loc[parent_valid])
    return replay_train, replay.category


def _context(frame, strategy, *, task='classification'):
    split = {'strategy': strategy, 'group_column': 'entity'}
    if strategy == 'oot':
        split.update(date_column='date', label_end_column='end')
    return {
        'frame': frame, 'labels': frame.outcome, 'task': task,
        'target_column': 'outcome', 'excluded_features': ['entity', 'date', 'end'],
        'split_meta': {'split_config': split}, 'encoding_plan': TARGET_ENCODING,
        'use_native': False, 'purifier_recipe': recipe([]),
    }


def _frame(rows):
    dates = pd.date_range('2020-01-01', periods=rows)
    return pd.DataFrame({
        'category': ['b' if row % 3 else 'a' for row in range(rows)],
        'entity': np.arange(rows) // 4,
        'date': dates, 'end': dates + pd.Timedelta(days=2),
        'outcome': (np.arange(rows) % 5 < 3).astype(int),
    })


def test_oot_target_encoding_has_label_free_warmup_and_preserves_past_encodings():
    frame = _frame(64)
    # Equal timestamps must stay together even when the parent order is reversed.
    frame.loc[6, 'date'] = frame.loc[7, 'date']
    frame.loc[13, 'date'] = frame.loc[14, 'date']
    frame.loc[[0, 10, 15], 'category'] = None
    frame.loc[[1, 11, 16], 'category'] = '__NULL__'
    # These early rows are unsafe for one or more later application blocks.
    frame.loc[2, 'entity'] = frame.loc[20, 'entity']
    frame.loc[3, 'end'] = frame.loc[30, 'date']
    frame.loc[53:, 'category'] = 'validation-only'
    frame.loc[0, 'category'] = 'rare-early'
    frame.loc[47, 'category'] = 'rare-late'
    train, valid = frame.index[:48][::-1], frame.index[52:]
    context = _context(frame, 'oot')
    context['purifier_recipe'] = recipe(
        [34], [{'Feature_Name': 'category', 'Level_of_Measurement': 'Nominal'}],
    )
    fit, apply, receipt = prepare_fold(context, train, valid)
    spec = receipt['encoding'][0]['mapping']
    expected_fit, expected_apply = _assert_maps(
        frame, context['labels'], receipt['encoding'][0], train.tolist(), valid.tolist(),
        strategy='oot', warmup_prior=.5,
    )
    assert fit.category.tolist() == pytest.approx(expected_fit.tolist())
    assert apply.category.tolist() == pytest.approx(expected_apply.tolist())
    assert fit.loc[spec['warmup_rows'], 'category'].eq(.5).all()
    assert {'n:', 's:__NULL__', 's:rare-early', 's:rare-late'} <= spec['mapping'].keys()
    assert 'category' not in receipt['purifier']['category_replacements']
    # A label ending exactly at the next prediction time is not mature there.
    boundary = frame.loc[spec['oof_fits'][0]['validation_rows'], 'date'].min()
    exact_boundary = frame.copy()
    exact_boundary.loc[0, 'end'] = boundary
    _, _, boundary_receipt = prepare_fold({**context, 'frame': exact_boundary}, train, valid)
    first = boundary_receipt['encoding'][0]['mapping']['oof_fits'][0]
    assert frame.loc[first['validation_rows'], 'date'].min() == boundary
    assert 0 not in first['train_rows']

    changed = copy.deepcopy(frame)
    changed.loc[32:, 'outcome'] = 1 - changed.loc[32:, 'outcome']
    changed.loc[valid, 'category'] = 'another-validation-only'
    changed_fit, _, _ = prepare_fold({**context, 'frame': changed, 'labels': changed.outcome}, train, valid)
    unchanged = train[train < 32]
    pd.testing.assert_series_equal(fit.loc[unchanged, 'category'], changed_fit.loc[unchanged, 'category'])

    validation_only = frame.copy()
    validation_only.loc[valid, 'outcome'] = 1 - frame.loc[valid, 'outcome']
    _, changed_apply, changed_receipt = prepare_fold(
        {**context, 'frame': validation_only, 'labels': validation_only.outcome}, train, valid,
    )
    pd.testing.assert_frame_equal(apply, changed_apply)
    assert changed_receipt['encoding'][0]['mapping'] == spec


def test_group_target_encoding_uses_whole_groups_and_continuous_labels():
    frame = _frame(44)
    frame['outcome'] = np.resize([-7.25, 3.5, 8.125, 12.75, -4., 1.625], len(frame))
    frame.loc[40:, 'category'] = 'validation-only'
    train, valid = frame.index[:40], frame.index[40:]
    context = _context(frame, 'group', task='regression')
    fit, apply, receipt = prepare_fold(context, train, valid)
    expected_fit, expected_apply = _assert_maps(
        frame, context['labels'], receipt['encoding'][0], train.tolist(), valid.tolist(),
        strategy='group', warmup_prior=None,
    )
    assert fit.category.tolist() == pytest.approx(expected_fit.tolist())
    assert apply.category.tolist() == pytest.approx(expected_apply.tolist())
    assert 's:validation-only' not in receipt['encoding'][0]['mapping']['mapping']

    first = receipt['encoding'][0]['mapping']['oof_fits'][0]
    changed = frame.copy()
    changed.loc[first['validation_rows'], 'outcome'] += 1000
    changed_fit, _, _ = prepare_fold(_context(changed, 'group', task='regression'), train, valid)
    pd.testing.assert_series_equal(
        changed_fit.loc[first['validation_rows'], 'category'], fit.loc[first['validation_rows'], 'category'],
    )


@pytest.mark.parametrize('strategy', ['group', 'oot'])
def test_target_encoding_rejects_impossible_inner_partitions(strategy):
    frame = _frame(28)
    train, valid = frame.index[:24], frame.index[24:]
    if strategy == 'group':
        frame.loc[train, 'entity'] = 999
    else:
        # The trained row windows overlap every feasible inner date boundary.
        frame.loc[train, 'end'] = frame.loc[valid[-1], 'date'] - pd.Timedelta(hours=1)
    context = _context(frame, strategy)
    issue = 'at least two training groups' if strategy == 'group' else 'mature, group-disjoint historical rows'
    with pytest.raises(ValueError, match=issue):
        prepare_fold(context, train, valid)
    without_recipe = {**context, 'purifier_recipe': None}
    with pytest.raises(ValueError, match='frozen raw-input recipe'):
        prepare_fold(without_recipe, train, valid)
    if strategy == 'oot':
        del context['split_meta']['split_config']['label_end_column']
        with pytest.raises(ValueError, match='prediction-date and outcome-end columns'):
            prepare_fold(context, train, valid)


def _run_job(world, operation, source):
    identifier, _, _ = launch(world, operation, source)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == 'succeeded', list(job.events.values('event_type', 'detail'))
    return job


def _read_job_maps(world, job, frame, labels):
    url = f'/api/jobs/{job.pk}/fold-provenance/?sha256={job.result_sha256}'
    response = world.clients['reviewer'].get(url)
    assert response.status_code == 200, response.content
    payload = response.json()
    assert verify(response.content, response['X-DeclarAI-Export-SHA256'])['unverified_count'] == 0
    assert b'protected-only' not in response.content
    assert b'final_holdout' not in response.content
    stages = set()
    for fit in payload['fits']:
        state = payload['transform_states'][fit['transforms_sha256']]
        category = [entry for entry in state['encoding'] if entry['feature'] == 'category']
        if category:
            report, = category
            partition = payload['partitions'][fit['partition_sha256']]
            train, valid = partition['train_rows'], partition['validation_rows']
            assert max(train + valid) < 144
            _assert_maps(frame, labels, report, train, valid, strategy='oot', warmup_prior=.5)
            stages.add(fit['stage'])
    return stages


@pytest.mark.django_db(transaction=True)
def test_durable_oot_target_encoding_reaches_training_sfs_hpo_and_reviewer_export(world):
    frame = _frame(180)
    labels = frame.outcome.copy()
    frame['outcome'] = labels.map({0: 'bad', 1: 'good'})
    frame.loc[144:, 'category'] = 'protected-only'
    frame.to_csv(world.path, index=False)
    declared = {
        'strategy': 'oot', 'date_column': 'date', 'label_end_column': 'end',
        'group_column': 'entity', 'cutoff': frame.loc[143, 'date'].strftime('%Y-%m-%d'),
    }
    prepared = post(world.clients['developer'], '/api/preprocessing/run/', {
        'file_id': world.file_id, 'options': [29], 'target_column': 'outcome', 'split': declared,
    })
    assert prepared.status_code == 200, prepared.content[:1000]
    training = {**options(world), 'processed_file': prepared.json()['processed_file'],
                'encoding_plan': TARGET_ENCODING, 'encoding_use_native': False}
    training['business_understanding']['target_contract']['positive_class'] = 'good'
    trained = _run_job(world, 'training', training)
    source = {
        'file_id': world.file_id, 'source_job_id': str(trained.pk),
        'source_result_sha256': trained.result_sha256,
        'execution_id': trained.result['payload']['execution_id'], 'cv_folds': 2, 'n_jobs': 1,
    }
    sfs = _run_job(world, 'sfs', {
        **source, 'methods': ['forward'], 'top_k': 1, 'stopping_criteria': {'max_features': 1},
    })
    hpo = _run_job(world, 'hpo', {
        **source, 'features': ['category'], 'n_iter': 2, 'search_method': 'random',
        'fixed_params': {'n_estimators': 5}, 'validation_curve_points': 2,
        'param_space': {'max_depth': {'type': 'int', 'min': 1, 'max': 2, 'enabled': True}},
    })
    assert {'model/fit', 'model/cv/1'} <= _read_job_maps(world, trained, frame, labels)
    assert {'forward/1/selected/cv/1', 'candidate/forward/cv/1'} <= _read_job_maps(world, sfs, frame, labels)
    assert {'trial/0/cv/1', 'candidate/winner/cv/1'} <= _read_job_maps(world, hpo, frame, labels)


@pytest.mark.django_db
def test_raw_target_encoding_scores_independent_csv_batches(_use_tmp_media, settings):
    from pathlib import Path

    from django.core.files.uploadedfile import SimpleUploadedFile
    from rest_framework.test import APIRequestFactory

    from declaration.models import Declaration
    from deployment.deploy_utils import build_score_bundle
    from deployment.views import DeploymentScoreView
    from evaluation.views import EvaluationRunView
    from modeling.views import ModelingStartView
    from preprocessing.views import PreprocessingRunView
    from tests.unit.test_governed_foundation import declaration

    frame = _frame(120)
    frame['outcome'] = frame.outcome.map({0: 'bad', 1: 'good'})
    # Use a text column in the frozen raw recipe and independently parse
    # smaller batches whose numeric-looking categories would otherwise coerce.
    frame['category'] = np.resize(['007', '7', 'seven', None], len(frame))
    frame['x'] = np.sin(np.arange(len(frame)) / 10)
    raw = Path(settings.MEDIA_ROOT) / 'data_files' / 'raw-target.csv'
    frame.to_csv(raw, index=False)
    file = Declaration.objects.create(name='target encoding package', original_name=raw.name,
                                      file=f'data_files/{raw.name}')
    factory = APIRequestFactory()
    prepared = PreprocessingRunView.as_view()(factory.post('/preprocessing/run/', {
        'file_id': file.pk, 'options': [29], 'target_column': 'outcome',
        'split': {'strategy': 'group', 'group_column': 'entity'},
    }, format='json'))
    assert prepared.status_code == 200, prepared.data
    trained = ModelingStartView.as_view()(factory.post('/modeling/start/', {
        'file_id': file.pk, 'processed_file': prepared.data['processed_file'], 'algorithm': 'xgboost',
        'excluded_variables': ['date', 'end'],
        'business_understanding': declaration('classification'),
        'encoding_plan': TARGET_ENCODING, 'encoding_use_native': False,
    }, format='json'))
    assert trained.status_code == 200, trained.data
    assert trained.data['job_status'] == 'completed', trained.data['model']
    state = trained.data['model']['encoding_report'][0]['mapping']
    assert state['oof_fits']
    execution = trained.data['execution_id']
    assessed = EvaluationRunView.as_view()(factory.post('/evaluation/run/', {
        'file_id': file.pk, 'execution_id': execution,
    }, format='json'))
    assert assessed.status_code == 200, assessed.data
    package = build_score_bundle(file.pk)
    encoder = package['manifest']['encoding_report'][0]['mapping']
    assert set(encoder['mapping']) == {'s:007', 's:7', 's:seven', 'n:'}
    assert 'oof_fits' not in encoder and 'fit_rows' not in encoder

    def score(raw_csv):
        response = DeploymentScoreView.as_view()(factory.post('/deployment/score/', {
            'file_id': file.pk, 'bundle_id': package['bundle_id'],
            'file': SimpleUploadedFile('batch.csv', raw_csv.encode(), content_type='text/csv'),
        }, format='multipart'))
        assert response.status_code == 200, response.data
        assert response.data['input']['parser'] == 'pandas.read_csv/constrained_text_v1'
        assert response.data['input']['string_columns'] == ['category']
        return response.data['scores']

    batch = score('category,x\n007,0.4\n7,0.4\n,0.4\nunknown,0.4\n')
    assert batch == pytest.approx([score(f'category,x\n{key},0.4\n')[0]
                                   for key in ('007', '7', '', 'unknown')])
