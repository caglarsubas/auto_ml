"""Binary stopping values retain independent metric and validation semantics."""
import numpy as np
import pytest
from sklearn import metrics

from modeling import development_assessment as assessment

pytestmark = pytest.mark.unit
SELECTED = ['brier', 'log_loss', 'accuracy', 'f1', 'precision', 'recall', 'expected_cost']


def reference(y, p, threshold, costs):
    pred = (p >= threshold).astype(int)
    precision, recall, f1, _ = metrics.precision_recall_fscore_support(y, pred, average='binary', zero_division=0)
    tn, fp, fn, tp = metrics.confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return dict(brier=float(metrics.brier_score_loss(y, p)),
                log_loss=float(metrics.log_loss(y, p, labels=[0, 1])),
                accuracy=float(metrics.accuracy_score(y, pred)),
                f1=float(f1), precision=float(precision), recall=float(recall),
                expected_cost=float((fn * costs.get('fn_cost', 1) + fp * costs.get('fp_cost', 1)) / len(y)))


@pytest.mark.parametrize('dtype', [bool, np.int8, np.int64, np.uint64, np.float32, np.float64])
@pytest.mark.parametrize('size', [1, 2, 31, 1024])
def test_selected_metrics_match_public_references_for_encoded_populations(dtype, size):
    rng = np.random.default_rng(size)
    for style, threshold in [('random', .5), ('ties', .25), ('zero', 0.), ('one', 1.), ('boundary', np.nan)]:
        y, p = rng.integers(0, 2, size).astype(dtype), rng.uniform(size=size)
        if style == 'ties':
            p = np.round(p, 1)
        elif style in {'zero', 'one'}:
            y[:] = int(style == 'one')
            p[:] = int(style == 'one')
        elif style == 'boundary':
            eps = np.finfo(float).eps
            p = np.resize([0., np.nextafter(0., 1.), eps, 1 - eps, np.nextafter(1., 0.), 1.], size)
        costs = {'fn_cost': 7.25, 'fp_cost': .125}
        expected = reference(y, p, threshold, costs)
        before_y, before_p = y.copy(), p.copy()
        for name in SELECTED:
            actual = assessment.development_metrics(y, p, 'classification', metric=name, threshold=threshold, costs=costs)
            assert list(actual) == [name]
            assert actual[name] == pytest.approx(expected[name], rel=1e-15, abs=1e-15)
        np.testing.assert_array_equal(y, before_y)
        np.testing.assert_array_equal(p, before_p)
        assert costs == {'fn_cost': 7.25, 'fp_cost': .125}


@pytest.mark.parametrize('metric', SELECTED)
@pytest.mark.parametrize('invalid', ['fractional_label', 'missing_label', 'infinite_label', 'unknown_label',
                                     'missing_probability', 'infinite_probability', 'negative', 'above_one', 'columns', 'rows'])
def test_validation_precedes_selected_arithmetic(metric, invalid):
    y, p = np.array([0., 1., 0., 1.]), np.array([0., .25, .5, 1.])
    if invalid.endswith('label'):
        y[0] = {'fractional_label': .25, 'missing_label': np.nan, 'infinite_label': np.inf, 'unknown_label': 2.}[invalid]
    elif invalid == 'columns':
        p = np.column_stack([p, 1 - p])
    elif invalid == 'rows':
        p = p[:-1]
    else:
        p[0] = {'missing_probability': np.nan, 'infinite_probability': np.inf, 'negative': -.001, 'above_one': 1.001}[invalid]
    with pytest.raises(ValueError):
        assessment.development_metrics(y, p, 'classification', metric=metric)


@pytest.mark.parametrize('metric,function', [('brier', 'brier_score_loss'), ('log_loss', 'log_loss'), ('expected_cost', 'confusion_matrix')])
def test_column_labels_keep_public_fallback(monkeypatch, metric, function):
    y, p = np.array([[0], [1], [1], [0]]), np.array([0., .25, .5, 1.])
    calls = []
    original = getattr(assessment, function)

    def observed(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(assessment, function, observed)
    actual = assessment.development_metrics(y, p, 'classification', metric=metric)[metric]
    assert actual == pytest.approx(reference(y, p, .5, {})[metric], rel=1e-15, abs=1e-15)
    assert calls == [True]


def test_selected_calls_reobserve_mutated_inputs_costs_threshold_and_positive_mapping():
    y, p = np.array([0, 1, 0, 1]), np.array([0., .4, .6, 1.])
    costs = {}
    for threshold in [.5, .1, 1.]:
        expected = reference(y, p, threshold, costs)
        for metric in SELECTED:
            assert assessment.development_metrics(y, p, 'classification', costs=costs, threshold=threshold,
                                                  metric=metric)[metric] == pytest.approx(expected[metric], rel=1e-15, abs=1e-15)
        y[:] = 1 - y
        p[:] = p[::-1]
        costs.update(fn_cost=0., fp_cost=4.5)


def test_readonly_strided_inputs_and_single_class_zero_division_conventions():
    y, p = np.zeros(16, dtype=np.uint64)[::2], np.ones(16)[::2]
    y.flags.writeable = p.flags.writeable = False
    expected = reference(y, p, .5, {'fp_cost': 0.})
    for metric in SELECTED:
        assert assessment.development_metrics(y, p, 'classification', costs={'fp_cost': 0.}, metric=metric)[metric] == expected[metric]
