"""
Hyperparameter tuning utilities for boosting models (XGBoost / LightGBM / CatBoost).

This module implements a *random joint search* over an editable
hyperparameter space plus per-hyperparameter *validation curves*
(train vs. cross-validation score across a 1-D sweep, holding the other
params at the best configuration — the classic ``validation_curve``
shape).  It mirrors the architecture of ``sfs_utils.py``:

    * StratifiedKFold cross-validation via shared booster adapters.
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
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score, fbeta_score,
    precision_score, recall_score, accuracy_score, matthews_corrcoef,
    log_loss, brier_score_loss, mean_absolute_error, mean_squared_error, r2_score,
)
from scipy.stats import spearmanr

from modeling.booster_adapters import fit_booster, config_to_booster_params

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
    'r2': 1, 'rmse': -1, 'mae': -1,
}
METRIC_NAMES: List[str] = list(METRIC_DIRECTION.keys())
CLASSIFICATION_METRICS: List[str] = [
    'roc_auc', 'pr_auc', 'f1', 'f2', 'precision', 'recall',
    'accuracy', 'mcc', 'log_loss', 'brier',
]
REGRESSION_METRICS: List[str] = ['r2', 'rmse', 'mae']


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
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    out = _nan_metric_map()
    try:
        out['r2'] = float(r2_score(y_true, y_pred)) if len(y_true) >= 2 else float('nan')
    except Exception:
        out['r2'] = float('nan')
    try:
        out['rmse'] = float(np.sqrt(mean_squared_error(y_true, y_pred))) if len(y_true) else float('nan')
    except Exception:
        out['rmse'] = float('nan')
    try:
        out['mae'] = float(mean_absolute_error(y_true, y_pred)) if len(y_true) else float('nan')
    except Exception:
        out['mae'] = float('nan')
    return out


def _compute_metrics(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    threshold: float = 0.5,
    task: str = 'classification',
) -> Dict[str, float]:
    """Boosting metrics for classification (proba+threshold) or regression (raw preds)."""
    if _normalize_task(task) == 'regression':
        return _compute_regression_metrics(y_true, y_proba)

    y_true = np.asarray(y_true).astype(int)
    y_proba = np.asarray(y_proba, dtype=float)
    y_pred = (y_proba >= threshold).astype(int)
    single_class = len(np.unique(y_true)) < 2
    out = _nan_metric_map()
    try:
        out['roc_auc'] = float('nan') if single_class else float(roc_auc_score(y_true, y_proba))
    except Exception:
        out['roc_auc'] = float('nan')
    try:
        out['pr_auc'] = float(average_precision_score(y_true, y_proba)) if not single_class else float('nan')
    except Exception:
        out['pr_auc'] = float('nan')
    out['f1'] = float(f1_score(y_true, y_pred, zero_division=0))
    out['f2'] = float(fbeta_score(y_true, y_pred, beta=2, zero_division=0))
    out['precision'] = float(precision_score(y_true, y_pred, zero_division=0))
    out['recall'] = float(recall_score(y_true, y_pred, zero_division=0))
    out['accuracy'] = float(accuracy_score(y_true, y_pred))
    try:
        out['mcc'] = float(matthews_corrcoef(y_true, y_pred))
    except Exception:
        out['mcc'] = 0.0
    try:
        out['log_loss'] = float(log_loss(y_true, np.clip(y_proba, 1e-7, 1 - 1e-7), labels=[0, 1]))
    except Exception:
        out['log_loss'] = float('nan')
    try:
        out['brier'] = float(brier_score_loss(y_true, y_proba))
    except Exception:
        out['brier'] = float('nan')
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
) -> Dict[str, Any]:
    """Cross-validate one config and also fit on full train -> valid/train metrics.

    ``X_test`` here is the modeling validation holdout (not the locked outer test).
    Returns a trial dict with cv (mean+std per metric), train, test metric maps.
    """
    task = _normalize_task(task)
    t0 = time.time()

    skf = _make_cv_splitter(task, cv_folds)
    fold_metrics: List[Dict[str, float]] = []
    for tr_idx, va_idx in skf.split(X_train, y_train):
        adapter = fit_booster(
            algorithm,
            X_train.iloc[tr_idx], y_train.iloc[tr_idx],
            X_train.iloc[va_idx], y_train.iloc[va_idx],
            config, task=task, nthread=nthread,
            scale_pos_weight=scale_pos_weight,
            early_stopping_rounds=early_stopping_rounds,
        )
        proba = adapter.predict_proba(X_train.iloc[va_idx])
        fold_metrics.append(_compute_metrics(y_train.iloc[va_idx].values, proba, threshold, task=task))

    cv: Dict[str, Dict[str, float]] = {}
    for m in METRIC_NAMES:
        vals = np.array([fm[m] for fm in fold_metrics], dtype=float)
        vals = vals[np.isfinite(vals)]
        if len(vals):
            cv[m] = {'mean': float(np.mean(vals)), 'std': float(np.std(vals))}
        else:
            cv[m] = {'mean': float('nan'), 'std': float('nan')}

    # Full-fit on train with early stopping on the modeling validation holdout.
    full = fit_booster(
        algorithm, X_train, y_train, X_test, y_test, config,
        task=task, nthread=nthread, scale_pos_weight=scale_pos_weight,
        early_stopping_rounds=early_stopping_rounds,
    )
    train_metrics = _compute_metrics(y_train.values, full.predict_proba(X_train), threshold, task=task)
    test_metrics = _compute_metrics(y_test.values, full.predict_proba(X_test), threshold, task=task)

    return {
        'params': config,
        'cv': cv,
        'train': train_metrics,
        'test': test_metrics,
        'best_iteration': int(getattr(full, 'best_iteration', 0) or 0),
        'fit_time': round(time.time() - t0, 3),
        'algorithm': algorithm,
    }


def _evaluate_cv_only(
    X_train: pd.DataFrame, y_train: pd.Series,
    config: Dict[str, Any], cv_folds: int, has_cat: bool,
    nthread: int, threshold: float, metric: str,
    scale_pos_weight: Optional[float] = None,
    early_stopping_rounds: int = 50,
    task: str = 'classification',
    algorithm: str = 'xgboost',
) -> Tuple[float, float, float, float]:
    """Lightweight CV used for validation curves: returns
    (train_mean, train_std, cv_mean, cv_std) for a single ``metric``."""
    task = _normalize_task(task)
    skf = _make_cv_splitter(task, cv_folds)
    tr_scores, cv_scores = [], []
    for tr_idx, va_idx in skf.split(X_train, y_train):
        adapter = fit_booster(
            algorithm,
            X_train.iloc[tr_idx], y_train.iloc[tr_idx],
            X_train.iloc[va_idx], y_train.iloc[va_idx],
            config, task=task, nthread=nthread,
            scale_pos_weight=scale_pos_weight,
            early_stopping_rounds=early_stopping_rounds,
        )
        tr_scores.append(
            _compute_metrics(
                y_train.iloc[tr_idx].values, adapter.predict_proba(X_train.iloc[tr_idx]),
                threshold, task=task,
            )[metric]
        )
        cv_scores.append(
            _compute_metrics(
                y_train.iloc[va_idx].values, adapter.predict_proba(X_train.iloc[va_idx]),
                threshold, task=task,
            )[metric]
        )
    tr_scores = np.array([s for s in tr_scores if np.isfinite(s)], dtype=float)
    cv_scores = np.array([s for s in cv_scores if np.isfinite(s)], dtype=float)
    return (
        float(np.mean(tr_scores)) if len(tr_scores) else float('nan'),
        float(np.std(tr_scores)) if len(tr_scores) else 0.0,
        float(np.mean(cv_scores)) if len(cv_scores) else float('nan'),
        float(np.std(cv_scores)) if len(cv_scores) else 0.0,
    )


def _best_trial_for_metric(trials: List[Dict[str, Any]], metric: str) -> Optional[Dict[str, Any]]:
    direction = METRIC_DIRECTION.get(metric, 1)
    best, best_val = None, None
    for t in trials:
        v = t['cv'].get(metric, {}).get('mean')
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
        scores = direction * np.where(np.isfinite(cv_mean), cv_mean, -np.inf)
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
            if gap is not None and gap > 0.05:
                extra = (f" Train-CV gap is large (~{gap:.3f}); the higher end overfits, "
                         f"so narrowing here also reduces variance.")
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
    primary_metric: str = 'roc_auc',
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
    task = _normalize_task(task)
    algorithm = (algorithm or 'xgboost').strip().lower()
    space, space_warnings = validate_param_space(param_space)
    fixed = {**DEFAULT_FIXED_PARAMS, **(fixed_params or {})}
    if primary_metric not in METRIC_DIRECTION:
        primary_metric = 'r2' if task == 'regression' else 'roc_auc'
    elif task == 'regression' and primary_metric not in REGRESSION_METRICS:
        primary_metric = 'r2'
    elif task != 'regression' and primary_metric in REGRESSION_METRICS:
        primary_metric = 'roc_auc'

    # Restrict to the SFS-selected features when supplied.
    if features:
        valid = [f for f in features if f in X_train.columns]
        if valid:
            X_train, X_test = X_train[valid], X_test[valid]

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
        'holdout_role': 'validation',  # X_test arg is modeling valid, not locked outer test
        'feature_count': int(X_train.shape[1]),
        'features': list(X_train.columns),
        'trials': [],
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

    def evaluate_batch(cfgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Cross-validate a batch of configs in parallel; updates progress."""
        out: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, n_jobs)) as pool:
            futures = {
                pool.submit(
                    _evaluate_config, X_train, y_train, X_test, y_test,
                    cfg, cv_folds, has_cat, nthread, threshold,
                    scale_pos_weight, early_stopping_rounds, task, algorithm,
                ): i
                for i, cfg in enumerate(cfgs)
            }
            for fut in as_completed(futures):
                if is_stop():
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    out.append(fut.result())
                except Exception as trial_err:
                    print(f"[Hyperparam] trial failed: {trial_err}")
                done_units[0] += 1
                done = len(trials) + len(out)
                step = max(1, n_search // 20)
                if done % step == 0 or done >= n_search:
                    best = _best_trial_for_metric(trials + out, primary_metric)
                    cur = best['cv'][primary_metric]['mean'] if best else None
                    emit(f'{method.capitalize()} search: {done}/{n_search} configs evaluated',
                         {'completed_trials': done,
                          'current_best': {'metric': primary_metric, 'cv_mean': cur}})
        return out

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
            result = _evaluate_config(
                X_train, y_train, X_test, y_test, cfg, cv_folds, has_cat,
                nthread, threshold, scale_pos_weight, early_stopping_rounds, task,
                algorithm,
            )
            trials.append(result)
            done_units[0] += 1
            mean = result['cv'].get(primary_metric, {}).get('mean')
            emit(
                f'{label}: {len(trials)}/{n_iter} trials',
                {'completed_trials': len(trials),
                 'current_best': {'metric': primary_metric, 'cv_mean': mean}},
            )
            if mean is None or not np.isfinite(mean):
                return float('-inf') if direction > 0 else float('inf')
            return float(mean)

        study.optimize(_objective, n_trials=int(n_iter), n_jobs=1, catch=(Exception,))
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

        if not trials:
            results['status'] = 'stopped' if is_stop() else 'error'
            if results['status'] == 'error':
                results['error'] = 'No trials completed successfully'
            return results

        # ---------- Best metric "space points" ----------
        for m in METRIC_NAMES:
            bt = _best_trial_for_metric(trials, m)
            if bt:
                results['best_points'][m] = {
                    'params': bt['params'],
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
        base_config = dict(best_trial['params']) if best_trial else dict(fixed)
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
                        scale_pos_weight, early_stopping_rounds, task, algorithm,
                    ): idx
                    for idx, cfg in enumerate(point_configs)
                }
                for fut in as_completed(futs):
                    idx = futs[fut]
                    try:
                        point_results[idx] = fut.result()
                    except Exception as cv_err:
                        print(f"[Hyperparam] curve point failed ({param}): {cv_err}")
                        point_results[idx] = (float('nan'), 0.0, float('nan'), 0.0)
                    done_units[0] += 1

            ordered = [point_results[i] for i in range(len(grid))]
            tr_mean = [r[0] for r in ordered]
            tr_std = [r[1] for r in ordered]
            cv_mean = [r[2] for r in ordered]
            cv_std = [r[3] for r in ordered]
            direction = METRIC_DIRECTION.get(primary_metric, 1)
            finite_cv = [(i, c) for i, c in enumerate(cv_mean) if np.isfinite(c)]
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
            })
            emit(f'{param} curve complete')

        results['validation_curves'] = curves
        results['guidance'] = _build_guidance(curves, primary_metric)

        results['status'] = 'stopped' if is_stop() else 'completed'
        emit('Hyperparameter tuning stopped by user' if is_stop()
             else 'Hyperparameter tuning completed')
        return results

    except Exception as e:
        results['status'] = 'error'
        results['error'] = str(e)
        if status_callback:
            status_callback({'message': f'Hyperparameter tuning failed: {e}',
                             'progress': 0.0, 'status': 'error', 'error': str(e)})
        print(f"[Hyperparam] Error: {e}")
        import traceback
        traceback.print_exc()
        return results
