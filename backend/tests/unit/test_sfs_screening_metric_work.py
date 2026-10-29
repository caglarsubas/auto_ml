"""Objective-only screening preserves full CV, ranking and independent reports."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from sklearn import metrics

from modeling import development_assessment as assessment
from modeling import sfs_utils as sfs
from modeling.sfs_objective import direction

pytestmark = pytest.mark.unit


CLASSIFICATION = ['roc_auc', 'pr_auc', 'ks', 'log_loss', 'brier', 'accuracy',
                  'f1', 'precision', 'recall', 'expected_cost']
REGRESSION = ['r2', 'rmse', 'mae', 'mse']


def step(monkeypatch, task, metric, mode='forward', parallel=1, tied=False):
    rng = np.random.default_rng(161)
    frame = pd.DataFrame(rng.uniform(.05, .95, size=(36, 3)), columns=['a', 'b', 'c'])
    if tied:
        frame.loc[:, :] = .5
    labels = pd.Series(np.arange(len(frame)) % 2 if task == 'classification' else np.linspace(0, 1, len(frame)))
    fits = []

    def fit(algorithm, train, y_train, valid, y_valid, parameters, **options):
        fits.append((list(train.columns), train.index.tolist(), valid.index.tolist(), dict(parameters), options))
        predict = lambda values: values.mean(axis=1).to_numpy()
        return SimpleNamespace(predict=predict, predict_proba=predict,
                               shap_model=lambda: None, gain_importance=lambda: [], fit_receipt={'independent_test_adapter': True})

    monkeypatch.setattr(sfs, '_sfs_fit', fit)
    monkeypatch.setattr(sfs, 'compute_shap_importance', lambda *args: {})
    result = sfs._run_selection_step(
        frame.iloc[:24], labels.iloc[:24], frame.iloc[24:], labels.iloc[24:],
        ['a'] if mode == 'forward' else list(frame), 1, 2, parallel, 2, task,
        'xgboost', None, mode,
        {'primary_metric': metric, 'direction': direction(metric), 'cost_matrix': {'fn_cost': 3, 'fp_cost': 2},
         'qualification': 'development test fixture'},
    )
    return result, fits


@pytest.mark.parametrize('task,metric', [('classification', m) for m in CLASSIFICATION] +
                         [('regression', m) for m in REGRESSION])
@pytest.mark.parametrize('mode', ['forward', 'backward'])
def test_ranked_top_k_folds_reports_and_fit_budgets_match_full_reference(monkeypatch, task, metric, mode):
    reference = assessment.development_metrics
    observed = Mock(wraps=reference)
    monkeypatch.setattr(assessment, 'development_metrics', observed)
    actual, actual_fits = step(monkeypatch, task, metric, mode)
    calls = list(observed.call_args_list)
    screening = [call for call in calls if call.kwargs.get('metric') is not None]
    assert len(screening) == (2 if mode == 'forward' else 3)
    assert all(call.kwargs['metric'] == metric for call in screening)
    assert len(calls) - len(screening) == 6  # two top-K folds each, then train/valid
    assert all(set(row) == set(CLASSIFICATION if task == 'classification' else REGRESSION)
               for row in actual['cv_evidence']['fold_metrics'])
    for call in screening:
        args = call.args
        actual_value = reference(*args, metric=metric)[metric]
        assert actual_value == pytest.approx(reference(*args)[metric], abs=2e-14, rel=2e-14)
        y, p = args[:2]
        if metric == 'roc_auc':
            assert actual_value == pytest.approx(metrics.roc_auc_score(y, p), abs=2e-14)
        elif metric == 'rmse':
            assert actual_value == pytest.approx(np.sqrt(metrics.mean_squared_error(y, p)))
    monkeypatch.setattr(assessment, 'development_metrics', lambda *args, **kwargs: reference(*args))
    expected, expected_fits = step(monkeypatch, task, metric, mode)
    assert actual_fits == expected_fits
    for key in ['feature_name', 'selected_features', 'top_k_evaluated']:
        assert actual[key] == expected[key]
    assert actual['screening_scores'] == pytest.approx(expected['screening_scores'], abs=2e-14)
    assert actual['cv_candidate_scores'] == expected['cv_candidate_scores']
    assert actual['cv_evidence'] == expected['cv_evidence']
    assert actual['fit_receipt'] == expected['fit_receipt']


@pytest.mark.parametrize('mode,parallel', [('forward', 1), ('forward', 2), ('backward', 1), ('backward', 2)])
def test_exact_screening_ties_keep_declared_feature_order_and_full_evidence(monkeypatch, mode, parallel):
    actual, _ = step(monkeypatch, 'classification', 'roc_auc', mode, parallel, tied=True)
    assert actual['top_k_evaluated'] == (['b', 'c'] if mode == 'forward' else ['a', 'b'])
    assert actual['feature_name'] == actual['top_k_evaluated'][0]
    assert all(v == .5 for v in actual['screening_scores'].values())
    assert len(actual['cv_evidence']['fold_metrics']) == 2


@pytest.mark.parametrize('name', ['roc_auc_score', 'confusion_matrix', 'roc_curve', 'precision_recall_curve'])
def test_screening_cannot_bypass_public_reference_failure_in_top_k_assessment(monkeypatch, name):
    def refuse(*args, **kwargs):
        raise ValueError('independent full assessment refused')
    monkeypatch.setattr(assessment, name, refuse)
    with pytest.raises(ValueError, match='independent full assessment refused'):
        step(monkeypatch, 'classification', 'roc_auc')


@pytest.mark.parametrize('failure', ['labels', 'predictions', 'unavailable'])
def test_invalid_or_unavailable_screening_cannot_start_cv_or_publish_a_step(monkeypatch, failure):
    original = assessment.development_metrics
    full_calls = []

    def invalid(y, p, task, *args, **kwargs):
        if not kwargs.get('metric'):
            full_calls.append(1)
        if failure == 'labels':
            y = np.full(len(y), 2)
        elif failure == 'predictions':
            p = np.full(len(p), np.nan)
        else:
            y = np.zeros(len(y), dtype=int)
        return original(y, p, task, *args, **kwargs)

    monkeypatch.setattr(assessment, 'development_metrics', invalid)
    with pytest.raises(ValueError):
        step(monkeypatch, 'classification', 'roc_auc')
    assert not full_calls
