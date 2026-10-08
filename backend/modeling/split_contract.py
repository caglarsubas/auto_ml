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
from sklearn.model_selection import GroupShuffleSplit, train_test_split


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
            raise ValueError('Split artifact must be a JSON object.')
        return data
    except (OSError, ValueError) as error:
        raise ValueError('Stored split artifact is unreadable; repair it before execution.') from error


def _align_indices(df: pd.DataFrame, idx_list: Sequence) -> pd.Index:
    """Resolve exact row labels; never substitute positions or a partial subset."""
    if not idx_list:
        return pd.Index([])
    if len(set(idx_list)) != len(idx_list) or any(i not in df.index for i in idx_list):
        raise ValueError('Stored split rows do not align exactly with this dataset. Recreate the split.')
    return pd.Index(idx_list)


def resolve_modeling_splits(
    df: pd.DataFrame,
    y: pd.Series,
    file_id: Optional[int] = None,
    *,
    valid_size: float = 0.2,
    random_state: int = 42,
    task: str = 'classification',
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

    if not df.index.is_unique or len(df) < 8 or not 0 < valid_size < 1:
        raise ValueError('Validation requires unique row IDs, at least eight rows and a valid validation fraction.')
    if not y.index.equals(df.index) or y.isna().any():
        raise ValueError('Labels must align exactly with the split frame and contain no missing outcomes.')
    if artifact:
        outer_train = _align_indices(df, artifact.get('train_idx') or [])
        outer_test = _align_indices(df, artifact.get('test_idx') or [])
        meta['strategy'] = artifact.get('strategy', 'random')
        meta['split_config'] = artifact.get('split_config')
        if len(outer_train) >= 5 and len(outer_test) >= 1 and outer_train.intersection(outer_test).empty:
            meta['source'] = 'preprocessing'
            meta['used_preprocessing_split'] = True
        else:
            raise ValueError('Stored outer split is undersized or overlapping. Execution cannot fall back to shuffled validation.')

    if len(outer_train) < 5:
        outer_train, outer_test = _random_partition(df.index, y, 0.2, random_state, task, meta)
        meta['source'] = 'generated_random'

    # Carve validation from outer train
    config = meta.get('split_config') or {}
    group_column = config.get('group_column')
    groups = None
    if group_column:
        if group_column not in df or df[group_column].isna().any():
            raise ValueError('Declared group_column is absent or contains missing identifiers.')
        groups = df[group_column]
        if set(groups.loc[outer_train]).intersection(groups.loc[outer_test]):
            raise ValueError('Entities overlap the declared outer partitions. Recreate a group-disjoint split.')
    if meta['strategy'] == 'oot':
        date_column = config.get('date_column')
        if date_column:
            if date_column not in df:
                raise ValueError('Declared date_column is absent from the split frame.')
            dates = pd.to_datetime(df[date_column], errors='coerce', utc=True)
            if dates.isna().any():
                raise ValueError('Temporal validation requires a valid date for every row.')
            outer_train = dates.loc[outer_train].sort_values(kind='mergesort').index
            if dates.loc[outer_train].max() >= dates.loc[outer_test].min():
                raise ValueError('Temporal outer partitions overlap or share a boundary timestamp.')
            cut = max(1, int(len(outer_train) * (1 - valid_size)))
            boundary = dates.loc[outer_train[cut]]
            train_idx = outer_train[dates.loc[outer_train] < boundary]
            valid_idx = outer_train[dates.loc[outer_train] >= boundary]
            end_column = config.get('label_end_column')
            if end_column:
                if end_column not in df:
                    raise ValueError('Declared label_end_column is absent.')
                ends = pd.to_datetime(df[end_column], errors='coerce', utc=True)
                if ends.isna().any() or (ends < dates).any():
                    raise ValueError('Label windows require valid ends at or after prediction time.')
                train_idx = train_idx[ends.loc[train_idx] < boundary]
                valid_idx = valid_idx[ends.loc[valid_idx] < dates.loc[outer_test].min()]
        else:
            # Historical artifacts preserve ordered membership, but cannot prove
            # that this order corresponds to dates; never shuffle it.
            cut = max(1, int(len(outer_train) * (1 - valid_size)))
            train_idx, valid_idx = outer_train[:cut], outer_train[cut:]
            meta['warnings'].append('Legacy ordered split lacks date evidence; chronology is unverified.')
        if groups is not None:
            train_idx = train_idx[~groups.loc[train_idx].isin(groups.loc[valid_idx])]
    elif meta['strategy'] in ('random', 'group'):
        if groups is not None:
            a, b = next(GroupShuffleSplit(n_splits=1, test_size=valid_size, random_state=random_state).split(np.zeros(len(outer_train)), groups=groups.loc[outer_train]))
            train_idx, valid_idx = outer_train[a], outer_train[b]
        else:
            train_idx, valid_idx = _random_partition(outer_train, y.loc[outer_train], valid_size, random_state, task, meta)
    else:
        raise ValueError(f'Unsupported validation strategy: {meta["strategy"]}')
    if len(train_idx) < 2 or len(valid_idx) < 1:
        raise ValueError('Declared validation constraints leave insufficient fit/validation rows.')
    meta['membership'] = {'train': _to_index_list(train_idx), 'valid': _to_index_list(valid_idx), 'test': _to_index_list(outer_test)}
    meta['task'] = task
    return pd.Index(train_idx), pd.Index(valid_idx), pd.Index(outer_test), meta


def _random_partition(index, labels, fraction, seed, task, meta):
    stratify = labels if task in ('classification', 'anomaly') else None
    try:
        return train_test_split(index, test_size=fraction, random_state=seed, stratify=stratify)
    except ValueError as error:
        if stratify is None:
            raise
        meta['warnings'].append(f'Random split is unstratified because class counts do not permit stratification: {error}')
        return train_test_split(index, test_size=fraction, random_state=seed)


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
