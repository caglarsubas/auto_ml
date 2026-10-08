"""Search semantics against independent metrics, actual boosters and API failure paths."""

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_squared_error, average_precision_score

from modeling import sfs_utils as sfs
from modeling.sfs_objective import (
    prepare_search,
    resolve_objective,
    improvement_pct,
    stopping_decision,
    validate_resume,
)

pytestmark = pytest.mark.unit


def data(task="regression", metric="rmse", constant=False):
    rng = np.random.default_rng(21)
    X = pd.DataFrame({"x": rng.normal(size=90), "noise": rng.normal(size=90)})
    y = pd.Series(np.ones(90) if constant else (2 * X.x if task == "regression" else (X.x > 0).astype(int)))
    contract = {"class_mapping": [] if task == "regression" else [{}, {}], "objective": {"primary_metric": metric}}
    context = {
        "task": task,
        "frame": X,
        "labels": y,
        "prediction_contract": contract,
        "target_column": "outcome",
        "split_meta": {"strategy": "random"},
    }
    return X.iloc[:60], y.iloc[:60], X.iloc[60:], y.iloc[60:], context


def run(parts, **options):
    X, y, V, z, context = parts
    params = dict(
        X_train=X,
        y_train=y,
        X_test=V,
        y_test=z,
        X_train_raw=X,
        X_test_raw=V,
        task=context["task"],
        validation_context=context,
        methods=["forward"],
        cv_folds=2,
        stopping_criteria={
            "metrics": [{"metric": context["prediction_contract"]["objective"]["primary_metric"], "pct_change": 0}],
            "min_features": 1,
            "max_features": 1,
        },
    )
    params.update(options)
    return sfs.run_sfs_with_progress(**params)


@pytest.mark.parametrize("algorithm", ["xgboost", "lightgbm", "catboost"])
@pytest.mark.parametrize(
    "task,metric", [("regression", "rmse"), ("classification", "pr_auc"), ("classification", "expected_cost")]
)
def test_real_search_records_declared_objective_complete_folds_and_exact_fit(algorithm, task, metric):
    parts = data(task, metric)
    result = run(parts, algorithm=algorithm)
    assert result["status"] == "completed", result.get("error")
    step = result["forward"][0]
    assert step["selection_objective"]["primary_metric"] == metric
    assert result["selection_objective"]["direction"] == ("maximize" if metric == "pr_auc" else "minimize")
    assert step["cv_evidence"]["metric_coverage"][metric]["status"] == "complete"
    assert len(step["cv_evidence"]["fold_metrics"]) == 2
    assert step["search_basis_sha256"] == result["resume_basis"]["sha256"]
    assert step["fit_receipt"]["train"]["features"] == step["selected_features"]
    assert step["fit_receipt"]["num_boost_round"] == 100
    if task == "regression":
        assert "cv_roc_auc" not in step and "cv_pr_auc" not in step
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("task,metric", [("regression", "rmse"), ("classification", "pr_auc")])
def test_metric_value_matches_independent_prediction_and_rank_direction(task, metric):
    parts = data(task, metric)
    result = run(parts)
    X, y, V, z, _ = parts
    step = result["forward"][0]
    adapter = sfs._sfs_fit(
        "xgboost",
        X[step["selected_features"]],
        y,
        V[step["selected_features"]],
        z,
        sfs._sfs_booster_params(task, 0),
        task=task,
    )
    p = (
        adapter.predict(V[step["selected_features"]])
        if task == "regression"
        else adapter.predict_proba(V[step["selected_features"]])
    )
    expected = np.sqrt(mean_squared_error(z, p)) if task == "regression" else average_precision_score(z, p)
    assert step["test_" + metric] == pytest.approx(expected)
    scores = step["cv_candidate_scores"]
    best = min(scores, key=scores.get) if task == "regression" else max(scores, key=scores.get)
    assert step["feature_name"] == best


def test_constant_target_supports_loss_but_never_invents_r2():
    result = run(data(constant=True))
    assert result["status"] == "completed"
    row = result["forward"][0]
    assert row["cv_r2"] is None and row["test_r2"] is None
    assert row["cv_evidence"]["metric_coverage"]["r2"]["status"] == "unavailable"
    failed = run(
        data(constant=True), stopping_criteria={"metrics": [{"metric": "r2", "pct_change": 0}], "max_features": 1}
    )
    assert failed["status"] == "error" and not failed["forward"]
    assert "Stopping metric r2 is unavailable" in failed["error"]
    failed_primary = run(data(metric="r2", constant=True))
    assert failed_primary["status"] == "error" and "unavailable" in failed_primary["error"]


@pytest.mark.parametrize(
    "criteria,match",
    [
        ({"primary_metric": "r2"}, "contradicts"),
        ({"metrics": [{"metric": "roc_auc"}]}, "unsupported for regression"),
        ({"metrics": [{"metric": "rmse", "pct_change": -1}]}, "nonnegative"),
        ({"metrics": [{"metric": "rmse", "pct_change": float("nan")}]}, "finite"),
        ({"metrics": [{"metric": "rmse"}, {"metric": "rmse"}]}, "unique"),
    ],
)
def test_invalid_or_contradictory_criteria_fail_closed(criteria, match):
    result = run(data(), stopping_criteria=criteria)
    assert result["status"] == "error" and match in result["error"]


def test_aliases_resolve_without_redefining_accepted_task_or_direction():
    context = data("classification", "average_precision")[-1]
    objective, criteria = resolve_objective("classification", context, {"metrics": [{"metric": "pr_auc"}]})
    assert objective["primary_metric"] == criteria[0]["metric"] == "pr_auc"
    context["prediction_contract"]["objective"]["direction"] = "minimize"
    with pytest.raises(ValueError, match="direction contradicts"):
        resolve_objective("classification", context, {})


@pytest.mark.parametrize(
    "metric,before,after,expected", [("rmse", 10, 8, 20), ("r2", -0.5, -0.4, 20), ("r2", 0.5, 0.4, -20)]
)
def test_improvement_direction_handles_losses_and_negative_r2(metric, before, after, expected):
    assert improvement_pct(after, before, metric) == pytest.approx(expected)
    criteria = [{"metric": metric, "pct_change": 5}]
    _, reasons = stopping_decision({metric: after}, {metric: before}, criteria, "backward")
    assert bool(reasons) == (expected < -5)


def test_zero_baseline_is_unavailable_and_zero_threshold_disables_gate():
    assert improvement_pct(1, 0, "rmse") is None
    changes, reasons = stopping_decision({"rmse": 1}, {"rmse": 0}, [{"metric": "rmse", "pct_change": 5}], "forward")
    assert changes == {"rmse": None} and "undefined" in reasons[0]
    assert stopping_decision({"rmse": 1}, {"rmse": 0}, [{"metric": "rmse", "pct_change": 0}], "forward")[1] == []


@pytest.mark.parametrize("candidate,accepted", [(12, False), (8, True), (10.2, True)])
def test_backward_first_removal_uses_full_feature_baseline(monkeypatch, candidate, accepted):
    monkeypatch.setattr(sfs, "_selection_cv", lambda *args: {"metrics": {"rmse": 10}})
    monkeypatch.setattr(
        sfs, "_run_backward_step", lambda *args, **kw: {"cv_rmse": candidate, "selected_features": ["x"]}
    )
    result = run(
        data(),
        methods=["backward"],
        stopping_criteria={"metrics": [{"metric": "rmse", "pct_change": 5}], "min_features": 1},
    )
    assert result["status"] == "completed"
    assert bool(result["backward"]) is accepted
    assert result["backward_remaining_features"] == (["x"] if accepted else ["x", "noise"])
    assert result["baselines"]["backward"]["metrics"]["rmse"] == 10
    if not accepted:
        assert result["rejected_steps"][0]["pct_changes"]["rmse"] == -20


def test_mid_search_failure_retains_evidence_without_completion(monkeypatch):
    original = sfs._run_forward_step

    def step(*args, **kw):
        if args[7] == 2:
            raise ValueError("deliberate CV failure")
        return original(*args, **kw)

    monkeypatch.setattr(sfs, "_run_forward_step", step)
    updates = []
    result = run(data(), stopping_criteria={"max_features": 2}, status_callback=updates.append)
    assert result["status"] == "error" and len(result["forward"]) == 1
    assert updates[-1]["status"] == "error" and len(updates[-1]["completed_steps"]) == 1
    assert all(update["status"] != "completed" for update in updates)


def test_cancellation_resume_keeps_full_step_evidence_and_rejects_changed_basis():
    parts = data()
    flag = {}
    updates = []

    def cancel_after_step(info):
        updates.append(info)
        if info["completed_steps"]:
            flag["stop_requested"] = True

    stopped = run(parts, stopping_criteria={"max_features": 2}, stop_flag=flag, status_callback=cancel_after_step)
    assert stopped["status"] == "stopped"
    state = stopped["resume_state"]
    assert state["completed_steps"][0]["selected_features"]
    assert state["completed_steps"][0]["cv_evidence"]["metric_coverage"]["rmse"]["n_total"] == 2
    resumed = run(parts, stopping_criteria={"max_features": 2}, resume_state=state)
    assert resumed["status"] == "completed" and len(resumed["forward"]) == 2
    changed = run(parts, stopping_criteria={"max_features": 2}, resume_state=state, top_k=1)
    assert changed["status"] == "error" and "different or unverified" in changed["error"]


@pytest.mark.parametrize(
    "change", ["labels", "rows", "features", "folds", "threshold", "execution", "validation", "raw"]
)
def test_resume_binds_inputs_objective_constraints_and_budget(change):
    X, y, V, z, context = data()
    args = [X, y, V, z, "regression", "xgboost", context, {}, 2, 3, ["forward"], None, "recorded-run", 1]
    basis = prepare_search(*args)[-1]
    altered = copy.deepcopy(args)
    if change == "labels":
        altered[1].iloc[0] += 1
    if change == "rows":
        altered[0], altered[1] = altered[0].iloc[::-1], altered[1].iloc[::-1]
    if change == "features":
        altered[11] = ["x"]
    if change == "folds":
        altered[8] = 3
    if change == "threshold":
        altered[7] = {"metrics": [{"metric": "rmse", "pct_change": 5}]}
    if change == "execution":
        altered[12] = "new-run"
    if change == "validation":
        altered[6]["split_meta"]["strategy"] = "group"
    if change == "raw":
        altered[6]["frame"].iloc[0, 0] += 1
    next_basis = prepare_search(*altered)[-1]
    with pytest.raises(ValueError, match="different or unverified"):
        validate_resume({"resume_basis": basis}, next_basis)
    with pytest.raises(ValueError, match="unverified"):
        validate_resume({"completed_steps": []}, basis)
    validate_resume({"resume_basis": basis}, basis)


@pytest.mark.parametrize("failure", ["search", "publication"])
def test_api_failed_search_preserves_error_and_never_publishes(monkeypatch, _use_tmp_media, settings, failure):
    from rest_framework.test import APIRequestFactory
    from modeling.views import SFSStartView, SFSResultsView, SFS_PROGRESS

    X, y, V, z, context = data()
    saved = {
        "X_train": X,
        "y_train": y,
        "X_valid": V,
        "y_valid": z,
        "task": "regression",
        "algorithm": "xgboost",
        "validation_context": context,
        "prediction_contract": context["prediction_contract"],
        "execution_id": "source-run",
    }
    root = Path(settings.MEDIA_ROOT)
    (root / "train_data").mkdir()
    (root / "train_data" / "1_train_data.pkl").touch()
    monkeypatch.setattr("modeling.views.load_development_data", lambda *args: saved)
    called = []

    def fail(**kwargs):
        called.append(kwargs)
        if failure == "publication":
            kwargs["status_callback"]({"status": "completed", "completed_steps": []})
            assert SFS_PROGRESS[1]["status"] == "running"
            return {"status": "completed", "forward": [{"selected_features": ["x"]}], "backward": []}
        return {"status": "error", "error": "Objective unavailable", "forward": [], "backward": []}

    monkeypatch.setattr("modeling.views.run_sfs_with_progress", fail)
    if failure == "publication":

        def refit_failure(*args, **kwargs):
            raise ValueError("deliberate refit failure")

        monkeypatch.setattr(sfs, "_sfs_fit", refit_failure)
    monkeypatch.setattr(
        "modeling.views.publish_candidate", lambda *args, **kwargs: pytest.fail("Failed selection cannot publish")
    )

    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr("modeling.views.threading.Thread", InlineThread)
    factory = APIRequestFactory()
    request = factory.post(
        "/sfs/start/",
        {"file_id": 1, "cv_folds": 4, "stopping_criteria": {"metrics": [{"metric": "rmse"}]}},
        format="json",
    )
    response = SFSStartView.as_view()(request)
    assert response.status_code == 200
    assert called[0]["cv_folds"] == 4
    assert SFS_PROGRESS[1]["status"] == "error"
    result = SFSResultsView.as_view()(factory.get("/sfs/results/1/"), file_id=1)
    assert result.data["status"] == "error" and result.data["sfs_completed"] is False
    assert result.data["error"] == (
        "Candidate publication failed: deliberate refit failure"
        if failure == "publication"
        else "Objective unavailable"
    )
    request = factory.post("/sfs/start/", {"file_id": 1, "resume": True}, format="json")
    assert SFSStartView.as_view()(request).status_code == 409
    SFS_PROGRESS.pop(1, None)


@pytest.mark.parametrize("metric,winner", [("expected_cost", "lower_cost"), ("roc_auc", "better_auc")])
def test_screening_uses_cost_instead_of_auc_when_the_declaration_requires_it(monkeypatch, metric, winner):
    from modeling.development_assessment import development_metrics

    X = pd.DataFrame({"better_auc": [0.7, 0.9, 0.7, 0.9] * 4, "lower_cost": [0.1, 0.6, 0.2, 0.15] * 4})
    y = pd.Series([0, 1, 0, 1] * 4)

    class ProbabilityAdapter:
        fit_receipt = {}

        def predict_proba(self, values):
            return values.iloc[:, 0].to_numpy()

        def shap_model(self):
            return object()

        def gain_importance(self):
            return []

    monkeypatch.setattr(sfs, "_sfs_fit", lambda *args, **kwargs: ProbabilityAdapter())
    monkeypatch.setattr(sfs, "compute_shap_importance", lambda *args: {})

    def cv(values, *args):
        # Independently known scores from the controlled prediction fixture.
        return {"metrics": development_metrics(y, values.iloc[:, 0], "classification"), "fold_provenance": []}

    monkeypatch.setattr(sfs, "_selection_cv", cv)
    contract = {"objective": {"primary_metric": metric}}
    result = sfs.run_sfs_with_progress(
        X,
        y,
        X,
        y,
        X,
        X,
        ["forward"],
        {"max_features": 1},
        task="classification",
        prediction_contract=contract,
        cv_folds=2,
        top_k=1,
    )
    assert result["status"] == "completed"
    step = result["forward"][0]
    assert step["feature_name"] == winner and step["top_k_evaluated"] == [winner]
    assert step["screening_scores"]["lower_cost"] == (0.25 if metric == "expected_cost" else 0.75)


def test_resume_rejects_changed_runtime_and_native_configuration(monkeypatch):
    parts = data()
    stopped = run(parts, stop_flag={"stop_requested": True})
    state = stopped["resume_state"]
    assert state["resume_basis"]["native_fit_params"]["eval_metric"] == "rmse"
    assert state["resume_basis"]["implementation_sha256"]["sfs_utils.py"]
    monkeypatch.setattr("modeling.sfs_objective.runtime_versions", lambda algorithm: {"python": "changed"})
    result = run(parts, resume_state=state)
    assert result["status"] == "error" and "different or unverified" in result["error"]


@pytest.mark.parametrize('single_class', ['screening', 'fold'])
def test_available_brier_objective_cannot_hide_unavailable_native_early_stopping(single_class):
    X, y, V, z, context = data('classification', 'brier')
    if single_class == 'screening':
        z = z * 0
        context['labels'].loc[z.index] = z
    else:
        y = y.copy()
        y.iloc[:20] = np.tile([0, 1], 10)
        y.iloc[20:] = 0
        context['labels'].loc[y.index] = y
        context['frame']['date'] = pd.date_range('2025-01-01', periods=90)
        context['split_meta'] = {'strategy': 'oot', 'split_config': {'date_column': 'date'}}
    result = run((X, y, V, z, context))
    assert result['status'] == 'error' and result['forward'] == []
    assert 'AUC early stopping' in result['error']
    assert 'both encoded classes' in result['error']
