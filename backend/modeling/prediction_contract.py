"""Versioned, explicit task/label semantics shared by execution artifacts.

This is a structural contract, not evidence that the customer's statements
about availability, population or label maturity have been independently checked.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np
import pandas as pd


class PredictionContractError(ValueError):
    pass


def _object(value, name):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PredictionContractError(f'{name} must be an object.')
    return value


def bind_training_declaration(requested, state):
    """Bind the task identity to its saved pipeline when one has been declared."""
    saved = state.get('business_understanding') or (state.get('crisp_dm') or {}).get('business_understanding')
    if requested is None:
        return saved
    if not isinstance(requested, dict):
        raise PredictionContractError('Supply the accepted business declaration as an object.')
    if isinstance(saved, dict):
        def identity(value):
            target = _object(value.get('target_contract'), 'target_contract')
            task = str(value.get('problem_type') or '').strip().lower()
            positive = target.get('positive_class') if task in {'classification', 'anomaly'} else None
            return task, str(target.get('target_column') or '').strip(), None if positive is None else str(positive)

        accepted = identity(saved)
        if accepted[0] and accepted[1] and identity(requested) != accepted:
            raise PredictionContractError('The requested task, target or positive label differs from the saved pipeline declaration. Save the updated declaration before training.')
    return requested


def frozen_prediction_task(contract, *recorded_tasks):
    """Validate frozen label semantics before interpreting model outputs."""
    task = contract.get('task') if isinstance(contract, dict) else None
    if task not in ('classification', 'regression', 'anomaly') or any(
        value is not None and value != task for value in recorded_tasks
    ):
        raise PredictionContractError('Recorded model task disagrees with the frozen prediction contract. Select valid execution evidence.')
    target, mapping, positive = contract.get('target_column'), contract.get('class_mapping'), contract.get('positive_class')
    if not isinstance(target, str) or not target or not isinstance(mapping, list):
        raise PredictionContractError('Frozen target or class mapping is missing. Select valid execution evidence.')
    labels = []
    for index, entry in enumerate(mapping):
        label = entry.get('label') if isinstance(entry, dict) else None
        if (type(label) not in (str, bool, int, float) or (type(label) is float and not math.isfinite(label))
                or type(entry.get('encoded')) is not int or entry['encoded'] != index):
            raise PredictionContractError('Frozen class order is invalid. Select valid execution evidence.')
        labels.append(label)
    count = len(labels)
    if (len(set(labels)) != count or (task == 'regression' and count != 0)
            or (task == 'anomaly' and count != 2) or (task == 'classification' and count < 2)
            or (count == 2 and (type(positive) is not type(labels[1]) or positive != labels[1]))
            or (count != 2 and positive is not None)):
        raise PredictionContractError('Frozen positive label or class mapping disagrees with the declared task. Select valid execution evidence.')
    return task


def resolve_prediction_contract(frame: pd.DataFrame, declaration: dict, algorithm: str):
    if not isinstance(declaration, dict):
        raise PredictionContractError('Accept a business declaration before training.')
    task = str(declaration.get('problem_type') or '').strip().lower()
    if task not in ('classification', 'regression', 'anomaly'):
        raise PredictionContractError('Declare problem_type: classification, regression or anomaly; label cardinality does not determine the task.')
    target_spec = _object(declaration.get('target_contract'), 'target_contract')
    for field in ('population', 'prediction_horizon', 'objective'):
        if not str(declaration.get(field) or '').strip():
            raise PredictionContractError(f'Declare {field} before training.')
    for field in ('event_definition', 'label_maturity'):
        if not str(target_spec.get(field) or '').strip():
            raise PredictionContractError(f'Declare target_contract.{field} before training.')
    availability = _object(declaration.get('feature_availability'), 'feature_availability')
    if availability.get('default') != 'available_at_prediction':
        raise PredictionContractError('Confirm the feature availability policy at prediction time; exclude features observed only after the outcome.')
    target = str(target_spec.get('target_column') or '').strip()
    if not target or target not in frame.columns:
        raise PredictionContractError('Declare a target_column present in this dataset.')
    if not frame.index.is_unique or not frame.columns.is_unique:
        raise PredictionContractError('Dataset row and column identifiers must be unique.')
    labels = frame[target]
    if labels.isna().any():
        raise PredictionContractError('Target contains missing labels. Define and prepare the eligible, mature-label population before training; missing labels are never treated as negative outcomes.')
    classes: list[Any] = []
    if task == 'regression':
        if algorithm in ('logistic_regression', 'scorecard', 'isolation_forest'):
            raise PredictionContractError(f'{algorithm} does not support the declared regression task. Choose a regression booster.')
        encoded = pd.to_numeric(labels, errors='coerce').astype(float)
        if not np.isfinite(encoded.to_numpy()).all():
            raise PredictionContractError('Regression labels must be finite numeric values.')
    else:
        if algorithm == 'isolation_forest' and task != 'anomaly':
            raise PredictionContractError('Isolation forest produces an anomaly ranking. Declare the anomaly task; these scores are not classification probabilities.')
        classes = sorted(labels.unique().tolist(), key=lambda x: (type(x).__name__, str(x)))
        if len(classes) < 2:
            raise PredictionContractError('At least two observed outcome classes are required for this labeled workflow.')
        if algorithm in ('logistic_regression', 'scorecard', 'isolation_forest') and len(classes) != 2:
            raise PredictionContractError(f'{algorithm} currently supports binary labeled outcomes only.')
        if task == 'anomaly' and algorithm != 'isolation_forest':
            raise PredictionContractError('The anomaly task currently requires isolation_forest.')
        if len(classes) == 2:
            positive = target_spec.get('positive_class')
            matches = [value for value in classes if str(value) == str(positive)] if positive is not None else []
            if len(matches) != 1:
                raise PredictionContractError('Declare positive_class as one of the two observed labels, including its business meaning in event_definition.')
            positive = matches[0]
            classes = [value for value in classes if value != positive] + [positive]
        encoded = labels.map({value: index for index, value in enumerate(classes)}).astype(int)
    objective = _object(declaration.get('success_criteria'), 'success_criteria')
    metric = str(objective.get('primary_metric') or '').strip().lower()
    classification_metrics = {'roc_auc', 'auc', 'pr_auc', 'average_precision', 'log_loss', 'accuracy', 'f1', 'precision', 'recall', 'ks', 'brier', 'expected_cost'}
    regression_metrics = {'r2', 'rmse', 'mae', 'mse'}
    anomaly_metrics = {'roc_auc', 'auc', 'pr_auc', 'average_precision'}
    supported_metrics = regression_metrics if task == 'regression' else (anomaly_metrics if task == 'anomaly' else classification_metrics)
    if metric not in supported_metrics:
        raise PredictionContractError(f'Objective {metric!r} is incompatible with the declared task or is not yet supported.')
    if task == 'classification' and len(classes) > 2:
        if metric not in {'roc_auc', 'auc', 'log_loss', 'accuracy', 'f1'}:
            raise PredictionContractError('Multiclass objectives currently support weighted one-vs-rest ROC-AUC, log loss, accuracy and weighted F1 only.')
        if objective.get('averaging', 'weighted') != 'weighted':
            raise PredictionContractError('Multiclass objective averaging currently requires weighted; revise the objective explicitly.')
        objective = {**objective, 'averaging': 'weighted', 'multiclass_auc': 'one_vs_rest'}
    expected_direction = 'minimize' if metric in {'rmse', 'mae', 'mse', 'log_loss', 'brier', 'expected_cost'} else 'maximize'
    if objective.get('direction', expected_direction) != expected_direction:
        raise PredictionContractError(f'{metric} requires direction={expected_direction}.')
    objective = {**objective, 'primary_metric': metric, 'direction': expected_direction}
    costs = _object(objective.get('cost_matrix'), 'success_criteria.cost_matrix')
    try:
        costs = {name: float(costs.get(name, 1)) for name in ('fn_cost', 'fp_cost')}
        if any(not np.isfinite(value) or value < 0 for value in costs.values()):
            raise ValueError()
        floor = objective.get('floor')
        if floor is not None and not np.isfinite(float(floor)):
            raise ValueError()
    except (ValueError, TypeError):
        raise PredictionContractError('Metric floors must be finite and business costs must be finite and nonnegative.')
    objective['cost_matrix'] = costs
    forbidden = declaration.get('forbidden_features') or []
    if not isinstance(forbidden, list):
        raise PredictionContractError('forbidden_features must be a list of column names.')
    overrides = availability.get('overrides') or {}
    if not isinstance(overrides, dict) or any(value not in ('available_at_prediction', 'excluded') for value in overrides.values()):
        raise PredictionContractError('Feature availability overrides must mark columns as available_at_prediction or excluded.')
    forbidden = list(dict.fromkeys(forbidden + [str(column) for column, value in overrides.items() if value == 'excluded']))
    class_mapping = [{'encoded': index, 'label': value.item() if isinstance(value, np.generic) else value} for index, value in enumerate(classes)]
    positive_label = class_mapping[1]['label'] if len(class_mapping) == 2 else None
    contract = {
        'schema_version': 1,
        'task': task,
        'target_column': target,
        'class_mapping': class_mapping,
        'positive_class': positive_label,
        'population': str(declaration.get('population') or ''),
        'prediction_horizon': str(declaration.get('prediction_horizon') or ''),
        'target_contract': {**target_spec, 'target_column': target, 'positive_class': positive_label},
        'feature_availability': availability,
        'forbidden_features': list(map(str, forbidden)),
        'objective': objective,
        'qualification': 'declared; population, availability and maturity require review',
    }
    frozen_prediction_task(contract)
    contract['sha256'] = hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return contract, encoded
