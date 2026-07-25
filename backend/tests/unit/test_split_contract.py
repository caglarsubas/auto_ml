"""Unit tests for leakage-safe split contract + impute helpers."""

import json
import os

import numpy as np
import pandas as pd
import pytest
from django.conf import settings

from modeling.split_contract import (
    fit_numeric_imputer,
    load_split_artifact,
    normalize_boosting_algorithm,
    resolve_modeling_splits,
    save_split_artifact,
    transform_numeric_impute,
)


@pytest.mark.django_db
def test_save_and_load_split_artifact(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    idx = pd.RangeIndex(0, 20)
    train = idx[:15]
    test = idx[15:]
    art = save_split_artifact(99, train, test, {'strategy': 'oot', 'percent': 25})
    assert art['n_train'] == 15
    assert art['n_test'] == 5
    loaded = load_split_artifact(99)
    assert loaded is not None
    assert loaded['strategy'] == 'oot'
    assert loaded['train_idx'] == list(range(15))


@pytest.mark.django_db
def test_resolve_uses_preprocessing_split(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    rng = np.random.RandomState(0)
    n = 100
    df = pd.DataFrame({
        'a': rng.randn(n),
        'b': rng.randn(n),
    })
    y = pd.Series(rng.randint(0, 2, size=n))
    # Persist first 70 as train / last 30 as test (OOT-style)
    save_split_artifact(7, df.index[:70], df.index[70:], {'strategy': 'oot'})
    tr, va, te, meta = resolve_modeling_splits(df, y, file_id=7, valid_size=0.2)
    assert meta['used_preprocessing_split'] is True
    assert set(te.tolist()) == set(range(70, 100))
    # valid carved from outer train only
    assert set(tr).isdisjoint(set(te))
    assert set(va).isdisjoint(set(te))
    assert set(tr).union(set(va)) == set(range(70))


def test_impute_fit_on_train_only():
    X_train = pd.DataFrame({'x': [1.0, np.nan, 3.0], 'c': ['a', 'b', None]})
    X_valid = pd.DataFrame({'x': [np.nan, 10.0], 'c': ['a', None]})
    means = fit_numeric_imputer(X_train)
    assert means['x'] == pytest.approx(2.0)
    out = transform_numeric_impute(X_valid, means)
    assert out.loc[0, 'x'] == pytest.approx(2.0)
    assert out.loc[1, 'x'] == pytest.approx(10.0)
    # categorical null preserved
    assert pd.isna(out.loc[1, 'c'])


def test_normalize_boosting_algorithm_accepts_xgboost():
    algo2, err2 = normalize_boosting_algorithm('xgboost')
    assert algo2 == 'xgboost'
    assert err2 is None
    # lightgbm/catboost succeed when installed, else return an install error (not silent XGB)
    algo, err = normalize_boosting_algorithm('lightgbm')
    assert algo == 'lightgbm'
    # err is None if importable, else an actionable message
    if err is not None:
        assert 'not installed' in err.lower() or 'unable' in err.lower()
