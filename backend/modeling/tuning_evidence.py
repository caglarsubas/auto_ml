"""Native tuning contracts and evidence; development selection is exploratory."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

from modeling.fit_receipts import input_receipt, receipt_digest, runtime_versions
from modeling.sfs_objective import SUPPORTED, canonical_metric, direction


def resolve_tuning_objective(task, context, requested=None, threshold=.5):
    if task not in SUPPORTED or (context and context['task'] != task):
        raise ValueError('Tuning requires the recorded classification/regression task.')
    contract = (context or {}).get('prediction_contract') or {}
    if len(contract.get('class_mapping') or []) > 2:
        raise ValueError('Native tuning does not support multiclass objectives yet.')
    declared = contract.get('objective') or {}
    primary = canonical_metric(requested or declared.get('primary_metric') or
                               ('r2' if task == 'regression' else 'roc_auc'))
    supported = SUPPORTED[task] | ({'f2', 'mcc'} if task == 'classification' and not contract else set())
    if primary not in supported:
        raise ValueError(f'Tuning objective {primary!r} is unsupported for {task}; revise the declaration or request.')
    if declared.get('primary_metric') and primary != canonical_metric(declared['primary_metric']):
        raise ValueError('Tuning objective contradicts the accepted prediction contract. Revise the declaration in a new execution.')
    if declared.get('direction', direction(primary)) != direction(primary):
        raise ValueError('Tuning direction contradicts the accepted objective.')
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Tuning threshold must be finite and within [0, 1].')
    if contract and task == 'classification' and threshold != .5:
        raise ValueError('Accepted threshold metrics use 0.5; threshold selection requires a separate versioned policy workflow.')
    return {'schema_version': 1, 'primary_metric': primary, 'requested_primary_metric': requested,
            'direction': direction(primary), 'cost_matrix': declared.get('cost_matrix') or {},
            'threshold': threshold,
            'qualification': 'Exploratory development selection; folds, early stopping and validation curves reuse development data. Fold spread is descriptive, not a confidence interval.',
            'training_policy': 'Native fixed training/early-stopping criterion is recorded separately; full objective alignment remains open.'}


def validate_features(features, X_train, X_valid):
    selected = list(X_train.columns) if features is None else features
    if not isinstance(selected, list) or not selected or len(set(selected)) != len(selected):
        raise ValueError('Tuning features must be a nonempty list of unique feature names.')
    if any(name not in X_train.columns or name not in X_valid.columns for name in selected):
        raise ValueError('Tuning features differ from the selected execution; refresh the feature selection.')
    return selected


def fit_for_tuning(algorithm, X_train, y_train, X_valid, y_valid, config, *, task,
                   nthread, scale_pos_weight, early_stopping_rounds, context=None):
    # The native classification early-stopping criterion is AUC, even when
    # the selection objective is a loss. Do not use an undefined criterion.
    if task == 'classification' and (context or {}).get('prediction_contract') and early_stopping_rounds:
        if set(y_train.unique()) != {0, 1} or set(y_valid.unique()) != {0, 1}:
            raise ValueError('Native AUC early stopping requires both declared classes in each training/validation partition; revise the split or population.')
    if task == 'classification' and (context or {}).get('class_weight_policy') == 'train_label_ratio':
        if not (y_train == 1).any():
            raise ValueError('Training partition lacks the declared positive class.')
        scale_pos_weight = float((y_train == 0).sum() / (y_train == 1).sum())
    from modeling.booster_adapters import fit_booster
    return fit_booster(algorithm, X_train, y_train, X_valid, y_valid, config, task=task,
                       nthread=nthread, scale_pos_weight=scale_pos_weight,
                       early_stopping_rounds=early_stopping_rounds)


def tuning_basis(X_train, y_train, X_valid, y_valid, context, execution_id, algorithm, objective, configuration):
    root = Path(__file__).parent
    validation = {'qualification': 'Legacy upstream transformation and partition provenance unverified.'}
    if context and 'frame' in context:
        validation = {'raw_train': input_receipt(context['frame'].loc[X_train.index], y_train),
                      'raw_valid': input_receipt(context['frame'].loc[X_valid.index], y_valid),
                      'configuration': {key: context.get(key) for key in (
                          'task', 'prediction_contract', 'target_column', 'split_meta',
                          'excluded_features', 'purifier_recipe', 'encoding_plan', 'use_native', 'class_weight_policy')}}
    try:
        search_runtime = {'optuna': version('optuna')}
    except PackageNotFoundError:
        search_runtime = {'optuna': None}
    basis = {'schema_version': 1, 'execution_id': execution_id, 'algorithm': algorithm,
             'train': input_receipt(X_train, y_train), 'valid': input_receipt(X_valid, y_valid),
             'objective': objective, 'configuration': configuration, 'validation': validation,
             'runtime': {**runtime_versions(algorithm), 'validation': runtime_versions('sklearn'), 'search': search_runtime},
             'implementation_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                       for name in ('hyperparam_utils.py', 'tuning_evidence.py', 'sfs_objective.py',
                                                    'development_validation.py', 'development_assessment.py', 'booster_adapters.py')}}
    basis['sha256'] = receipt_digest(basis)
    return basis
