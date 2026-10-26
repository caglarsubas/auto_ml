"""Full development summaries agree with independent public metric APIs."""
import numpy as np
import pytest
from sklearn import metrics

from modeling.development_assessment import development_metrics


def probability_reference(labels, probabilities):
    y, p = np.asarray(labels), np.asarray(probabilities, dtype=float)
    both = len(np.unique(y)) == 2
    fpr, tpr, _ = metrics.roc_curve(y, p) if both else (None, None, None)
    return {
        'roc_auc': float(metrics.roc_auc_score(y, p)) if both else None,
        'pr_auc': float(metrics.average_precision_score(y, p)) if both else None,
        'ks': float(np.max(np.abs(tpr - fpr))) if both else None,
        'log_loss': float(metrics.log_loss(y, p, labels=[0, 1])),
        'brier': float(metrics.brier_score_loss(y, p)),
    }


def reference(labels, probabilities, costs, threshold, probability_values=None):
    y, p = np.asarray(labels), np.asarray(probabilities, dtype=float)
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = metrics.confusion_matrix(y, pred, labels=[0, 1]).ravel()
    values = dict(probability_reference(y, p) if probability_values is None else probability_values)
    values.update({
        'accuracy': float(metrics.accuracy_score(y, pred)),
        'f1': float(metrics.f1_score(y, pred, zero_division=0)),
        'precision': float(metrics.precision_score(y, pred, zero_division=0)),
        'recall': float(metrics.recall_score(y, pred, zero_division=0)),
        'expected_cost': float((fn * costs.get('fn_cost', 1) + fp * costs.get('fp_cost', 1)) / len(y)),
    })
    return values


def compare(y, p, costs, threshold, probability_values=None):
    original_y, original_p, original_costs = y.copy(), p.copy(), dict(costs)
    expected = reference(y, p, costs, threshold, probability_values)
    actual = development_metrics(y, p, 'classification', costs=costs, threshold=threshold)
    assert list(actual) == list(expected)
    for name, value in expected.items():
        if value is None:
            assert actual[name] is None
        else:
            assert actual[name] == pytest.approx(value, rel=1e-15, abs=1e-15), name
    np.testing.assert_array_equal(y, original_y)
    np.testing.assert_array_equal(p, original_p)
    assert costs == original_costs


@pytest.mark.unit
@pytest.mark.parametrize('dtype', [bool, np.int8, np.int64, np.uint64, np.float32, np.float64])
@pytest.mark.parametrize('population', [1, 2, 3, 7, 65, 1024])
def test_binary_summary_matches_independent_metrics_across_supported_labels(dtype, population):
    rng = np.random.default_rng(7132026)
    for n in [1, 2, 3, 7, 65, 1024]:
        for style in ['random', 'ties', 'zeros', 'ones', 'boundaries']:
            y = rng.integers(0, 2, n).astype(dtype)
            if style == 'random':
                p = rng.uniform(0, 1, n)
            elif style == 'ties':
                p = rng.choice([0., .2, .5, .8, 1.], n)
            elif style == 'zeros':
                p, y = np.zeros(n), np.zeros(n, dtype=dtype)
            elif style == 'ones':
                p, y = np.ones(n), np.ones(n, dtype=dtype)
            else:
                eps = np.finfo(float).eps
                p = np.resize([0., np.nextafter(0., 1.), eps / 2, eps, 1 - eps, np.nextafter(1., 0.), 1.], n)
            if n == population:
                # These five reference metrics are threshold-independent. Keep
                # all comparisons, without recomputing identical reference calls.
                independent = probability_reference(y, p)
                for threshold in [.5, 0., 1., np.nan]:
                    compare(y, p, {'fn_cost': 2.5, 'fp_cost': .125}, threshold, independent)
        if n == population:
            break


@pytest.mark.unit
def test_binary_summary_observes_new_inputs_costs_and_thresholds_without_mutation():
    y = np.array([0, 1, 0, 1])
    p = np.array([.1, .4, .6, .8])
    costs = {'fn_cost': 0., 'fp_cost': 0.}
    compare(y, p, costs, .5)
    y[:] = [1, 0, 1, 0]
    p[:] = [.9, .3, .2, .7]
    costs.update(fn_cost=5., fp_cost=.25)
    compare(y, p, costs, .25)
    costs.clear()
    compare(y, p, costs, 1.)


@pytest.mark.unit
def test_column_labels_retain_the_independent_metric_fallback():
    compare(np.array([[0], [1], [1], [0]]), np.array([0., .5, 1., .25]), {}, .5)
