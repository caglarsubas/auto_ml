"""Trusted metric callbacks; business validation criteria are distinct from fit losses."""
from __future__ import annotations

import copy
import hashlib
from importlib.metadata import version
from pathlib import Path

import numpy as np
from scipy.special import expit, softmax

from modeling.prediction_contract import PredictionContractError


def metric_spec(contract):
    objective = (contract or {}).get('objective') or {}
    if not objective.get('primary_metric'):
        return None  # Historical input, never retroactively claim an accepted criterion.
    from modeling.sfs_objective import canonical_metric, direction, SUPPORTED
    task = contract.get('task') or ('classification' if contract.get('class_mapping') else 'regression')
    primary = canonical_metric(objective['primary_metric'])
    classes = len(contract.get('class_mapping') or []) if task == 'classification' else 0
    if task not in SUPPORTED or primary not in SUPPORTED[task]:
        raise PredictionContractError('The accepted objective is unsupported by native supervised fitting.')
    if task == 'classification' and classes < 2:
        raise PredictionContractError('Native fitting requires the accepted class mapping.')
    if classes > 2 and primary not in {'roc_auc', 'log_loss', 'accuracy', 'f1'}:
        raise PredictionContractError('This objective does not support the declared multiclass population.')
    if objective.get('direction', direction(primary)) != direction(primary):
        raise PredictionContractError('The accepted objective has a contradictory direction.')
    try:
        costs = {key: float((objective.get('cost_matrix') or {}).get(key, 1)) for key in ('fn_cost', 'fp_cost')}
        if any(not np.isfinite(value) or value < 0 for value in costs.values()):
            raise ValueError()
    except (TypeError, ValueError) as error:
        raise PredictionContractError('Business costs must be finite and nonnegative.') from error
    metric_runtime = {package: version(package) for package in ('numpy', 'scipy', 'scikit-learn')}
    implementation = hashlib.sha256()
    for name in ('declared_metric.py', 'development_assessment.py'):
        implementation.update(name.encode())
        implementation.update((Path(__file__).parent / name).read_bytes())
    return {'schema_version': 1, 'task': task, 'class_count': classes, 'primary_metric': primary,
            'direction': direction(primary), 'cost_matrix': costs, 'threshold': .5,
            'contract_sha256': contract.get('sha256'),
            'implementation_sha256': implementation.hexdigest(), 'metric_runtime': metric_runtime,
            'weighting': 'Unweighted observations; training class weights do not weight validation metrics.',
            'semantics': 'Weighted one-vs-rest ROC-AUC / weighted F1 across declared classes' if classes > 2 else
                         ('Regression prediction errors' if task == 'regression' else
                          'Binary probabilities; threshold metrics use 0.5; expected cost is per observation.')}


def bind_declared_metric(params, contract):
    result = dict(params)
    expected = metric_spec(contract)
    if expected:
        if result.get('_metric_spec') and result['_metric_spec'] != expected:
            raise PredictionContractError('Fit metric differs from the accepted declaration; refit the current execution.')
        result['_metric_spec'] = expected
    return result


def metric_value(spec, labels, predictions):
    from modeling.development_assessment import development_metrics
    value = development_metrics(labels, predictions, spec['task'], spec['class_count'], spec['cost_matrix'])[spec['primary_metric']]
    if value is None or not np.isfinite(value):
        raise PredictionContractError(f"Declared early-stopping metric {spec['primary_metric']} is unavailable in this partition. Revise the split/population or explicitly disable early stopping; no fallback criterion is used.")
    return float(value)


def prepare_metric(adapter, params, y_train, y_valid, enabled, num_boost_round):
    adapter.declared_metric_spec = copy.deepcopy(params.get('_metric_spec'))
    adapter.stopping_evidence = None
    spec = adapter.declared_metric_spec
    if not spec:
        return None
    if num_boost_round < 1 or enabled < 0:
        raise PredictionContractError('Declared native fitting requires positive boosting rounds and nonnegative early-stopping rounds.')
    if spec['task'] != adapter.task or (spec['class_count'] > 2 and params.get('num_class') != spec['class_count']):
        raise PredictionContractError('Native fitter task/class count contradicts the declared metric.')
    if spec['task'] == 'classification' and set(np.unique(y_train)) != set(range(spec['class_count'])):
        raise PredictionContractError('Training partition lacks a declared class; revise the split/population.')
    if enabled:
        # Check availability before a native fit. CatBoost evaluates its learn partition too.
        for labels in (y_train, y_valid):
            predictions = (np.full((len(labels), spec['class_count']), 1 / spec['class_count'])
                           if spec['class_count'] > 2 else np.full(len(labels), .5))
            metric_value(spec, labels, predictions)
    return spec


class CatBoostDeclaredMetric:
    """CatBoost provides raw margins. Ignore fit weights for business evaluation."""
    def __init__(self, spec):
        self.spec = spec

    def is_max_optimal(self):
        return self.spec['direction'] == 'maximize'

    def evaluate(self, approxes, target, weight):
        raw = np.asarray([list(values) for values in approxes], dtype=float)
        if self.spec['task'] == 'regression':
            predictions = raw[0]
        elif self.spec['class_count'] > 2:
            predictions = softmax(raw.T, axis=1)
        else:
            predictions = expit(raw[0])
        return metric_value(self.spec, np.asarray(list(target)), predictions), 1.

    def get_final_error(self, error, weight):
        return error


def record_stopping(adapter, values, training_loss, enabled, prediction_rounds):
    spec = adapter.declared_metric_spec
    if not spec:
        return
    values = [float(value) for value in values]
    if enabled and (not values or not np.isfinite(values).all() or not 1 <= prediction_rounds <= len(values)):
        raise PredictionContractError('Native fitter did not retain complete declared-metric stopping evidence.')
    adapter.stopping_evidence = {
        'schema_version': 1, 'metric_spec': spec, 'mode': 'declared_metric' if enabled else 'disabled',
        'validation_round_scores': values, 'evaluated_rounds': len(values),
        'prediction_rounds': int(prediction_rounds), 'best_iteration_zero_based': int(prediction_rounds - 1),
        'selected_validation_score': values[prediction_rounds - 1] if enabled else None,
        'label_precision': 'Native evaluation labels; regression labels may be rounded to float32.',
        'metric_precision': 'Native callback precision; XGBoost records evaluation history to six decimal places.',
        'training_loss': {'native_name': training_loss,
                          'role': 'Fitter surrogate loss, distinct from the business validation metric; class weights are recorded in effective parameters.'},
        'qualification': ('Exploratory development stopping; these validation outcomes are used during fitting, not independent assessment.'
                          if enabled else 'Early stopping disabled; validation outcomes are not used by the fitter. No independent-assessment claim.')}
