"""Full development curves retain independent references and row-bound values."""
import copy
from unittest.mock import Mock

import numpy as np
import pytest
from sklearn.metrics import average_precision_score, roc_auc_score

from modeling import development_assessment as assessment
from tests.unit.test_development_assessment import context

pytestmark = pytest.mark.unit


def evidence(y, p):
    record = {}
    metrics = assessment.development_metrics(y, p, 'classification', _curve_evidence=record)
    return metrics, record


@pytest.mark.parametrize('dtype', [np.bool_, np.int64, np.float32, np.float64])
@pytest.mark.parametrize('scenario', ['continuous', 'ties', 'constant'])
def test_fold_and_micro_reports_match_public_references_without_mutating_inputs(dtype, scenario):
    rng = np.random.default_rng(159)
    labels = [np.array([0, 1] * 15 + [1], dtype=dtype) for _ in range(3)]
    predictions = [rng.uniform(size=len(y)) for y in labels]
    if scenario == 'ties':
        predictions = [p.round(1) for p in predictions]
    elif scenario == 'constant':
        predictions = [np.full(len(y), .5) for y in labels]
    originals = [a.copy() for a in labels + predictions]
    records = []
    for y, p in zip(labels, predictions):
        metrics, record = evidence(y, p)
        assert metrics['roc_auc'] == roc_auc_score(y, p)
        assert metrics['pr_auc'] == average_precision_score(y, p)
        assert record['labels'].dtype == y.dtype
        for snapshot, source in [(record['labels'], y), (record['predictions'], p)]:
            assert not np.shares_memory(snapshot, source) and not snapshot.flags.writeable
        records.append(record)
    reused = assessment._binary_curves(labels, predictions, records)
    assert reused == assessment._binary_curves(labels, predictions)
    assert reused['pr_curve_micro']['ap'] == average_precision_score(np.concatenate(labels), np.concatenate(predictions))
    for before, after in zip(originals, labels + predictions):
        np.testing.assert_array_equal(before, after)


@pytest.mark.parametrize('change', ['label', 'probability', 'order', 'dtype', 'missing_key',
                                     'mutable', 'bad_tuple', 'different_lengths', 'wrong_fold_count'])
def test_changed_or_malformed_evidence_uses_fresh_public_curves(monkeypatch, change):
    y = np.array([0, 1, 0, 1, 1, 0])
    p = np.array([.1, .9, .6, .3, 1., .5])
    _, record = evidence(y, p)
    records = [record]
    if change == 'label':
        y[0] = 1
    elif change == 'probability':
        p[0] = .8
    elif change == 'order':
        y, p = y[::-1], p[::-1]
    elif change == 'dtype':
        y = y.astype(float)
    elif change == 'missing_key':
        record.pop('pr')
    elif change == 'mutable':
        record['labels'].setflags(write=True)
    elif change == 'bad_tuple':
        record['roc'] = (record['roc'][0],)
    elif change == 'different_lengths':
        record['pr'] = (record['pr'][0][:-1], record['pr'][1])
    else:
        records = []
    expected = assessment._binary_curves([y], [p])
    roc = Mock(wraps=assessment.roc_curve)
    pr = Mock(wraps=assessment.precision_recall_curve)
    monkeypatch.setattr(assessment, 'roc_curve', roc)
    monkeypatch.setattr(assessment, 'precision_recall_curve', pr)
    assert assessment._binary_curves([y], [p], records) == expected
    assert roc.call_count == 1 and pr.call_count == 2


@pytest.mark.parametrize('reference', ['confusion_matrix', 'roc_auc_score', 'roc_curve', 'precision_recall_curve'])
def test_failed_public_full_assessment_cannot_create_reusable_evidence(monkeypatch, reference):
    record = {}
    def refuse(*args, **kwargs):
        raise ValueError('reference refusal')
    monkeypatch.setattr(assessment, reference, refuse)
    with pytest.raises(ValueError, match='reference refusal'):
        assessment.development_metrics([0, 1], [.2, .8], 'classification', _curve_evidence=record)
    assert record == {}


@pytest.mark.parametrize('p', [[.5], [float('nan'), .5], [-.1, .5], [.5, 1.1], [[.5], [.5]]])
def test_invalid_predictions_do_not_emit_evidence(p):
    record = {}
    with pytest.raises(ValueError):
        assessment.development_metrics([0, 1], p, 'classification', _curve_evidence=record)
    assert record == {}


@pytest.mark.parametrize('labels', [[0, 0], [1, 1]])
def test_single_class_discrimination_is_unavailable_and_not_reused(labels):
    metrics, record = evidence(labels, [.2, .8])
    assert metrics['roc_auc'] is metrics['pr_auc'] is metrics['ks'] is None
    assert record == {}


def test_noncanonical_column_labels_keep_public_fallback():
    y, p = np.array([[0], [1], [0], [1]]), np.array([.1, .2, .6, .9])
    metrics, record = evidence(y, p)
    assert record == {}
    assert metrics['pr_auc'] == average_precision_score(y, p)
    assert assessment._binary_curves([y], [p])['pr_curve_micro']['ap'] == average_precision_score(y, p)


def test_actual_cv_reuses_only_current_folds_and_keeps_independent_auc_and_confusion(monkeypatch):
    config = context('classification')
    parameters = {'task': 'classification', 'objective': 'binary:logistic', 'eval_metric': 'auc', 'nthread': 1}
    baseline = assessment.assess_development_cv(config, config['frame'][['x']], config['labels'], 'xgboost', parameters,
                                               n_splits=3, num_boost_round=3, early_stopping_rounds=2)
    observed = {}
    for name in ['roc_auc_score', 'confusion_matrix', 'roc_curve', 'precision_recall_curve']:
        observed[name] = Mock(wraps=getattr(assessment, name))
        monkeypatch.setattr(assessment, name, observed[name])
    actual = assessment.assess_development_cv(copy.deepcopy(config), config['frame'][['x']], config['labels'],
                                              'xgboost', parameters, n_splits=3,
                                              num_boost_round=3, early_stopping_rounds=2)
    assert actual == baseline
    assert observed['roc_auc_score'].call_count == observed['confusion_matrix'].call_count == 3
    assert observed['roc_curve'].call_count == 3
    assert observed['precision_recall_curve'].call_count == 4
