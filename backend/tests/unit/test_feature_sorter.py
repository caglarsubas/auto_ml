"""Unit tests for SFS feature sorter (combined_score ordering)."""

import json
import os
import tempfile

from modeling.feature_sorter import (
    load_combined_score_ranking,
    order_features_by_combined_score,
    resolve_sorted_initial_features,
)


def test_order_features_by_combined_score_basic():
    cols = ['c', 'a', 'b', 'd']
    ranking = [('a', 0.9), ('b', 0.5), ('z', 0.1)]  # z not in cols
    out = order_features_by_combined_score(cols, ranking)
    assert out[:2] == ['a', 'b']
    assert set(out) == set(cols)
    assert out.index('a') < out.index('c')


def test_order_features_top_k():
    cols = ['a', 'b', 'c']
    ranking = [('a', 1.0), ('b', 0.5), ('c', 0.1)]
    assert order_features_by_combined_score(cols, ranking, top_k=2) == ['a', 'b']


def test_resolve_from_modeling_status():
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, 'modeling'))
        status = {
            'model': {
                'selected_features': [
                    {'feature': 'f2', 'combined_score': 0.4},
                    {'feature': 'f1', 'combined_score': 0.9},
                    {'feature': 'f3', 'combined_score': 0.2},
                ]
            }
        }
        with open(os.path.join(td, 'modeling', '7_status.json'), 'w') as f:
            json.dump(status, f)
        ranked = load_combined_score_ranking(td, 7)
        assert [n for n, _ in ranked] == ['f1', 'f2', 'f3']
        ordered, meta = resolve_sorted_initial_features(
            td, 7, ['f3', 'f1', 'f2', 'extra'],
            use_combined_score_order=True,
            candidate_top_k=2,
        )
        assert ordered == ['f1', 'f2']
        assert meta['n_ranked'] == 3
        off, _ = resolve_sorted_initial_features(
            td, 7, ['f3', 'f1'],
            use_combined_score_order=False,
            existing_initial=['f3'],
        )
        assert off == ['f3']
