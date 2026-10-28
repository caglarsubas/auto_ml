"""Selected metric validation keeps every declared value and independent checks."""
from decimal import Decimal

import numpy as np
import pytest

from evaluation import eval_utils
from modeling import development_assessment, rank_metrics

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('dtype', [np.int8, np.int64, np.uint64, np.float32, np.float64, bool])
def test_numeric_membership_matches_general_mapping_without_mutation(dtype):
    y = np.asarray([0, 1, 2, 2, 0], dtype=dtype)
    before = y.copy()
    assert rank_metrics.contiguous_class_membership(y, 65) == bool(np.isin(y, np.arange(65)).all())
    np.testing.assert_array_equal(y, before)


@pytest.mark.parametrize('y', [np.array([0, 1], dtype=object), np.array(['0', '1']),
                               np.array([0j, 1j]), np.array([0, 1], dtype='>i8'),
                               np.array([0, 1], dtype=np.longdouble), np.array([0, 1], dtype=np.float16)])
def test_unusual_label_profiles_keep_the_general_path(y):
    assert rank_metrics.contiguous_class_membership(y, 3) is None


@pytest.mark.parametrize('classes', [0, True, 3.0, '3', np.int64(3), 2**24 + 1])
def test_unusual_class_counts_keep_the_existing_conversion_boundary(classes):
    assert rank_metrics.contiguous_class_membership(np.array([0, 1]), classes) is None


@pytest.mark.parametrize('classes', [3, 65])
@pytest.mark.parametrize('dtype', [np.int64, np.float32, np.float64])
@pytest.mark.parametrize('metric', ['roc_auc', 'accuracy', 'f1', 'log_loss'])
def test_selected_values_match_complete_independent_assessment(classes, dtype, metric):
    rng = np.random.default_rng(1602)
    y = (np.arange(classes * 3) % classes).astype(dtype)
    p = rng.random((len(y), classes))
    p /= p.sum(axis=1, keepdims=True)
    before_y, before_p = y.copy(), p.copy()
    reference = eval_utils.evaluate_multiclass(y, p)['metrics'][metric]
    assert eval_utils.evaluate_multiclass(y, p, metric_names=[metric], include_confusion=False)['metrics'][metric] == pytest.approx(reference, abs=1e-13)
    assert development_assessment.development_metrics(y, p, 'classification', classes, metric=metric)[metric] == pytest.approx(reference, abs=1e-13)
    np.testing.assert_array_equal(y, before_y)
    np.testing.assert_array_equal(p, before_p)


INVALID = [np.array([-1., 0., 1.]), np.array([0., 1., 3.]), np.array([0., .5, 1.]),
           np.array([0., np.nan, 1.]), np.array([0., np.inf, 1.]), np.array([0., -np.inf, 1.]),
           np.array([0, 1, 2**64 - 1], dtype=np.uint64)]


@pytest.mark.parametrize('y', INVALID)
@pytest.mark.parametrize('entry', ['evaluation', 'development'])
def test_invalid_labels_stop_with_the_existing_actionable_error(y, entry):
    p = np.full((len(y), 3), 1 / 3)
    if entry == 'evaluation':
        with pytest.raises(ValueError, match='Multiclass labels must be encoded declared classes'):
            eval_utils.evaluate_multiclass(y, p, metric_names=['accuracy'], include_confusion=False)
    else:
        with pytest.raises(ValueError, match='Development labels do not match the declared class mapping'):
            development_assessment.development_metrics(y, p, 'classification', 3, metric='accuracy')


@pytest.mark.parametrize('labels', [[Decimal(0), Decimal(1), Decimal(2)], [False, True, False]])
def test_supported_noncanonical_labels_retain_reference_values(labels):
    y = np.array(labels, dtype=object)
    p = np.array([[.8, .1, .1], [.1, .8, .1], [.1, .1, .8]])
    expected = eval_utils.evaluate_multiclass(y, p)['metrics']['accuracy']
    assert development_assessment.development_metrics(y, p, 'classification', 3, metric='accuracy')['accuracy'] == expected


def test_selected_numeric_mapping_avoids_general_membership_but_full_assessment_keeps_it(monkeypatch):
    original = np.isin
    calls = []
    def observed(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(np, 'isin', observed)
    y = np.array([0., 1., 2.], dtype=np.float32)
    p = np.full((3, 3), 1 / 3)
    development_assessment.development_metrics(y, p, 'classification', 3, metric='roc_auc')
    assert not calls
    development_assessment.development_metrics(y, p, 'classification', 3)
    assert calls


def test_new_label_values_are_rechecked_each_call():
    y = np.array([0., 1., 2.])
    p = np.full((3, 3), 1 / 3)
    assert development_assessment.development_metrics(y, p, 'classification', 3, metric='roc_auc')['roc_auc'] == .5
    y[1] = .5
    with pytest.raises(ValueError, match='Development labels do not match'):
        development_assessment.development_metrics(y, p, 'classification', 3, metric='roc_auc')


@pytest.mark.parametrize('labels', [[], [0, 1, 0]])
def test_empty_or_missing_classes_keep_unavailable_discrimination(labels):
    p = np.full((len(labels), 3), 1 / 3)
    if not labels:
        with pytest.raises(ValueError, match='Multiclass labels must be encoded declared classes'):
            eval_utils.evaluate_multiclass(np.array(labels), p, metric_names=['roc_auc'], include_confusion=False)
    else:
        assert development_assessment.development_metrics(np.array(labels), p, 'classification', 3, metric='roc_auc')['roc_auc'] is None
