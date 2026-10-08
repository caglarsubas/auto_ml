"""Auditable development CV. Fold spread is descriptive, not a confidence interval."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score, average_precision_score, brier_score_loss, confusion_matrix,
    f1_score, log_loss, mean_absolute_error, mean_squared_error, precision_recall_curve,
    precision_score, r2_score, recall_score, roc_auc_score, roc_curve,
)

from modeling.development_validation import prepared_folds


def metric_coverage(values, *, complete_only=True):
    usable = [float(value) for value in values if value is not None and np.isfinite(value)]
    complete = len(usable) == len(values) and len(values) > 0
    summarize = bool(usable) and (complete or not complete_only)
    return {'mean': float(np.mean(usable)) if summarize else None,
            'std': float(np.std(usable)) if summarize else None,
            'n_valid': len(usable), 'n_total': len(values),
            'status': 'complete' if complete else ('partial' if usable else 'unavailable')}


def development_metrics(labels, predictions, task, class_count=2, costs=None):
    y, p = np.asarray(labels), np.asarray(predictions, dtype=float)
    if p.shape[0:1] != (len(y),) or not np.isfinite(p).all():
        raise ValueError('Development predictions must be finite and preserve every validation row.')
    if task == 'regression':
        if p.ndim != 1 or not np.isfinite(y.astype(float)).all():
            raise ValueError('Regression validation requires one finite numeric label and prediction per row.')
        # A constant validation target has undefined R², rather than an invented 0/1.
        r2 = float(r2_score(y, p, force_finite=False)) if len(y) >= 2 and np.var(y) > 0 else None
        mse = float(mean_squared_error(y, p))
        return {'r2': r2 if r2 is not None and np.isfinite(r2) else None,
                'rmse': float(np.sqrt(mse)), 'mse': mse, 'mae': float(mean_absolute_error(y, p))}
    if task != 'classification':
        raise ValueError('Supervised development CV supports classification and regression only.')
    if not np.isin(y, np.arange(class_count)).all():
        raise ValueError('Development labels do not match the declared class mapping.')
    if class_count > 2:
        if p.ndim != 2 or p.shape[1] != class_count:
            raise ValueError('Development predictions must include every declared class in its recorded order.')
        if (p < 0).any() or (p > 1).any() or not np.allclose(p.sum(axis=1), 1., atol=1e-6, rtol=0):
            raise ValueError('Multiclass development validation requires probabilities in [0, 1] summing to one per row.')
        from evaluation.eval_utils import evaluate_multiclass
        return {key: value for key, value in evaluate_multiclass(y, p)['metrics'].items() if key != 'n_samples'}
    if p.ndim != 1 or (p < 0).any() or (p > 1).any():
        raise ValueError('Binary development validation requires one probability in [0, 1] per row.')
    both = len(np.unique(y)) == 2
    pred = (p >= .5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    costs = costs or {}
    ks = None
    if both:
        fpr, tpr, _ = roc_curve(y, p)
        ks = float(np.max(np.abs(tpr - fpr)))
    return {'roc_auc': float(roc_auc_score(y, p)) if both else None,
            'pr_auc': float(average_precision_score(y, p)) if both else None,
            'ks': ks, 'log_loss': float(log_loss(y, p, labels=[0, 1])),
            'brier': float(brier_score_loss(y, p)), 'accuracy': float(accuracy_score(y, pred)),
            'f1': float(f1_score(y, pred, zero_division=0)),
            'precision': float(precision_score(y, pred, zero_division=0)),
            'recall': float(recall_score(y, pred, zero_division=0)),
            'expected_cost': float((fn * costs.get('fn_cost', 1) + fp * costs.get('fp_cost', 1)) / len(y))}


def _binary_curves(labels, predictions):
    """Only draw curves when every fold supports the discrimination metrics."""
    grid = np.linspace(0., 1., 101)
    tprs, precisions, raw, baselines = [], [], [], []
    for y, p in zip(labels, predictions):
        fpr, tpr, _ = roc_curve(y, p)
        interpolated = np.interp(grid, fpr, tpr)
        interpolated[0], interpolated[-1] = 0., 1.
        tprs.append(interpolated)
        precision, recall, _ = precision_recall_curve(y, p)
        raw.append({'recall': recall.tolist(), 'precision': precision.tolist()})
        # Sample the first threshold attaining each recall after reversing
        # sklearn's decreasing-recall curve. Duplicate recalls retain the
        # precision before extra false positives, matching AP step areas.
        recall, precision = recall[::-1], precision[::-1]
        idx = np.clip(np.searchsorted(recall, grid, side='left'), 0, len(precision) - 1)
        precisions.append(precision[idx])
        baselines.append(float(np.mean(y)))
    precision, recall, _ = precision_recall_curve(np.concatenate(labels), np.concatenate(predictions))
    return {'roc_curve': {'fpr': grid.tolist(), 'mean_tpr': np.mean(tprs, axis=0).tolist(),
                         'std_tpr': np.std(tprs, axis=0).tolist(), 'fold_tpr': [v.tolist() for v in tprs]},
            'pr_curve': {'recall': grid.tolist(), 'mean_precision': np.mean(precisions, axis=0).tolist(),
                        'std_precision': np.std(precisions, axis=0).tolist(),
                        'fold_precision': [v.tolist() for v in precisions], 'folds_raw': raw,
                        'baseline': float(np.mean(baselines))},
            'pr_curve_micro': {'recall': recall.tolist(), 'precision': precision.tolist(),
                              'ap': float(average_precision_score(np.concatenate(labels), np.concatenate(predictions)))}}


def assess_development_cv(context, X, y, algorithm, params, *, n_splits=5,
                          num_boost_round=500, early_stopping_rounds=50, all_declared_features=True):
    task = context['task']
    contract = context.get('prediction_contract') or {}
    objective = contract.get('objective') or {}
    class_count = len(contract.get('class_mapping') or []) or int(context['labels'].nunique())
    rows, receipts, fold_labels, fold_predictions = [], [], [], []
    for fold, (X_tr, y_tr, X_va, y_va, receipt) in enumerate(
            prepared_folds(context, X, y, n_splits, all_declared_features=all_declared_features), 1):
        if task == 'classification' and set(y_tr.unique()) != set(range(class_count)):
            raise ValueError(f'Development fold {fold} training population lacks a declared class; revise the split or population.')
        from modeling.alt_pipelines import get_alt_adapter, is_alt_algorithm
        fold_params = dict(params)
        if not is_alt_algorithm(algorithm) and context.get('class_weight_policy') == 'train_label_ratio':
            fold_params['scale_pos_weight'] = float((y_tr == 0).sum() / (y_tr == 1).sum())
            receipt['class_weight'] = {'policy': 'train_label_ratio',
                'scale_pos_weight': fold_params['scale_pos_weight'], 'fit_rows': receipt['train_rows']}
        if is_alt_algorithm(algorithm):
            adapter = get_alt_adapter(algorithm)
            adapter.train(X_tr, y_tr, X_va, y_va, params=fold_params)
        else:
            from modeling.booster_adapters import get_adapter
            adapter = get_adapter(algorithm)
            adapter.train(X_tr, y_tr, X_va, y_va, fold_params,
                          num_boost_round=num_boost_round, early_stopping_rounds=early_stopping_rounds)
        predictions = adapter.predict(X_va) if task == 'regression' else adapter.predict_proba(X_va)
        metrics = development_metrics(y_va, predictions, task, class_count, objective.get('cost_matrix'))
        rows.append({**metrics, 'training_eval_metric': getattr(adapter, 'training_eval_metric', None), 'fold': fold, 'n_train': len(y_tr), 'n_valid': len(y_va),
                     'best_iteration': int(getattr(adapter, 'best_iteration', 0) or 0)})
        receipt['native_fit'] = adapter.fit_receipt
        receipts.append(receipt)
        fold_labels.append(np.asarray(y_va))
        fold_predictions.append(np.asarray(predictions))
    if len(rows) != n_splits:
        raise ValueError('Development validation did not produce every requested fold.')
    keys = list(metrics)
    coverage = {key: metric_coverage([row[key] for row in rows]) for key in keys}
    primary = {'auc': 'roc_auc', 'average_precision': 'pr_auc'}.get(objective.get('primary_metric'), objective.get('primary_metric'))
    if context.get('purifier_recipe') and primary and coverage.get(primary, {}).get('status') != 'complete':
        count = coverage.get(primary, {}).get('n_valid', 0)
        raise ValueError(f'Declared objective {primary} is available in {count} of {n_splits} development folds; revise the metric or validation population.')
    config = (context.get('split_meta') or {}).get('split_config') or {}
    group = config.get('group_column')
    strategy = (context.get('split_meta') or {}).get('strategy', 'random')
    summary = {'schema_version': 2, 'status': 'completed', 'task': task, 'n_splits': n_splits,
               'folds': rows, 'fold_provenance': receipts, 'metric_coverage': coverage,
               'cv_strategy': 'time_series' if strategy == 'oot' else ('group' if group else 'random'),
               'group_column': group, 'primary_metric': primary, 'training_eval_metric': rows[0]['training_eval_metric'],
               'requested_training_eval_metric': params.get('eval_metric'),
               'configuration': {'algorithm': algorithm, 'feature_scope': 'all_declared' if all_declared_features else 'selected',
                                 'features': list(X.columns), 'num_boost_round': num_boost_round,
                                 'early_stopping_rounds': early_stopping_rounds},
               'qualification': 'development; partition-fitted purifier replay' if context.get('purifier_recipe') else 'development; legacy upstream purifier provenance unverified',
               'aggregation': 'Unweighted fold mean; unavailable folds are never silently omitted.',
               'uncertainty': 'Fold standard deviations describe fold spread; dependent folds do not form a confidence interval.',
               'metric_semantics': 'Regression prediction errors' if task == 'regression' else ('weighted one-vs-rest AUC and weighted F1' if class_count > 2 else 'Binary probabilities; threshold metrics use fixed 0.5; expected cost is per observation'),
               'roc_curve': None, 'pr_curve': None, 'pr_curve_micro': None}
    for key, result in coverage.items():
        summary[key + '_mean'], summary[key + '_std'] = result['mean'], result['std']
    summary['limitations'] = [f'{key} is available in {result["n_valid"]} of {n_splits} folds; its aggregate is unavailable.'
                              for key, result in coverage.items() if result['status'] != 'complete']
    if task == 'classification' and class_count == 2 and coverage['roc_auc']['status'] == 'complete':
        summary.update(_binary_curves(fold_labels, fold_predictions))
    return summary


def run_development_cv(context, X, y, algorithm, params, **options):
    try:
        if context['task'] == 'anomaly':
            return {'schema_version': 2, 'status': 'not_applicable', 'task': 'anomaly',
                    'limitations': ['Supervised probability/error CV is unavailable for anomaly rankings.']}
        return assess_development_cv(context, X, y, algorithm, params, **options)
    except Exception as error:
        if context.get('purifier_recipe'):
            from modeling.prediction_contract import PredictionContractError
            raise PredictionContractError(f"Declared development validation failed: {str(error).rstrip('.')}. Revise the split, purifier or feature configuration.") from error
        return {'schema_version': 2, 'status': 'unavailable', 'task': context['task'],
                'limitations': [str(error)], 'qualification': 'Legacy input; development validation unavailable.'}
