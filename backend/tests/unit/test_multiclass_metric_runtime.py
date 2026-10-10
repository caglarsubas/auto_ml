"""Independent AUC references, rejected inputs and native stopping equivalence."""
import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from evaluation.eval_utils import evaluate_multiclass
from modeling.declared_metric import metric_spec, metric_value
from tests.unit.test_declared_metric import fit

pytestmark = pytest.mark.unit


def probabilities(classes, mode, dtype):
    rng = np.random.default_rng(117)
    # Includes singleton and imbalanced classes, in non-class-sorted row order.
    y = np.repeat(np.arange(classes), np.arange(1, classes + 1))
    rng.shuffle(y)
    if mode == 'uniform':
        p = np.ones((len(y), classes))
    elif mode in ('perfect', 'inverted'):
        p = np.eye(classes)[y] if mode == 'perfect' else 1 - np.eye(classes)[y]
    else:
        p = rng.integers(1, 5, (len(y), classes)) if mode == 'ties' else rng.random((len(y), classes))
    p = p / p.sum(axis=1, keepdims=True)
    return y, p.astype(dtype)


def reference(y, p):
    # Match the declared normalization of native float32 probabilities.
    p = np.asarray(p, dtype=float)
    return roc_auc_score(y, p / p.sum(axis=1, keepdims=True), labels=np.arange(p.shape[1]),
                         multi_class='ovr', average='weighted')


@pytest.mark.parametrize('classes', [3, 5, 65])
@pytest.mark.parametrize('mode', ['random', 'ties', 'uniform', 'perfect', 'inverted'])
@pytest.mark.parametrize('dtype', ['float32', 'float64'])
def test_rank_metric_matches_independent_sklearn_with_ties_imbalance_and_many_classes(classes, mode, dtype):
    y, p = probabilities(classes, mode, dtype)
    fast = evaluate_multiclass(y, p, metric_names=['roc_auc'])
    full = evaluate_multiclass(y, p)
    assert fast['metrics']['roc_auc'] == pytest.approx(reference(y, p), abs=1e-12, rel=1e-12)
    assert fast['metrics']['roc_auc'] == pytest.approx(full['metrics']['roc_auc'], abs=1e-12, rel=1e-12)
    assert full['metric_semantics']['roc_auc_calculation'] == 'sklearn_roc_integration'
    assert fast['metric_semantics']['roc_auc_calculation'] == 'weighted_ovr_rank_auc_v1'
    assert fast['confusion_matrix'] == full['confusion_matrix']


@pytest.mark.parametrize('classes', [3, 65])
def test_class_and_row_permutations_preserve_weighted_mean(classes):
    y, _ = probabilities(classes, 'ties', 'float64')
    rng = np.random.default_rng(31)
    # Exact binary fractions keep row normalization unchanged under column
    # reordering. Many zeros/ties remain; no tie-breaking jitter is introduced.
    p = rng.multinomial(64, np.full(classes, 1 / classes), size=len(y)) / 64.
    columns, rows = rng.permutation(classes), rng.permutation(len(y))
    relabeled = np.argsort(columns)[y]
    original = evaluate_multiclass(y, p, metric_names=['roc_auc'])['metrics']['roc_auc']
    changed = evaluate_multiclass(relabeled[rows], p[rows][:, columns], metric_names=['roc_auc'])['metrics']['roc_auc']
    assert changed == pytest.approx(original, abs=1e-12, rel=1e-12)


def test_near_ties_follow_reference_normalization_without_rounding_or_jitter():
    y, p = probabilities(65, 'ties', 'float64')
    rng = np.random.default_rng(31)
    columns, rows = rng.permutation(65), rng.permutation(len(y))
    for labels, scores in [(y, p), (np.argsort(columns)[y][rows], p[rows][:, columns])]:
        # Reordering a floating-point row sum may change an almost-tied score
        # by one ULP. Preserve existing normalization and match its reference.
        result = evaluate_multiclass(labels, scores, metric_names=['roc_auc'])
        assert result['metrics']['roc_auc'] == pytest.approx(reference(labels, scores), abs=1e-12, rel=1e-12)


def test_rank_metric_matches_explicit_positive_negative_pair_count():
    y, p = probabilities(3, 'ties', 'float64')
    # Small independent definition: tied positive/negative pairs receive 1/2.
    values, weights = [], []
    for label in range(3):
        positive, negative = p[y == label, label], p[y != label, label]
        comparisons = positive[:, None] - negative[None, :]
        values.append(np.mean((comparisons > 0) + .5 * (comparisons == 0)))
        weights.append(len(positive))
    expected = np.average(values, weights=weights)
    assert evaluate_multiclass(y, p, metric_names=['roc_auc'])['metrics']['roc_auc'] == pytest.approx(expected)


@pytest.mark.parametrize('labels', [
    [0, .5, 2], [0, np.nan, 2], [0, np.inf, 2], [-1, 1, 2], [0, 1, 3],
    [[0], [1], [2]], ['0', '1', '2'], [0, None, 2], [0j, 1 + 0j, 2 + 0j], [],
])
@pytest.mark.parametrize('metric_names', [None, ['roc_auc']])
def test_invalid_labels_cannot_be_truncated_filtered_or_reinterpreted(labels, metric_names):
    with pytest.raises(ValueError):
        evaluate_multiclass(labels, np.eye(3), metric_names=metric_names)


@pytest.mark.parametrize('change', ['nan', 'infinity', 'negative', 'sum', 'columns', 'rows'])
@pytest.mark.parametrize('metric_names', [None, ['roc_auc']])
def test_invalid_probabilities_still_fail_before_either_calculation(change, metric_names):
    p = np.eye(3) * .8 + .2 / 3
    if change in ('nan', 'infinity', 'negative'):
        p[0, 0] = {'nan': np.nan, 'infinity': np.inf, 'negative': -.1}[change]
    elif change == 'sum':
        p *= 2
    elif change == 'columns':
        p = p[:, :2]
    else:
        p = p[:2]
    with pytest.raises(ValueError):
        evaluate_multiclass([0, 1, 2], p, metric_names=metric_names)


@pytest.mark.parametrize('classes', [3, 65])
def test_missing_classes_remain_unavailable_and_stopping_never_falls_back(classes):
    spec = metric_spec({'task': 'classification', 'class_mapping': [{}] * classes,
                        'objective': {'primary_metric': 'roc_auc'}})
    y, p = np.arange(classes - 1), np.full((classes - 1, classes), 1 / classes)
    assert evaluate_multiclass(y, p, metric_names=['roc_auc'])['metrics']['roc_auc'] is None
    assert evaluate_multiclass(y, p)['metrics']['roc_auc'] is None
    with pytest.raises(ValueError, match='unavailable.*no fallback'):
        metric_value(spec, y, p)


def test_full_assessment_remains_independent_and_metric_spec_names_calculation(monkeypatch):
    y, p = probabilities(3, 'random', 'float64')
    expected = reference(y, p)
    def broken(*args):
        raise RuntimeError('Injected rank implementation failure')
    monkeypatch.setattr('evaluation.eval_utils._weighted_ovr_rank_auc', broken)
    assert evaluate_multiclass(y, p)['metrics']['roc_auc'] == pytest.approx(expected)
    with pytest.raises(RuntimeError, match='Injected rank'):
        evaluate_multiclass(y, p, metric_names=['roc_auc'])
    spec = metric_spec({'task': 'classification', 'class_mapping': [{}] * 3,
                        'objective': {'primary_metric': 'roc_auc'}})
    assert spec['calculation'] == 'weighted_ovr_rank_auc_v1'
    assert len(spec['implementation_sha256']) == 64


@pytest.mark.parametrize('algorithm', ['xgboost', 'lightgbm', 'catboost'])
@pytest.mark.parametrize('classes', [3, 65])
def test_native_round_history_selected_model_and_replay_match_reference_callback(algorithm, classes, monkeypatch, tmp_path):
    adapter, parts = fit(algorithm, 'roc_auc', classes=classes, rounds=6, stopping=3)
    original = adapter.fit_receipt['stopping_evidence']
    observed = []
    def independently_evaluate(spec, labels, predictions):
        value = reference(labels.astype(int), predictions)
        observed.append(value)
        return value
    # CatBoost's metric object and XGBoost/LightGBM callbacks have distinct imports.
    monkeypatch.setattr('modeling.declared_metric.metric_value', independently_evaluate)
    monkeypatch.setattr('modeling.booster_adapters.metric_value', independently_evaluate)
    baseline, _ = fit(algorithm, 'roc_auc', classes=classes, rounds=6, stopping=3, parts=parts)
    expected = baseline.fit_receipt['stopping_evidence']
    assert observed
    np.testing.assert_allclose(original['validation_round_scores'], expected['validation_round_scores'], atol=1e-12, rtol=1e-12)
    assert original['prediction_rounds'] == expected['prediction_rounds']
    assert original['evaluated_rounds'] == expected['evaluated_rounds']
    assert original['selected_validation_score'] == pytest.approx(reference(parts[3], adapter.predict(parts[2])), abs=1e-6)
    np.testing.assert_allclose(adapter.predict(parts[2]), baseline.predict(parts[2]), atol=1e-12, rtol=1e-12)
    path = str(tmp_path / adapter.model_filename(1))
    adapter.save(path)
    replay = type(adapter).load(path, feature_names=list(parts[2].columns))
    np.testing.assert_allclose(replay.predict(parts[2]), adapter.predict(parts[2]), atol=1e-12, rtol=1e-12)
    # The public full assessment remains independent of the callback calculation.
    assert evaluate_multiclass(parts[3], replay.predict(parts[2]))['metrics']['roc_auc'] == pytest.approx(original['selected_validation_score'], abs=1e-6)
