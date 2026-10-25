"""Selected metrics and export metadata retain independent reference semantics."""

import json
from importlib import metadata

import numpy as np
import pytest

from deployment import native_candidate
from modeling import development_assessment
from modeling.declared_metric import metric_value
from modeling.prediction_contract import PredictionContractError
from tests.unit.test_durable_training_search import world  # noqa: F401
from tests.unit.test_native_protected_assessment import candidate  # noqa: F401

pytestmark = pytest.mark.unit
PROBABILITY_METRICS = ["roc_auc", "pr_auc", "ks", "log_loss", "brier"]
ALL_METRICS = PROBABILITY_METRICS + ["accuracy", "f1", "precision", "recall", "expected_cost"]


@pytest.mark.parametrize("metric", PROBABILITY_METRICS)
@pytest.mark.parametrize("population", ["both", "zero", "one"])
def test_probability_objectives_do_not_depend_on_threshold_statistics(monkeypatch, metric, population):
    y = np.array([0, 1, 0, 1]) if population == "both" else np.full(4, int(population == "one"))
    p = np.array([0.0, 0.4, 0.4, 1.0])
    expected = development_assessment.development_metrics(y, p, "classification")[metric]

    def unrelated(*args, **kwargs):
        raise AssertionError("An unrequested threshold statistic was evaluated")

    monkeypatch.setattr(development_assessment, "confusion_matrix", unrelated)
    observed = development_assessment.development_metrics(y, p, "classification", metric=metric)[metric]
    spec = {"task": "classification", "class_count": 2, "cost_matrix": {}, "primary_metric": metric}
    if expected is None:
        assert observed is None
        with pytest.raises(PredictionContractError, match="unavailable in this partition"):
            metric_value(spec, y, p)
    else:
        assert observed == pytest.approx(expected, rel=1e-14, abs=1e-14)
        assert metric_value(spec, y, p) == pytest.approx(expected, rel=1e-14, abs=1e-14)
    with pytest.raises(AssertionError, match="unrequested threshold"):
        development_assessment.development_metrics(y, p, "classification")


@pytest.mark.parametrize("metric", ALL_METRICS)
@pytest.mark.parametrize("threshold", [0.0, 0.5, 1.0])
def test_selected_values_match_complete_reference_metrics(metric, threshold):
    rng = np.random.default_rng(153)
    y = np.array([0, 1] * 20)
    p = np.round(rng.uniform(size=len(y)), 1)
    costs = {"fn_cost": 7.25, "fp_cost": 0.125}
    expected = development_assessment.development_metrics(y, p, "classification", costs=costs, threshold=threshold)
    selected = development_assessment.development_metrics(
        y, p, "classification", costs=costs, threshold=threshold, metric=metric
    )
    assert list(selected) == [metric]
    assert selected[metric] == pytest.approx(expected[metric], rel=1e-14, abs=1e-14)


class TextDistribution(metadata.Distribution):
    def __init__(self, version):
        self.text = f"Metadata-Version: 2.1\nVersion: {version}\n\n"
        self.reads = 0
        self.failure = None

    def read_text(self, name):
        self.reads += 1
        if self.failure:
            raise self.failure
        return self.text if name == "METADATA" else None

    def locate_file(self, path):
        raise AssertionError("Version lookup does not locate installed code")


def export(job):
    return native_candidate.export_candidate(job.pk, job.dataset_id, job.project_id, job.result, job.result_sha256)


def distributions(monkeypatch):
    values = {name: TextDistribution(metadata.version(name)) for name in ("numpy", "pandas", "xgboost")}
    monkeypatch.setattr(metadata.Distribution, "from_name", classmethod(lambda cls, name: values[name]))
    return values


@pytest.mark.django_db(transaction=True)
def test_warm_candidate_export_observes_current_metadata_and_scoring_rejects_version_drift(candidate, monkeypatch):
    values = distributions(monkeypatch)
    first = json.loads(export(candidate.trained))
    version = first["scoring_runtime"]["packages"]["numpy"]
    changed = ("9" if version[0] != "9" else "8") + version[1:]
    values["numpy"].text = values["numpy"].text.replace(f"Version: {version}\n", f"Version: {changed}\n")
    raw = export(candidate.trained)
    second = json.loads(raw)
    assert second["scoring_runtime"]["packages"]["numpy"] == changed
    assert first["result"] == second["result"]
    assert all(value.reads == 2 for value in values.values())
    features = candidate.trained.result["features"]
    input_bytes = (",".join(features) + "\n" + ",".join("1" for _ in features) + "\n").encode()
    with pytest.raises(ValueError, match="candidate_scoring_runtime_changed"):
        native_candidate.score(raw, native_candidate.sha(raw), input_bytes)


@pytest.mark.parametrize("failure", ["missing", "unreadable"])
@pytest.mark.django_db(transaction=True)
def test_warm_candidate_export_never_hides_a_new_metadata_failure(candidate, monkeypatch, failure):
    values = distributions(monkeypatch)
    export(candidate.trained)
    if failure == "unreadable":
        values["numpy"].failure = OSError("Owned metadata read refused")
        error = OSError
    else:
        def missing(cls, name):
            raise metadata.PackageNotFoundError(name)

        monkeypatch.setattr(metadata.Distribution, "from_name", classmethod(missing))
        error = metadata.PackageNotFoundError
    with pytest.raises(error):
        export(candidate.trained)
