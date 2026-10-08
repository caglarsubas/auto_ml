"""Leakage fixtures, immutable recipes and raw-input scoring equivalence."""
import json
import pickle
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from rest_framework.test import APIRequestFactory

from declaration.models import Declaration
from modeling.development_validation import development_folds, prepare_fold
from modeling.execution_artifacts import load_execution
from modeling.split_contract import resolve_modeling_splits, save_split_artifact
from modeling.views import ModelingStartView
from preprocessing.replay import apply_purifier, fit_purifier, load_recipe_input, save_recipe, subset_purifier
from preprocessing.views import PreprocessingRunView
from tests.unit.test_governed_foundation import declaration

pytestmark = pytest.mark.unit


def recipe(options, dictionary=None):
    return {'schema_version': 2, 'recipe_id': str(uuid.uuid4()), 'options': options,
            'data_dictionary': dictionary or [], 'preserve': [],
            'raw_input': {'sha256': 'synthetic-input-hash'}, 'population_operation': 'No row filtering'}


@pytest.mark.parametrize('options', [[1], [3], [4], [7], [11], [17], [23], [29], [34]])
def test_validation_changes_cannot_change_fitted_purifier(options):
    rng = np.random.default_rng(21)
    frame = pd.DataFrame({'x': rng.normal(size=400), 'duplicate': np.arange(400, dtype=float),
        'sparse': np.r_[np.zeros(298), [1., 2.], np.ones(100)],
        'missing': np.r_[np.full(290, np.nan), np.arange(110)],
        'category': ['a'] * 298 + ['b', 'c'] + ['unseen'] * 100})
    frame.loc[:299, 'duplicate'] = frame.loc[:299, 'x']
    config = recipe(options, [{'Feature_Name': 'category', 'Level_of_Measurement': 'Nominal'}])
    train = frame.index[:300]
    first = fit_purifier(frame, config, train)
    changed = frame.copy()
    changed.loc[300:, 'x'] = 1e15
    changed.loc[300:, 'duplicate'] = -1e15
    changed.loc[300:, 'category'] = 'b'
    changed.loc[300:, 'missing'] = np.nan
    assert fit_purifier(changed, config, train) == first
    assert first['fit_rows'] == train.tolist()
    assert apply_purifier(frame, first).index.equals(frame.index)


def test_typed_ordinal_merges_use_training_categories_and_survive_json():
    frame = pd.DataFrame({'ordinal': [1] * 292 + [2] + [3] * 7 + [0, 4], 'x': range(302)})
    state = fit_purifier(frame, recipe([34], [{'Feature_Name': 'ordinal', 'Level_of_Measurement': 'Ordinal'}]), frame.index[:300])
    result = apply_purifier(frame, json.loads(json.dumps(state)))
    assert result.loc[292, 'ordinal'] == 1
    assert result.ordinal.dtype.kind in 'ifu'
    assert result.loc[300:, 'ordinal'].tolist() == [0, 4]
    assert {'from': 2, 'to': 1} in state['category_replacements']['ordinal']


def test_duplicate_drop_preserves_target_and_numeric_dtype():
    frame = pd.DataFrame({'x': [1., 2., 3.], 'Target': [1., 2., 3.], 'redundant': [1., 2., 3.]})
    fitted, dropped, _, _ = PreprocessingRunView()._apply_options(frame, {1}, preserve={'Target'})
    assert fitted.columns.tolist() == ['x', 'Target']
    assert dropped == ['redundant']
    assert fitted.x.dtype == frame.x.dtype


@pytest.mark.parametrize('strategy', ['oot', 'group'])
def test_fold_purifier_fits_exact_constrained_rows(strategy):
    rng = np.random.default_rng(12)
    frame = pd.DataFrame({'x': rng.normal(size=180), 'date': pd.date_range('2025-01-01', periods=180),
                          'end': pd.date_range('2025-01-02', periods=180),
                          'entity': np.repeat(np.arange(30), 6), 'outcome': [0, 1] * 90})
    config = {'group_column': 'entity'}
    if strategy == 'oot':
        config.update(date_column='date', label_end_column='end')
    context = {'frame': frame, 'labels': frame.outcome, 'target_column': 'outcome', 'task': 'classification',
        'excluded_features': ['date', 'end', 'entity'], 'split_meta': {'strategy': strategy, 'split_config': config},
        'purifier_recipe': recipe([29])}
    for train, valid in development_folds(context, frame.index, frame.outcome, 3):
        X_train, X_valid, receipt = prepare_fold(context, train, valid, ['x'])
        state = receipt['purifier']
        assert state['fit_rows'] == train.tolist()
        assert state['clip_bounds']['x']['hi'] == pytest.approx(frame.loc[train, 'x'].quantile(.95))
        assert state['clip_bounds']['x']['lo'] == pytest.approx(frame.loc[train, 'x'].quantile(.05))
        assert set(frame.loc[train, 'entity']).isdisjoint(frame.loc[valid, 'entity'])
        assert X_train.index.equals(train) and X_valid.index.equals(valid)
        assert receipt['upstream_limitation'] is None
        if strategy == 'oot':
            assert frame.loc[train, 'end'].max() < frame.loc[valid, 'date'].min()


def test_fold_column_drops_do_not_reintroduce_zero_filled_raw_features():
    frame = pd.DataFrame({'x': [1.] * 10 + [2.] * 10, 'x_other': np.arange(20), 'outcome': [0, 1] * 10})
    context = {'frame': frame, 'labels': frame.outcome, 'target_column': 'outcome', 'task': 'classification',
               'purifier_recipe': recipe([3])}
    train, valid, receipt = prepare_fold(context, frame.index[:10], frame.index[10:], ['x', 'x_other'])
    assert train.columns.tolist() == valid.columns.tolist() == ['x_other']
    assert receipt['purifier']['dropped_by_rule']['zero_var'] == ['x']


@pytest.mark.parametrize('train', [[0], [0, 0], [0, 999]])
def test_invalid_fit_membership_never_falls_back(train):
    with pytest.raises(ValueError, match='fit rows'):
        fit_purifier(pd.DataFrame({'x': range(10)}), recipe([29]), train)


@pytest.mark.parametrize('options', [[0], [35], [True], ['29']])
def test_unknown_purifier_options_fail(options):
    with pytest.raises(ValueError, match='catalog identifiers'):
        fit_purifier(pd.DataFrame({'x': range(10)}), recipe(options), [0, 1, 2])


def test_recipe_integrity_and_split_version_are_bound_to_input(_use_tmp_media, settings):
    root = Path(settings.MEDIA_ROOT)
    frame = pd.DataFrame({'x': range(40), 'Target': [0, 1] * 20})
    processed = root/'data_files'/f'processed_1_{uuid.uuid4().hex}.csv'
    frame.to_csv(processed, index=False)
    split = {'strategy': 'random', 'split_config': {'strategy': 'random'}, 'train_idx': list(range(30)), 'test_idx': list(range(30, 40))}
    saved = save_recipe(processed, 1, frame, [29], [], {'Target'}, split, frame.index)
    save_split_artifact(1, range(10, 40), range(10), {'strategy': 'random'})
    raw, loaded = load_recipe_input(processed, 1)
    tr, va, te, _ = resolve_modeling_splits(raw, raw.Target, 1, split_artifact=loaded['outer_split'])
    assert te.tolist() == split['test_idx']
    assert set(tr).union(va) == set(split['train_idx'])
    with pytest.raises(ValueError, match='identity'):
        load_recipe_input(processed, 2)
    (root/saved['raw_input']['path']).write_text('tampered')
    with pytest.raises(ValueError, match='Raw input failed'):
        load_recipe_input(processed, 1)


def test_missing_new_recipe_blocks_but_legacy_input_remains_unverified(_use_tmp_media, settings):
    root = Path(settings.MEDIA_ROOT)/'data_files'
    fresh = root/f'processed_1_{uuid.uuid4().hex}.csv'
    fresh.write_text('x\n1\n')
    with pytest.raises(ValueError, match='recipe is missing'):
        load_recipe_input(fresh, 1)
    historical = root/'processed_1_20260101000000.csv'
    historical.write_text('x\n1\n')
    assert load_recipe_input(historical, 1) == (None, None)


def test_candidate_raw_dependencies_and_batch_row_alignment():
    frame = pd.DataFrame({'x': range(30), 'category': ['a'] * 30, 'unused': range(30)})
    state = fit_purifier(frame, recipe([2, 29]), frame.index[:20])
    subset = subset_purifier(state, ['x', 'category_a'], [{'feature': 'category', 'mapping': {'columns': ['category_a']}}])
    duplicated = frame[['category', 'x']].iloc[[0, 0, 25, 8]]
    transformed = apply_purifier(duplicated, subset)
    assert transformed.index.tolist() == duplicated.index.tolist()
    assert len(transformed) == 4
    with pytest.raises(ValueError, match='Missing required raw'):
        apply_purifier(duplicated.drop(columns='x'), subset)


@pytest.mark.django_db
@pytest.mark.parametrize('task', ['classification', 'regression'])
def test_raw_recipe_training_assessment_bundle_and_candidate_replay(_use_tmp_media, settings, task):
    from deployment.deploy_utils import build_score_bundle, score_frame
    from evaluation.views import EvaluationRunView
    from modeling.alt_pipelines import load_model_adapter
    from modeling.calibration_utils import apply_calibrator, load_calibrator
    from modeling.execution_artifacts import publish_candidate
    rng = np.random.default_rng(42)
    x = rng.normal(size=300)
    outcomes = np.where(x > 0, 'bad', 'good') if task == 'classification' else np.where(x > 0, 10., 20.)
    raw = pd.DataFrame({'x': x, 'unused': rng.normal(size=300), 'outcome': outcomes,
                       'category': ['common'] * 40 + ['rare-a', 'rare-b', None] + ['common'] * 105 + ['second'] * 52 + ['unseen'] * 100,
                       'date': pd.date_range('2025-01-01', periods=300)})
    raw.loc[200:, 'x'] = 1e9
    source = Path(settings.MEDIA_ROOT)/'data_files'/'raw.csv'
    raw.to_csv(source, index=False)
    file = Declaration.objects.create(name='replay', original_name='raw.csv', file='data_files/raw.csv')
    factory = APIRequestFactory()
    preprocessing = PreprocessingRunView.as_view()(factory.post('/preprocessing/run/', {
        'file_id': file.pk, 'options': [29, 34], 'target_column': 'outcome',
        'data_dictionary': [{'Feature_Name': 'category', 'Level_of_Measurement': 'Nominal'}],
        'split': {'strategy': 'oot', 'date_column': 'date', 'cutoff': '2025-07-19'},
    }, format='json'))
    assert preprocessing.status_code == 200, preprocessing.data
    trained = ModelingStartView.as_view()(factory.post('/modeling/start/', {
        'file_id': file.pk, 'processed_file': preprocessing.data['processed_file'], 'algorithm': 'xgboost',
        'business_understanding': declaration(task),
        'encoding_plan': [{'feature': 'category', 'user_lom': 'nominal', 'nunique': 5,
                           'encoding_method': 'one_hot_encoding'}], 'encoding_use_native': False,
    }, format='json'))
    assert trained.status_code == 200, trained.data
    model = trained.data['model']
    assert model['input_stage'] == 'raw_unencoded'
    assert model['cv']['task'] == task and model['cv']['status'] == 'completed'
    assert model['cv']['metric_coverage']['rmse' if task == 'regression' else 'roc_auc']['n_valid'] == 5
    with (Path(settings.MEDIA_ROOT)/model['train_data_path']).open('rb') as stream:
        development = pickle.load(stream)
    state = development['purifier_state']
    assert {'from': 'rare-a', 'to': 'Others-Outliers'} in state['category_replacements']['category']
    expected_hi = raw.loc[state['fit_rows'], 'x'].quantile(.95)
    assert state['clip_bounds']['x']['hi'] == pytest.approx(expected_hi)
    assert 'y_test' not in development
    assert len(development['validation_context']['frame']) < len(raw)
    assert not (development['validation_context']['frame'].x == 1e9).any()
    assessed = EvaluationRunView.as_view()(factory.post('/evaluation/run/', {
        'file_id': file.pk, 'execution_id': trained.data['execution_id'],
    }, format='json'))
    assert assessed.status_code == 200, assessed.data
    assert assessed.data['evaluation']['purifier_provenance'] == state
    assert assessed.data['evaluation']['evidence_status'] == 'exploratory'
    bundle = build_score_bundle(file.pk)
    assert bundle['manifest']['input_stage'] == 'raw_unencoded'
    inputs = raw[['unused', 'category', 'x']]
    scores = np.asarray(score_frame(file.pk, inputs)['scores'])
    chunks = np.concatenate([score_frame(file.pk, inputs.iloc[i:i+17])['scores'] for i in range(0, len(inputs), 17)])
    assert np.allclose(scores, chunks, atol=1e-9)
    # Missing/unseen categories and repeated scoring rows use frozen training state.
    changed = inputs.iloc[[0, 0, 199, 299]].copy()
    changed['category'] = ['unseen', None, 'rare-a', 'rare-b']
    changed_scores = np.asarray(score_frame(file.pk, changed)['scores'])
    individual = np.concatenate([score_frame(file.pk, changed.iloc[[i]])['scores'] for i in range(len(changed))])
    assert np.allclose(changed_scores, individual, atol=1e-9)
    with (Path(settings.MEDIA_ROOT)/model['holdout_path']).open('rb') as stream:
        holdout = pickle.load(stream)
    adapter = load_model_adapter(str(Path(settings.MEDIA_ROOT)/model['model_path']), algorithm='xgboost')
    expected = adapter.predict(holdout['X_test']) if task == 'regression' else adapter.predict_proba(holdout['X_test'])
    if model.get('calibrator_path'):
        expected = apply_calibrator(load_calibrator(model['calibrator_path'], settings.MEDIA_ROOT), expected)
    assert np.allclose(scores[holdout['X_test'].index], expected, atol=1e-9)
    # A later preprocessing version must not invalidate or overwrite this execution.
    old_recipe = Path(settings.MEDIA_ROOT)/preprocessing.data['processed_file']
    before = old_recipe.read_bytes()
    next_preprocessing = PreprocessingRunView.as_view()(factory.post('/preprocessing/run/', {
        'file_id': file.pk, 'options': [], 'target_column': 'outcome',
        'split': {'strategy': 'random'},
    }, format='json'))
    assert next_preprocessing.status_code == 200, next_preprocessing.data
    assert next_preprocessing.data['processed_file'] != preprocessing.data['processed_file']
    assert old_recipe.read_bytes() == before
    load_execution(trained.data['execution_id'], file.pk)
    # Candidate adoption must retain fitted raw replay and avoid requiring an unused feature.
    candidate_adapter = load_model_adapter(str(Path(settings.MEDIA_ROOT)/model['model_path']), algorithm='xgboost')
    candidate_adapter.train(development['X_train'][['x']], development['y_train'],
                            development['X_valid'][['x']], development['y_valid'],
                            {'objective': 'reg:squarederror' if task == 'regression' else 'binary:logistic'}, num_boost_round=10)
    candidate = publish_candidate(trained.data['execution_id'], file.pk, candidate_adapter, ['x'], {}, 'replay-test')
    assert candidate['model']['fit_receipt']['num_boost_round'] == 10
    assert candidate['model']['cv']['configuration']['features'] == ['x']
    assert candidate['model']['cv']['configuration']['num_boost_round'] == 10
    assert candidate['model']['purifier_path'] != model['purifier_path']
    assessed = EvaluationRunView.as_view()(factory.post('/evaluation/run/', {
        'file_id': file.pk, 'execution_id': candidate['execution_id'],
    }, format='json'))
    assert assessed.status_code == 200, assessed.data
    child_bundle = build_score_bundle(file.pk)
    assert child_bundle['manifest']['fit_receipt'] == candidate['model']['fit_receipt']
    assert child_bundle['manifest']['input_features'] == ['x']
    assert score_frame(file.pk, raw[['x']])['n_scored'] == len(raw)
    path = Path(settings.MEDIA_ROOT)/child_bundle['bundle_path']/'purifier.json'
    path.unlink()
    with pytest.raises(ValueError, match='integrity verification'):
        score_frame(file.pk, raw[['x']])


def test_iso_and_day_first_dates_agree_in_preprocessing_and_folds():
    from preprocessing.purifier_contract import build_outer_split_indices, parse_split_dates
    values = pd.Series(['2025-01-02', '03/01/2025', '2025-01-04T00:00:00Z'])
    assert parse_split_dates(values).dt.day.tolist() == [2, 3, 4]
    frame = pd.DataFrame({'date': pd.date_range('2025-01-01', periods=60).strftime('%Y-%m-%d'), 'x': range(60)})
    train, test, _ = build_outer_split_indices(frame, {'strategy': 'oot', 'date_column': 'date', 'cutoff': '2025-02-01'})
    assert len(train) == 32 and len(test) == 28


@pytest.mark.django_db
@pytest.mark.parametrize('task', ['classification', 'regression'])
def test_invalid_purifier_fold_is_not_silently_discarded(_use_tmp_media, settings, task):
    frame = pd.DataFrame({'x': [1.] * 80 + list(range(220)), 'outcome': ['bad', 'good'] * 150 if task == 'classification' else np.arange(300.),
                          'date': pd.date_range('2025-01-01', periods=300)})
    source = Path(settings.MEDIA_ROOT)/'data_files'/'invalid-fold.csv'
    frame.to_csv(source, index=False)
    file = Declaration.objects.create(name='invalid fold', original_name=source.name, file='data_files/invalid-fold.csv')
    factory = APIRequestFactory()
    preprocessed = PreprocessingRunView.as_view()(factory.post('/preprocessing/run/', {
        'file_id': file.pk, 'options': [3], 'target_column': 'outcome',
        'split': {'strategy': 'oot', 'date_column': 'date', 'cutoff': '2025-07-19'},
    }, format='json'))
    assert preprocessed.status_code == 200, preprocessed.data
    trained = ModelingStartView.as_view()(factory.post('/modeling/start/', {
        'file_id': file.pk, 'processed_file': preprocessed.data['processed_file'], 'algorithm': 'xgboost',
        'business_understanding': declaration(task),
    }, format='json'))
    assert trained.status_code == 400, trained.data
    assert trained.data['job_status'] == 'failed'
    assert 'Declared development validation failed' in trained.data['model']['error']
    assert 'no valid retained feature schema' in trained.data['model']['error']


@pytest.mark.parametrize('task', ['classification', 'regression'])
def test_tuning_receipts_include_partition_fitted_purifier(task):
    from modeling.hyperparam_utils import _evaluate_config
    rng = np.random.default_rng(25)
    frame = pd.DataFrame({'x': rng.normal(size=120), 'entity': np.repeat(range(20), 6)})
    labels = pd.Series((frame.x > 0).astype(int) if task == 'classification' else frame.x * 2, index=frame.index)
    context = {'frame': frame, 'labels': labels, 'task': task, 'target_column': 'outcome',
               'excluded_features': ['entity'], 'split_meta': {'strategy': 'group', 'split_config': {'group_column': 'entity'}},
               'purifier_recipe': recipe([29])}
    trial = _evaluate_config(frame[['x']], labels, frame[['x']].iloc[-20:], labels.iloc[-20:],
        {'max_depth': 2, 'n_estimators': 10}, 3, False, 1, .5, task=task, validation_context=context)
    assert len(trial['validation_provenance']) == 3
    for receipt in trial['validation_provenance']:
        state = receipt['purifier']
        assert state['fit_rows'] == receipt['train_rows']
        assert state['clip_bounds']['x']['hi'] == pytest.approx(frame.loc[state['fit_rows'], 'x'].quantile(.95))
        assert set(frame.loc[state['fit_rows'], 'entity']).isdisjoint(frame.loc[receipt['valid_rows'], 'entity'])
