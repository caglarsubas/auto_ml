"""Train-fit / transform-apply contract for the Data Purifier.

Structural hygiene (column/row dedup) runs on the full frame.
All *learned* decisions (variance, correlation, missingness, sparsity,
clip bounds, rare-category merges) are fit on the outer-train partition
only, then applied identically to train and holdout rows.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from django.conf import settings
from sklearn.model_selection import GroupShuffleSplit


PURIFIER_DIRNAME = 'purifier'
PURIFIER_VERSION = 1


def parse_split_dates(values):
    """Keep ISO year-first dates unambiguous; retain day-first legacy parsing."""
    series = values if isinstance(values, pd.Series) else pd.Series([values])
    iso = series.astype(str).str.match(r'^\d{4}-\d{2}-\d{2}(?:$|[ T])')
    parsed = pd.to_datetime(series, errors='coerce', format='mixed', dayfirst=True, utc=True)
    if iso.any():
        parsed.loc[iso] = pd.to_datetime(series.loc[iso], errors='coerce', format='ISO8601', utc=True)
    return parsed


def purifier_path(file_id: int) -> str:
    return os.path.join(settings.MEDIA_ROOT, PURIFIER_DIRNAME, f'{file_id}_purifier.json')


def build_outer_split_indices(
    frame: pd.DataFrame,
    split: Optional[dict] = None,
) -> Tuple[pd.Index, pd.Index, Dict[str, Any]]:
    """Return (train_idx, test_idx, meta) for the current frame index."""
    meta: Dict[str, Any] = {
        'strategy': (split or {}).get('strategy', 'random') if isinstance(split, dict) else 'random',
        'fallback': False,
    }
    strategy = (split or {}).get('strategy', 'random')
    if strategy == 'oot':
        date_col = split.get('date_column')
        if not date_col or date_col not in frame:
            raise ValueError('Out-of-time validation requires an existing date_column; random fallback is prohibited.')
        dates = parse_split_dates(frame[date_col])
        if dates.isna().any():
            raise ValueError('Out-of-time validation requires a valid timestamp for every eligible row.')
        if split.get('percent') is not None:
            percent = float(split['percent'])
            if not 0 < percent < 100:
                raise ValueError('Out-of-time holdout percentage must be between zero and 100.')
            ordered = dates.sort_values(kind='mergesort').index
            position = int(len(ordered) * (1 - percent / 100))
            if not 0 < position < len(ordered):
                raise ValueError('Out-of-time split leaves an empty partition.')
            boundary = dates.loc[ordered[position]]
            train, test = dates.index[dates < boundary], dates.index[dates >= boundary]
        elif split.get('cutoff'):
            cutoff = parse_split_dates(split['cutoff']).iloc[0]
            if pd.isna(cutoff):
                raise ValueError('The declared temporal cutoff is not a valid timestamp.')
            train, test = dates.index[dates <= cutoff], dates.index[dates > cutoff]
        else:
            raise ValueError('Declare an out-of-time cutoff or holdout percentage.')
        if not len(train) or not len(test):
            raise ValueError('Out-of-time split leaves an empty partition.')
        return train, test, meta
    if strategy == 'group' or (split or {}).get('group_column'):
        column = (split or {}).get('group_column')
        if not column or column not in frame or frame[column].isna().any():
            raise ValueError('Group validation requires a complete group_column.')
        fraction = float((split or {}).get('percent', 25)) / 100
        a, b = next(GroupShuffleSplit(n_splits=1, test_size=fraction, random_state=42).split(frame, groups=frame[column]))
        meta['strategy'] = 'group'
        return frame.index[a], frame.index[b], meta
    if strategy != 'random':
        raise ValueError(f'Unsupported outer validation strategy: {strategy}')

    train_ratio = 0.75
    if isinstance(split, dict) and split.get('percent') is not None:
        try:
            pctf = float(split['percent'])
            if 0 < pctf < 100:
                train_ratio = 1.0 - pctf / 100.0
        except Exception:
            pass
    rng = np.random.RandomState(42)
    m = rng.rand(len(frame)) < train_ratio
    meta['strategy'] = 'random' if not meta.get('fallback') else meta.get('strategy', 'random')
    if meta.get('fallback'):
        meta['strategy'] = 'random'
    return frame.index[m], frame.index[~m], meta


def resolve_fit_index(
    frame: pd.DataFrame,
    split: Optional[dict] = None,
    train_idx: Optional[Sequence] = None,
) -> Tuple[pd.Index, Dict[str, Any]]:
    """Choose the row index used to *learn* purifier statistics.

    When ``split`` is provided (or an explicit ``train_idx``), fit on the
    outer-train partition. Otherwise fit on the full frame (unit-test /
    legacy path).
    """
    meta: Dict[str, Any] = {'fit_scope': 'full_frame', 'n_fit': int(len(frame))}
    if train_idx is not None:
        idx = pd.Index([i for i in train_idx if i in frame.index])
        if len(idx) != len(train_idx) or len(idx) < 2:
            raise ValueError('Explicit purifier fit rows are missing or insufficient; full-frame fitting is prohibited.')
        if len(idx) >= 2:
            meta['fit_scope'] = 'outer_train'
            meta['n_fit'] = int(len(idx))
            return idx, meta
    if isinstance(split, dict) and split:
        tr, _te, split_meta = build_outer_split_indices(frame, split)
        if len(tr) < 2:
            raise ValueError('Declared purifier split leaves insufficient fit rows.')
        if len(tr) >= 2:
            meta['fit_scope'] = 'outer_train'
            meta['n_fit'] = int(len(tr))
            meta['split_strategy'] = split_meta.get('strategy')
            return tr, meta
    return frame.index, meta


def remap_indices_to_positions(
    frame: pd.DataFrame,
    train_idx,
    test_idx,
) -> Tuple[pd.DataFrame, list, list]:
    """Reset to RangeIndex and convert label indices to positions for CSV artifacts."""
    pos_map = {label: i for i, label in enumerate(frame.index)}
    train_pos = [pos_map[i] for i in pd.Index(train_idx) if i in pos_map]
    test_pos = [pos_map[i] for i in pd.Index(test_idx) if i in pos_map]
    out = frame.reset_index(drop=True)
    return out, train_pos, test_pos


def save_purifier_artifact(file_id: int, artifact: Dict[str, Any]) -> Dict[str, Any]:
    out_dir = os.path.join(settings.MEDIA_ROOT, PURIFIER_DIRNAME)
    os.makedirs(out_dir, exist_ok=True)
    path = purifier_path(file_id)
    rel = os.path.relpath(path, settings.MEDIA_ROOT)
    payload = {
        'version': PURIFIER_VERSION,
        'file_id': int(file_id),
        'path': rel,
        **artifact,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, default=str)
    return payload


def load_purifier_artifact(file_id: int) -> Optional[Dict[str, Any]]:
    path = purifier_path(file_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        data.setdefault('path', os.path.relpath(path, settings.MEDIA_ROOT))
        return data
    except Exception:
        return None
