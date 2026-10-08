"""
Hyperparameter tuning utilities for boosting models (XGBoost / LightGBM / CatBoost).

This module implements a *random joint search* over an editable
hyperparameter space plus per-hyperparameter *validation curves*
(train vs. cross-validation score across a 1-D sweep, holding the other
params at the best configuration — the classic ``validation_curve``
shape).  It mirrors the architecture of ``sfs_utils.py``:

    * Declared partition-aware CV and shared native booster fit receipts.
    * ``ThreadPoolExecutor(n_jobs)`` parallelism (booster pinned to a
      single thread per worker to avoid oversubscription).
    * A ``status_callback`` for progress polling and a ``stop_flag``
      dict checked cooperatively so the run can be stopped gracefully.

Beyond raw search it produces the four deliverables the pipeline needs:
    1. Best metric "space points" for F1, F2, ROC-AUC, PR-AUC, Precision,
       Recall, Accuracy and MCC (the trial maximizing each CV metric).
    2. Per-hyperparameter validation curves (train/CV mean +/- std).
    3. Surrogate-model param-importance attribution for which params
       drive CV gain / overfitting (train-CV gap) / shrinkage (CV-test
       gap), used to emphasize the most impactful hyperparameters.
    4. Verbal zoom-in / zoom-out guidance for the next search space.
"""

import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold, StratifiedKFold
from modeling.development_validation import iter_validation_folds
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    fbeta_score, matthews_corrcoef,
)
from scipy.stats import spearmanr

from modeling.booster_adapters import config_to_booster_params
from modeling.development_assessment import development_metrics, metric_coverage
from modeling.tuning_evidence import resolve_tuning_objective, validate_features, fit_for_tuning, tuning_basis
from modeling.sfs_objective import json_record
from modeling.fit_receipts import receipt_digest

warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')


def _build_xgb_params(
    config: Dict[str, Any],
    nthread: int,
    has_cat: bool = False,
    scale_pos_weight: Optional[float] = None,
    task: str = 'classification',
) -> Tuple[Dict[str, Any], int]:
    """Compatibility wrapper: shared config → XGBoost learning-API params."""
    params, num_boost_round = config_to_booster_params(
        config, task=task, nthread=nthread, scale_pos_weight=scale_pos_weight,
    )
    # Drop sklearn aliases; keep learning-API keys for legacy tests / callers.
    out = {
        'objective': params['objective'],
        'eval_metric': params['eval_metric'],
        'seed': params.get('seed', 42),
        'nthread': nthread,
        'eta': float(params['eta']),
        'max_depth': int(params['max_depth']),
        'min_child_weight': float(params['min_child_weight']),
        'subsample': float(params['subsample']),
        'colsample_bytree': float(params['colsample_bytree']),
        'gamma': float(params.get('gamma', 0.0)),
        'alpha': float(params['alpha']),
        'lambda': float(params['lambda']),
    }
    if has_cat:
        out['enable_categorical'] = True
    if 'scale_pos_weight' in params:
        out['scale_pos_weight'] = params['scale_pos_weight']
    return out, num_boost_round


# ---------------------------------------------------------------------------
# Hyperparameter space + metric catalogue
# ---------------------------------------------------------------------------
#
# Each entry of the default space is a dict:
#   {'type': 'int'|'float', 'min': .., 'max': .., 'log': bool, 'enabled': bool}
# or for categoricals: {'type': 'categorical', 'values': [...], 'enabled': bool}.
# The frontend lets the user edit min/max/log/enabled per param; the search
# only samples params with enabled=True (disabled ones use ``fixed_params``).

DEFAULT_PARAM_SPACE: Dict[str, Dict[str, Any]] = {
    'n_estimators':     {'type': 'int',   'min': 50,   'max': 600,  'log': False, 'enabled': True},
    'max_depth':        {'type': 'int',   'min': 2,    'max': 10,   'log': False, 'enabled': True},
    'learning_rate':    {'type': 'float', 'min': 0.01, 'max': 0.3,  'log': True,  'enabled': True},
    'min_child_weight': {'type': 'int',   'min': 1,    'max': 10,   'log': False, 'enabled': True},
    'subsample':        {'type': 'float', 'min': 0.5,  'max': 1.0,  'log': False, 'enabled': True},
    'colsample_bytree': {'type': 'float', 'min': 0.5,  'max': 1.0,  'log': False, 'enabled': True},
    'gamma':            {'type': 'float', 'min': 0.0,  'max': 5.0,  'log': False, 'enabled': False},
    'reg_alpha':        {'type': 'float', 'min': 0.0,  'max': 5.0,  'log': False, 'enabled': False},
    'reg_lambda':       {'type': 'float', 'min': 0.0,  'max': 5.0,  'log': False, 'enabled': False},
}

# Default fixed values applied to any param the user disables.
DEFAULT_FIXED_PARAMS: Dict[str, Any] = {
    'n_estimators': 200, 'max_depth': 6, 'learning_rate': 0.1,
    'min_child_weight': 1, 'subsample': 0.8, 'colsample_bytree': 0.8,
    'gamma': 0.0, 'reg_alpha': 0.0, 'reg_lambda': 1.0,
}

# metric -> +1 if higher is better, -1 if lower is better.
METRIC_DIRECTION: Dict[str, int] = {
    'roc_auc': 1, 'pr_auc': 1, 'f1': 1, 'f2': 1, 'precision': 1,
    'recall': 1, 'accuracy': 1, 'mcc': 1, 'log_loss': -1, 'brier': -1,
    'ks': 1, 'expected_cost': -1, 'r2': 1, 'rmse': -1, 'mae': -1, 'mse': -1,
}
METRIC_NAMES: List[str] = list(METRIC_DIRECTION.keys())
CLASSIFICATION_METRICS: List[str] = [
    'roc_auc', 'pr_auc', 'f1', 'f2', 'precision', 'recall',
    'accuracy', 'mcc', 'log_loss', 'brier', 'ks', 'expected_cost',
]
REGRESSION_METRICS: List[str] = ['r2', 'rmse', 'mae', 'mse']


def _normalize_task(task: Optional[str]) -> str:
    t = (task or 'classification').strip().lower()
    return 'regression' if t in ('regression', 'regressor', 'reg') else 'classification'


def _active_metrics(task: str) -> List[str]:
    return REGRESSION_METRICS if task == 'regression' else CLASSIFICATION_METRICS

# ---------------------------------------------------------------------------
# Search-method selection (grid / random / bayesian)
# ---------------------------------------------------------------------------
# The user can force a method; 'auto' applies a fit-count heuristic based on
# how large an *exhaustive grid* over the enabled space would be, measured in
# model fits per parallel worker (grid_candidates * cv_folds / n_jobs):
#   * < 100 fits/worker   -> grid     (exhaustive search is cheap)
#   * <= 500 fits/worker  -> random   (grid too big; sample n_iter configs)
#   * > 500 fits/worker   -> bayesian (large space; Optuna TPE)
SEARCH_METHODS: Tuple[str, ...] = ('grid', 'random', 'bayesian', 'optuna')
_DEFAULT_GRID_POINTS = 5          # grid resolution per param when method=grid
_GRID_MAX_CANDIDATES = 2000       # safety cap for an explicit grid run
_FITS_PER_JOB_GRID_MAX = 100      # < this -> grid
_FITS_PER_JOB_RANDOM_MAX = 500    # <= this -> random, else bayesian

# Bounds enforced on the editable space so a malformed payload can't make
# XGBoost diverge or explode runtime.
_PARAM_BOUNDS: Dict[str, Tuple[float, float]] = {
    'n_estimators': (5, 5000), 'max_depth': (1, 20), 'learning_rate': (1e-4, 1.0),
    'min_child_weight': (0, 100), 'subsample': (0.1, 1.0), 'colsample_bytree': (0.1, 1.0),
    'gamma': (0.0, 50.0), 'reg_alpha': (0.0, 100.0), 'reg_lambda': (0.0, 100.0),
}

def validate_param_space(space: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """Merge a (partial) user-supplied space onto the defaults, clamping each
    field to its safe bounds.  Returns (clean_space, warnings)."""
    warnings_out: List[str] = []
    clean: Dict[str, Any] = {}
    space = space or {}

    for name, default_spec in DEFAULT_PARAM_SPACE.items():
        spec = dict(default_spec)
        user = space.get(name) if isinstance(space, dict) else None
        if isinstance(user, dict):
            if 'enabled' in user:
                spec['enabled'] = bool(user['enabled'])
            if spec['type'] in ('int', 'float'):
                lo_b, hi_b = _PARAM_BOUNDS[name]
                lo = user.get('min', spec['min'])
                hi = user.get('max', spec['max'])
                try:
                    lo = float(lo); hi = float(hi)
                except (TypeError, ValueError):
                    warnings_out.append(f"{name}: non-numeric min/max ignored")
                    lo, hi = spec['min'], spec['max']
                if not np.isfinite(lo) or not np.isfinite(hi):
                    raise ValueError(f'{name}: tuning bounds must be finite.')
                if lo > hi:
                    warnings_out.append(f"{name}: min>max swapped")
                    lo, hi = hi, lo
                lo = max(lo_b, min(lo, hi_b))
                hi = max(lo_b, min(hi, hi_b))
                if spec.get('log') and lo <= 0:
                    lo = lo_b if lo_b > 0 else 1e-4
                spec['min'] = int(round(lo)) if spec['type'] == 'int' else float(lo)
                spec['max'] = int(round(hi)) if spec['type'] == 'int' else float(hi)
                if 'log' in user:
                    spec['log'] = bool(user['log'])
        clean[name] = spec

    if not any(s.get('enabled') for s in clean.values()):
        warnings_out.append('No params enabled; falling back to default enabled set')
        for n in ('n_estimators', 'max_depth', 'learning_rate'):
            clean[n]['enabled'] = True

    return clean, warnings_out


def _has_categorical(X: pd.DataFrame) -> bool:
    return any(
        hasattr(X[c], 'cat') or X[c].dtype.name == 'category'
        or X[c].dtype == 'object' or pd.api.types.is_string_dtype(X[c])
        for c in X.columns
    )


def _nan_metric_map() -> Dict[str, float]:
    return {m: float('nan') for m in METRIC_NAMES}


def _compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    return _compute_metrics(y_true, y_pred, task='regression')


def _compute_metrics(y_true, y_proba, threshold=.5, task='classification', costs=None):
    """Shared trusted metrics. Internal NaN compatibility; public evidence uses null."""
    metrics = development_metrics(y_true, y_proba, task, costs=costs, threshold=threshold)
    out = _nan_metric_map()
    out.update({key: float(value) if value is not None else float('nan') for key, value in metrics.items()})
    if task == 'classification':
        pred = (np.asarray(y_proba) >= threshold).astype(int)
        out['f2'] = float(fbeta_score(y_true, pred, beta=2, zero_division=0))
        out['mcc'] = float(matthews_corrcoef(y_true, pred))
    return out


def _make_cv_splitter(task: str, cv_folds: int):
    if _normalize_task(task) == 'regression':
        return KFold(n_splits=cv_folds, shuffle=True, random_state=42)
    return StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)


def _sample_config(space: Dict[str, Any], fixed: Dict[str, Any], rng: np.random.Generator) -> Dict[str, Any]:
    """Draw one random configuration; disabled params take their fixed value."""
    cfg: Dict[str, Any] = {}
    for name, spec in space.items():
        if not spec.get('enabled'):
            cfg[name] = fixed.get(name, DEFAULT_FIXED_PARAMS.get(name))
            continue
        cfg[name] = _sample_value(spec, rng)
    return cfg


def _sample_value(spec: Dict[str, Any], rng: np.random.Generator) -> Any:
    t = spec.get('type')
    if t == 'categorical':
        vals = spec['values']
        return vals[int(rng.integers(0, len(vals)))]
    lo, hi = spec['min'], spec['max']
    if t == 'int':
        lo, hi = int(lo), int(hi)
        if spec.get('log') and lo >= 1:
            return int(round(float(np.exp(rng.uniform(np.log(lo), np.log(hi))))))
        return int(rng.integers(lo, hi + 1))
    lo, hi = float(lo), float(hi)
    if spec.get('log') and lo > 0:
        return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
    return float(rng.uniform(lo, hi))


def _grid_values(spec: Dict[str, Any], points: int) -> List[Any]:
    """Evenly spaced sweep values for a param's validation curve."""
    t = spec.get('type')
    if t == 'categorical':
        return list(spec['values'])
    lo, hi = spec['min'], spec['max']
    if spec.get('log') and float(lo) > 0:
        seq = np.exp(np.linspace(np.log(float(lo)), np.log(float(hi)), points))
    else:
        seq = np.linspace(float(lo), float(hi), points)
    if t == 'int':
        vals = sorted({int(round(v)) for v in seq})
        return vals
    return [float(round(v, 6)) for v in seq]


def estimate_grid_candidates(
    space: Dict[str, Any],
    grid_points_per_param: int = _DEFAULT_GRID_POINTS,
    points_map: Optional[Dict[str, int]] = None,
) -> int:
    """Number of candidate configs an exhaustive grid over the *enabled* params
    would enumerate.  Each param uses ``points_map[name]`` checkpoints when given
    (the per-param Walk_Step granularity from the UI), else the scalar
    ``grid_points_per_param`` resolution.  Int params whose integer range is
    smaller than the resolution yield fewer (deduped) points."""
    count = 1
    default_pts = max(2, int(grid_points_per_param))
    pm = points_map or {}
    for name, spec in space.items():
        if not spec.get('enabled'):
            continue
        pts = max(2, int(pm.get(name, default_pts)))
        count *= max(1, len(_grid_values(spec, pts)))
    return int(count)


def recommend_search_method(
    space: Dict[str, Any], cv_folds: int, n_jobs: int,
    grid_points_per_param: int = _DEFAULT_GRID_POINTS,
    points_map: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Default search-method heuristic based on the exhaustive-grid fit count
    per parallel worker (``grid_candidates * cv_folds / n_jobs``):

        < 100 fits/worker   -> grid
        <= 500 fits/worker  -> random
        > 500 fits/worker   -> bayesian

    Returns a dict with the chosen ``method`` plus the numbers behind it so the
    UI / AI can explain the recommendation to the user.
    """
    candidates = estimate_grid_candidates(space, grid_points_per_param, points_map)
    folds = max(2, int(cv_folds))
    workers = max(1, int(n_jobs))
    total_fits = candidates * folds
    fits_per_job = total_fits / workers
    if fits_per_job < _FITS_PER_JOB_GRID_MAX:
        method = 'grid'
        why = (f"An exhaustive grid is only ~{fits_per_job:.0f} fits/worker "
               f"(< {_FITS_PER_JOB_GRID_MAX}) — cheap enough to evaluate every combination.")
    elif fits_per_job <= _FITS_PER_JOB_RANDOM_MAX:
        method = 'random'
        why = (f"An exhaustive grid would be ~{fits_per_job:.0f} fits/worker "
               f"({_FITS_PER_JOB_GRID_MAX}–{_FITS_PER_JOB_RANDOM_MAX}) — random sampling "
               f"covers the space efficiently.")
    else:
        method = 'bayesian'
        why = (f"An exhaustive grid would be ~{fits_per_job:.0f} fits/worker "
               f"(> {_FITS_PER_JOB_RANDOM_MAX}) — Optuna TPE spends the budget where it matters.")
    return {
        'method': method,
        'grid_candidates': int(candidates),
        'total_fits': int(total_fits),
        'fits_per_job': round(float(fits_per_job), 1),
        'cv_folds': folds,
        'n_jobs': workers,
        'grid_points_per_param': int(max(2, grid_points_per_param)),
        'rationale': why,
    }


def _grid_configs(
    space: Dict[str, Any], fixed: Dict[str, Any],
    grid_points_per_param: int, max_candidates: int, rng: np.random.Generator,
    points_map: Optional[Dict[str, int]] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Cartesian product of per-param grids for the enabled params (disabled
    params take their fixed value).  Each enabled param uses ``points_map[name]``
    checkpoints when supplied, else the scalar ``grid_points_per_param``.  If the
    product exceeds ``max_candidates`` the grid is uniformly down-sampled to the
    cap (returns truncated=True)."""
    import itertools
    default_pts = max(2, int(grid_points_per_param))
    pm = points_map or {}
    names: List[str] = []
    axes: List[List[Any]] = []
    for name, spec in space.items():
        if not spec.get('enabled'):
            continue
        names.append(name)
        axes.append(_grid_values(spec, max(2, int(pm.get(name, default_pts)))))
    base = {n: fixed.get(n, DEFAULT_FIXED_PARAMS.get(n)) for n in space}
    if not axes:
        return [dict(base)], False

    total = 1
    for a in axes:
        total *= len(a)

    configs: List[Dict[str, Any]] = []
    if total > max_candidates:
        # Uniformly sample distinct index-combinations up to the cap.
        sizes = [len(a) for a in axes]
        seen = set()
        attempts = 0
        cap = int(max_candidates)
        while len(configs) < cap and attempts < cap * 20:
            attempts += 1
            idx = tuple(int(rng.integers(0, s)) for s in sizes)
            if idx in seen:
                continue
            seen.add(idx)
            cfg = dict(base)
            for j, name in enumerate(names):
                cfg[name] = axes[j][idx[j]]
            configs.append(cfg)
        return configs, True

    for combo in itertools.product(*axes):
        cfg = dict(base)
        for j, name in enumerate(names):
            cfg[name] = combo[j]
        configs.append(cfg)
    return configs, False


def _evaluate_config(
    X_train: pd.DataFrame, y_train: pd.Series,
    X_test: pd.DataFrame, y_test: pd.Series,
    config: Dict[str, Any], cv_folds: int, has_cat: bool,
    nthread: int, threshold: float,
    scale_pos_weight: Optional[float] = None,
    early_stopping_rounds: int = 50,
    task: str = 'classification',
    algorithm: str = 'xgboost',
    validation_context=None,
) -> Dict[str, Any]:
    """Cross-validate one config and also fit on full train -> valid/train metrics.

    ``X_test`` here is the modeling validation holdout (not the locked outer test).
    Returns a trial dict with cv (mean+std per metric), train, test metric maps.
    """
    task = _normalize_task(task)
    t0 = time.time()

    costs = (((validation_context or {}).get('prediction_contract') or {}).get('objective') or {}).get('cost_matrix')
    fold_metrics: List[Dict[str, float]] = []
    provenance = []
    for X_tr, y_tr, X_va, y_va, fold_receipt in iter_validation_folds(validation_context, X_train, y_train, cv_folds, task):
        provenance.append(fold_receipt)
        adapter = fit_for_tuning(
            algorithm,
            X_tr, y_tr,
            X_va, y_va,
            config, task=task, nthread=nthread,
            scale_pos_weight=scale_pos_weight,
            early_stopping_rounds=early_stopping_rounds, context=validation_context,
        )
        fold_receipt['fit_receipt'] = adapter.fit_receipt
        proba = adapter.predict(X_va)
        fold_metrics.append(_compute_metrics(y_va.values, proba, threshold, task=task, costs=costs))

    cv: Dict[str, Dict[str, float]] = {}
    for m in METRIC_NAMES:
        coverage = metric_coverage([fm[m] for fm in fold_metrics], complete_only=True)
        cv[m] = {**coverage, 'mean': coverage['mean'] if coverage['mean'] is not None else float('nan'),
                 'std': coverage['std'] if coverage['std'] is not None else float('nan')}

    # Full-fit on train with early stopping on the modeling validation holdout.
    full = fit_for_tuning(
        algorithm, X_train, y_train, X_test, y_test, config,
        task=task, nthread=nthread, scale_pos_weight=scale_pos_weight,
        early_stopping_rounds=early_stopping_rounds, context=validation_context,
    )
    train_metrics = _compute_metrics(y_train.values, full.predict_proba(X_train), threshold, task=task, costs=costs)
    test_metrics = _compute_metrics(y_test.values, full.predict_proba(X_test), threshold, task=task, costs=costs)

    return {
        'params': config,
        'cv': cv,
        'train': train_metrics,
        'test': test_metrics,
        'best_iteration': int(getattr(full, 'best_iteration', 0) or 0),
        'fit_time': round(time.time() - t0, 3),
        'algorithm': algorithm,
        'validation_provenance': provenance,
        'fold_metrics': fold_metrics,
        'fit_receipt': full.fit_receipt,
    }


def _evaluate_cv_only(
    X_train: pd.DataFrame, y_train: pd.Series,
    config: Dict[str, Any], cv_folds: int, has_cat: bool,
    nthread: int, threshold: float, metric: str,
    scale_pos_weight: Optional[float] = None,
    early_stopping_rounds: int = 50,
    task: str = 'classification',
    algorithm: str = 'xgboost',
    validation_context=None,
    return_evidence=False,
) -> Tuple[float, float, float, float]:
    """Lightweight CV used for validation curves: returns
    (train_mean, train_std, cv_mean, cv_std) for a single ``metric``."""
    task = _normalize_task(task)
    costs = (((validation_context or {}).get('prediction_contract') or {}).get('objective') or {}).get('cost_matrix')
    tr_scores, cv_scores = [], []
    provenance = []
    for X_tr, y_tr, X_va, y_va, fold_receipt in iter_validation_folds(validation_context, X_train, y_train, cv_folds, task):
        provenance.append(fold_receipt)
        adapter = fit_for_tuning(
            algorithm,
            X_tr, y_tr,
            X_va, y_va,
            config, task=task, nthread=nthread,
            scale_pos_weight=scale_pos_weight,
            early_stopping_rounds=early_stopping_rounds, context=validation_context,
        )
        fold_receipt['fit_receipt'] = adapter.fit_receipt
        tr_scores.append(
            _compute_metrics(
                y_tr.values, adapter.predict_proba(X_tr),
                threshold, task=task, costs=costs,
            )[metric]
        )
        cv_scores.append(
            _compute_metrics(
                y_va.values, adapter.predict_proba(X_va),
                threshold, task=task, costs=costs,
            )[metric]
        )
    coverage = metric_coverage(cv_scores)
    if coverage['status'] != 'complete':
        raise ValueError(f'Requested validation-curve metric {metric} is available in {coverage["n_valid"]} of {coverage["n_total"]} folds; partial-fold averaging is prohibited.')
    train_coverage = metric_coverage(tr_scores)
    evidence = {'status': 'complete', 'train': train_coverage, 'cv': coverage,
                'train_scores': tr_scores, 'cv_scores': cv_scores, 'validation_provenance': provenance}
    if return_evidence:
        return evidence
    return (train_coverage['mean'], train_coverage['std'], coverage['mean'], coverage['std'])


def _best_trial_for_metric(trials: List[Dict[str, Any]], metric: str) -> Optional[Dict[str, Any]]:
    direction = METRIC_DIRECTION.get(metric, 1)
    best, best_val = None, None
    for t in trials:
        evidence = t['cv'].get(metric, {})
        if evidence.get('status', 'complete') != 'complete':
            continue
        v = evidence.get('mean')
        if v is None or not np.isfinite(v):
            continue
        if best_val is None or (direction * v) > (direction * best_val):
            best_val, best = v, t
    return best


def _param_matrix(trials: List[Dict[str, Any]], param_names: List[str], space: Dict[str, Any]) -> np.ndarray:
    rows = []
    for t in trials:
        row = []
        for p in param_names:
            v = t['params'].get(p)
            spec = space[p]
            if spec['type'] == 'categorical':
                try:
                    row.append(float(spec['values'].index(v)))
                except ValueError:
                    row.append(-1.0)
            else:
                row.append(float(v))
        rows.append(row)
    return np.asarray(rows, dtype=float)


def _surrogate_importance(X: np.ndarray, y: np.ndarray, param_names: List[str]) -> Dict[str, float]:
    """Normalized RandomForest importances mapping params -> target."""
    finite = np.isfinite(y)
    X, y = X[finite], y[finite]
    if len(X) < 5 or np.allclose(y, y[0]):
        return {p: 0.0 for p in param_names}
    rf = RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=1)
    rf.fit(X, y)
    imp = rf.feature_importances_
    total = float(imp.sum())
    return {param_names[i]: (float(imp[i] / total) if total > 0 else 0.0) for i in range(len(param_names))}


def _directions(X: np.ndarray, y: np.ndarray, param_names: List[str]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    finite = np.isfinite(y)
    Xf, yf = X[finite], y[finite]
    for i, p in enumerate(param_names):
        try:
            if len(yf) < 3 or np.allclose(Xf[:, i], Xf[0, i]):
                out[p] = 0.0
                continue
            r, _ = spearmanr(Xf[:, i], yf)
            out[p] = float(r) if np.isfinite(r) else 0.0
        except Exception:
            out[p] = 0.0
    return out


def _build_guidance(validation_curves: List[Dict[str, Any]], primary_metric: str) -> List[Dict[str, Any]]:
    """Verbal zoom-in / zoom-out suggestions for the next search space."""
    direction = METRIC_DIRECTION.get(primary_metric, 1)
    guidance: List[Dict[str, Any]] = []
    for curve in validation_curves:
        vals = curve.get('values', [])
        cv_mean = np.asarray(curve.get('cv_mean', []), dtype=float)
        if curve.get('type') == 'categorical' or len(vals) < 3 or not np.any(np.isfinite(cv_mean)):
            continue
        scores = np.where(np.isfinite(cv_mean), direction * cv_mean, -np.inf)
        best_i = int(np.argmax(scores))
        n = len(vals)
        gap = None
        tr_mean = np.asarray(curve.get('train_mean', []), dtype=float)
        if len(tr_mean) == n and np.isfinite(tr_mean[best_i]) and np.isfinite(cv_mean[best_i]):
            gap = float(direction * (tr_mean[best_i] - cv_mean[best_i]))

        param = curve['param']
        if best_i == 0:
            lo, hi = vals[0], vals[1]
            span = (hi - lo)
            guidance.append({
                'param': param, 'type': 'zoom_out',
                'suggested_range': [round(lo - span, 6), round(hi, 6)],
                'rationale': (f"Best CV {primary_metric} is at the lower edge "
                              f"({vals[0]}). Extend the range below {vals[0]} to find the optimum."),
            })
        elif best_i == n - 1:
            lo, hi = vals[-2], vals[-1]
            span = (hi - lo)
            guidance.append({
                'param': param, 'type': 'zoom_out',
                'suggested_range': [round(lo, 6), round(hi + span, 6)],
                'rationale': (f"Best CV {primary_metric} is at the upper edge "
                              f"({vals[-1]}). Extend the range above {vals[-1]} to find the optimum."),
            })
        else:
            lo, hi = vals[best_i - 1], vals[best_i + 1]
            extra = ''
            if gap is not None:
                extra = f' Observed directional train-CV gap: {gap:.3f}; this is descriptive development evidence.'
            guidance.append({
                'param': param, 'type': 'zoom_in',
                'suggested_range': [round(lo, 6), round(hi, 6)],
                'rationale': (f"CV {primary_metric} peaks at {vals[best_i]} (interior). "
                              f"Zoom into [{round(lo, 6)}, {round(hi, 6)}] for finer resolution.{extra}"),
            })
    return guidance


def run_hyperparam_search_with_progress(
    X_train: pd.DataFrame, y_train: pd.Series,
    X_test: pd.DataFrame, y_test: pd.Series,
    param_space: Optional[Dict[str, Any]] = None,
    fixed_params: Optional[Dict[str, Any]] = None,
    n_iter: int = 40,
    cv_folds: int = 5,
    n_jobs: int = 1,
    primary_metric: Optional[str] = None,
    threshold: float = 0.5,
    validation_curve_points: int = 8,
    random_state: int = 42,
    features: Optional[List[str]] = None,
    search_method: str = 'auto',
    grid_points_per_param: int = _DEFAULT_GRID_POINTS,
    grid_points_per_param_map: Optional[Dict[str, int]] = None,
    status_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    stop_flag: Optional[Dict[str, Any]] = None,
    scale_pos_weight: Optional[float] = None,
    early_stopping_rounds: int = 50,
    task: str = 'classification',
    algorithm: str = 'xgboost',
    validation_context=None,
    execution_id=None,
) -> Dict[str, Any]:
    """Run a hyperparameter search + validation curves with progress + stop support.

    ``search_method`` is one of {'auto', 'grid', 'random', 'bayesian', 'optuna'}.
    'auto' applies the fit-count heuristic in ``recommend_search_method`` (grid
    when an exhaustive search is cheap, random for mid-size spaces, Optuna TPE
    for large spaces).  ``bayesian`` and ``optuna`` both run Optuna TPE (the FE
    exposes the label as Bayesian).  ``grid_points_per_param`` sets the per-param
    grid resolution (also used to size the recommendation);
    ``grid_points_per_param_map`` may override it per param (param name ->
    checkpoint count) — this is how the UI Walk_Step column drives a different
    granularity for each hyperparameter.

    Returns a JSON-serializable dict (see module docstring for the shape).
    """
    objective = resolve_tuning_objective(task, validation_context, primary_metric, threshold)
    primary_metric = objective['primary_metric']
    algorithm = (algorithm or 'xgboost').strip().lower()
    space, space_warnings = validate_param_space(param_space)
    fixed = {**DEFAULT_FIXED_PARAMS, **(fixed_params or {})}
    for name, value in fixed.items():
        if name not in _PARAM_BOUNDS or not np.isfinite(float(value)) or not _PARAM_BOUNDS[name][0] <= float(value) <= _PARAM_BOUNDS[name][1]:
            raise ValueError(f'Fixed tuning parameter {name!r} is unsupported or outside its finite bounds.')
    selected = validate_features(features, X_train, X_test)
    X_train, X_test = X_train[selected], X_test[selected]

    has_cat = _has_categorical(X_train)
    nthread = 1 if n_jobs and n_jobs > 1 else 0
    enabled_params = [p for p, s in space.items() if s.get('enabled')]
    rng = np.random.default_rng(random_state)

    # Auto scale_pos_weight from train labels when not supplied (classification only)
    if task == 'regression':
        scale_pos_weight = None
    elif scale_pos_weight is None:
        try:
            pos = float((np.asarray(y_train) == 1).sum())
            neg = float((np.asarray(y_train) == 0).sum())
            if pos > 0:
                scale_pos_weight = round(neg / pos, 6)
        except Exception:
            scale_pos_weight = None
    results_scale_pos_weight = scale_pos_weight

    # ── Resolve the search method (grid / random / bayesian / auto) ──
    grid_points_per_param = max(2, int(grid_points_per_param or _DEFAULT_GRID_POINTS))
    # Per-param checkpoint counts (from the UI Walk_Step column).  Keep only
    # known, enabled-or-not param names; clamp each to a safe [2, 500] range.
    points_map: Dict[str, int] = {}
    if isinstance(grid_points_per_param_map, dict):
        for _name, _cnt in grid_points_per_param_map.items():
            if _name not in space:
                continue
            try:
                points_map[_name] = max(2, min(int(_cnt), 500))
            except (TypeError, ValueError):
                continue
    recommendation = recommend_search_method(
        space, cv_folds, n_jobs, grid_points_per_param, points_map=points_map or None)
    requested = (search_method or 'auto').strip().lower()
    if requested not in SEARCH_METHODS:
        requested = 'auto'
    method = recommendation['method'] if requested == 'auto' else requested

    print(f"[Hyperparam] method={method} (requested={requested}), algo={algorithm}, n_iter={n_iter}, "
          f"cv_folds={cv_folds}, n_jobs={n_jobs}, enabled={enabled_params}, "
          f"features={X_train.shape[1]}, has_cat={has_cat}, "
          f"grid~{recommendation['grid_candidates']} cand "
          f"(~{recommendation['fits_per_job']} fits/worker), CPUs={os.cpu_count()}")

    def is_stop() -> bool:
        return bool(stop_flag and stop_flag.get('stop_requested'))

    results: Dict[str, Any] = {
        'status': 'running',
        'task': task,
        'algorithm': algorithm,
        'primary_metric': primary_metric,
        'selection_objective': objective,
        'active_metrics': _active_metrics(task),
        'search_method': method,
        'search_method_requested': requested,
        'recommendation': recommendation,
        'grid_points_per_param': grid_points_per_param,
        'grid_points_per_param_map': points_map,
        'param_space': space,
        'fixed_params': fixed,
        'enabled_params': enabled_params,
        'space_warnings': list(space_warnings),
        'threshold': threshold,
        'cv_folds': cv_folds,
        'scale_pos_weight': results_scale_pos_weight,
        'early_stopping_rounds': early_stopping_rounds,
        'holdout_role': 'development_validation',
        'class_weight_policy': (validation_context or {}).get('class_weight_policy') or 'Fixed development-training weight',  # X_test arg is modeling valid, not locked outer test
        'feature_count': int(X_train.shape[1]),
        'features': list(X_train.columns),
        'trials': [],
        'trial_attempts': [],
        'limitations': [objective['qualification'], objective['training_policy'],
                         'Search projections and cancellation are in-process; durable immutable jobs remain open.',
                         'Surrogate importance and range suggestions are ranking heuristics, not causal effects.'],
        'best_points': {},
        'validation_curves': [],
        'param_importance': {},
        'emphasized': {},
        'guidance': [],
    }

    # Build the search configs up-front for grid/random; bayesian/optuna
    # propose configs iteratively via Optuna TPE (see Phase A below).
    grid_truncated = False
    search_configs: Optional[List[Dict[str, Any]]] = None
    if method == 'grid':
        search_configs, grid_truncated = _grid_configs(
            space, fixed, grid_points_per_param, _GRID_MAX_CANDIDATES, rng,
            points_map=points_map or None)
        if grid_truncated:
            results['space_warnings'].append(
                f'Grid exceeded {_GRID_MAX_CANDIDATES} candidates; down-sampled to the cap.')
        n_search = len(search_configs)
    elif method in ('bayesian', 'optuna'):
        n_search = int(n_iter)
    else:  # random
        search_configs = [_sample_config(space, fixed, rng) for _ in range(n_iter)]
        n_search = int(n_iter)
    results['n_search_evals'] = n_search
    results['grid_truncated'] = grid_truncated
    results['search_basis'] = tuning_basis(X_train, y_train, X_test, y_test, validation_context, execution_id,
        algorithm, objective, {'param_space': space, 'fixed_params': fixed, 'n_iter': n_iter,
        'cv_folds': cv_folds, 'n_jobs': n_jobs, 'nthread': nthread, 'random_state': random_state,
        'search_method_requested': requested, 'search_method_resolved': method, 'n_search_evals': n_search,
        'grid_points_per_param': grid_points_per_param, 'grid_points_per_param_map': points_map,
        'validation_curve_points': validation_curve_points, 'scale_pos_weight': scale_pos_weight,
        'early_stopping_rounds': early_stopping_rounds})

    total_units = max(1, n_search + len(enabled_params) * max(2, validation_curve_points))
    done_units = [0]

    def emit(message: str, extra: Optional[Dict[str, Any]] = None):
        if not status_callback:
            return
        payload = {
            'message': message,
            'progress': min(0.999, done_units[0] / total_units),
            'status': 'running',
        }
        if extra:
            payload.update(extra)
        status_callback(payload)

    trials: List[Dict[str, Any]] = []
    results['trials'] = trials

    def record_attempt(index, config, result=None, error=None, state=None):
        coverage = (result or {}).get('cv', {}).get(primary_metric, {})
        usable = coverage.get('status') == 'complete' and coverage.get('mean') is not None and np.isfinite(coverage['mean'])
        attempt = {'trial_index': index, 'params': dict(config),
                   'status': state or ('failed' if error else 'completed' if usable else 'objective_unavailable'),
                   'primary_coverage': coverage, 'error': str(error) if error else None,
                   'search_basis_sha256': results['search_basis']['sha256']}
        results['trial_attempts'].append(attempt)
        if result is not None:
            result.update({'trial_index': index, 'selection_usable': usable,
                           'search_basis_sha256': results['search_basis']['sha256']})
        return usable

    def evaluate_batch(cfgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Cross-validate a batch of configs in parallel; updates progress."""
        out: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, n_jobs)) as pool:
            futures = {
                pool.submit(
                    _evaluate_config, X_train, y_train, X_test, y_test,
                    cfg, cv_folds, has_cat, nthread, threshold,
                    scale_pos_weight, early_stopping_rounds, task, algorithm, validation_context,
                ): i
                for i, cfg in enumerate(cfgs)
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                if is_stop():
                    for pending in futures:
                        pending.cancel()
                if fut.cancelled():
                    record_attempt(idx, cfgs[idx], state='cancelled')
                else:
                    try:
                        result = fut.result()
                        record_attempt(idx, cfgs[idx], result=result)
                        out.append(result)
                    except Exception as trial_err:
                        record_attempt(idx, cfgs[idx], error=trial_err)
                done_units[0] += 1
                done = len(results['trial_attempts'])
                step = max(1, n_search // 20)
                if done % step == 0 or done >= n_search:
                    best = _best_trial_for_metric(trials + out, primary_metric)
                    cur = best['cv'][primary_metric]['mean'] if best else None
                    emit(f'{method.capitalize()} search: {done}/{n_search} configs evaluated',
                         {'completed_trials': done,
                          'current_best': {'metric': primary_metric, 'cv_mean': cur}})
        return sorted(out, key=lambda row: row['trial_index'])

    def run_optuna_tpe(label: str) -> bool:
        """Run Optuna TPE into ``trials``. Returns True on success."""
        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)
        except ImportError:
            results['space_warnings'].append(
                'Optuna is not installed; falling back to random search.')
            return False

        emit(f'Starting {label} ({n_iter} trials, Optuna TPE)...')
        direction = METRIC_DIRECTION.get(primary_metric, 1)
        study = optuna.create_study(
            direction='maximize' if direction > 0 else 'minimize',
            sampler=optuna.samplers.TPESampler(seed=random_state),
        )

        def _suggest_config(trial: 'optuna.Trial') -> Dict[str, Any]:
            cfg: Dict[str, Any] = {}
            for name, spec in space.items():
                if not spec.get('enabled'):
                    cfg[name] = fixed.get(name, DEFAULT_FIXED_PARAMS.get(name))
                    continue
                t = spec.get('type')
                if t == 'categorical':
                    cfg[name] = trial.suggest_categorical(name, list(spec['values']))
                elif t == 'int':
                    lo, hi = int(spec['min']), int(spec['max'])
                    if spec.get('log') and lo >= 1:
                        cfg[name] = trial.suggest_int(name, lo, hi, log=True)
                    else:
                        cfg[name] = trial.suggest_int(name, lo, hi)
                else:
                    lo, hi = float(spec['min']), float(spec['max'])
                    if spec.get('log') and lo > 0:
                        cfg[name] = trial.suggest_float(name, lo, hi, log=True)
                    else:
                        cfg[name] = trial.suggest_float(name, lo, hi)
            return cfg

        def _objective(trial: 'optuna.Trial') -> float:
            if is_stop():
                raise optuna.TrialPruned()
            cfg = _suggest_config(trial)
            try:
                result = _evaluate_config(
                    X_train, y_train, X_test, y_test, cfg, cv_folds, has_cat,
                    nthread, threshold, scale_pos_weight, early_stopping_rounds, task,
                    algorithm, validation_context,
                )
            except Exception as error:
                record_attempt(trial.number, cfg, error=error)
                done_units[0] += 1
                raise
            usable = record_attempt(trial.number, cfg, result=result)
            trials.append(result)
            done_units[0] += 1
            mean = result['cv'].get(primary_metric, {}).get('mean')
            emit(
                f'{label}: {len(trials)}/{n_iter} trials',
                {'completed_trials': len(trials),
                 'current_best': {'metric': primary_metric, 'cv_mean': mean}},
            )
            if not usable:
                raise optuna.TrialPruned('Declared objective is unavailable in every required fold.')
            return float(mean)

        def stop_study(study, trial):
            if is_stop():
                study.stop()
        study.optimize(_objective, n_trials=int(n_iter), n_jobs=1, catch=(Exception,), callbacks=[stop_study])
        results['search_backend'] = 'optuna_tpe'
        try:
            results['optuna_best_value'] = study.best_value if study.trials else None
            results['optuna_best_params'] = study.best_params if study.trials else None
        except ValueError:
            results['optuna_best_value'] = None
            results['optuna_best_params'] = None
        return True

    try:
        # ---------- Phase A: hyperparameter search ----------
        if method in ('bayesian', 'optuna'):
            label = 'Bayesian (TPE)' if method == 'bayesian' else 'Optuna TPE'
            if not run_optuna_tpe(label):
                method = 'random'
                results['search_method'] = method
                results['search_basis']['configuration']['search_method_resolved'] = method
                results['search_basis']['sha256'] = receipt_digest({key: value for key, value in results['search_basis'].items() if key != 'sha256'})
                search_configs = [_sample_config(space, fixed, rng) for _ in range(n_iter)]
                n_search = int(n_iter)
                results['n_search_evals'] = n_search
                emit(f'Starting random search ({n_search} configs)...')
                trials.extend(evaluate_batch(search_configs))
        elif method in ('grid', 'random'):
            label = 'Grid' if method == 'grid' else 'Random'
            emit(f'Starting {label.lower()} search ({n_search} configs)...')
            trials.extend(evaluate_batch(search_configs or []))

        results['trials'] = trials
        results['n_trials'] = len(trials)
        results['trial_attempts'].sort(key=lambda row: row['trial_index'])
        results['n_attempted'] = len(results['trial_attempts'])
        results['n_failed'] = sum(row['status'] != 'completed' for row in results['trial_attempts'])

        if not trials:
            results['status'] = 'stopped' if is_stop() else 'error'
            if results['status'] == 'error':
                results['error'] = 'No trials completed successfully'
            return json_record(results)

        if _best_trial_for_metric(trials, primary_metric) is None:
            results.update(status='stopped' if is_stop() else 'error', error='No configuration has a complete finite declared objective across all required folds.')
            return json_record(results)

        # ---------- Best metric "space points" ----------
        for m in METRIC_NAMES:
            bt = _best_trial_for_metric(trials, m)
            if bt:
                results['best_points'][m] = {
                    'params': bt['params'],
                    'trial_index': bt['trial_index'],
                    'metric_coverage': bt['cv'][m],
                    'cv_mean': bt['cv'][m]['mean'],
                    'cv_std': bt['cv'][m]['std'],
                    'test': bt['test'].get(m),
                    'train': bt['train'].get(m),
                }

        # ---------- Param-importance attribution (surrogate models) ----------
        if enabled_params and len(trials) >= 5:
            Xp = _param_matrix(trials, enabled_params, space)
            cv_primary = np.array([t['cv'][primary_metric]['mean'] for t in trials], dtype=float)
            overfit = np.array([
                (t['train'].get(primary_metric, np.nan) - t['cv'][primary_metric]['mean'])
                * METRIC_DIRECTION.get(primary_metric, 1) for t in trials], dtype=float)
            shrink = np.array([
                (t['cv'][primary_metric]['mean'] - t['test'].get(primary_metric, np.nan))
                * METRIC_DIRECTION.get(primary_metric, 1) for t in trials], dtype=float)

            imp_gain = _surrogate_importance(Xp, cv_primary, enabled_params)
            imp_overfit = _surrogate_importance(Xp, overfit, enabled_params)
            imp_shrink = _surrogate_importance(Xp, shrink, enabled_params)
            results['param_importance'] = {
                'cv_gain': imp_gain,
                'overfitting': imp_overfit,
                'shrinkage': imp_shrink,
                'direction': {
                    'cv_gain': _directions(Xp, cv_primary, enabled_params),
                    'overfitting': _directions(Xp, overfit, enabled_params),
                    'shrinkage': _directions(Xp, shrink, enabled_params),
                },
            }

            def _argmax(d: Dict[str, float]) -> Optional[str]:
                return max(d, key=d.get) if d and max(d.values()) > 0 else None
            results['emphasized'] = {
                'most_cv_gain': _argmax(imp_gain),
                'most_overfitting': _argmax(imp_overfit),
                'most_shrinkage': _argmax(imp_shrink),
            }

        # ---------- Phase B: per-hyperparameter validation curves ----------
        best_trial = _best_trial_for_metric(trials, primary_metric)
        base_config = dict(best_trial['params'])
        results['selected_trial_index'] = best_trial['trial_index']
        results['selected_params'] = dict(base_config)
        curves: List[Dict[str, Any]] = []

        for param in enabled_params:
            if is_stop():
                break
            spec = space[param]
            grid = _grid_values(spec, validation_curve_points)
            emit(f'Validation curve: {param} ({len(grid)} points)')

            point_configs = []
            for v in grid:
                cfg = dict(base_config)
                cfg[param] = v
                point_configs.append(cfg)

            point_results: Dict[int, Tuple[float, float, float, float]] = {}
            with ThreadPoolExecutor(max_workers=max(1, n_jobs)) as pool:
                futs = {
                    pool.submit(
                        _evaluate_cv_only, X_train, y_train, cfg, cv_folds,
                        has_cat, nthread, threshold, primary_metric,
                        scale_pos_weight, early_stopping_rounds, task, algorithm, validation_context, True,
                    ): idx
                    for idx, cfg in enumerate(point_configs)
                }
                for fut in as_completed(futs):
                    idx = futs[fut]
                    try:
                        point_results[idx] = fut.result()
                    except Exception as cv_err:
                        print(f"[Hyperparam] curve point failed ({param}): {cv_err}")
                        point_results[idx] = {'status': 'failed', 'error': str(cv_err),
                            'train': {'mean': None, 'std': None}, 'cv': {'mean': None, 'std': None}}
                    done_units[0] += 1

            ordered = [point_results[i] for i in range(len(grid))]
            tr_mean = [r['train']['mean'] for r in ordered]
            tr_std = [r['train']['std'] for r in ordered]
            cv_mean = [r['cv']['mean'] for r in ordered]
            cv_std = [r['cv']['std'] for r in ordered]
            direction = METRIC_DIRECTION.get(primary_metric, 1)
            finite_cv = [(i, c) for i, c in enumerate(cv_mean) if c is not None and np.isfinite(c)]
            best_value = None
            if finite_cv:
                best_idx = max(finite_cv, key=lambda ic: direction * ic[1])[0]
                best_value = grid[best_idx]
            curves.append({
                'param': param,
                'type': spec['type'],
                'scale': 'log' if spec.get('log') else 'linear',
                'metric': primary_metric,
                'values': grid,
                'train_mean': tr_mean, 'train_std': tr_std,
                'cv_mean': cv_mean, 'cv_std': cv_std,
                'best_value': best_value,
                'base_params': base_config,
                'points': [{'params': cfg, **point, 'search_basis_sha256': results['search_basis']['sha256']}
                           for cfg, point in zip(point_configs, ordered)],
            })
            emit(f'{param} curve complete')

        results['validation_curves'] = curves
        results['guidance'] = _build_guidance(curves, primary_metric)
        results['n_failed_curve_points'] = sum(point['status'] != 'complete' for curve in curves for point in curve['points'])

        results['status'] = 'stopped' if is_stop() else 'completed'
        emit('Hyperparameter tuning stopped by user' if is_stop()
             else 'Hyperparameter tuning completed')
        return json_record(results)

    except Exception as e:
        results['status'] = 'error'
        results['error'] = str(e)
        if status_callback:
            status_callback({'message': f'Hyperparameter tuning failed: {e}',
                             'progress': 0.0, 'status': 'error', 'error': str(e)})
        print(f"[Hyperparam] Error: {e}")
        import traceback
        traceback.print_exc()
        return json_record(results)
