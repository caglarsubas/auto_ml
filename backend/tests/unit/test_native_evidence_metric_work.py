"""Independent metric references, legacy fallbacks and fresh implementation pins."""
import hashlib
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from sklearn import metrics

from evaluation import eval_utils as evaluation
from execution_jobs import service, training_search
from modeling import development_assessment as assessment
from modeling import rank_metrics
from modeling.declared_metric import metric_spec

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('scenario', ['ties', 'constant', 'continuous', 'subnormal'])
@pytest.mark.parametrize('dtype', [np.float32, np.float64])
def test_selected_tie_groups_match_independent_integration_and_row_permutations(scenario, dtype):
    rng = np.random.default_rng(159)
    y = np.array([0] * 29 + [1, 1], dtype=np.int64)
    p = rng.uniform(size=len(y)).astype(dtype)
    if scenario == 'ties':
        p = p.round(1)
    elif scenario == 'constant':
        p[:] = .5
    elif scenario == 'subnormal':
        p = np.nextafter(dtype(0), dtype(1)) * np.arange(len(y), dtype=dtype)
    expected = metrics.roc_auc_score(y, p.astype(float))
    y.setflags(write=False)
    p.setflags(write=False)
    assert assessment.development_metrics(y, p, 'classification', metric='roc_auc')['roc_auc'] == pytest.approx(expected, abs=2e-14)
    assert rank_metrics.tie_group_auc(y == 1, p) == pytest.approx(expected, abs=2e-14)
    order = rng.permutation(len(y))
    assert rank_metrics.tie_group_auc(y[order] == 1, p[order]) == pytest.approx(expected, abs=2e-14)
    assert rank_metrics.tie_group_auc(y == 0, p) == pytest.approx(1 - expected, abs=2e-14)


def test_constant_scores_still_obey_the_exact_rank_ceiling(monkeypatch):
    reference = Mock(wraps=metrics.roc_auc_score)
    monkeypatch.setattr(assessment, '_MAX_BINARY_RANK_ROWS', 3)
    monkeypatch.setattr(assessment, 'roc_auc_score', reference)
    assert assessment.development_metrics([0, 1, 0, 1], [.5] * 4, 'classification', metric='roc_auc')['roc_auc'] == .5
    assert reference.call_count == 1


@pytest.mark.parametrize('classes', [3, 65])
@pytest.mark.parametrize('scenario', ['random', 'perfect', 'uniform', 'missing_class'])
def test_multiclass_selection_matches_full_public_assessment_without_input_mutation(classes, scenario):
    y = np.arange(classes * 2) % classes
    p = np.random.default_rng(159).random((len(y), classes)).astype(np.float32)
    if scenario == 'perfect':
        p = np.eye(classes, dtype=np.float32)[y]
    elif scenario == 'uniform':
        p[:] = 1.
    elif scenario == 'missing_class':
        y[-1] = y[classes - 1] = 0
    p /= p.sum(axis=1, keepdims=True)
    before = p.copy()
    y.setflags(write=False)
    p.setflags(write=False)
    full = evaluation.evaluate_multiclass(y, p)
    selected = evaluation.evaluate_multiclass(y, p, metric_names=['roc_auc', 'log_loss', 'accuracy', 'f1', 'f1_weighted'], include_confusion=False)
    for name, value in selected['metrics'].items():
        if value is None:
            assert full['metrics'][name] is None
        else:
            assert value == pytest.approx(full['metrics'][name], abs=2e-14, rel=2e-14)
    assert selected['confusion_matrix'] is None
    np.testing.assert_array_equal(before, p)


@pytest.mark.parametrize('name', ['roc_auc_score', 'log_loss', 'f1_score', 'confusion_matrix'])
def test_full_multiclass_assessment_keeps_public_reference_failures(monkeypatch, name):
    def refuse(*args, **kwargs):
        raise ValueError('independent reference refused')
    monkeypatch.setattr(evaluation, name, refuse)
    with pytest.raises(ValueError, match='independent reference refused'):
        evaluation.evaluate_multiclass([0, 1, 2], np.eye(3))


@pytest.mark.parametrize('scenario', ['ties', 'continuous', 'boundary', 'constant', 'only_zero', 'only_one'])
@pytest.mark.parametrize('dtype', [np.float32, np.float64])
def test_full_binary_values_and_curves_match_independent_references(scenario, dtype):
    y = np.array([0, 1] * 15 + [0])
    p = np.random.default_rng(159).random(len(y)).astype(dtype)
    if scenario == 'ties':
        p = p.round(1)
    elif scenario == 'boundary':
        p[:4] = [0, 1, np.nextafter(dtype(0), dtype(1)), np.nextafter(dtype(1), dtype(0))]
    elif scenario == 'constant':
        p[:] = .5
    elif scenario in {'only_zero', 'only_one'}:
        y[:] = scenario == 'only_one'
    original = p.copy()
    actual = evaluation.evaluate_binary(y, p)['metrics']
    normalized = p.astype(float)
    pred = (normalized >= .5).astype(int)
    expected = dict(accuracy=metrics.accuracy_score(y, pred),
        f1=metrics.f1_score(y, pred, zero_division=0), f2=metrics.fbeta_score(y, pred, beta=2, zero_division=0),
        precision=metrics.precision_score(y, pred, zero_division=0), recall=metrics.recall_score(y, pred, zero_division=0),
        mcc=metrics.matthews_corrcoef(y, pred),
        log_loss=metrics.log_loss(y, np.clip(normalized, 1e-7, 1 - 1e-7), labels=[0, 1]),
        brier=metrics.brier_score_loss(y, normalized))
    for name, value in expected.items():
        assert actual[name] == pytest.approx(value, abs=2e-14, rel=2e-14)
    if len(np.unique(y)) == 2:
        assert actual['roc_auc'] == metrics.roc_auc_score(y, normalized)
        assert actual['pr_auc'] == metrics.average_precision_score(y, normalized)
        assert actual['gini'] == 2 * actual['roc_auc'] - 1
        fpr, tpr, _ = metrics.roc_curve(y, normalized)
        assert actual['ks'] == np.max(np.abs(tpr - fpr))
    else:
        assert actual['roc_auc'] is actual['pr_auc'] is actual['ks'] is actual['gini'] is None
    report = evaluation.evaluate_binary(y, p)
    fpr, tpr, _ = metrics.roc_curve(y, normalized)
    np.testing.assert_allclose(report['curves']['roc']['fpr'], fpr[::max(1, len(fpr)//100)], equal_nan=True)
    np.testing.assert_allclose(report['curves']['roc']['tpr'], tpr[::max(1, len(tpr)//100)], equal_nan=True)
    precision, recall, _ = metrics.precision_recall_curve(y, normalized)
    np.testing.assert_array_equal(report['curves']['pr']['precision'], precision[::max(1, len(precision)//100)])
    np.testing.assert_array_equal(report['curves']['pr']['recall'], recall[::max(1, len(recall)//100)])
    np.testing.assert_array_equal(original, p)


@pytest.mark.parametrize('name', ['roc_auc_score', 'average_precision_score', 'confusion_matrix'])
def test_full_binary_reference_failures_are_still_observable(monkeypatch, name):
    def refuse(*args, **kwargs):
        raise ValueError('reference refused')
    monkeypatch.setattr(evaluation, name, refuse)
    with pytest.raises(ValueError, match='reference refused'):
        evaluation.evaluate_binary([0, 1], [.2, .8])


def test_roc_failure_is_not_reused_as_success_and_retries_legacy_curve_read(monkeypatch):
    reference = metrics.roc_curve
    calls = []
    def first_refused(*args):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError('curve unavailable')
        return reference(*args)
    monkeypatch.setattr(evaluation, 'roc_curve', first_refused)
    result = evaluation.evaluate_binary([0, 1], [.2, .8])
    assert result['metrics']['ks'] is result['metrics']['gini'] is None
    assert result['curves']['roc'] is not None and len(calls) == 2


@pytest.mark.parametrize('scenario', ['ties', 'nan', 'float32', 'nonfinite_threshold', 'one_threshold'])
def test_threshold_partitions_preserve_inclusive_ties_and_legacy_fallbacks(scenario):
    y = np.array([0, 1] * 15)
    p = np.linspace(0., 1., len(y))
    thresholds = [0., .05, .1, .25, .5, .75, .9, .95, 1.]
    if scenario == 'ties':
        p = np.resize(np.array([0., -0., .5, .5, 1.]), len(y))
    elif scenario == 'nan':
        p[0] = np.nan
    elif scenario == 'float32':
        p = p.astype(np.float32)
    elif scenario == 'nonfinite_threshold':
        thresholds[0] = np.inf
    else:
        thresholds = [.501]
    rows = evaluation.threshold_table(y, p, thresholds)
    for row, threshold in zip(rows, thresholds):
        prediction = (p >= threshold).astype(int)
        tn, fp, fn, tp = metrics.confusion_matrix(y, prediction, labels=[0, 1]).ravel()
        assert [row[k] for k in ['tn', 'fp', 'fn', 'tp']] == [tn, fp, fn, tp]
        assert row['f1'] == pytest.approx(metrics.f1_score(y, prediction, zero_division=0))
        assert row['mcc'] == pytest.approx(metrics.matthews_corrcoef(y, prediction))


def test_list_score_input_keeps_legacy_threshold_validation():
    rows = evaluation.threshold_table([0, 1], [.2, .8])
    assert len(rows) == 19 and rows[9]['tp'] == rows[9]['tn'] == 1
    with pytest.raises(TypeError):
        evaluation.threshold_table([0, 1], [.2, .8], [.501])


def test_new_calculation_source_is_freshly_bound_to_metric_and_job_runtime(monkeypatch, settings):
    contract = {'task': 'classification', 'class_mapping': [{}, {}], 'objective': {'primary_metric': 'roc_auc'}}
    before_metric = metric_spec(contract)
    before_runtime = service.runtime(training_search.KIND)
    name = 'modeling/rank_metrics.py'
    path = Path(settings.BASE_DIR) / name
    raw = path.read_bytes()
    assert before_runtime['sources'][name] == hashlib.sha256(raw).hexdigest()
    original = Path.read_bytes
    def changed(self):
        return original(self) + b'\n# altered implementation' if self == path else original(self)
    monkeypatch.setattr(Path, 'read_bytes', changed)
    assert metric_spec(contract)['implementation_sha256'] != before_metric['implementation_sha256']
    assert service.runtime(training_search.KIND)['sources'][name] != before_runtime['sources'][name]
