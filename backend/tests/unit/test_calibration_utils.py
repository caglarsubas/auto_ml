"""Unit tests for probability calibration helpers."""

import numpy as np

from modeling.calibration_utils import (
    apply_calibrator,
    fit_calibrator,
    load_calibrator,
    save_calibrator,
)


def test_fit_platt_on_small_valid():
    rng = np.random.default_rng(0)
    y = np.array([0] * 40 + [1] * 40)
    # Mis-scaled scores: positives tend higher but not calibrated
    proba = np.clip(0.2 + 0.5 * y + rng.normal(0, 0.08, size=y.shape), 0.01, 0.99)
    calibrator, meta = fit_calibrator(y, proba, method='platt')
    assert calibrator is not None
    assert meta['fitted'] is True
    assert meta['method'] == 'platt'
    assert meta['brier_after'] is not None
    cal = apply_calibrator(calibrator, proba)
    assert cal.shape == proba.shape
    assert np.all((cal >= 0) & (cal <= 1))


def test_fit_isotonic_auto_on_large_valid():
    rng = np.random.default_rng(1)
    n = 300
    y = rng.integers(0, 2, size=n)
    proba = np.clip(0.15 + 0.6 * y + rng.normal(0, 0.1, size=n), 0.01, 0.99)
    calibrator, meta = fit_calibrator(y, proba, method='auto')
    assert calibrator is not None
    assert meta['method'] == 'isotonic'
    assert meta['fitted'] is True


def test_insufficient_samples_skips_fit():
    calibrator, meta = fit_calibrator([0, 1, 0], [0.2, 0.8, 0.3], method='auto')
    assert calibrator is None
    assert meta['fitted'] is False
    assert 'warning' in meta


def test_save_load_roundtrip(tmp_path):
    y = np.array([0] * 50 + [1] * 50)
    proba = np.linspace(0.1, 0.9, 100)
    calibrator, _ = fit_calibrator(y, proba, method='platt')
    rel = save_calibrator(42, calibrator, str(tmp_path))
    assert rel.endswith('_calibrator.joblib')
    loaded = load_calibrator(rel, str(tmp_path))
    a = apply_calibrator(calibrator, proba[:10])
    b = apply_calibrator(loaded, proba[:10])
    np.testing.assert_allclose(a, b, rtol=1e-6)
