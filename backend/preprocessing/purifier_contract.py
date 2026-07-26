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


PURIFIER_DIRNAME = 'purifier'
PURIFIER_VERSION = 1


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
    try:
        if isinstance(split, dict) and split.get('strategy') == 'oot':
            date_col = split.get('date_column')
            ser = None
            if date_col and date_col in frame.columns:
                ser = pd.to_datetime(frame[date_col], errors='coerce', dayfirst=True)
            if ser is not None and ser.shape[0] > 0:
                pct = split.get('percent')
                if pct is not None:
                    try:
                        pctf = float(pct)
                    except Exception:
                        pctf = None
                    if pctf is not None and 0 < pctf < 100:
                        order = ser.sort_values(kind='mergesort').index
                        k = int(len(order) * (1 - pctf / 100.0))
                        k = max(0, min(len(order), k))
                        meta['strategy'] = 'oot'
                        return order[:k], order[k:], meta
                cutoff = split.get('cutoff')
                if cutoff:
                    mask_train = ser <= pd.to_datetime(cutoff, dayfirst=True)
                    meta['strategy'] = 'oot'
                    return ser.index[mask_train], ser.index[~mask_train], meta
            meta['fallback'] = True
    except Exception:
        meta['fallback'] = True

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
        if len(idx) >= 5:
            meta['fit_scope'] = 'outer_train'
            meta['n_fit'] = int(len(idx))
            return idx, meta
    if isinstance(split, dict) and split:
        tr, _te, split_meta = build_outer_split_indices(frame, split)
        if len(tr) >= 5:
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
