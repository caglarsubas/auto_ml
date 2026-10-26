"""Complete assessment retains public references and independent diagnostics."""
import numpy as np
import pytest
from sklearn import metrics

from evaluation import eval_utils as evaluation
from modeling import development_assessment as development

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('dtype', [bool, np.int8, np.int64, np.uint64, np.float32, np.float64])
@pytest.mark.parametrize('size', [1, 2, 31, 1024])
def test_complete_binary_metrics_match_independent_public_references(dtype, size):
    rng = np.random.default_rng(size)
    for style, threshold in [('random', .5), ('tied', .25), ('zero', 0.), ('one', 1.), ('boundary', np.nan)]:
        y, p = rng.integers(0, 2, size).astype(dtype), rng.uniform(size=size)
        if style == 'tied':
            p = np.round(p, 1)
        elif style in {'zero', 'one'}:
            y[:], p[:] = int(style == 'one'), int(style == 'one')
        elif style == 'boundary':
            p = np.resize([0., np.nextafter(0., 1.), .5, np.nextafter(1., 0.), 1.], size)
        before_y, before_p = y.copy(), p.copy()
        pred = (p >= threshold).astype(int)
        expected = dict(f1=metrics.f1_score(y, pred, zero_division=0),
                        f2=metrics.fbeta_score(y, pred, beta=2, zero_division=0),
                        precision=metrics.precision_score(y, pred, zero_division=0),
                        recall=metrics.recall_score(y, pred, zero_division=0),
                        accuracy=metrics.accuracy_score(y, pred), mcc=metrics.matthews_corrcoef(y, pred),
                        log_loss=metrics.log_loss(y, np.clip(p, 1e-7, 1 - 1e-7), labels=[0, 1]),
                        brier=metrics.brier_score_loss(y, p))
        result = evaluation.evaluate_binary(y, p, threshold)
        observed = result['metrics']
        for name, value in expected.items():
            assert observed[name] == pytest.approx(value, rel=1e-14, abs=1e-14), name
        tn, fp, fn, tp = metrics.confusion_matrix(y, pred, labels=[0, 1]).ravel()
        assert observed['confusion'] == dict(tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp))
        if len(np.unique(y)) == 2:
            auc = metrics.roc_auc_score(y, p)
            fpr, tpr, _ = metrics.roc_curve(y, p)
            assert observed['roc_auc'] == auc
            assert observed['pr_auc'] == metrics.average_precision_score(y, p)
            assert observed['ks'] == np.max(np.abs(tpr - fpr))
            assert observed['gini'] == 2 * auc - 1
            assert result['curves']['roc'] == dict(fpr=fpr[::max(1, len(fpr)//100)].tolist(),
                                                 tpr=tpr[::max(1, len(tpr)//100)].tolist())
        else:
            assert observed['roc_auc'] is observed['pr_auc'] is None
        precision, recall, _ = metrics.precision_recall_curve(y, p)
        assert result['curves']['pr'] == dict(precision=precision[::max(1, len(precision)//100)].tolist(),
                                            recall=recall[::max(1, len(recall)//100)].tolist())
        assert observed['n_samples'] == size and observed['positive_rate'] == float(np.mean(y.astype(int)))
        assert len(result['threshold_table']) == 19
        np.testing.assert_array_equal(y, before_y)
        np.testing.assert_array_equal(p, before_p)


@pytest.mark.parametrize('scenario', ['empty', 'unknown_label', 'nan', 'infinite', 'negative', 'above_one', 'row_mismatch'])
def test_invalid_binary_inputs_still_fail_public_assessment(scenario):
    y, p = np.array([0, 1, 0, 1]), np.array([0., .25, .5, 1.])
    if scenario == 'empty':
        y, p = y[:0], p[:0]
    elif scenario == 'unknown_label':
        y[1] = 2
    elif scenario == 'row_mismatch':
        p = p[:-1]
    else:
        p[0] = {'nan': np.nan, 'infinite': np.inf, 'negative': -.001, 'above_one': 1.001}[scenario]
    with pytest.raises(ValueError):
        evaluation.evaluate_binary(y, p)


@pytest.mark.parametrize('function', ['roc_auc_score', 'confusion_matrix'])
def test_independent_public_binary_checks_remain_observable(monkeypatch, function):
    def refused(*args, **kwargs):
        raise RuntimeError('Independent public check reached')

    monkeypatch.setattr(evaluation, function, refused)
    with pytest.raises(RuntimeError, match='Independent public check'):
        evaluation.evaluate_binary([0, 1, 0, 1], [0., .25, .5, 1.])


@pytest.mark.parametrize('classes', [3, 5, 65])
@pytest.mark.parametrize('population', ['all', 'missing', 'ties'])
def test_multiclass_f1_aliases_share_one_public_result_per_call(monkeypatch, classes, population):
    rng = np.random.default_rng(classes)
    y = np.tile(np.arange(classes), 2)
    p = rng.uniform(size=(len(y), classes))
    if population == 'missing':
        y[y == classes - 1] = 0
    elif population == 'ties':
        p[:] = 1
    p /= p.sum(axis=1, keepdims=True)
    expected = metrics.f1_score(y, p.argmax(axis=1), labels=np.arange(classes), average='weighted', zero_division=0)
    original, calls = evaluation.f1_score, []

    def observed(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(evaluation, 'f1_score', observed)
    result = evaluation.evaluate_multiclass(y, p)
    assert result['metrics']['f1'] == result['metrics']['f1_weighted'] == expected
    assert calls == [True]
    calls.clear()
    changed = evaluation.evaluate_multiclass(y, p[:, ::-1])
    assert changed['metrics']['f1'] == metrics.f1_score(y, p[:, ::-1].argmax(axis=1), labels=np.arange(classes),
                                                     average='weighted', zero_division=0)
    assert calls == [True]


@pytest.mark.parametrize('size', [1, 3, 31])
@pytest.mark.parametrize('constant', [True, False])
def test_regression_mse_and_rmse_share_one_public_result_per_call(monkeypatch, size, constant):
    y = np.ones(size) if constant else np.arange(size, dtype=float)
    p = y + np.linspace(.25, 2., size)
    original, calls = development.mean_squared_error, []

    def observed(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(development, 'mean_squared_error', observed)
    result = development.development_metrics(y, p, 'regression')
    assert result['mse'] == metrics.mean_squared_error(y, p)
    assert result['rmse'] == np.sqrt(metrics.mean_squared_error(y, p))
    assert result['mae'] == metrics.mean_absolute_error(y, p)
    if constant or size < 2:
        assert result['r2'] is None
    else:
        assert result['r2'] == metrics.r2_score(y, p, force_finite=False)
    assert calls == [True]
    calls.clear()
    p[:] += 1.
    changed = development.development_metrics(y, p, 'regression')
    assert changed['mse'] == metrics.mean_squared_error(y, p) and changed['mse'] != result['mse']
    assert calls == [True]


def test_column_labels_retain_public_scalar_fallback_without_input_mutation(monkeypatch):
    y, p = np.array([[0], [1], [1], [0]]), np.array([0., .25, .5, 1.])
    y.flags.writeable = p.flags.writeable = False
    original, calls = evaluation.f1_score, []

    def observed(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(evaluation, 'f1_score', observed)
    assert evaluation.evaluate_binary(y, p)['metrics']['f1'] == metrics.f1_score(y, p >= .5)
    assert calls == [True] * 20 and not y.flags.writeable and not p.flags.writeable
