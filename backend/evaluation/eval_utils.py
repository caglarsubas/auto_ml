"""Outer-test evaluation helpers for the boosting pipeline."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, average_precision_score, brier_score_loss, confusion_matrix,
    f1_score, fbeta_score, log_loss, matthews_corrcoef, mean_absolute_error,
    mean_squared_error, precision_recall_curve, precision_score, r2_score,
    recall_score, roc_auc_score, roc_curve,
)


def _safe_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def compute_ks_gini(y_true: np.ndarray, y_proba: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    try:
        fpr, tpr, _ = roc_curve(y_true, y_proba)
        ks = float(np.max(np.abs(tpr - fpr)))
        auc = float(roc_auc_score(y_true, y_proba))
        gini = 2.0 * auc - 1.0
        return ks, gini
    except Exception:
        return None, None


def _weighted_ovr_rank_auc(y, p):
    """Unweighted observations, support-weighted OvR AUC for validated inputs.

    Average ranks give tied positive/negative pairs half credit. Compute one
    class at a time, so temporary rank storage grows with rows, not rows ×
    classes. Full assessment keeps sklearn's independent ROC integration.
    """
    from modeling.rank_metrics import MAX_EXACT_RANK_ROWS, tie_group_auc

    values, supports = [], []
    for label in range(p.shape[1]):
        positive = y == label
        support = float(positive.sum())
        if len(y) <= MAX_EXACT_RANK_ROWS:
            value = tie_group_auc(positive, p[:, label])
        else:
            from scipy.stats import rankdata
            ranks = rankdata(p[:, label], method='average')
            u = ranks[positive].sum() - support * (support + 1.) / 2.
            value = u / (support * (len(y) - support))
        values.append(value)
        supports.append(support)
    return float(np.average(values, weights=supports))


def evaluate_multiclass(y_true, probabilities, *, metric_names=None, include_confusion=True):
    y = np.asarray(y_true)
    p = np.asarray(probabilities, dtype=float)
    if y.ndim != 1 or p.ndim != 2 or p.shape[0] != len(y) or p.shape[1] < 3 or not np.isfinite(p).all():
        raise ValueError('Multiclass evaluation requires one finite probability per declared class and row.')
    if not len(y) or np.iscomplexobj(y) or not np.isin(y, np.arange(p.shape[1])).all():
        raise ValueError('Multiclass labels must be encoded declared classes; fractional, missing or unknown labels are invalid.')
    y = y.astype(int)
    if (p < 0).any() or not np.allclose(p.sum(axis=1), 1, atol=1e-5):
        raise ValueError('Multiclass probabilities must be nonnegative and sum to one.')
    # Native float32 probabilities may sum to 1 within their precision but
    # trigger float64 log-loss warnings after conversion. Normalize only after
    # enforcing the declared tolerance; never accept arbitrary score vectors.
    p = p / p.sum(axis=1, keepdims=True)
    classes = np.arange(p.shape[1])
    needs_labels = include_confusion or metric_names is None or any(name in {'accuracy', 'f1', 'f1_weighted'} for name in metric_names)
    pred = p.argmax(axis=1) if needs_labels else None
    # The two exported F1 names are aliases of the same public calculation.
    f1_result = {}

    def weighted_f1():
        if not f1_result:
            if metric_names is not None:
                support = np.bincount(y, minlength=len(classes))
                predicted = np.bincount(pred, minlength=len(classes))
                correct = np.bincount(y[y == pred], minlength=len(classes))
                denominator = support.astype(float) + predicted
                values = np.divide(2. * correct, denominator, out=np.zeros(len(classes)), where=denominator != 0)
                f1_result['value'] = _safe_float(np.average(values, weights=support))
            else:
                f1_result['value'] = _safe_float(f1_score(y, pred, labels=classes, average='weighted', zero_division=0))
        return f1_result['value']

    def probability_loss():
        if metric_names is None:
            return _safe_float(log_loss(y, p, labels=classes))
        epsilon = np.finfo(p.dtype).eps
        return _safe_float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], epsilon, 1 - epsilon))))

    values = {
        'accuracy': lambda: _safe_float(np.mean(y == pred) if metric_names is not None else accuracy_score(y, pred)),
        'log_loss': probability_loss,
        'f1_weighted': weighted_f1,
        'f1': weighted_f1,
        'roc_auc': lambda: _safe_float(_weighted_ovr_rank_auc(y, p) if metric_names is not None else
                                      roc_auc_score(y, p, labels=classes, multi_class='ovr', average='weighted'))
                          if set(np.unique(y)) == set(classes) else None,
        'n_samples': lambda: len(y)}
    metrics = {name: values[name]() for name in (metric_names if metric_names is not None else values)}
    return {
        'task': 'classification', 'class_count': p.shape[1],
        'metrics': metrics,
        'confusion_matrix': confusion_matrix(y, pred, labels=classes).tolist() if include_confusion else None,
        'threshold_table': [],
        'metric_semantics': {'roc_auc': 'weighted one-vs-rest', 'f1': 'weighted across declared classes',
                             'roc_auc_calculation': 'weighted_ovr_rank_auc_v1' if metric_names is not None else 'sklearn_roc_integration'},
        'limitations': ['Weighted multiclass AUC is unavailable when the assessment partition lacks a declared class.'] if 'roc_auc' in metrics and metrics['roc_auc'] is None else [],
    }


def select_development_threshold(y_valid, probabilities, fn_cost=1.0, fp_cost=1.0):
    """Select on development outcomes only; the caller supplies no final outcomes."""
    from modeling.crisp_dm import expected_cost_table, recommend_threshold_by_cost
    if any(not np.isfinite(float(cost)) or float(cost) < 0 for cost in (fn_cost, fp_cost)):
        raise ValueError('Outcome costs must be finite and nonnegative.')
    rows = threshold_table(np.asarray(y_valid, dtype=int), np.asarray(probabilities, dtype=float).ravel())
    costs = expected_cost_table(rows, fn_cost=float(fn_cost), fp_cost=float(fp_cost))
    return recommend_threshold_by_cost(costs), costs


def threshold_table(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    thresholds: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    if thresholds is None:
        thresholds = [round(x, 2) for x in np.linspace(0.05, 0.95, 19)]
    # The governed binary path already supplies one-dimensional 0/1 outcomes.
    # Derive all threshold metrics from the same counts rather than validating
    # the same arrays through seven sklearn metric calls for every threshold.
    # Preserve sklearn's legacy validation for other input shapes/types.
    truth = np.asarray(y_true)
    scores = np.asarray(y_proba)
    binary_counts = (
        truth.ndim == scores.ndim == 1
        and len(truth) == len(scores) > 0
        and truth.dtype.kind in 'biuf'
        and scores.dtype.kind in 'biuf'
        and np.isin(truth, [0, 1]).all()
    )
    positives = truth == 1 if binary_counts else None
    # Sorted partitions share threshold counts without changing inclusive ties.
    # Other dtypes, nonfinite scores and legacy scalar/container inputs retain
    # their existing comparison and validation behavior.
    ordered = (binary_counts and type(y_proba) is np.ndarray and scores.dtype == np.dtype(float) and np.isfinite(scores).all()
               and isinstance(thresholds, (list, tuple)) and len(thresholds) >= 8
               and all(isinstance(t, (int, float, np.integer, np.floating)) and np.isfinite(t) for t in thresholds))
    if ordered:
        positive_scores, negative_scores = np.sort(scores[positives]), np.sort(scores[~positives])
    rows = []
    for thr in thresholds:
        y_pred = None if ordered else (y_proba >= thr).astype(int)
        if binary_counts and (ordered or y_pred.shape == truth.shape):
            if ordered:
                fn = int(np.searchsorted(positive_scores, thr, side='left'))
                tn = int(np.searchsorted(negative_scores, thr, side='left'))
                tp, fp = len(positive_scores) - fn, len(negative_scores) - tn
            else:
                predicted = y_pred.astype(bool)
                tp = int(np.count_nonzero(positives & predicted))
                fn = int(np.count_nonzero(positives & ~predicted))
                fp = int(np.count_nonzero(~positives & predicted))
                tn = int(np.count_nonzero(~positives & ~predicted))
            # Float factors avoid fixed-width integer overflow. A missing
            # predicted/actual class has the same MCC convention as sklearn.
            denominator = math.sqrt(float(tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
            rows.append({
                'threshold': thr,
                'precision': tp / (tp + fp) if tp + fp else 0.0,
                'recall': tp / (tp + fn) if tp + fn else 0.0,
                'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
                'f2': 5 * tp / (5 * tp + fp + 4 * fn) if 5 * tp + fp + 4 * fn else 0.0,
                'accuracy': (tp + tn) / len(truth),
                'mcc': (float(tp) * tn - float(fp) * fn) / denominator if denominator else 0.0,
                'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
            })
            continue
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        rows.append({
            'threshold': thr,
            'precision': _safe_float(precision_score(y_true, y_pred, zero_division=0)),
            'recall': _safe_float(recall_score(y_true, y_pred, zero_division=0)),
            'f1': _safe_float(f1_score(y_true, y_pred, zero_division=0)),
            'f2': _safe_float(fbeta_score(y_true, y_pred, beta=2, zero_division=0)),
            'accuracy': _safe_float(accuracy_score(y_true, y_pred)),
            'mcc': _safe_float(matthews_corrcoef(y_true, y_pred)),
            'tp': int(tp), 'fp': int(fp), 'tn': int(tn), 'fn': int(fn),
        })
    return rows


def calibration_curve_data(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    n_bins: int = 10,
) -> Dict[str, Any]:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    centers, frac_pos, counts, mean_pred = [], [], [], []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (y_proba >= lo) & (y_proba < hi if i < n_bins - 1 else y_proba <= hi)
        if not mask.any():
            continue
        centers.append(float((lo + hi) / 2))
        frac_pos.append(float(y_true[mask].mean()))
        mean_pred.append(float(y_proba[mask].mean()))
        counts.append(int(mask.sum()))
    return {
        'bin_centers': centers,
        'fraction_positives': frac_pos,
        'mean_predicted': mean_pred,
        'counts': counts,
    }


def evaluate_binary(
    y_true,
    y_proba,
    threshold: float = 0.5,
) -> Dict[str, Any]:
    y_true = np.asarray(y_true).astype(int)
    y_proba = np.asarray(y_proba, dtype=float).ravel()
    y_pred = (y_proba >= threshold).astype(int)
    single = len(np.unique(y_true)) < 2
    # Reuse the independently checked count formulas already used by the
    # threshold table. Legacy/invalid shapes and ranges retain public fallbacks.
    counts = None
    if (y_true.ndim == 1 and len(y_true) == len(y_proba) > 0 and np.ndim(threshold) == 0
            and np.isin(y_true, [0, 1]).all() and np.isfinite(y_proba).all()
            and (y_proba >= 0).all() and (y_proba <= 1).all()):
        counts = threshold_table(y_true, y_proba, [threshold])[0]

    from scipy.special import xlogy
    clipped = np.clip(y_proba, 1e-7, 1 - 1e-7)
    checked_auc = None if single else _safe_float(roc_auc_score(y_true, y_proba))
    metrics: Dict[str, Any] = {
        'threshold': threshold,
        'n_samples': int(len(y_true)),
        'positive_rate': _safe_float(y_true.mean()) if len(y_true) else None,
        'roc_auc': checked_auc,
        'pr_auc': None if single else _safe_float(average_precision_score(y_true, y_proba)),
        'f1': counts['f1'] if counts is not None else _safe_float(f1_score(y_true, y_pred, zero_division=0)),
        'f2': counts['f2'] if counts is not None else _safe_float(fbeta_score(y_true, y_pred, beta=2, zero_division=0)),
        'precision': counts['precision'] if counts is not None else _safe_float(precision_score(y_true, y_pred, zero_division=0)),
        'recall': counts['recall'] if counts is not None else _safe_float(recall_score(y_true, y_pred, zero_division=0)),
        'accuracy': counts['accuracy'] if counts is not None else _safe_float(accuracy_score(y_true, y_pred)),
        'mcc': counts['mcc'] if counts is not None else _safe_float(matthews_corrcoef(y_true, y_pred)),
        'log_loss': _safe_float(-np.mean(xlogy(y_true, clipped) + xlogy(1 - y_true, 1 - clipped))) if counts is not None else _safe_float(log_loss(y_true, clipped, labels=[0, 1])),
        'brier': _safe_float(np.mean((y_true - y_proba)**2)) if counts is not None else _safe_float(brier_score_loss(y_true, y_proba)),
    }
    roc_evidence = None
    if counts is None:
        ks, gini = compute_ks_gini(y_true, y_proba)
    else:
        ks, gini = None, None
        if not single:
            try:
                fpr, tpr, _ = roc_curve(y_true, y_proba)
                ks, gini = float(np.max(np.abs(tpr - fpr))), 2. * checked_auc - 1.
                roc_evidence = fpr, tpr
            except Exception:
                pass
    metrics['ks'] = ks
    metrics['gini'] = gini

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    metrics['confusion'] = {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)}

    curves: Dict[str, Any] = {}
    try:
        if roc_evidence is None:
            fpr, tpr, _ = roc_curve(y_true, y_proba)
        else:
            fpr, tpr = roc_evidence
        curves['roc'] = {
            'fpr': [float(x) for x in fpr[:: max(1, len(fpr) // 100)]],
            'tpr': [float(x) for x in tpr[:: max(1, len(tpr) // 100)]],
        }
    except Exception:
        curves['roc'] = None
    try:
        prec, rec, _ = precision_recall_curve(y_true, y_proba)
        curves['pr'] = {
            'precision': [float(x) for x in prec[:: max(1, len(prec) // 100)]],
            'recall': [float(x) for x in rec[:: max(1, len(rec) // 100)]],
        }
    except Exception:
        curves['pr'] = None

    return {
        'metrics': metrics,
        'curves': curves,
        'threshold_table': threshold_table(y_true, y_proba),
        'calibration': calibration_curve_data(y_true, y_proba),
        'task': 'classification',
    }


def evaluate_regression(y_true, y_pred) -> Dict[str, Any]:
    """Outer-test metrics for continuous boosting regressors."""
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[mask], y_pred[mask]
    residuals = y_true - y_pred if len(y_true) else np.array([])

    metrics: Dict[str, Any] = {
        'n_samples': int(len(y_true)),
        'r2': _safe_float(r2_score(y_true, y_pred, force_finite=False)) if len(y_true) >= 2 and np.var(y_true) > 0 else None,
        'rmse': _safe_float(np.sqrt(mean_squared_error(y_true, y_pred))) if len(y_true) else None,
        'mae': _safe_float(mean_absolute_error(y_true, y_pred)) if len(y_true) else None,
        'mean_residual': _safe_float(residuals.mean()) if len(residuals) else None,
        'residual_std': _safe_float(residuals.std()) if len(residuals) else None,
        'y_true_mean': _safe_float(y_true.mean()) if len(y_true) else None,
        'y_pred_mean': _safe_float(y_pred.mean()) if len(y_pred) else None,
    }

    # Residual histogram for quick visual diagnostics in the FE / model card
    residual_hist: Optional[Dict[str, Any]] = None
    try:
        if len(residuals) >= 5:
            counts, edges = np.histogram(residuals, bins=min(20, max(5, len(residuals) // 10)))
            residual_hist = {
                'counts': [int(c) for c in counts],
                'bin_edges': [float(e) for e in edges],
            }
    except Exception:
        residual_hist = None

    # Predicted-vs-actual scatter sample (cap for payload size)
    scatter = None
    try:
        if len(y_true):
            step = max(1, len(y_true) // 200)
            scatter = {
                'y_true': [float(x) for x in y_true[::step]],
                'y_pred': [float(x) for x in y_pred[::step]],
            }
    except Exception:
        scatter = None

    return {
        'metrics': metrics,
        'curves': {'residual_hist': residual_hist, 'pred_vs_actual': scatter},
        'threshold_table': [],
        'calibration': None,
        'task': 'regression',
    }


def _psi_for_series(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> Optional[float]:
    """Classic PSI between two numeric distributions."""
    try:
        expected = np.asarray(expected, dtype=float)
        actual = np.asarray(actual, dtype=float)
        mask_e = np.isfinite(expected)
        mask_a = np.isfinite(actual)
        expected, actual = expected[mask_e], actual[mask_a]
        if len(expected) < 5 or len(actual) < 5:
            return None
        quantiles = np.linspace(0, 1, bins + 1)
        breaks = np.unique(np.quantile(expected, quantiles))
        if len(breaks) < 3:
            return None
        e_counts = np.histogram(expected, bins=breaks)[0].astype(float)
        a_counts = np.histogram(actual, bins=breaks)[0].astype(float)
        e_pct = np.clip(e_counts / max(e_counts.sum(), 1.0), 1e-6, None)
        a_pct = np.clip(a_counts / max(a_counts.sum(), 1.0), 1e-6, None)
        return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))
    except Exception:
        return None


def feature_psi_report(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    top_n: int = 25,
) -> Dict[str, Any]:
    """PSI of numeric features between train and locked outer test."""
    rows = []
    for c in X_train.columns:
        if c not in X_test.columns:
            continue
        if not pd.api.types.is_numeric_dtype(X_train[c]):
            continue
        psi = _psi_for_series(X_train[c].to_numpy(), X_test[c].to_numpy())
        if psi is None:
            continue
        band = 'stable' if psi < 0.10 else ('moderate' if psi < 0.25 else 'shift')
        rows.append({'feature': str(c), 'psi': round(psi, 6), 'band': band})
    rows.sort(key=lambda r: r['psi'], reverse=True)
    return {
        'n_features': len(rows),
        'top': rows[:top_n],
        'n_shift': sum(1 for r in rows if r['band'] == 'shift'),
        'n_moderate': sum(1 for r in rows if r['band'] == 'moderate'),
    }


def assess_deploy_readiness(
    evaluation: Optional[Dict[str, Any]] = None,
    lineage: Optional[Dict[str, Any]] = None,
    modeling_status: Optional[Dict[str, Any]] = None,
    *,
    evaluation_present: bool = True,
) -> Dict[str, Any]:
    """Decide whether a modeled file may freeze a score bundle.

    Hard blockers (automated):
      - evaluation artifact / outer-test metrics missing
      - lineage missing (not traceable)
      - high-severity leakage flags still present

    Soft items stay as warnings + human_checks_remaining (calibration, metric
    floors, stakeholder review) — no numeric AUC/PSI cutoffs without product
    defaults.
    """
    evaluation = evaluation or {}
    lineage = lineage or {}
    model = (modeling_status or {}).get('model') or {}
    task = (
        evaluation.get('task')
        or model.get('task')
        or ('regression' if 'regressor' in str(model.get('model_type') or '') else 'classification')
    )
    leak = model.get('leakage_scan') or evaluation.get('leakage_scan') or {}
    n_high = int(leak.get('n_high') or 0)
    metrics = evaluation.get('metrics') or {}
    outer_ok = bool(metrics)
    traceable = bool(lineage and (lineage.get('lineage_id') or lineage.get('split') or lineage.get('features')))
    calibrated = bool(
        evaluation.get('scores_calibrated')
        or (model.get('calibration') or {}).get('fitted')
        or (evaluation.get('calibration') or {}).get('fitted')
    )

    blocking: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    if not evaluation_present:
        blocking.append({
            'code': 'evaluation_missing',
            'message': 'Run Evaluation before creating a score bundle.',
        })
    elif not outer_ok:
        blocking.append({
            'code': 'outer_test_missing',
            'message': 'Outer-test evaluation metrics are missing from the model card.',
        })
    if not traceable:
        blocking.append({
            'code': 'lineage_missing',
            'message': 'Pipeline lineage is missing — data/encoding/split decisions are not traceable.',
        })
    if n_high > 0:
        blocking.append({
            'code': 'leakage_high',
            'message': f'Automated leakage scan flagged {n_high} high-severity feature(s). Exclude or justify before deploy.',
        })

    if task not in ('regression', 'anomaly') and not calibrated:
        warnings.append({
            'code': 'uncalibrated_scores',
            'message': 'Probability calibrator was not fitted; review score interpretation before go-live.',
        })
    if not (model.get('importances') or evaluation.get('feature_psi')):
        warnings.append({
            'code': 'explanations_review',
            'message': 'Confirm feature explanations (SHAP/gain) are understandable to stakeholders.',
        })

    human_checks = [
        'Confirm ID/timestamp/leakage fields are excluded via Model_Usage.',
        'Confirm split strategy matches the deployment scenario (random vs OOT).',
        'Review automated leakage warnings and SHAP/gain/VIF before accepting the feature set.',
        'Confirm performance and stability metrics are acceptable for the intended use case.',
        'Define monitoring for future data drift and performance decay (PSI / score distribution).',
    ]
    if task == 'regression':
        human_checks.append('Review residual bias / RMSE against the business tolerance for continuous scores.')
    else:
        human_checks.append('Document business threshold / cost trade-off from the threshold table.')

    checklist_coverage = {
        'data_declaration': {
            'status': 'enforced' if (lineage.get('features') or model.get('feature_count') is not None) else 'human',
            'detail': 'Feature count / exclusions captured in lineage when present.',
        },
        'split_and_stability': {
            'status': 'enforced' if traceable else 'blocking',
            'detail': 'Split metadata required via lineage for deploy.',
        },
        'encoding': {
            'status': 'enforced' if (lineage.get('encoding') is not None or model.get('enable_categorical') is not None) else 'human',
            'detail': 'Encoding plan / native categorical flag recorded when available.',
        },
        'modeling': {
            'status': 'enforced' if outer_ok else 'blocking',
            'detail': 'Outer-test metrics required before score-bundle freeze.',
        },
        'leakage_scan': {
            'status': 'blocking' if n_high > 0 else 'enforced',
            'detail': 'High-severity leakage findings block deploy; medium/low remain human review.',
        },
        'evaluation_outer_test': {
            'status': 'enforced' if outer_ok else 'blocking',
            'detail': 'Locked outer-test evaluation must exist.',
        },
        'assistant_and_action_review': {
            'status': 'human',
            'detail': 'Assistant recommendations require human review before approval.',
        },
        'deployment_readiness': {
            'status': 'enforced' if not blocking else 'blocking',
            'detail': 'Automated blockers must clear; residual human checks remain documented.',
        },
        'monitoring': {
            'status': 'human',
            'detail': 'Post-go-live PSI / score drift monitoring is a residual human check.',
        },
    }

    ready = len(blocking) == 0
    summary = (
        'Deploy-ready: automated blockers cleared; complete residual human checks before go-live.'
        if ready else
        'Not deploy-ready: resolve blocking items before creating a score bundle.'
    )
    return {
        'ready': ready,
        'summary': summary,
        'task': task,
        'blocking': blocking,
        'warnings': warnings,
        'human_checks_remaining': human_checks,
        'checklist_coverage': checklist_coverage,
        'flags': {
            'traceable': traceable,
            'outer_test_evaluated': outer_ok,
            'scores_calibrated': calibrated,
            'leakage_n_high': n_high,
            'evaluation_present': evaluation_present,
        },
    }


def build_model_card(
    file_id: int,
    evaluation: Dict[str, Any],
    lineage: Optional[Dict[str, Any]] = None,
    modeling_status: Optional[Dict[str, Any]] = None,
    business_understanding: Optional[Dict[str, Any]] = None,
    governance_checks: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Map governance checklist sections into a reviewable model card."""
    from modeling.crisp_dm import evaluate_success_floors, normalize_business_understanding

    model = (modeling_status or {}).get('model') or {}
    split = model.get('split') or (lineage or {}).get('split') or {}
    readiness = assess_deploy_readiness(
        evaluation, lineage, modeling_status, evaluation_present=True,
    )
    task = readiness['task']
    bu = normalize_business_understanding(business_understanding)
    floors = evaluate_success_floors(
        evaluation.get('metrics') or {},
        bu.get('success_criteria') or {},
    )
    limitations = _deployment_limitations(model, evaluation, task)
    for note in (bu.get('assumptions'), bu.get('regulatory_notes')):
        if note and str(note).strip():
            limitations.append(str(note).strip())
    if bu.get('forbidden_features'):
        limitations.append(
            'Forbidden features from Business Understanding: '
            + ', '.join(bu['forbidden_features'][:20])
        )
    checks = governance_checks if isinstance(governance_checks, dict) else {}
    return {
        'file_id': file_id,
        'title': f'Boosting model card — file {file_id}',
        'task': task,
        'algorithm': (lineage or {}).get('algorithm') or model.get('model_type') or 'xgboost_classifier',
        'lineage_id': (lineage or {}).get('lineage_id') or model.get('lineage_id'),
        'deploy_ready': readiness['ready'],
        'business_understanding': bu,
        'success_criteria_result': floors,
        'governance_checks': checks,
        'sections': {
            'data_declaration': {
                'excluded_variables': (lineage or {}).get('features', {}).get('excluded'),
                'feature_count': (lineage or {}).get('features', {}).get('count') or model.get('feature_count'),
                'target_contract': bu.get('target_contract'),
                'objective': bu.get('objective'),
            },
            'split_and_stability': {
                'source': split.get('source'),
                'strategy': split.get('strategy'),
                'used_preprocessing_split': split.get('used_preprocessing_split'),
                'n_train': split.get('n_train') or (lineage or {}).get('row_counts', {}).get('train'),
                'n_valid': split.get('n_valid') or (lineage or {}).get('row_counts', {}).get('valid'),
                'n_test': split.get('n_test') or (lineage or {}).get('row_counts', {}).get('test'),
                'warnings': split.get('warnings') or [],
            },
            'encoding': (lineage or {}).get('encoding') or {
                'use_native': model.get('enable_categorical'),
            },
            'modeling': {
                'task': task,
                'valid_auc': model.get('valid_auc'),
                'test_auc': model.get('test_auc'),
                'test_auc_calibrated': model.get('test_auc_calibrated'),
                'valid_r2': model.get('valid_r2'),
                'test_r2': model.get('test_r2'),
                'test_rmse': model.get('test_rmse'),
                'test_mae': model.get('test_mae'),
                'scale_pos_weight': model.get('scale_pos_weight') or (lineage or {}).get('scale_pos_weight'),
                'best_iteration': model.get('best_iteration'),
                'impute_fit_on_train_only': model.get('impute_fit_on_train_only', True),
                'cv_strategy': (model.get('cv') or {}).get('cv_strategy'),
                'calibration': model.get('calibration') or evaluation.get('calibration'),
            },
            'leakage_scan': model.get('leakage_scan') or evaluation.get('leakage_scan'),
            'evaluation_outer_test': evaluation.get('metrics'),
            'final_outcome_access': {
                'evidence_status': evaluation.get('evidence_status', 'historical_unverified'),
                'access_id': evaluation.get('holdout_access_id'),
                'holdout_history': evaluation.get('holdout_history'),
                'limitation': evaluation.get('evidence_limitation'),
            },
            'business_success_criteria': floors,
            'deployment_readiness': {
                'ready': readiness['ready'],
                'summary': readiness['summary'],
                'blocking': readiness['blocking'],
                'warnings': readiness['warnings'],
                'checklist_coverage': readiness['checklist_coverage'],
                'traceable': readiness['flags']['traceable'],
                'outer_test_evaluated': readiness['flags']['outer_test_evaluated'],
                'scores_calibrated': readiness['flags']['scores_calibrated'],
                'known_limitations': limitations,
            },
        },
        'human_checks_remaining': readiness['human_checks_remaining'],
    }


def _deployment_limitations(
    model: Dict[str, Any],
    evaluation: Dict[str, Any],
    task: str = 'classification',
) -> list:
    limits = []
    if task != 'regression':
        cal = model.get('calibration') or evaluation.get('calibration') or {}
        if not cal.get('fitted') and not evaluation.get('scores_calibrated'):
            limits.append(
                'Probability calibrator was not fitted (insufficient validation samples or non-binary target).'
            )
    leak = model.get('leakage_scan') or evaluation.get('leakage_scan') or {}
    if leak.get('n_high'):
        limits.append(
            f"Automated leakage scan flagged {leak.get('n_high')} high-severity feature(s)."
        )
    if not limits:
        limits.append('Review PSI / score drift in deployment monitoring after go-live.')
    return limits
