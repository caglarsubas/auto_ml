"""Bounded selected calculations retain independent metrics and scalar behavior."""
from unittest.mock import Mock

import numpy as np
import pytest
from sklearn import metrics

from evaluation import eval_utils as evaluation
from modeling import rank_metrics

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('classes', [8, 65, 256])
@pytest.mark.parametrize('scenario', ['random', 'ties', 'constant', 'reversed', 'imbalanced'])
def test_bounded_many_class_selection_matches_independent_public_assessment(classes, scenario):
    rng = np.random.default_rng(160)
    y = np.arange(classes * 2) % classes
    if scenario == 'imbalanced':
        y = np.r_[y, np.zeros(classes, dtype=int)]
    p = rng.random((len(y), classes))
    if scenario == 'ties':
        p = p.round(1) + .1
    if scenario == 'constant':
        p[:] = 1
    if scenario == 'reversed':
        y, p = y[::-1], p[::-1]
    p /= p.sum(axis=1, keepdims=True)
    original_y, original_p = y.copy(), p.copy()
    y.setflags(write=False)
    p.setflags(write=False)
    result = evaluation.evaluate_multiclass(y, p, metric_names=['roc_auc'], include_confusion=False)
    assert result['metrics']['roc_auc'] == pytest.approx(metrics.roc_auc_score(y, p / p.sum(axis=1, keepdims=True), multi_class='ovr', average='weighted'), rel=2e-14, abs=2e-14)
    np.testing.assert_array_equal(y, original_y)
    np.testing.assert_array_equal(p, original_p)


@pytest.mark.parametrize('bound', ['MAX_BATCH_RANK_CELLS', 'MAX_BATCH_RANK_CLASSES', 'MAX_BATCH_RANK_ROWS', 'MAX_EXACT_RANK_ROWS'])
def test_each_rank_bound_retains_the_original_class_wise_calculation(bound, monkeypatch):
    y = np.arange(24) % 8
    p = np.random.default_rng(160).random((24, 8))
    p /= p.sum(axis=1, keepdims=True)
    monkeypatch.setattr(rank_metrics, bound, 1)
    assert rank_metrics.small_weighted_ovr_auc(y, p) is None
    result = evaluation.evaluate_multiclass(y, p, metric_names=['roc_auc'], include_confusion=False)
    assert result['metrics']['roc_auc'] == pytest.approx(metrics.roc_auc_score(y, p, multi_class='ovr', average='weighted'), abs=2e-14)


@pytest.mark.parametrize('kind', ['full', 'missing', 'invalid'])
def test_batched_selection_cannot_override_full_or_unavailable_evidence(kind, monkeypatch):
    y = np.arange(24) % 8
    p = np.ones((24, 8)) / 8
    observed = Mock(wraps=rank_metrics.small_weighted_ovr_auc)
    monkeypatch.setattr(rank_metrics, 'small_weighted_ovr_auc', observed)
    if kind == 'full':
        reference = Mock(wraps=metrics.roc_auc_score)
        monkeypatch.setattr(evaluation, 'roc_auc_score', reference)
        assert evaluation.evaluate_multiclass(y, p)['metrics']['roc_auc'] == .5
        assert reference.call_count == 1
    elif kind == 'missing':
        y[y == 7] = 0
        assert evaluation.evaluate_multiclass(y, p, metric_names=['roc_auc'], include_confusion=False)['metrics']['roc_auc'] is None
    else:
        p[0, 0] = np.nan
        with pytest.raises(ValueError):
            evaluation.evaluate_multiclass(y, p, metric_names=['roc_auc'], include_confusion=False)
    assert observed.call_count == 0


@pytest.mark.parametrize('scenario', ['random', 'tied', 'all_negative', 'all_positive', 'boundary', 'default'])
def test_vector_threshold_search_preserves_all_rows_and_public_confusion(scenario, monkeypatch):
    rng = np.random.default_rng(160)
    y = rng.integers(0, 2, 53)
    p = rng.random(53)
    if scenario == 'tied':
        p = p.round(1)
    elif scenario == 'all_negative':
        y[:] = 0
    elif scenario == 'all_positive':
        y[:] = 1
    elif scenario == 'boundary':
        p[:4] = [0., 1., np.nextafter(.5, 0.), np.nextafter(.5, 1.)]
    thresholds = ([round(x, 2) for x in np.linspace(.05, .95, 19)] if scenario == 'default' else
                  [.5, .2, .5, 0., 1., -1., 2., .8, .01])
    before_y, before_p = y.copy(), p.copy()
    search = Mock(wraps=np.searchsorted)
    monkeypatch.setattr(evaluation.np, 'searchsorted', search)
    rows = evaluation.threshold_table(y, p, None if scenario == 'default' else thresholds)
    assert search.call_count == 2 and [r['threshold'] for r in rows] == thresholds
    for t, row in zip(thresholds, rows):
        pred = (p >= t).astype(int)
        tn, fp, fn, tp = metrics.confusion_matrix(y, pred, labels=[0, 1]).ravel()
        assert (row['tn'], row['fp'], row['fn'], row['tp']) == (tn, fp, fn, tp)
        assert row['f1'] == pytest.approx(metrics.f1_score(y, pred, zero_division=0))
        assert row['mcc'] == pytest.approx(metrics.matthews_corrcoef(y, pred))
    np.testing.assert_array_equal(y, before_y)
    np.testing.assert_array_equal(p, before_p)


@pytest.mark.parametrize('thresholds', [[0, 1] * 4, [np.float32(.5)] * 8, [np.longdouble(.5)] * 8, [2**64, .5] * 4])
def test_extended_or_mixed_threshold_scalars_retain_scalar_search(thresholds, monkeypatch):
    y, p = np.array([0, 1, 0, 1]), np.array([0., .25, .5, 1.])
    search = Mock(wraps=np.searchsorted)
    monkeypatch.setattr(evaluation.np, 'searchsorted', search)
    if any(type(t) is int and t > np.iinfo(np.uint64).max for t in thresholds):
        # Preserve the existing NumPy scalar-validity rejection, before search.
        with pytest.raises(TypeError):
            evaluation.threshold_table(y, p, thresholds)
        assert search.call_count == 0
        return
    rows = evaluation.threshold_table(y, p, thresholds)
    assert search.call_count == 2 * len(thresholds)
    for t, row in zip(thresholds, rows):
        tn, fp, fn, tp = metrics.confusion_matrix(y, (p >= t).astype(int), labels=[0, 1]).ravel()
        assert (row['tn'], row['fp'], row['fn'], row['tp']) == (tn, fp, fn, tp)
