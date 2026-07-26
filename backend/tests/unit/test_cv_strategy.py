"""Unit tests for CV splitter selection."""

import numpy as np
import pandas as pd
import pytest

from modeling.cv_strategy import (
    build_cv_splitter,
    iter_cv_splits,
    looks_like_group_column,
    pick_group_column,
)


@pytest.mark.unit
def test_looks_like_group_column():
    assert looks_like_group_column('customer_id')
    assert looks_like_group_column('loan_id')
    assert not looks_like_group_column('income')


@pytest.mark.unit
def test_pick_group_column_prefers_excluded_id():
    df = pd.DataFrame({
        'customer_id': [1, 1, 2, 2, 3, 3, 4, 4, 5, 5],
        'x': range(10),
    })
    col, groups = pick_group_column(df, df.index, ['customer_id'], min_groups=5)
    assert col == 'customer_id'
    assert groups is not None
    assert groups.nunique() == 5


@pytest.mark.unit
def test_build_cv_splitter_oot_beats_groups():
    y = pd.Series([0, 1] * 20)
    groups = pd.Series([i // 2 for i in range(40)])
    splitter, strategy, hint = build_cv_splitter(
        {'strategy': 'oot'}, y, groups=groups, n_splits=5,
    )
    assert strategy == 'time_series'
    assert hint['groups'] is False


@pytest.mark.unit
def test_build_cv_splitter_group_when_ids_present():
    y = pd.Series([0, 1] * 20)
    groups = pd.Series([i // 4 for i in range(40)])  # 10 groups
    splitter, strategy, hint = build_cv_splitter(
        {'strategy': 'random'}, y, groups=groups, n_splits=5,
    )
    assert strategy in ('stratified_group', 'group')
    assert hint['groups'] is True
    splits = list(iter_cv_splits(splitter, np.zeros((40, 1)), y, groups.values, hint))
    assert len(splits) == 5
    # No group appears in both train and valid within a fold
    for tr, va in splits:
        g_tr = set(groups.iloc[tr])
        g_va = set(groups.iloc[va])
        assert g_tr.isdisjoint(g_va)


@pytest.mark.unit
def test_default_stratified_without_groups():
    y = pd.Series([0, 1] * 20)
    splitter, strategy, hint = build_cv_splitter({'strategy': 'random'}, y, groups=None)
    assert strategy == 'stratified'
    assert hint['y'] is True
