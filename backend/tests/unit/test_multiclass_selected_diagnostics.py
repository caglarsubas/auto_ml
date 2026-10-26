"""Selected objectives are independent of unrelated diagnostic construction."""
import numpy as np
import pytest
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss, roc_auc_score

from evaluation import eval_utils
from modeling.development_assessment import development_metrics

pytestmark = pytest.mark.unit


def population(case):
    y = np.array([0, 1, 2, 0, 1, 2])
    p = np.array([[.6, .3, .1], [.2, .6, .2], [.1, .3, .6],
                  [.4, .4, .2], [.3, .4, .3], [.3, .2, .5]])
    if case == 'missing':
        return y[y != 2], p[y != 2]
    if case == 'repeated':
        return np.tile(y, 3), np.tile(p, (3, 1))
    if case == 'permuted':
        return y[::-1], p[::-1]
    return y, p


def reference(y, p, metric):
    p = p / p.sum(axis=1, keepdims=True)
    if metric == 'roc_auc':
        return float(roc_auc_score(y, p, labels=[0, 1, 2], multi_class='ovr', average='weighted')) if set(y) == {0, 1, 2} else None
    if metric == 'log_loss':
        return float(log_loss(y, p, labels=[0, 1, 2]))
    pred = p.argmax(axis=1)
    return float(accuracy_score(y, pred) if metric == 'accuracy' else
                 f1_score(y, pred, labels=[0, 1, 2], average='weighted', zero_division=0))


@pytest.mark.parametrize('metric', ['roc_auc', 'log_loss', 'accuracy', 'f1'])
@pytest.mark.parametrize('case', ['balanced', 'missing', 'repeated'])
def test_selected_objectives_retain_independent_reference_values(metric, case):
    y, p = population(case)
    result = development_metrics(y, p, 'classification', 3, metric=metric)
    expected = reference(y, p, metric)
    assert set(result) == {metric}
    assert result[metric] is None if expected is None else result[metric] == pytest.approx(expected, abs=1e-14)


@pytest.mark.parametrize('metric', ['roc_auc', 'log_loss', 'accuracy', 'f1'])
def test_unrelated_confusion_diagnostic_cannot_break_a_selected_objective(metric, monkeypatch):
    y, p = population('balanced')

    def unavailable(*args, **kwargs):
        raise AssertionError('Unrelated diagnostic construction')

    monkeypatch.setattr(eval_utils, 'confusion_matrix', unavailable)
    assert development_metrics(y, p, 'classification', 3, metric=metric)[metric] == pytest.approx(reference(y, p, metric))


@pytest.mark.parametrize('case', ['balanced', 'missing', 'repeated', 'permuted'])
def test_complete_assessment_retains_confusion_and_independent_auc(case):
    y, p = population(case)
    value = eval_utils.evaluate_multiclass(y, p)
    np.testing.assert_array_equal(value['confusion_matrix'], confusion_matrix(y, p.argmax(axis=1), labels=[0, 1, 2]))
    assert value['metric_semantics']['roc_auc_calculation'] == 'sklearn_roc_integration'
    expected = reference(y, p, 'roc_auc')
    assert value['metrics']['roc_auc'] is None if expected is None else value['metrics']['roc_auc'] == pytest.approx(expected)


@pytest.mark.parametrize('invalid', ['fractional_label', 'missing_probability', 'bad_sum', 'wrong_rows'])
def test_selected_objectives_still_reject_invalid_inputs(invalid):
    y, p = population('balanced')
    if invalid == 'fractional_label':
        y = y.astype(float); y[0] = .5
    elif invalid == 'missing_probability':
        p[0, 0] = np.nan
    elif invalid == 'bad_sum':
        p[0, 0] += .2
    else:
        p = p[:-1]
    with pytest.raises(ValueError):
        development_metrics(y, p, 'classification', 3, metric='roc_auc')
