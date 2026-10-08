"""Independent metric references, native round selection and scoring replay."""
import json

import numpy as np
import pandas as pd
import pytest
from sklearn import metrics

from modeling.booster_adapters import get_adapter
from modeling.declared_metric import bind_declared_metric, metric_spec

pytestmark = pytest.mark.unit
ALGORITHMS = ['xgboost', 'lightgbm', 'catboost']


def population(task='classification', classes=2):
    rng = np.random.default_rng(28)
    size = classes * 60 if classes > 2 else 180
    split = size * 2 // 3
    X = pd.DataFrame({'signal': rng.normal(size=size), 'noise': rng.normal(size=size)})
    if task == 'regression':
        y = pd.Series(X.signal * 2 + rng.normal(0, .2, len(X)))
    elif classes > 2:
        y = pd.Series(np.tile(np.arange(classes), len(X) // classes))
        X.signal += y
    else:
        y = pd.Series((X.signal > .3).astype(int))
    return X.iloc[:split], y.iloc[:split], X.iloc[split:], y.iloc[split:]


def fit(algorithm, metric, task='classification', classes=2, rounds=12, stopping=3, parts=None):
    contract = {'task': task, 'class_mapping': [{'encoded': i} for i in range(classes)] if task == 'classification' else [],
                'objective': {'primary_metric': metric, 'cost_matrix': {'fn_cost': 7, 'fp_cost': 2}}}
    params = {'task': task, 'objective': 'reg:squarederror' if task == 'regression' else 'binary:logistic',
              'eval_metric': 'rmse' if task == 'regression' else 'auc', 'nthread': 1, 'seed': 42,
              'max_depth': 2, 'eta': .2}
    if classes > 2 and task == 'classification':
        params.update(objective='multi:softprob', num_class=classes, eval_metric='mlogloss')
    elif task == 'classification':
        params['scale_pos_weight'] = 3
    parts = parts or population(task, classes)
    return get_adapter(algorithm).train(*parts, bind_declared_metric(params, contract),
                                       num_boost_round=rounds, early_stopping_rounds=stopping), parts


def reference(metric, y, p):
    if metric == 'mse':
        return metrics.mean_squared_error(y, p)
    if metric == 'rmse':
        return np.sqrt(metrics.mean_squared_error(y, p))
    if metric == 'mae':
        return metrics.mean_absolute_error(y, p)
    if metric == 'r2':
        return metrics.r2_score(y, p)
    if metric == 'roc_auc':
        return metrics.roc_auc_score(y, p)
    if metric == 'pr_auc':
        return metrics.average_precision_score(y, p)
    if metric == 'log_loss':
        return metrics.log_loss(y, p, labels=[0, 1])
    if metric == 'brier':
        return metrics.brier_score_loss(y, p)
    if metric == 'ks':
        fpr, tpr, _ = metrics.roc_curve(y, p)
        return np.max(np.abs(tpr - fpr))
    pred = (p >= .5).astype(int)
    if metric == 'expected_cost':
        return (7 * np.sum((y == 1) & (pred == 0)) + 2 * np.sum((y == 0) & (pred == 1))) / len(y)
    if metric == 'accuracy':
        return metrics.accuracy_score(y, pred)
    return {'f1': metrics.f1_score, 'precision': metrics.precision_score,
            'recall': metrics.recall_score}[metric](y, pred, zero_division=0)


@pytest.mark.parametrize('algorithm', ALGORITHMS)
@pytest.mark.parametrize('task,metric', [('classification', name) for name in
    ['roc_auc', 'pr_auc', 'log_loss', 'brier', 'expected_cost', 'accuracy', 'f1', 'precision', 'recall', 'ks']] +
    [('regression', name) for name in ['r2', 'rmse', 'mae', 'mse']])
def test_declared_metric_selects_rounds_and_matches_independent_reference(algorithm, task, metric, tmp_path):
    adapter, (_, _, X, y) = fit(algorithm, metric, task)
    receipt = adapter.fit_receipt
    stopping = receipt['stopping_evidence']
    scores = stopping['validation_round_scores']
    optimal = int(np.argmin(scores) if stopping['metric_spec']['direction'] == 'minimize' else np.argmax(scores))
    assert stopping['best_iteration_zero_based'] == optimal
    assert stopping['prediction_rounds'] == optimal + 1
    assert receipt['training_eval_metric'] == metric
    prediction = adapter.predict(X)
    # XGBoost formats recorded evaluation values to six decimals; labels in native datasets are float32.
    assert stopping['selected_validation_score'] == pytest.approx(reference(metric, y.astype('float32'), prediction), abs=1e-6, rel=1e-6)
    assert receipt['validation_role'] == 'early_stopping'
    assert stopping['metric_spec']['cost_matrix'] == {'fn_cost': 7, 'fp_cost': 2}
    json.dumps(receipt, allow_nan=False)
    path = tmp_path / adapter.model_filename(1)
    adapter.save(str(path))
    replay = type(adapter).load(str(path), feature_names=list(X.columns))
    np.testing.assert_allclose(replay.predict(X), prediction, atol=1e-12, rtol=1e-12)
    np.testing.assert_allclose(np.concatenate([replay.predict(X.iloc[:9]), replay.predict(X.iloc[9:])]), prediction,
                               atol=1e-12, rtol=1e-12)


@pytest.mark.parametrize('algorithm', ALGORITHMS)
@pytest.mark.parametrize('metric', ['roc_auc', 'log_loss', 'accuracy', 'f1'])
@pytest.mark.parametrize('classes', [3, 65])
def test_multiclass_metric_preserves_weighted_semantics(algorithm, metric, classes):
    # The many-class case exercises probability dimension/order, not model-quality claims.
    parts = population(classes=classes) if classes == 3 else (
        pd.DataFrame({'signal': np.tile(np.arange(65), 4)}), pd.Series(np.tile(np.arange(65), 4)),
        pd.DataFrame({'signal': np.tile(np.arange(65), 2)}, index=range(260, 390)),
        pd.Series(np.tile(np.arange(65), 2), index=range(260, 390)))
    adapter, (_, _, X, y) = fit(algorithm, metric, classes=classes, parts=parts, rounds=4, stopping=2)
    p = adapter.predict_proba(X)
    expected = {'roc_auc': lambda: metrics.roc_auc_score(y, p, multi_class='ovr', average='weighted'),
                'log_loss': lambda: metrics.log_loss(y, p, labels=np.arange(classes)),
                'accuracy': lambda: metrics.accuracy_score(y, p.argmax(axis=1)),
                'f1': lambda: metrics.f1_score(y, p.argmax(axis=1), average='weighted')}[metric]()
    assert adapter.fit_receipt['stopping_evidence']['selected_validation_score'] == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize('algorithm', ALGORITHMS)
@pytest.mark.parametrize('task,metric', [('classification', 'roc_auc'), ('regression', 'r2')])
def test_disabled_stopping_uses_no_validation_labels_and_preserves_round_budget(algorithm, task, metric):
    X, y, V, z = population(task)
    first, _ = fit(algorithm, metric, task, stopping=0, parts=(X, y, V, z))
    second, _ = fit(algorithm, metric, task, stopping=0, parts=(X, y, V, z * 0))
    receipt = first.fit_receipt
    assert receipt['validation_role'] == 'not_used_by_fitter'
    assert receipt['stopping_evidence']['mode'] == 'disabled'
    assert receipt['stopping_evidence']['validation_round_scores'] == []
    assert receipt['stopping_evidence']['prediction_rounds'] == 12
    np.testing.assert_array_equal(first.predict(V), second.predict(V))


@pytest.mark.parametrize('algorithm', ALGORITHMS)
@pytest.mark.parametrize('metric', ['brier', 'log_loss', 'expected_cost'])
def test_single_class_validation_can_use_available_loss(algorithm, metric):
    X, y, V, z = population()
    adapter, _ = fit(algorithm, metric, parts=(X, y, V, z * 0))
    assert adapter.training_eval_metric == metric
    assert adapter.fit_receipt['stopping_evidence']['evaluated_rounds'] >= 1


@pytest.mark.parametrize('algorithm', ALGORITHMS)
@pytest.mark.parametrize('task,metric', [('classification', 'roc_auc'), ('classification', 'pr_auc'),
                                       ('classification', 'ks'), ('regression', 'r2')])
def test_undefined_declared_criterion_blocks_without_native_fallback(algorithm, task, metric):
    X, y, V, z = population(task)
    with pytest.raises(ValueError, match='unavailable.*disable early stopping'):
        fit(algorithm, metric, task, parts=(X, y, V, z * 0))


@pytest.mark.parametrize('algorithm', ALGORITHMS)
def test_first_round_is_retained_when_validation_deteriorates(algorithm):
    X = pd.DataFrame({'signal': np.tile([-1., 1.], 100)})
    y = pd.Series(np.tile([0, 1], 100))
    adapter, _ = fit(algorithm, 'log_loss', parts=(X.iloc[:120], y.iloc[:120], X.iloc[120:], 1-y.iloc[120:]))
    receipt = adapter.fit_receipt['stopping_evidence']
    assert receipt['best_iteration_zero_based'] == 0
    assert receipt['prediction_rounds'] == 1
    assert receipt['evaluated_rounds'] < 12
    if algorithm == 'catboost':
        assert adapter.best_iteration == 0 and adapter.model.tree_count_ == 1


@pytest.mark.parametrize('change', ['direction', 'costs', 'multiclass', 'stale'])
def test_contradictory_contract_cannot_supply_a_fit_metric(change):
    contract = {'task': 'classification', 'class_mapping': [{}, {}], 'objective': {'primary_metric': 'brier'}}
    if change == 'direction':
        contract['objective']['direction'] = 'maximize'
    elif change == 'costs':
        contract['objective']['cost_matrix'] = {'fn_cost': float('nan')}
    elif change == 'multiclass':
        contract['class_mapping'].append({})
    else:
        params = bind_declared_metric({}, contract)
        contract['objective']['primary_metric'] = 'pr_auc'
        with pytest.raises(ValueError, match='differs'):
            bind_declared_metric(params, contract)
        return
    with pytest.raises(ValueError):
        metric_spec(contract)


@pytest.mark.parametrize('algorithm', ALGORITHMS)
def test_zero_round_budget_is_explicitly_unsupported(algorithm):
    with pytest.raises(ValueError, match='positive boosting rounds'):
        fit(algorithm, 'brier', rounds=0)
