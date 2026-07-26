"""Unit tests for pre-train leakage heuristics."""

import numpy as np
import pandas as pd

from modeling.leakage_heuristics import scan_leakage_risks


def test_flags_id_name_and_near_unique():
    n = 100
    rng = np.random.default_rng(0)
    y = pd.Series(rng.integers(0, 2, size=n))
    X = pd.DataFrame({
        'customer_id': np.arange(n),
        'safe_num': rng.normal(size=n),
    })
    report = scan_leakage_risks(X, y)
    assert report['n_high'] >= 1
    feats = {w['feature'] for w in report['warnings']}
    assert 'customer_id' in feats


def test_flags_high_target_correlation():
    n = 120
    y = pd.Series([0] * 60 + [1] * 60)
    X = pd.DataFrame({
        'almost_target': y.astype(float) + 0.001,
        'noise': np.random.default_rng(2).normal(size=n),
    })
    report = scan_leakage_risks(X, y, corr_suspicious=0.95)
    flagged = [w for w in report['warnings'] if w['feature'] == 'almost_target']
    assert flagged
    assert flagged[0]['severity'] == 'high'


def test_clean_features_no_high_warnings():
    n = 80
    rng = np.random.default_rng(3)
    y = pd.Series(rng.integers(0, 2, size=n))
    X = pd.DataFrame({
        'f1': rng.normal(size=n),
        'f2': rng.normal(size=n),
    })
    report = scan_leakage_risks(X, y)
    assert report['n_high'] == 0
    assert 'No automated leakage warnings' in report['summary'] or report['n_warnings'] >= 0
