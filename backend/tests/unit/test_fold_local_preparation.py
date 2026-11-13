"""Constrained development fits and fitted transforms across model/search paths."""

import copy

import numpy as np
import pandas as pd
import pytest

from modeling.alt_pipelines import fit_woe_maps, transform_woe
from modeling.development_assessment import assess_development_cv
from modeling.development_validation import prepare_fold
from modeling.hyperparam_utils import _evaluate_config
from modeling.sfs_objective import resolve_objective
from modeling.sfs_utils import _selection_cv
from modeling.split_contract import resolve_modeling_splits
from modeling.views import execute_legacy_hpo, execute_legacy_sfs
from tests.unit.test_durable_legacy_execution import launch, options, post, world  # noqa: F401
from tests.unit.test_purifier_replay import recipe

pytestmark = pytest.mark.unit


@pytest.fixture
def temporal_context():
    rows = 120
    index = pd.RangeIndex(rows)
    dates = pd.date_range('2025-01-01', periods=rows)
    frame = pd.DataFrame({
        'x': np.arange(rows, dtype=float) * 100,
        'planned': ['common', 'rare'] * (rows // 2),
        'unplanned': np.repeat(['early', 'middle', 'late'], rows // 3),
        'entity': np.arange(rows) // 3,
        'date': dates,
        'end': dates + pd.Timedelta(days=3),
        'outcome': index % 2,
    })
    frame.loc[::7, 'x'] = np.nan
    return {
        'frame': frame, 'labels': frame.outcome, 'task': 'classification',
        'target_column': 'outcome', 'excluded_features': ['entity', 'date', 'end'],
        'split_meta': {'split_config': {
            'strategy': 'oot', 'group_column': 'entity', 'date_column': 'date', 'label_end_column': 'end',
        }},
        'purifier_recipe': recipe([]),
        'encoding_plan': [{'feature': 'planned', 'encoding_method': 'frequency_encoding'}],
        'use_native': False,
        'prediction_contract': {'class_mapping': [{}, {}], 'objective': {'primary_metric': 'log_loss'}},
    }


def assert_fit_partition(context, receipt):
    frame = context['frame']
    fit = frame.loc[receipt['train_rows']]
    valid = frame.loc[receipt['valid_rows']]
    assert fit.end.max() < valid.date.min()
    assert set(fit.entity).isdisjoint(valid.entity)
    assert receipt['purifier']['fit_rows'] == fit.index.tolist()
    assert receipt['impute_means']['x'] == pytest.approx(fit.x.mean())
    maps = {item['feature']: item for item in receipt['encoding']}
    assert maps['unplanned']['categories'] == fit.unplanned.unique().tolist()
    assert maps['planned']['mapping']['mapping'] == pytest.approx(
        fit.planned.value_counts(normalize=True).to_dict()
    )


@pytest.mark.parametrize('algorithm', ['logistic_regression', 'scorecard'])
def test_alternate_cv_fits_on_purged_raw_partitions(temporal_context, algorithm):
    c = temporal_context
    result = assess_development_cv(c, c['frame'][['x', 'planned', 'unplanned']], c['labels'],
                                   algorithm, {'C': 1.}, n_splits=3)
    assert result['cv_strategy'] == 'time_series'
    assert result['metric_coverage']['log_loss']['n_valid'] == 3
    for receipt in result['fold_provenance']:
        assert_fit_partition(c, receipt)
        assert receipt['native_fit']['validation_role'] == 'not_used_by_fitter'


@pytest.mark.parametrize('operation', ['sfs', 'hpo'])
def test_search_replays_partial_encoding_plan_in_each_temporal_fold(temporal_context, operation):
    c = temporal_context
    # Use the production model-fit partition as the candidate pool.
    train, valid = c['frame'].index[:88], c['frame'].index[91:]
    X, V, _ = prepare_fold(c, train, valid)
    y, z = c['labels'].loc[train], c['labels'].loc[valid]
    if operation == 'sfs':
        objective, _ = resolve_objective('classification', c, {})
        result = _selection_cv(X, y, 'classification', 'xgboost', c, 2, objective)
        receipts = result['fold_provenance']
    else:
        result = _evaluate_config(X, y, V, z, {'n_estimators': 5, 'max_depth': 2},
                                  2, True, 1, .5, early_stopping_rounds=0, validation_context=c)
        receipts = result['validation_provenance']
    assert len(receipts) == 2
    for receipt in receipts:
        assert_fit_partition(c, receipt)
        assert set(receipt['train_rows'] + receipt['valid_rows']).issubset(train)


@pytest.mark.parametrize('operation', [execute_legacy_sfs, execute_legacy_hpo], ids=['sfs', 'hpo'])
def test_constrained_search_without_frozen_inputs_refuses_before_fitting(settings, tmp_path, monkeypatch, operation):
    settings.MEDIA_ROOT = str(tmp_path)
    directory = tmp_path / 'train_data'
    directory.mkdir()
    (directory / '1_train_data.pkl').touch()
    X = pd.DataFrame({'x': range(30)})
    y = pd.Series([0, 1] * 15)
    monkeypatch.setattr('modeling.views.load_development_data', lambda *_: {
        'X_train': X.iloc[:20], 'X_valid': X.iloc[20:],
        'y_train': y.iloc[:20], 'y_valid': y.iloc[20:],
        'split_meta': {'split_config': {'strategy': 'group', 'group_column': 'entity'}},
    })
    result = operation({'file_id': 1, 'algorithm': 'xgboost'})
    assert result.status_code == 400
    assert 'recorded development inputs' in result.data['error']


@pytest.mark.parametrize('split', [
    {'strategy': 'group'},
    {'strategy': 'random', 'split_config': {'strategy': 'oot', 'date_column': 'date'}},
    {'strategy': 'random', 'split_config': {'label_end_column': 'end'}},
])
def test_incomplete_constraints_cannot_select_shuffled_outer_fit(temporal_context, split):
    frame = temporal_context['frame']
    artifact = {**split, 'train_idx': list(range(90)), 'test_idx': list(range(90, 120))}
    with pytest.raises(ValueError, match='group_column|temporal|Outcome windows'):
        resolve_modeling_splits(frame, frame.outcome, split_artifact=artifact)


def test_scorecard_numeric_fit_uses_the_same_raw_bins_during_scoring():
    values = np.repeat(np.arange(30, dtype=float) * 1000, 3)
    X = pd.DataFrame({'x': values})
    y = pd.Series((values >= 15000).astype(int))
    maps, fitted = fit_woe_maps(X, y)
    assert fitted.x.nunique() > 1
    pd.testing.assert_frame_equal(fitted, transform_woe(X, maps))
    validation = pd.DataFrame({'x': [-5000., 40000., np.nan]})
    assert transform_woe(validation, maps).x.tolist() == [fitted.x.iloc[0], fitted.x.iloc[-1], 0.]


def test_partial_plan_and_validation_only_changes_cannot_alter_fitted_state(temporal_context):
    c = temporal_context
    train, valid = c['frame'].index[:40], c['frame'].index[45:60]
    expected, applied, receipt = prepare_fold(c, train, valid)
    assert applied.unplanned.isna().all()
    changed = copy.deepcopy(c)
    changed['frame'].loc[valid, 'x'] = 1e12
    changed['frame'].loc[valid, 'planned'] = 'unseen'
    changed['frame'].loc[valid, 'unplanned'] = 'another-validation-only-level'
    actual, _, changed_receipt = prepare_fold(changed, train, valid)
    pd.testing.assert_frame_equal(expected, actual)
    assert receipt['purifier'] == changed_receipt['purifier']
    assert receipt['impute_means'] == changed_receipt['impute_means']
    assert [item.get('mapping', item.get('categories')) for item in receipt['encoding']] == [
        item.get('mapping', item.get('categories')) for item in changed_receipt['encoding']
    ]


@pytest.mark.django_db(transaction=True)
def test_durable_searches_keep_the_source_temporal_recipe(world):
    from execution_jobs import service
    from execution_jobs.models import NativeJob

    w = world
    w.frame['unplanned'] = ['early'] * 30 + ['later'] * 90
    w.frame['planned'] = ['a', 'b'] * 60
    w.frame.to_csv(w.path, index=False)
    prepared = post(w.clients['developer'], '/api/preprocessing/run/', {
        'file_id': w.file_id, 'options': [29], 'target_column': 'outcome',
        'split': {'strategy': 'oot', 'date_column': 'date', 'label_end_column': 'end',
                  'group_column': 'entity', 'cutoff': '2020-03-20'},
    })
    assert prepared.status_code == 200, prepared.content[:1000]
    data = {**options(w), 'processed_file': prepared.json()['processed_file'],
            'encoding_plan': [{'feature': 'planned', 'encoding_method': 'frequency_encoding'}],
            'encoding_use_native': False}
    identifier, _, _ = launch(w, 'training', data)
    service.execute(identifier)
    trained = NativeJob.objects.get(pk=identifier)
    assert trained.state == 'succeeded', list(trained.events.values('event_type', 'detail'))
    source = {'file_id': w.file_id, 'source_job_id': identifier,
              'source_result_sha256': trained.result_sha256,
              'execution_id': trained.result['payload']['execution_id'], 'cv_folds': 2, 'n_jobs': 1}
    for operation, extra in (
        ('sfs', {'methods': ['forward'], 'top_k': 1, 'stopping_criteria': {'max_features': 1}}),
        ('hpo', {'features': ['x', 'planned', 'unplanned'], 'n_iter': 2, 'search_method': 'random',
                 'fixed_params': {'n_estimators': 5}, 'validation_curve_points': 2,
                 'param_space': {'max_depth': {'type': 'int', 'min': 1, 'max': 2, 'enabled': True}}}),
    ):
        job_id, _, _ = launch(w, operation, {**source, **extra})
        service.execute(job_id)
        search = NativeJob.objects.get(pk=job_id)
        assert search.state == 'succeeded', list(search.events.values('event_type', 'detail'))
        payload = search.result['payload']
        rows = payload['forward'] if operation == 'sfs' else payload['trials']
        assert rows
        for row in rows:
            assert len(row['validation_provenance']) == 2
            for fold in row['validation_provenance']:
                tr, va = w.frame.loc[fold['train_rows']], w.frame.loc[fold['valid_rows']]
                assert tr.end.max() < va.date.min()
                assert set(tr.entity).isdisjoint(va.entity)
                assert fold['purifier']['fit_rows'] == tr.index.tolist()
                assert 'unplanned' in {item['feature'] for item in fold['encoding']}
