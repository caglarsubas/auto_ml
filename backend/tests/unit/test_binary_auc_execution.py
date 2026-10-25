"""Versioned binary stopping AUC stays comparable to independent ROC integration."""

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from modeling import development_assessment as assessment
from modeling.declared_metric import metric_spec, metric_value
from modeling.prediction_contract import PredictionContractError

pytestmark = pytest.mark.unit


def selected(y, p):
    return assessment.development_metrics(y, p, "classification", metric="roc_auc")["roc_auc"]


@pytest.mark.parametrize("size", [2, 3, 8, 31, 128, 4097])
@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("scenario", ["continuous", "tied", "constant", "reversed"])
def test_rank_auc_matches_independent_integration_with_ties_and_permutations(size, dtype, scenario):
    rng = np.random.default_rng(size)
    y = rng.integers(0, 2, size=size)
    y[:2] = [0, 1]
    p = rng.uniform(size=size)
    if scenario == "tied":
        p = np.round(p, 1)
    elif scenario == "constant":
        p = np.full(size, 0.5)
    elif scenario == "reversed":
        p = 1 - p
    p = p.astype(dtype)
    expected = roc_auc_score(y, p.astype(float))
    order = rng.permutation(size)
    assert selected(y, p) == pytest.approx(expected, rel=2e-14, abs=2e-14)
    assert selected(y[order], p[order]) == pytest.approx(expected, rel=2e-14, abs=2e-14)
    assert assessment.development_metrics(y, p, "classification")["roc_auc"] == expected


@pytest.mark.parametrize("task,classes,metric,calculation", [
    ("classification", 2, "roc_auc", "binary_rank_auc_v1"),
    ("classification", 3, "roc_auc", "weighted_ovr_rank_auc_v1"),
    ("classification", 65, "roc_auc", "weighted_ovr_rank_auc_v1"),
    ("classification", 2, "log_loss", "trusted_reference_metrics_v1"),
    ("classification", 3, "log_loss", "trusted_reference_metrics_v1"),
    ("regression", 0, "rmse", "trusted_reference_metrics_v1"),
    ("classification", 2, "accuracy", "trusted_reference_metrics_v1"),
    ("regression", 0, "r2", "trusted_reference_metrics_v1"),
])
def test_fit_evidence_names_the_actual_calculation_and_reference(task, classes, metric, calculation):
    spec = metric_spec({"task": task, "class_mapping": [{}] * classes, "objective": {"primary_metric": metric}})
    assert spec["calculation"] == calculation
    if calculation == "binary_rank_auc_v1":
        assert spec["calculation_details"]["maximum_exact_rank_rows"] == assessment._MAX_BINARY_RANK_ROWS
        assert spec["calculation_details"]["independent_assessment_calculation"] == "sklearn_roc_integration"
        assert spec["calculation_details"]["larger_partition_calculation"] == "sklearn_roc_integration"
    else:
        assert "calculation_details" not in spec


@pytest.mark.parametrize("labels", [[], [0], [1], [0, 0], [1, 1]])
def test_undefined_partition_stays_unavailable_without_fallback(labels):
    y = np.asarray(labels)
    p = np.linspace(0, 1, len(y))
    assert selected(y, p) is None
    spec = {"task": "classification", "class_count": 2, "cost_matrix": {}, "primary_metric": "roc_auc"}
    with pytest.raises(PredictionContractError, match="unavailable in this partition"):
        metric_value(spec, y, p)


@pytest.mark.parametrize("invalid", ["rows", "columns", "nan", "infinite", "negative", "above_one", "label"])
def test_binary_validation_precedes_either_auc_calculation(invalid):
    y = np.array([0, 1, 0, 1])
    p = np.array([0.0, 0.4, 0.4, 1.0])
    if invalid == "rows":
        p = p[:-1]
    elif invalid == "columns":
        p = np.column_stack([p, 1 - p])
    elif invalid == "label":
        y[0] = 2
    else:
        p[0] = {"nan": np.nan, "infinite": np.inf, "negative": -0.1, "above_one": 1.1}[invalid]
    with pytest.raises(ValueError):
        selected(y, p)
    with pytest.raises(ValueError):
        assessment.development_metrics(y, p, "classification")


@pytest.mark.parametrize("scenario", ["continuous", "tied", "perfect", "reversed", "constant"])
def test_positive_class_reversal_preserves_auc_meaning(scenario):
    y = np.array([0, 1] * 100)
    p = np.random.default_rng(153).uniform(size=len(y))
    if scenario == "tied":
        p = np.round(p, 1)
    elif scenario == "perfect":
        p = y.astype(float)
    elif scenario == "reversed":
        p = 1 - y.astype(float)
    elif scenario == "constant":
        p = np.full(len(y), 0.5)
    assert selected(1 - y, p) == pytest.approx(1 - roc_auc_score(y, p), rel=2e-14, abs=2e-14)


@pytest.mark.parametrize("location", ["subnormal", "near_one"])
def test_float64_probability_order_is_not_lost_to_complement_rounding(location):
    y = np.array([0, 1, 0, 1])
    if location == "subnormal":
        p = np.nextafter(0.0, 1.0) * np.arange(4)
    else:
        epsilon = np.finfo(float).eps
        p = 1 - epsilon * np.array([3, 1, 2, 0])
    expected = roc_auc_score(y, p)
    assert selected(y, p) == pytest.approx(expected, rel=2e-14, abs=2e-14)
    assert assessment.development_metrics(y, p, "classification")["roc_auc"] == expected


def test_stopping_rank_path_does_not_replace_the_independent_assessment(monkeypatch):
    y = np.array([0, 1, 0, 1])
    p = np.array([0.0, 0.4, 0.4, 1.0])
    expected = roc_auc_score(y, p)

    def independent(*args, **kwargs):
        raise RuntimeError("Independent assessment reference reached")

    monkeypatch.setattr(assessment, "roc_auc_score", independent)
    assert selected(y, p) == pytest.approx(expected, rel=2e-14, abs=2e-14)
    with pytest.raises(RuntimeError, match="Independent assessment"):
        assessment.development_metrics(y, p, "classification")


def test_partitions_beyond_exact_rank_bound_keep_the_reference_implementation(monkeypatch):
    y = np.array([0, 1] * 6)
    p = np.linspace(0, 1, len(y))
    calls = []

    def reference(labels, probabilities):
        calls.append((labels.copy(), probabilities.copy()))
        return roc_auc_score(labels, probabilities)

    monkeypatch.setattr(assessment, "_MAX_BINARY_RANK_ROWS", 7, raising=False)
    monkeypatch.setattr(assessment, "roc_auc_score", reference)
    assert selected(y, p) == roc_auc_score(y, p)
    assert len(calls) == 1
    assert np.array_equal(calls[0][0], y) and np.array_equal(calls[0][1], p)
