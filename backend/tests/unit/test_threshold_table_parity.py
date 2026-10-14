"""Binary threshold metrics retain the existing sklearn reference semantics."""
import warnings

import numpy as np
import pytest
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, fbeta_score,
    matthews_corrcoef, precision_score, recall_score,
)

from evaluation.eval_utils import threshold_table

pytestmark = pytest.mark.unit


def reference(y, scores, thresholds):
    rows = []
    for threshold in thresholds:
        predicted = (scores >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
        values = {
            'precision': precision_score(y, predicted, zero_division=0),
            'recall': recall_score(y, predicted, zero_division=0),
            'f1': f1_score(y, predicted, zero_division=0),
            'f2': fbeta_score(y, predicted, beta=2, zero_division=0),
            'accuracy': accuracy_score(y, predicted),
            'mcc': matthews_corrcoef(y, predicted),
        }
        rows.append({
            'threshold': threshold,
            **{key: float(value) if np.isfinite(value) else None for key, value in values.items()},
            'tp': int(tp), 'fp': int(fp), 'tn': int(tn), 'fn': int(fn),
        })
    return rows


@pytest.mark.parametrize('outcomes', [
    [0, 0, 0, 0], [1, 1, 1, 1], [0, 1, 0, 1], [1, 0, 1, 0], [0], [1],
])
@pytest.mark.parametrize('dtype', [np.int8, np.bool_, np.float64])
def test_counts_match_reference_for_ties_single_classes_and_extreme_thresholds(outcomes, dtype):
    y = np.array(outcomes, dtype=dtype)
    scores = np.array([0.0, 0.5, 0.5, 1.0][:len(y)], dtype=np.float32)
    thresholds = [1.1, 0.5, 0.0, 0.5, -0.1, 1.0]
    actual = threshold_table(y, scores, thresholds)
    for row, original in zip(actual, reference(y, scores, thresholds)):
        assert row == pytest.approx(original, abs=1e-12, rel=1e-12)


@pytest.mark.parametrize('seed,size', [(7, 19), (42, 650), (83, 10003)])
def test_randomized_binary_metrics_match_independent_reference(seed, size):
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 2, size)
    scores = rng.random(size)
    thresholds = [round(x, 2) for x in np.linspace(0.05, 0.95, 19)]
    actual = threshold_table(y, scores)
    expected = reference(y, scores, thresholds)
    assert len(actual) == len(expected)
    for row, original in zip(actual, expected):
        assert row.keys() == original.keys()
        assert row == pytest.approx(original, abs=1e-12, rel=1e-12)
        assert all(type(row[name]) is int for name in ('tp', 'fp', 'tn', 'fn'))


@pytest.mark.parametrize('y,scores', [
    (np.array([[0], [1], [0]]), np.array([0.2, 0.8, 0.5])),
    (np.array([0, 1, 0, 1]), np.array([np.nan, np.inf, -np.inf, 0.5])),
])
def test_legacy_column_and_nonfinite_score_semantics_are_preserved(y, scores):
    thresholds = [0.5, np.nan]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        actual, expected = threshold_table(y, scores, thresholds), reference(y, scores, thresholds)
    for row, original in zip(actual, expected):
        assert row == pytest.approx(original, abs=1e-12, rel=1e-12, nan_ok=True)


@pytest.mark.parametrize('y,scores', [
    (np.array([], dtype=int), np.array([])),
    (np.array([0, 1]), np.array([0.1])),
    (np.array([0, 1, 2]), np.array([0.1, 0.8, 0.4])),
    (np.array([0, np.nan]), np.array([0.1, 0.8])),
])
def test_invalid_inputs_retain_reference_rejection(y, scores):
    with pytest.raises(ValueError):
        reference(y, scores, [0.5])
    with pytest.raises(ValueError):
        threshold_table(y, scores, [0.5])


def test_empty_threshold_selection_still_returns_no_rows():
    assert threshold_table(np.array([0, 1]), np.array([0.1, 0.8]), []) == []
