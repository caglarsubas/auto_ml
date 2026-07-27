"""Unit tests for multi-booster adapters + availability helpers."""

import numpy as np
import pandas as pd
import pytest

from modeling.booster_adapters import (
    available_boosting_algorithms,
    config_to_booster_params,
    fit_booster,
    get_adapter,
)
from modeling.split_contract import normalize_boosting_algorithm


def _toy_binary(n=80, seed=0):
    rng = np.random.RandomState(seed)
    X = pd.DataFrame({
        'n1': rng.randn(n),
        'n2': rng.randn(n),
        'c1': pd.Categorical(rng.choice(['a', 'b', 'c'], size=n)),
    })
    y = pd.Series((X['n1'] + rng.randn(n) * 0.1 > 0).astype(int))
    cut = int(n * 0.7)
    return X.iloc[:cut], y.iloc[:cut], X.iloc[cut:], y.iloc[cut:]


def test_normalize_accepts_three_boosters_when_installed():
    avail = available_boosting_algorithms()
    for algo, ok in avail.items():
        resolved, err = normalize_boosting_algorithm(algo)
        if ok:
            assert resolved == algo
            assert err is None
        else:
            assert err is not None


def test_xgboost_adapter_trains_and_predicts(tmp_path):
    Xtr, ytr, Xva, yva = _toy_binary()
    adapter = get_adapter('xgboost')
    adapter.train(
        Xtr, ytr, Xva, yva,
        {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'eta': 0.1, 'max_depth': 3, 'seed': 0},
        num_boost_round=40, early_stopping_rounds=10,
    )
    proba = adapter.predict_proba(Xva)
    assert len(proba) == len(Xva)
    assert np.all((proba >= 0) & (proba <= 1))
    path = tmp_path / 'm.json'
    adapter.save(str(path))
    assert path.exists()
    gains = adapter.gain_importance()
    assert isinstance(gains, list)


@pytest.mark.skipif(not available_boosting_algorithms().get('lightgbm'), reason='lightgbm not installed')
def test_lightgbm_adapter_trains(tmp_path):
    Xtr, ytr, Xva, yva = _toy_binary(seed=1)
    adapter = get_adapter('lightgbm')
    adapter.train(
        Xtr, ytr, Xva, yva,
        {'eta': 0.1, 'max_depth': 3, 'seed': 0},
        num_boost_round=40, early_stopping_rounds=10,
    )
    proba = adapter.predict_proba(Xva)
    assert len(proba) == len(Xva)
    path = tmp_path / 'm.txt'
    adapter.save(str(path))
    assert path.exists()


@pytest.mark.skipif(not available_boosting_algorithms().get('catboost'), reason='catboost not installed')
def test_catboost_adapter_trains(tmp_path):
    Xtr, ytr, Xva, yva = _toy_binary(seed=2)
    adapter = get_adapter('catboost')
    adapter.train(
        Xtr, ytr, Xva, yva,
        {'eta': 0.1, 'max_depth': 3, 'seed': 0},
        num_boost_round=40, early_stopping_rounds=10,
    )
    proba = adapter.predict_proba(Xva)
    assert len(proba) == len(Xva)
    path = tmp_path / 'm.cbm'
    adapter.save(str(path))
    assert path.exists()


def _toy_regression(n=80, seed=0):
    rng = np.random.RandomState(seed)
    X = pd.DataFrame({
        'n1': rng.randn(n),
        'n2': rng.randn(n),
        'c1': pd.Categorical(rng.choice(['a', 'b', 'c'], size=n)),
    })
    y = pd.Series(2.5 * X['n1'] + 0.5 * X['n2'] + rng.randn(n) * 0.2)
    cut = int(n * 0.7)
    return X.iloc[:cut], y.iloc[:cut], X.iloc[cut:], y.iloc[cut:]


def test_xgboost_adapter_regression(tmp_path):
    Xtr, ytr, Xva, yva = _toy_regression()
    adapter = get_adapter('xgboost')
    adapter.train(
        Xtr, ytr, Xva, yva,
        {'task': 'regression', 'eta': 0.1, 'max_depth': 3, 'seed': 0},
        num_boost_round=40, early_stopping_rounds=10,
    )
    assert adapter.task == 'regression'
    pred = adapter.predict(Xva)
    assert len(pred) == len(Xva)
    path = tmp_path / adapter.model_filename(99)
    assert 'regressor' in path.name
    adapter.save(str(path))
    assert path.exists()


def test_config_to_booster_params_shared_knobs():
    params, n = config_to_booster_params(
        {'n_estimators': 80, 'max_depth': 4, 'learning_rate': 0.05},
        task='classification', nthread=1,
    )
    assert n == 80
    assert params['eta'] == 0.05
    assert params['max_depth'] == 4
    assert params['objective'] == 'binary:logistic'


def test_fit_booster_xgboost_from_shared_config():
    Xtr, ytr, Xva, yva = _toy_binary(seed=3)
    adapter = fit_booster(
        'xgboost', Xtr, ytr, Xva, yva,
        {'n_estimators': 30, 'max_depth': 3, 'learning_rate': 0.1},
        task='classification', early_stopping_rounds=5,
    )
    proba = adapter.predict_proba(Xva)
    assert len(proba) == len(Xva)


@pytest.mark.skipif(not available_boosting_algorithms().get('lightgbm'), reason='lightgbm not installed')
def test_fit_booster_lightgbm_from_shared_config():
    Xtr, ytr, Xva, yva = _toy_binary(seed=4)
    adapter = fit_booster(
        'lightgbm', Xtr, ytr, Xva, yva,
        {'n_estimators': 30, 'max_depth': 3, 'learning_rate': 0.1},
        task='classification', early_stopping_rounds=5,
    )
    assert len(adapter.predict_proba(Xva)) == len(Xva)


@pytest.mark.skipif(not available_boosting_algorithms().get('catboost'), reason='catboost not installed')
def test_fit_booster_catboost_from_shared_config():
    Xtr, ytr, Xva, yva = _toy_binary(seed=5)
    adapter = fit_booster(
        'catboost', Xtr, ytr, Xva, yva,
        {'n_estimators': 30, 'max_depth': 3, 'learning_rate': 0.1},
        task='classification', early_stopping_rounds=5,
    )
    assert len(adapter.predict_proba(Xva)) == len(Xva)
