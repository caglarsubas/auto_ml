"""Order SFS candidate features by modeling combined_score (SHAP% × Gain%)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple


def load_combined_score_ranking(media_root: str, file_id: int) -> List[Tuple[str, float]]:
    """Return [(feature, combined_score), ...] sorted descending from modeling status."""
    path = os.path.join(media_root, 'modeling', f'{file_id}_status.json')
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            status = json.load(f)
    except Exception:
        return []
    feats = (status.get('model') or {}).get('selected_features') or []
    ranked: List[Tuple[str, float]] = []
    for row in feats:
        if not isinstance(row, dict):
            continue
        name = str(row.get('feature') or '').strip()
        if not name:
            continue
        try:
            score = float(row.get('combined_score'))
        except (TypeError, ValueError):
            score = 0.0
        ranked.append((name, score))
    ranked.sort(key=lambda x: -x[1])
    return ranked


def order_features_by_combined_score(
    columns: Sequence[str],
    ranking: Sequence[Tuple[str, float]],
    *,
    top_k: Optional[int] = None,
) -> List[str]:
    """Reorder ``columns`` by ranking; append unscored columns; optional top_k truncate."""
    col_set = {str(c) for c in columns}
    ordered: List[str] = []
    seen = set()
    for name, _score in ranking:
        if name in col_set and name not in seen:
            ordered.append(name)
            seen.add(name)
    for c in columns:
        cs = str(c)
        if cs not in seen:
            ordered.append(cs)
            seen.add(cs)
    if top_k is not None:
        try:
            k = int(top_k)
            if k > 0:
                ordered = ordered[:k]
        except (TypeError, ValueError):
            pass
    return ordered


def resolve_sorted_initial_features(
    media_root: str,
    file_id: int,
    available_columns: Sequence[str],
    *,
    use_combined_score_order: bool,
    candidate_top_k: Optional[int] = None,
    existing_initial: Optional[Sequence[str]] = None,
) -> Tuple[Optional[List[str]], Dict[str, Any]]:
    """Build initial_features list for SFS when sorter is enabled.

    If ``existing_initial`` is provided and sorter is off, return it unchanged.
    When sorter is on, ranking wins and existing_initial is ignored for order
    (caller should already have applied exclusions to available_columns).
    """
    meta: Dict[str, Any] = {
        'use_combined_score_order': bool(use_combined_score_order),
        'candidate_top_k': candidate_top_k,
        'ranking_source': None,
        'n_ranked': 0,
    }
    if not use_combined_score_order:
        if existing_initial:
            return list(existing_initial), meta
        return None, meta

    ranking = load_combined_score_ranking(media_root, file_id)
    meta['ranking_source'] = 'modeling_status.selected_features'
    meta['n_ranked'] = len(ranking)
    ordered = order_features_by_combined_score(
        available_columns, ranking, top_k=candidate_top_k,
    )
    meta['n_selected'] = len(ordered)
    return ordered, meta
