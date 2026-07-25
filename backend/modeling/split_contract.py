"""Canonical train/valid/test split contract for the boosting pipeline.

Preprocessing persists the outer train/test indices (random or OOT).
Modeling further splits the outer-train portion into fit/valid for early
stopping, and never uses the outer test until Evaluation.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from django.conf import settings
from sklearn.model_selection import train_test_split


SPLIT_DIRNAME = 'splits'
SPLIT_VERSION = 1


def split_path(file_id: int) -> str:
    return os.path.join(settings.MEDIA_ROOT, SPLIT_DIRNAME, f'{file_id}_split.json')


def _to_index_list(idx) -> List[Any]:
    """Serialize a pandas Index / ndarray to a JSON-friendly list."""
    if idx is None:
        return []
    try:
        values = pd.Index(idx).tolist()
    except Exception:
        values = list(idx)
    out: List[Any] = []
    for v in values:
        if isinstance(v, (np.integer,)):
            out.append(int(v))
        elif isinstance(v, (np.floating,)):
            out.append(float(v))
        else:
            # Preserve string labels; cast numpy scalars already handled
            try:
                if pd.isna(v):
                    continue
            except Exception:
                pass
            out.append(v if isinstance(v, (str, int, float, bool)) else str(v))
    return out


def save_split_artifact(
    file_id: int,
    train_idx,
    test_idx,
    split_config: Optional[Dict[str, Any]] = None,
    *,
    frame_index: Optional[Sequence] = None,
    source: str = 'preprocessing',
) -> Dict[str, Any]:
    """Persist outer train/test indices for downstream modeling/evaluation."""
    artifact: Dict[str, Any] = {
        'version': SPLIT_VERSION,
        'file_id': int(file_id),
        'source': source,
        'strategy': (split_config or {}).get('strategy', 'random'),
        'split_config': split_config or {'strategy': 'random'},
        'train_idx': _to_index_list(train_idx),
        'test_idx': _to_index_list(test_idx),
        'n_train': int(len(train_idx)) if train_idx is not None else 0,
        'n_test': int(len(test_idx)) if test_idx is not None else 0,
    }
    if frame_index is not None:
        artifact['frame_index'] = _to_index_list(frame_index)

    out_dir = os.path.join(settings.MEDIA_ROOT, SPLIT_DIRNAME)
    os.makedirs(out_dir, exist_ok=True)
    path = split_path(file_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(artifact, f)
    artifact['path'] = os.path.relpath(path, settings.MEDIA_ROOT)
    return artifact


def load_split_artifact(file_id: int) -> Optional[Dict[str, Any]]:
    path = split_path(file_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def _align_indices(df: pd.DataFrame, idx_list: Sequence) -> pd.Index:
    """Return the subset of idx_list that exists in df.index (order preserved)."""
    if not idx_list:
        return pd.Index([])
    # Prefer label-based membership (works for RangeIndex and custom labels)
    present = [i for i in idx_list if i in df.index]
    if present:
        return pd.Index(present)
    # Fallback: treat as positional if labels failed (e.g. reindex after reset)
    try:
        pos = [int(i) for i in idx_list if isinstance(i, (int, np.integer)) or str(i).isdigit()]
        pos = [p for p in pos if 0 <= p < len(df)]
        if pos:
            return df.index[pos]
    except Exception:
        pass
    return pd.Index([])


def resolve_modeling_splits(
    df: pd.DataFrame,
    y: pd.Series,
    file_id: Optional[int] = None,
    *,
    valid_size: float = 0.2,
    random_state: int = 42,
) -> Tuple[pd.Index, pd.Index, pd.Index, Dict[str, Any]]:
    """Return (train_idx, valid_idx, test_idx, meta).

    Prefer the preprocessing outer split when available. Outer test is locked;
    validation is carved from the outer-train portion for early stopping.
    """
    meta: Dict[str, Any] = {
        'source': 'fallback_stratified',
        'strategy': 'random',
        'used_preprocessing_split': False,
        'warnings': [],
    }

    artifact = load_split_artifact(file_id) if file_id is not None else None
    outer_train = pd.Index([])
    outer_test = pd.Index([])

    if artifact:
        outer_train = _align_indices(df, artifact.get('train_idx') or [])
        outer_test = _align_indices(df, artifact.get('test_idx') or [])
        meta['strategy'] = artifact.get('strategy', 'random')
        meta['split_config'] = artifact.get('split_config')
        if len(outer_train) >= 5 and len(outer_test) >= 1:
            meta['source'] = 'preprocessing'
            meta['used_preprocessing_split'] = True
        else:
            meta['warnings'].append(
                'Preprocessing split artifact present but indices could not be aligned; '
                'falling back to stratified split.'
            )
            outer_train = pd.Index([])
            outer_test = pd.Index([])

    if len(outer_train) < 5:
        # Full-frame stratified: 64/16/20 ≈ train/valid/test (test=20%, then valid=20% of remainder)
        try:
            idx_all = df.index
            y_aligned = y.loc[idx_all]
            tr_va_idx, test_idx, y_tr_va, _y_te = train_test_split(
                idx_all, y_aligned, test_size=0.2, random_state=random_state, stratify=y_aligned,
            )
            train_idx, valid_idx, _, _ = train_test_split(
                tr_va_idx, y_tr_va, test_size=valid_size, random_state=random_state, stratify=y_tr_va,
            )
            meta['source'] = 'fallback_stratified'
            meta['used_preprocessing_split'] = False
            return pd.Index(train_idx), pd.Index(valid_idx), pd.Index(test_idx), meta
        except Exception as e:
            meta['warnings'].append(f'Stratified fallback failed ({e}); using random proportions.')
            rng = np.random.RandomState(random_state)
            mask = rng.rand(len(df))
            test_mask = mask >= 0.8
            valid_mask = (mask >= 0.64) & (mask < 0.8)
            train_mask = mask < 0.64
            return (
                df.index[train_mask],
                df.index[valid_mask],
                df.index[test_mask],
                meta,
            )

    # Carve validation from outer train
    y_outer = y.loc[outer_train]
    try:
        if y_outer.nunique(dropna=True) >= 2 and len(outer_train) >= 5:
            train_idx, valid_idx = train_test_split(
                outer_train, test_size=valid_size, random_state=random_state, stratify=y_outer,
            )
        else:
            train_idx, valid_idx = train_test_split(
                outer_train, test_size=valid_size, random_state=random_state,
            )
    except Exception:
        train_idx, valid_idx = train_test_split(
            outer_train, test_size=valid_size, random_state=random_state,
        )

    return pd.Index(train_idx), pd.Index(valid_idx), pd.Index(outer_test), meta


def fit_numeric_imputer(X_train: pd.DataFrame) -> Dict[str, float]:
    """Fit mean impute values on train only."""
    means: Dict[str, float] = {}
    num_cols = X_train.select_dtypes(include=['number']).columns
    for c in num_cols:
        m = X_train[c].mean(skipna=True)
        means[str(c)] = float(m) if pd.notna(m) else 0.0
    return means


def transform_numeric_impute(X: pd.DataFrame, means: Dict[str, float]) -> pd.DataFrame:
    """Apply train-fitted means; leave categorical NaNs for native boosting."""
    out = X.copy()
    for c, m in means.items():
        if c in out.columns and pd.api.types.is_numeric_dtype(out[c]):
            out[c] = out[c].fillna(m)
    return out


SUPPORTED_BOOSTING_ALGORITHMS = frozenset({'xgboost', 'lightgbm', 'catboost'})


def normalize_boosting_algorithm(algorithm: Optional[str]) -> Tuple[str, Optional[str]]:
    """Return (resolved_algorithm, error_message).

    All three boosters are supported via BoosterAdapter when their packages
    are installed; missing deps surface as an actionable ImportError message.
    """
    algo = (algorithm or 'xgboost').strip().lower()
    if algo in ('logistic_regression', 'logit'):
        return algo, (
            f'{algo} belongs to the logit pipeline, not boosting. '
            'Select xgboost, lightgbm, or catboost for the boosting pipeline.'
        )
    if algo not in SUPPORTED_BOOSTING_ALGORITHMS:
        return 'xgboost', (
            f'Unsupported algorithm "{algorithm}". '
            f'Boosting supports: {sorted(SUPPORTED_BOOSTING_ALGORITHMS)}.'
        )
    try:
        from modeling.booster_adapters import available_boosting_algorithms
        avail = available_boosting_algorithms()
        if not avail.get(algo):
            installed = [k for k, v in avail.items() if v]
            return algo, (
                f'{algo} is not installed in this environment. '
                f'Available boosters: {installed or ["none"]}.'
            )
    except Exception:
        if algo != 'xgboost':
            return algo, f'Unable to verify {algo} availability.'
    return algo, None
