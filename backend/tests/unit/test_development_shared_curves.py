"""Shared curve work preserves reference values, arrays and independent checks."""
import numpy as np
import pytest
import sklearn
from sklearn import metrics
from modeling import development_assessment as m

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('dtype', [bool, np.uint64, np.float32])
@pytest.mark.parametrize('n', [2, 65, 1024])
@pytest.mark.parametrize('style', ['random', 'ties'])
def test_stored_curves_match_both_independent_public_apis(dtype, n, style):
    rng = np.random.default_rng(163)
    y = rng.integers(0, 2, n).astype(dtype)
    y[:2] = [0, 1]
    p = rng.random(n) if style == 'random' else rng.choice([0., .2, .5, .8, 1.], n)
    before_y, before_p = y.copy(), p.copy()
    evidence = {}
    result = m.development_metrics(y, p, 'classification', _curve_evidence=evidence)
    assert result['roc_auc'] == metrics.roc_auc_score(y, p)
    assert result['pr_auc'] == pytest.approx(metrics.average_precision_score(y, p), abs=1e-15)
    for key, expected in [('roc', metrics.roc_curve(y, p)[:2]),
                          ('pr', metrics.precision_recall_curve(y, p)[:2])]:
        for actual, reference in zip(evidence[key], expected):
            np.testing.assert_array_equal(actual, reference)
            assert not actual.flags.writeable
    np.testing.assert_array_equal(y, before_y)
    np.testing.assert_array_equal(p, before_p)


def test_full_summary_keeps_independent_roc_and_confusion_checks(monkeypatch):
    calls = []
    roc, confusion = m.roc_auc_score, m.confusion_matrix
    def checked_roc(*a, **kw):
        calls.append('roc')
        return roc(*a, **kw)
    def checked_confusion(*a, **kw):
        calls.append('confusion')
        return confusion(*a, **kw)
    monkeypatch.setattr(m, 'roc_auc_score', checked_roc)
    monkeypatch.setattr(m, 'confusion_matrix', checked_confusion)
    m.development_metrics(np.array([0, 1, 0, 1]), np.array([.1, .8, .6, .4]), 'classification')
    assert calls == ['confusion', 'roc']


def test_unqualified_version_and_large_inputs_keep_original_route(monkeypatch):
    y, p = np.array([0, 1]), np.array([.1, .9])
    with monkeypatch.context() as patch:
        patch.setattr(sklearn, '__version__', 'unqualified')
        assert m._shared_binary_curves(y, p) is None
    assert m._shared_binary_curves(np.resize(y, 2**18+1), np.resize(p, 2**18+1)) is None


def test_replaced_curve_callable_is_never_bypassed(monkeypatch):
    calls = []
    public = m.roc_curve
    def observed(*a, **kw):
        calls.append(True)
        return public(*a, **kw)
    monkeypatch.setattr(m, 'roc_curve', observed)
    m.development_metrics(np.array([0, 1]), np.array([.1, .9]), 'classification')
    assert calls == [True]


@pytest.mark.parametrize('n', [2, 19, 4096])
@pytest.mark.parametrize('style', ['constant', 'ties', 'ascending', 'random'])
def test_bounded_threshold_grouping_matches_reference_for_noncontiguous_inputs(n, style):
    rng = np.random.default_rng(164)
    y = np.resize([0, 1], 2*n)[::2].copy()
    y[::2], y[1::2] = 0, 1
    scores = rng.random(2*n)
    p = scores[::2]
    if style == 'constant':
        p[:] = .5
    elif style == 'ties':
        p[:] = rng.choice([0., .3, 1.], n)
    elif style == 'ascending':
        p[:] = np.linspace(0., 1., n)
    before_y, before_p = y.copy(), p.copy()
    actual = m._shared_binary_curves(y, p)
    # An unqualified installed library intentionally takes the public route.
    if actual is None:
        result = m.development_metrics(y, p, 'classification')
        assert result['roc_auc'] == metrics.roc_auc_score(y, p)
    else:
        fpr, tpr, precision, recall = actual
        for left, right in zip((fpr, tpr, precision, recall),
                               (*metrics.roc_curve(y, p)[:2], *metrics.precision_recall_curve(y, p)[:2])):
            np.testing.assert_array_equal(left, right)
    np.testing.assert_array_equal(y, before_y)
    np.testing.assert_array_equal(p, before_p)
