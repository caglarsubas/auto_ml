"""CV splitter selection for the boosting modeling path.

Priority:
1. Out-of-time → TimeSeriesSplit
2. Entity/group column available on CV rows → StratifiedGroupKFold / GroupKFold
3. Default → StratifiedKFold
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold, StratifiedKFold, TimeSeriesSplit


_ID_NAME_RE = re.compile(
    r'(^id$|_id$|^uuid$|customer.?id|account.?id|application.?id|loan.?id|'
    r'user.?id|entity.?id|group.?id|member.?id|policy.?id)',
    re.I,
)


def looks_like_group_column(name: str) -> bool:
    return bool(_ID_NAME_RE.search(str(name)))


def pick_group_column(
    df: pd.DataFrame,
    row_index: Sequence,
    candidates: Optional[Sequence[str]] = None,
    *,
    min_groups: int = 5,
) -> Tuple[Optional[str], Optional[pd.Series]]:
    """Return (column_name, group_labels aligned to row_index) or (None, None)."""
    idx = pd.Index(row_index)
    ordered: List[str] = []
    for c in candidates or []:
        if c and c not in ordered:
            ordered.append(str(c))
    for c in df.columns:
        if looks_like_group_column(c) and c not in ordered:
            ordered.append(str(c))

    for col in ordered:
        if col not in df.columns:
            continue
        try:
            series = df.loc[idx.intersection(df.index), col]
            # Align to full row_index order
            series = series.reindex(idx)
            n_groups = int(series.nunique(dropna=True))
            if n_groups >= min_groups and series.notna().mean() >= 0.9:
                return col, series
        except Exception:
            continue
    return None, None


def build_cv_splitter(
    split_meta: Optional[Dict[str, Any]],
    y_cv: pd.Series,
    groups: Optional[pd.Series] = None,
    *,
    n_splits: int = 5,
    random_state: int = 42,
):
    """Return (splitter, strategy_name, split_kwargs_hint).

    ``split_kwargs_hint`` documents how to call ``splitter.split(...)``.
    """
    strategy = (split_meta or {}).get('strategy')
    if strategy == 'oot':
        return TimeSeriesSplit(n_splits=n_splits), 'time_series', {'y': False, 'groups': False}

    if groups is not None:
        g = pd.Series(groups).reset_index(drop=True)
        n_groups = int(g.nunique(dropna=True))
        if n_groups >= n_splits:
            # Prefer stratified groups for classification-like targets
            try:
                y_arr = np.asarray(y_cv)
                if len(np.unique(y_arr[~pd.isna(y_arr)])) >= 2 and n_groups >= n_splits * 2:
                    return (
                        StratifiedGroupKFold(
                            n_splits=n_splits, shuffle=True, random_state=random_state,
                        ),
                        'stratified_group',
                        {'y': True, 'groups': True},
                    )
            except Exception:
                pass
            return GroupKFold(n_splits=n_splits), 'group', {'y': False, 'groups': True}

    return (
        StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state),
        'stratified',
        {'y': True, 'groups': False},
    )


def iter_cv_splits(splitter, X, y, groups, hint: Dict[str, bool]):
    """Yield (train_idx, valid_idx) from the splitter using the hint flags."""
    if hint.get('groups') and hint.get('y'):
        yield from splitter.split(X, y, groups)
    elif hint.get('groups'):
        yield from splitter.split(X, groups=groups)
    elif hint.get('y'):
        yield from splitter.split(X, y)
    else:
        yield from splitter.split(X)
