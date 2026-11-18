"""Versioned, explicit task/label semantics shared by execution artifacts.

This is a structural contract, not evidence that the customer's statements
about availability, population or label maturity have been independently checked.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
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


def _text(value, name, *, required=True):
    if value is None and not required:
        return ''
    if not isinstance(value, str) or (required and not value.strip()):
        raise PredictionContractError(f'Declare {name} as text before training.')
    return value.strip()


def _availability(value, forbidden):
    policy = _object(value, 'feature_availability')
    if set(policy) - {'default', 'overrides'} or policy.get('default') != 'available_at_prediction':
        raise PredictionContractError('Confirm availability at prediction time and declare individual feature overrides explicitly.')
    overrides = _object(policy.get('overrides'), 'feature_availability.overrides')
    if any(not isinstance(name, str) or not name.strip() or status not in ('available_at_prediction', 'excluded')
           for name, status in overrides.items()):
        raise PredictionContractError('Feature availability overrides must name columns and mark each as available_at_prediction or excluded.')
    if forbidden is None:
        forbidden = []
    if not isinstance(forbidden, list) or any(not isinstance(name, str) or not name.strip() for name in forbidden):
        raise PredictionContractError('forbidden_features must be a list of column names.')
    if any(overrides.get(name) == 'available_at_prediction' for name in forbidden):
        raise PredictionContractError('A forbidden feature cannot also be declared available at prediction time.')
    return {'default': policy['default'], 'overrides': overrides}, sorted(set(forbidden) | {
        name for name, status in overrides.items() if status == 'excluded'
    })


def outcome_window(value):
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'horizon_days', 'maturity_lag_days', 'development_as_of'}
            or type(value['horizon_days']) is not int or not 1 <= value['horizon_days'] <= 3650
            or type(value['maturity_lag_days']) is not int or not 0 <= value['maturity_lag_days'] <= 3650):
        raise PredictionContractError('Use an outcome window with 1–3650 horizon days, 0–3650 maturity-lag days and an explicit development as-of timestamp.')
    raw = value['development_as_of']
    try:
        if not isinstance(raw, str) or 'T' not in raw:
            raise ValueError
        as_of = datetime.fromisoformat(raw)
        if as_of.utcoffset() is None:
            raise ValueError
        stamp = as_of.astimezone(timezone.utc).isoformat()
        pd.Timestamp(stamp).as_unit('ns')
    except (ValueError, OverflowError):
        raise PredictionContractError('Use an ISO development as-of timestamp with a timezone inside the supported date range.') from None
    return {**value, 'development_as_of': stamp}


def outcome_window_bounds(frame, validation, window, as_of):
    """Return prediction and effective label-availability dates for a fixed window."""
    date, end = validation.get('date_column'), validation.get('label_end_column')
    if validation.get('strategy') != 'oot' or date == end or date not in frame or end not in frame:
        raise PredictionContractError('An executable outcome window requires out-of-time validation with separate prediction-date and label-end columns.')
    dates, ends = (pd.to_datetime(frame[name].astype('string'), format='ISO8601', errors='coerce', utc=True)
                   for name in (date, end))
    try:
        earliest_end = dates + pd.Timedelta(days=window['horizon_days'])
        mature = ends + pd.Timedelta(days=window['maturity_lag_days'])
        cutoff = pd.Timestamp(as_of).as_unit('ns')
    except (ValueError, OverflowError):
        raise PredictionContractError('Outcome window dates are outside the supported range.') from None
    if (dates.isna().any() or ends.isna().any() or (ends < earliest_end).any()
            or cutoff.tzinfo is None or pd.isna(cutoff) or (mature > cutoff).any()):
        raise PredictionContractError('Every eligible row needs valid dates, a complete prediction window and mature labels by the declared as-of timestamp.')
    return dates, mature


def check_availability_controls(contract, controls):
    overrides = contract['feature_availability'].get('overrides') or {}
    if any(overrides.get(name) == 'available_at_prediction' for name in controls):
        raise PredictionContractError('Validation control columns cannot be declared available predictors.')


def fixed_outcome_window(contract):
    if contract.get('schema_version') == 2:
        return (contract.get('target_contract') or {}).get('outcome_window')
    return None


def contract_business_understanding(contract):
    target = {**contract['target_contract'], 'target_column': contract['target_column'],
              'positive_class': contract['positive_class']}
    return {
        'problem_type': contract['task'], 'target_contract': target,
        'population': contract['population'], 'exclusions': contract.get('exclusions', ''),
        'prediction_horizon': contract['prediction_horizon'], 'feature_availability': contract.get('feature_availability', {}),
        'success_criteria': contract['objective'], 'forbidden_features': contract['forbidden_features'],
    }


def bind_training_declaration(requested, state):
    """Bind prediction identity and scope to the saved pipeline declaration."""
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
        if accepted[0] and accepted[1]:
            saved_target = _object(saved.get('target_contract'), 'target_contract')
            target = _object(requested.get('target_contract'), 'target_contract')
            for earlier, current, fields in (
                (saved, requested, ('population', 'exclusions', 'prediction_horizon')),
                (saved_target, target, ('event_definition', 'label_maturity', 'good_bad_window')),
            ):
                for field in fields:
                    value = _text(earlier.get(field), field, required=False)
                    explicit_optional = field in ('exclusions', 'good_bad_window') and field in earlier
                    if (value or explicit_optional) and value != _text(current.get(field), field, required=False):
                        raise PredictionContractError(f'The requested {field} differs from the saved pipeline declaration. Save the updated declaration before training.')
            existing = _object(saved.get('feature_availability'), 'feature_availability')
            if ((existing.get('default') or existing.get('overrides') or saved.get('forbidden_features'))
                    and _availability({**existing, 'default': existing.get('default') or 'available_at_prediction'}, saved.get('forbidden_features'))
                    != _availability(requested.get('feature_availability'), requested.get('forbidden_features'))):
                raise PredictionContractError('The requested feature policy differs from the saved pipeline declaration. Save the updated declaration before training.')
            if outcome_window(saved_target.get('outcome_window')) != outcome_window(target.get('outcome_window')):
                raise PredictionContractError('The requested outcome window differs from the saved pipeline declaration. Save the updated declaration before training.')
    return requested


def _digest(contract):
    return hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


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
    version = contract.get('schema_version')
    if version is not None and (type(version) is not int or version not in (1, 2)):
        raise PredictionContractError('The frozen prediction contract version is unsupported.')
    if version == 2:
        try:
            if contract.get('sha256') != _digest({key: value for key, value in contract.items() if key != 'sha256'}):
                raise ValueError
        except (TypeError, ValueError):
            raise PredictionContractError('Frozen prediction scope differs from its recorded digest. Select valid execution evidence.') from None
        target_spec = _object(contract.get('target_contract'), 'target_contract')
        _text(contract.get('population'), 'population')
        _text(contract.get('prediction_horizon'), 'prediction_horizon')
        _text(target_spec.get('label_maturity'), 'target_contract.label_maturity')
        availability, forbidden = _availability(contract.get('feature_availability'), contract.get('forbidden_features'))
        if (target_spec.get('target_column') != target or target_spec.get('positive_class') != positive
                or target in availability['overrides'] or availability != contract.get('feature_availability')
                or forbidden != contract.get('forbidden_features')
                or outcome_window(target_spec.get('outcome_window')) != target_spec.get('outcome_window')):
            raise PredictionContractError('Frozen feature or outcome scope is inconsistent. Select valid execution evidence.')
    return task


def resolve_prediction_contract(frame: pd.DataFrame, declaration: dict, algorithm: str, *, allow_outcome_window=False):
    if not isinstance(declaration, dict):
        raise PredictionContractError('Accept a business declaration before training.')
    task = str(declaration.get('problem_type') or '').strip().lower()
    if task not in ('classification', 'regression', 'anomaly'):
        raise PredictionContractError('Declare problem_type: classification, regression or anomaly; label cardinality does not determine the task.')
    target_spec = _object(declaration.get('target_contract'), 'target_contract')
    population = _text(declaration.get('population'), 'population')
    horizon = _text(declaration.get('prediction_horizon'), 'prediction_horizon')
    exclusions = _text(declaration.get('exclusions'), 'exclusions', required=False)
    _text(declaration.get('objective'), 'objective')
    maturity = _text(target_spec.get('label_maturity'), 'target_contract.label_maturity')
    event = _text(target_spec.get('event_definition'), 'target_contract.event_definition')
    availability, forbidden = _availability(declaration.get('feature_availability'), declaration.get('forbidden_features'))
    window = outcome_window(target_spec.get('outcome_window'))
    if window and not allow_outcome_window:
        raise PredictionContractError('Executable outcome windows are supported by native numeric out-of-time training. Use that training entrypoint.')
    target = str(target_spec.get('target_column') or '').strip()
    if not target or target not in frame.columns:
        raise PredictionContractError('Declare a target_column present in this dataset.')
    if not frame.index.is_unique or not frame.columns.is_unique:
        raise PredictionContractError('Dataset row and column identifiers must be unique.')
    if target in availability['overrides'] or any(name not in frame for name in availability['overrides']):
        raise PredictionContractError('Feature availability overrides must name existing dataset columns other than the target.')
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
    class_mapping = [{'encoded': index, 'label': value.item() if isinstance(value, np.generic) else value} for index, value in enumerate(classes)]
    positive_label = class_mapping[1]['label'] if len(class_mapping) == 2 else None
    target_spec = {**target_spec, 'target_column': target, 'positive_class': positive_label,
                   'event_definition': event, 'label_maturity': maturity}
    if window is not None:
        target_spec['outcome_window'] = window
    else:
        target_spec.pop('outcome_window', None)
    contract = {
        'schema_version': 2,
        'task': task,
        'target_column': target,
        'class_mapping': class_mapping,
        'positive_class': positive_label,
        'population': population,
        'exclusions': exclusions,
        'prediction_horizon': horizon,
        'target_contract': target_spec,
        'feature_availability': availability,
        'forbidden_features': forbidden,
        'objective': objective,
        'qualification': ('Declared population and availability require review. Fixed outcome windows are validated on the admitted temporal data.'
                          if window else 'Declared population, availability, horizon and maturity require review.'),
    }
    contract['sha256'] = _digest(contract)
    frozen_prediction_task(contract)
    return contract, encoded
