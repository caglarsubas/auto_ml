"""Task semantics, complete fold coverage, invalid inputs and real adapter CV."""
import numpy as np
import pandas as pd
import pytest

from modeling.development_assessment import assess_development_cv, development_metrics, metric_coverage, run_development_cv
from modeling.development_validation import development_folds, iter_validation_folds
from modeling.prediction_contract import PredictionContractError
from tests.unit.test_purifier_replay import recipe

pytestmark = pytest.mark.unit


def context(task='regression', strategy='group', primary=None):
    rng = np.random.default_rng(22)
    frame = pd.DataFrame({'x': rng.normal(size=180), 'entity': np.repeat(range(30), 6),
                          'date': pd.date_range('2025-01-01', periods=180)})
    labels = pd.Series(frame.x * 2 if task == 'regression' else (frame.x > 0).astype(int), index=frame.index)
    return {'frame': frame, 'labels': labels, 'task': task, 'target_column': 'outcome',
            'excluded_features': ['entity', 'date'], 'purifier_recipe': recipe([29]),
            'split_meta': {'strategy': strategy, 'split_config': {'group_column': 'entity', 'date_column': 'date'}},
            'class_weight_policy': 'train_label_ratio' if task == 'classification' else None,
            'prediction_contract': {'class_mapping': [] if task == 'regression' else [{'encoded': 0}, {'encoded': 1}],
                                    'objective': {'primary_metric': primary or ('rmse' if task == 'regression' else 'roc_auc')}}}


def test_metric_coverage_never_substitutes_an_available_fold_mean():
    result = metric_coverage([.9, None, .7, np.nan])
    assert result == {'mean': None, 'std': None, 'n_valid': 2, 'n_total': 4, 'status': 'partial'}
    complete = metric_coverage([.9, .7])
    assert complete['mean'] == pytest.approx(.8) and complete['std'] == pytest.approx(.1)
    assert metric_coverage([])['status'] == 'unavailable'


def test_regression_reference_metrics_do_not_invent_constant_target_r2():
    result = development_metrics([1., 1., 1.], [1., 2., 0.], 'regression')
    assert result['r2'] is None
    assert result['mse'] == pytest.approx(2/3)
    assert result['mae'] == pytest.approx(2/3)


@pytest.mark.parametrize('predictions', [[np.nan, .5], [.5], [.5, .8, .9], [[.5], [.5]], [-.1, .5], [1.1, .5]])
def test_bad_binary_predictions_fail_without_filtering_or_clipping(predictions):
    with pytest.raises(ValueError):
        development_metrics([0, 1], predictions, 'classification')


def test_one_class_validation_discloses_unavailable_discrimination():
    result = development_metrics([1, 1], [.9, .8], 'classification')
    assert result['roc_auc'] is None and result['pr_auc'] is None and result['ks'] is None
    assert result['accuracy'] == 1 and result['log_loss'] > 0


@pytest.mark.parametrize('n_splits', [True, 1, 2.5])
def test_invalid_fold_count_is_not_coerced(n_splits):
    config = context()
    with pytest.raises(ValueError, match='integer fold count'):
        list(development_folds(config, config['frame'].index, config['labels'], n_splits))


def test_group_contract_never_falls_back_to_shuffled_folds():
    config = context()
    config['split_meta']['split_config'] = {}
    with pytest.raises(ValueError, match='shuffled fallback is prohibited'):
        list(development_folds(config, config['frame'].index, config['labels'], 3))


def test_changed_labels_or_task_cannot_reuse_recorded_development_population():
    config = context()
    changed = config['labels'].copy()
    changed.iloc[0] = 1e8
    with pytest.raises(ValueError, match='recorded row membership'):
        list(development_folds(config, config['frame'].index, changed, 3))
    with pytest.raises(ValueError, match='contradicts'):
        list(iter_validation_folds(config, config['frame'][['x']], config['labels'], 3, 'classification'))
    with pytest.raises(ValueError, match='unique members'):
        list(development_folds(config, pd.Index([0, 0, 1]), config['labels'].iloc[:3], 2))


@pytest.mark.parametrize('task', ['classification', 'regression'])
@pytest.mark.parametrize('strategy', ['group', 'oot'])
@pytest.mark.parametrize('algorithm', ['xgboost', 'lightgbm', 'catboost'])
def test_real_booster_development_cv_records_exact_fit_population(task, strategy, algorithm):
    config = context(task, strategy)
    params = {'task': task, 'objective': 'reg:squarederror' if task == 'regression' else 'binary:logistic',
              'eval_metric': 'rmse' if task == 'regression' else 'auc', 'max_depth': 2, 'nthread': 1}
    result = assess_development_cv(config, config['frame'][['x']], config['labels'], algorithm, params,
                                   n_splits=3, num_boost_round=10, early_stopping_rounds=3)
    assert result['task'] == task and result['status'] == 'completed'
    expected_training_metric = ('RMSE' if task == 'regression' else 'AUC') if algorithm == 'catboost' else ('rmse' if task == 'regression' else 'auc')
    assert result['training_eval_metric'] == expected_training_metric
    assert all(fold['training_eval_metric'] == expected_training_metric for fold in result['folds'])
    assert result['metric_coverage'][result['primary_metric']]['n_valid'] == 3
    for fold, receipt in zip(result['folds'], result['fold_provenance']):
        assert receipt['purifier']['fit_rows'] == receipt['train_rows']
        if task == 'classification':
            labels = config['labels'].loc[receipt['train_rows']]
            assert receipt['class_weight']['fit_rows'] == receipt['train_rows']
            assert receipt['class_weight']['scale_pos_weight'] == pytest.approx((labels == 0).sum() / (labels == 1).sum())
        assert fold['n_train'] == len(receipt['train_rows'])
        assert set(config['frame'].loc[receipt['train_rows'], 'entity']).isdisjoint(config['frame'].loc[receipt['valid_rows'], 'entity'])
        assert receipt['purifier']['clip_bounds']['x']['hi'] == pytest.approx(config['frame'].loc[receipt['train_rows'], 'x'].quantile(.95))
    assert result['roc_curve'] is None if task == 'regression' else result['roc_curve'] is not None


@pytest.mark.parametrize('algorithm', ['logistic_regression', 'scorecard'])
def test_alternate_binary_cv_replays_raw_fitted_transforms(algorithm):
    config = context('classification')
    result = assess_development_cv(config, config['frame'][['x']], config['labels'], algorithm, {'C': 1.})
    assert len(result['fold_provenance']) == 5
    assert result['roc_auc_mean'] is not None


def test_undefined_required_metric_blocks_new_run_but_legacy_failure_is_explicit():
    config = context(primary='r2')
    config['labels'][:] = 1.
    with pytest.raises(PredictionContractError, match='r2 is available in 0 of 5'):
        run_development_cv(config, config['frame'][['x']], config['labels'], 'xgboost',
                           {'task': 'regression', 'objective': 'reg:squarederror', 'eval_metric': 'rmse', 'nthread': 1})
    config.pop('purifier_recipe')
    config['split_meta']['split_config'] = {}
    legacy = run_development_cv(config, config['frame'][['x']], config['labels'], 'xgboost', {})
    assert legacy['status'] == 'unavailable' and 'group_column' in legacy['limitations'][0]


def test_multiclass_probability_column_count_is_declared():
    with pytest.raises(ValueError, match='every declared class'):
        development_metrics([0, 1, 2], np.ones((3, 4))/4, 'classification', class_count=3)
    result = development_metrics([0, 1], np.array([[.8, .1, .1], [.1, .8, .1]]), 'classification', class_count=3)
    assert result['roc_auc'] is None and result['f1'] == 1


def test_hpo_cannot_hide_single_class_validation_folds():
    from modeling.hyperparam_utils import _evaluate_config, _evaluate_cv_only
    config = context('classification')
    config['frame']['entity'] = np.repeat(range(3), 60)
    config['labels'] = pd.Series([0] * 60 + [1] * 60 + [0, 1] * 30)
    X, y = config['frame'][['x']], config['labels']
    params = {'max_depth': 2, 'n_estimators': 5}
    result = _evaluate_config(X, y, X.iloc[-30:], y.iloc[-30:], params, 3, False, 1, .5,
                              early_stopping_rounds=2, validation_context=config)
    assert result['cv']['roc_auc']['n_valid'] == 1
    assert result['cv']['roc_auc']['n_total'] == 3
    assert result['cv']['roc_auc']['status'] == 'partial'
    assert np.isnan(result['cv']['roc_auc']['mean'])
    assert result['cv']['log_loss']['status'] == 'complete'
    with pytest.raises(ValueError, match='partial-fold averaging is prohibited'):
        _evaluate_cv_only(X, y, params, 3, False, 1, .5, 'roc_auc', early_stopping_rounds=2, validation_context=config)


def test_constant_target_r2_semantics_agree_in_hpo_and_final_assessment():
    from modeling.hyperparam_utils import _compute_regression_metrics
    from evaluation.eval_utils import evaluate_regression
    assert np.isnan(_compute_regression_metrics(np.ones(3), np.ones(3))['r2'])
    assert evaluate_regression(np.ones(3), np.ones(3))['metrics']['r2'] is None


@pytest.mark.parametrize('predictions', [
    [[-.1, .5, .6], [.1, .1, .8]], [[.1, .2, .2], [.1, .1, .8]],
])
def test_multiclass_invalid_probabilities_are_not_clipped_or_normalized(predictions):
    with pytest.raises(ValueError, match='summing to one'):
        development_metrics([0, 1], predictions, 'classification', class_count=3)


def test_pr_curve_grid_preserves_perfect_ranking_with_duplicate_recall_points():
    from modeling.development_assessment import _binary_curves
    curves = _binary_curves([np.array([0, 1]), np.array([0, 1])],
                            [np.array([.1, .9]), np.array([.2, .8])])
    assert np.allclose(curves['pr_curve']['mean_precision'], 1.)
    assert np.allclose(curves['pr_curve']['std_precision'], 0.)
    assert curves['pr_curve_micro']['ap'] == 1.


def test_partial_secondary_r2_keeps_errors_but_never_fabricates_an_aggregate():
    config = context()
    config['frame']['entity'] = np.repeat(range(3), 60)
    config['labels'].iloc[:60] = 1.
    result = assess_development_cv(config, config['frame'][['x']], config['labels'], 'xgboost',
        {'task': 'regression', 'objective': 'reg:squarederror', 'eval_metric': 'rmse', 'nthread': 1},
        n_splits=3, num_boost_round=10, early_stopping_rounds=3)
    assert result['status'] == 'completed' and result['rmse_mean'] is not None
    assert result['r2_mean'] is None and result['r2_std'] is None
    assert result['metric_coverage']['r2'] == {'mean': None, 'std': None, 'n_valid': 2, 'n_total': 3, 'status': 'partial'}
    assert '2 of 3 folds' in result['limitations'][0]
