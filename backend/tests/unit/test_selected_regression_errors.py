"""Selected regression errors retain independent complete-assessment semantics."""
import numpy as np
import pytest
from sklearn import metrics

from modeling import development_assessment as assessment

pytestmark = pytest.mark.unit


def reference(y, p, metric):
    if metric == 'mae':
        return metrics.mean_absolute_error(y, p)
    value = metrics.mean_squared_error(y, p)
    return np.sqrt(value) if metric == 'rmse' else value


@pytest.mark.parametrize('metric', ['mse', 'rmse', 'mae'])
@pytest.mark.parametrize('dtype', [bool, np.int32, np.int64, np.uint64, np.float32, np.float64])
def test_selected_errors_match_public_references_and_observe_mutations(metric, dtype):
    rng = np.random.default_rng(157)
    for n in [1, 3, 31]:
        y = rng.integers(0, 2, n).astype(dtype)
        p = rng.uniform(-2, 3, n)
        for _ in range(2):
            original_y, original_p = y.copy(), p.copy()
            expected = reference(y, p, metric)
            result = assessment.development_metrics(y, p, 'regression', metric=metric)
            assert result == {metric: pytest.approx(expected, rel=1e-14, abs=1e-14)}
            np.testing.assert_array_equal(y, original_y)
            np.testing.assert_array_equal(p, original_p)
            p += .25
    y.flags.writeable = p.flags.writeable = False
    assert assessment.development_metrics(y, p, 'regression', metric=metric)[metric] == pytest.approx(reference(y, p, metric))


@pytest.mark.parametrize('metric', ['mse', 'rmse', 'mae'])
@pytest.mark.parametrize('invalid', ['rows', 'columns', 'nan', 'infinite', 'empty'])
def test_selected_errors_retain_input_rejection(metric, invalid):
    y, p = np.array([0., 1., 2.]), np.array([.25, .5, 3.])
    if invalid == 'rows':
        p = p[:-1]
    elif invalid == 'columns':
        p = p[:, None]
    elif invalid == 'empty':
        y, p = y[:0], p[:0]
    else:
        y[0] = np.nan if invalid == 'nan' else np.inf
    with pytest.raises(ValueError):
        assessment.development_metrics(y, p, 'regression', metric=metric)


@pytest.mark.parametrize('metric', ['mse', 'rmse', 'mae'])
@pytest.mark.parametrize('representation', ['column', 'strings'])
def test_noncanonical_labels_keep_public_fallback(metric, representation, monkeypatch):
    y = np.array([[0.], [1.], [2.]]) if representation == 'column' else np.array(['0', '1', '2'])
    p = np.array([.25, .5, 3.])
    name = 'mean_absolute_error' if metric == 'mae' else 'mean_squared_error'
    original, calls = getattr(assessment, name), []

    def observed(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(assessment, name, observed)
    assert assessment.development_metrics(y, p, 'regression', metric=metric)[metric] == pytest.approx(reference(y, p, metric))
    assert calls == [True]


@pytest.mark.parametrize('metric', ['mse', 'rmse', 'mae'])
def test_validated_selected_errors_avoid_repeated_public_work_but_full_assessment_keeps_it(metric, monkeypatch):
    y, p = np.array([0., 1., 2.]), np.array([.25, .5, 3.])
    expected = reference(y, p, metric)

    def independent(*args, **kwargs):
        raise RuntimeError('Independent assessment reference reached')

    monkeypatch.setattr(assessment, 'mean_squared_error', independent)
    monkeypatch.setattr(assessment, 'mean_absolute_error', independent)
    assert assessment.development_metrics(y, p, 'regression', metric=metric)[metric] == pytest.approx(expected)
    with pytest.raises(RuntimeError, match='Independent assessment'):
        assessment.development_metrics(y, p, 'regression')
