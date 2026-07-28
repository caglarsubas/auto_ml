"""Unit tests for logit / scorecard / anomaly alternate modeling adapters."""

import numpy as np
import pandas as pd
import pytest

from modeling.alt_pipelines import (
    SklearnModelAdapter,
    coeffs_to_score_points,
    evaluate_anomaly_scores,
    fit_woe_maps,
    get_alt_adapter,
    is_alt_algorithm,
    normalize_alt_algorithm,
    transform_woe,
)


def _toy_cls(n=200, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({
        'n1': rng.normal(0, 1, n),
        'n2': rng.normal(0, 1, n),
        'c1': rng.choice(['a', 'b', 'c'], n),
    })
    y = pd.Series(((X['n1'] + (X['c1'] == 'a').astype(float)) > 0).astype(int))
    return X, y


def test_normalize_alt_aliases():
    assert normalize_alt_algorithm('logit')[0] == 'logistic_regression'
    assert normalize_alt_algorithm('credit-scoring')[0] == 'scorecard'
    assert normalize_alt_algorithm('anomaly')[0] == 'isolation_forest'
    assert is_alt_algorithm('xgboost') is False
    assert is_alt_algorithm('scorecard') is True


def test_logit_adapter_train_predict(tmp_path):
    X, y = _toy_cls()
    tr, va = X.iloc[:140], X.iloc[140:]
    yt, yv = y.iloc[:140], y.iloc[140:]
    adapter = get_alt_adapter('logistic_regression')
    adapter.train(tr, yt, va, yv, params={'C': 1.0, 'max_iter': 200})
    proba = adapter.predict_proba(va)
    assert len(proba) == len(va)
    assert np.all((proba >= 0) & (proba <= 1))
    path = tmp_path / 'logit.joblib'
    adapter.save(str(path))
    loaded = SklearnModelAdapter.load(str(path))
    p2 = loaded.predict_proba(va)
    assert np.allclose(proba, p2, atol=1e-6)
    assert adapter.gain_importance()


def test_scorecard_woe_and_points():
    X, y = _toy_cls(n=300)
    maps, Xw = fit_woe_maps(X, y)
    assert maps
    assert Xw.shape[0] == len(X)
    Xw2 = transform_woe(X, maps)
    assert list(Xw2.columns) == list(Xw.columns)
    pts = coeffs_to_score_points(['f1', 'f2'], [0.5, -0.2])
    assert pts[0]['points_per_woe'] < 0  # positive coef → lower score contribution
    adapter = get_alt_adapter('scorecard')
    adapter.train(X.iloc[:200], y.iloc[:200], X.iloc[200:], y.iloc[200:])
    assert adapter.iv_table
    assert adapter.score_points
    scores = adapter.predict_scorecard_scores(X.iloc[200:])
    assert len(scores) == 100


def test_isolation_forest_adapter():
    X, y = _toy_cls(n=250)
    adapter = get_alt_adapter('isolation_forest')
    adapter.train(X.iloc[:180], y.iloc[:180], X.iloc[180:], y.iloc[180:])
    scores = adapter.predict_proba(X.iloc[180:])
    assert len(scores) == 70
    metrics = evaluate_anomaly_scores(y.iloc[180:], scores)
    assert metrics['task'] == 'anomaly'
    assert metrics.get('roc_auc') is None or np.isfinite(metrics['roc_auc'])
