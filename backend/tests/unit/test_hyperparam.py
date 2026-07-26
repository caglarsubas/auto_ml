"""Unit tests - hyperparameter search engine.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

from tests.unit._shared import (
    _hp_space,
    _hp_synthetic,
)


@pytest.mark.unit
class TestHyperparamParamSpace:
    """validate_param_space clamps user input to safe bounds and never
    returns an empty enabled set (the search would have nothing to do)."""

    def test_swaps_inverted_min_max(self):
        from modeling.hyperparam_utils import validate_param_space
        clean, warns = validate_param_space({'max_depth': {'min': 12, 'max': 3}})
        assert clean['max_depth']['min'] <= clean['max_depth']['max']
        assert any('swapped' in w for w in warns)

    def test_clamps_to_hard_bounds(self):
        from modeling.hyperparam_utils import validate_param_space
        clean, _ = validate_param_space({'max_depth': {'min': -5, 'max': 999}})
        assert clean['max_depth']['min'] >= 1
        assert clean['max_depth']['max'] <= 20

    def test_enabled_toggle_respected(self):
        from modeling.hyperparam_utils import validate_param_space
        clean, _ = validate_param_space({'gamma': {'enabled': True}})
        assert clean['gamma']['enabled'] is True

    def test_fallback_when_nothing_enabled(self):
        from modeling.hyperparam_utils import validate_param_space, DEFAULT_PARAM_SPACE
        space = {k: {'enabled': False} for k in DEFAULT_PARAM_SPACE}
        clean, warns = validate_param_space(space)
        assert any(s.get('enabled') for s in clean.values())
        assert any('enabled' in w for w in warns)

    def test_none_payload_returns_defaults(self):
        from modeling.hyperparam_utils import validate_param_space
        clean, warns = validate_param_space(None)
        assert 'learning_rate' in clean and clean['learning_rate']['enabled'] is True

@pytest.mark.unit
class TestHyperparamMetrics:
    """_compute_metrics returns every catalogued metric and handles the
    degenerate single-class fold (ROC-AUC undefined) without raising."""

    def test_all_metric_keys_present(self):
        from modeling.hyperparam_utils import _compute_metrics, METRIC_NAMES
        out = _compute_metrics(np.array([0, 1, 0, 1]), np.array([0.2, 0.8, 0.4, 0.6]))
        assert set(METRIC_NAMES).issubset(out.keys())

    def test_single_class_roc_auc_is_nan(self):
        from modeling.hyperparam_utils import _compute_metrics
        out = _compute_metrics(np.array([1, 1, 1, 1]), np.array([0.6, 0.7, 0.8, 0.9]))
        assert np.isnan(out['roc_auc'])
        assert np.isnan(out['pr_auc'])

    def test_perfect_separation_scores(self):
        from modeling.hyperparam_utils import _compute_metrics
        out = _compute_metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]))
        assert out['roc_auc'] == 1.0
        assert out['f1'] == 1.0 and out['precision'] == 1.0 and out['recall'] == 1.0
        assert out['accuracy'] == 1.0

    def test_regression_metrics_r2_rmse_mae(self):
        from modeling.hyperparam_utils import _compute_metrics, REGRESSION_METRICS
        y = np.array([1.0, 2.0, 3.0, 4.0])
        pred = np.array([1.1, 1.9, 3.2, 3.8])
        out = _compute_metrics(y, pred, task='regression')
        assert set(REGRESSION_METRICS).issubset(out.keys())
        assert out['r2'] > 0.9
        assert out['rmse'] < 0.3
        assert np.isnan(out['roc_auc'])

    def test_build_xgb_params_regression_objective(self):
        from modeling.hyperparam_utils import _build_xgb_params
        params, n = _build_xgb_params(
            {'n_estimators': 50, 'max_depth': 3, 'learning_rate': 0.1},
            nthread=1, has_cat=False, task='regression',
        )
        assert params['objective'] == 'reg:squarederror'
        assert params['eval_metric'] == 'rmse'
        assert 'scale_pos_weight' not in params
        assert n == 50

    def test_f2_weights_recall_more_than_f1(self):
        from modeling.hyperparam_utils import _compute_metrics
        # One false negative: recall < precision -> F2 < F1 is FALSE; F2 emphasizes recall.
        y = np.array([1, 1, 1, 0])
        p = np.array([0.9, 0.9, 0.2, 0.1])  # one positive missed
        out = _compute_metrics(y, p)
        assert out['f2'] <= out['f1']  # missing positives penalizes F2 at least as much

@pytest.mark.unit
class TestHyperparamSampling:
    """Random sampling honors type/bounds; disabled params fall back to fixed."""

    def test_int_sampling_within_bounds(self):
        from modeling.hyperparam_utils import _sample_value
        rng = np.random.default_rng(1)
        spec = {'type': 'int', 'min': 2, 'max': 8}
        vals = [_sample_value(spec, rng) for _ in range(50)]
        assert all(isinstance(v, int) and 2 <= v <= 8 for v in vals)

    def test_float_log_sampling_within_bounds(self):
        from modeling.hyperparam_utils import _sample_value
        rng = np.random.default_rng(1)
        spec = {'type': 'float', 'min': 0.01, 'max': 0.3, 'log': True}
        vals = [_sample_value(spec, rng) for _ in range(50)]
        assert all(0.01 <= v <= 0.3 for v in vals)

    def test_disabled_param_uses_fixed_value(self):
        from modeling.hyperparam_utils import _sample_config, DEFAULT_FIXED_PARAMS
        space = _hp_space('max_depth')
        rng = np.random.default_rng(0)
        cfg = _sample_config(space, DEFAULT_FIXED_PARAMS, rng)
        assert cfg['learning_rate'] == DEFAULT_FIXED_PARAMS['learning_rate']
        assert 2 <= cfg['max_depth'] <= 10

    def test_grid_values_int_dedup_and_categorical(self):
        from modeling.hyperparam_utils import _grid_values
        ints = _grid_values({'type': 'int', 'min': 1, 'max': 3}, points=8)
        assert ints == sorted(set(ints)) and all(isinstance(v, int) for v in ints)
        cats = _grid_values({'type': 'categorical', 'values': ['a', 'b']}, points=8)
        assert cats == ['a', 'b']

@pytest.mark.unit
class TestHyperparamXgbParams:
    """Sklearn-style names are mapped to XGBoost learning-API keys and
    n_estimators is split out as num_boost_round."""

    def test_param_mapping(self):
        from modeling.hyperparam_utils import _build_xgb_params
        cfg = {'n_estimators': 123, 'max_depth': 5, 'learning_rate': 0.07,
               'reg_alpha': 1.5, 'reg_lambda': 2.5, 'subsample': 0.7}
        params, num_round = _build_xgb_params(cfg, nthread=1, has_cat=False)
        assert num_round == 123 and 'n_estimators' not in params
        assert params['eta'] == 0.07
        assert params['alpha'] == 1.5 and params['lambda'] == 2.5
        assert params['max_depth'] == 5 and isinstance(params['max_depth'], int)
        assert params['nthread'] == 1

@pytest.mark.unit
class TestHyperparamGuidance:
    """_build_guidance suggests zoom-out at range edges and zoom-in for an
    interior CV peak (the verbal next-search-space guidance)."""

    def test_edge_peak_suggests_zoom_out(self):
        from modeling.hyperparam_utils import _build_guidance
        curves = [{'param': 'max_depth', 'type': 'int', 'values': [2, 4, 6, 8],
                   'cv_mean': [0.90, 0.85, 0.80, 0.70],
                   'train_mean': [0.95, 0.96, 0.97, 0.98]}]
        g = _build_guidance(curves, 'roc_auc')
        assert g and g[0]['type'] == 'zoom_out'

    def test_interior_peak_suggests_zoom_in(self):
        from modeling.hyperparam_utils import _build_guidance
        curves = [{'param': 'learning_rate', 'type': 'float', 'values': [0.01, 0.1, 0.2, 0.3],
                   'cv_mean': [0.70, 0.90, 0.85, 0.80],
                   'train_mean': [0.72, 0.92, 0.95, 0.99]}]
        g = _build_guidance(curves, 'roc_auc')
        assert g and g[0]['type'] == 'zoom_in'
        assert g[0]['suggested_range'] == [0.01, 0.2]

@pytest.mark.unit
class TestHyperparamSurrogate:
    """Surrogate importances normalize to ~1 with signal and are all-zero on
    a constant target (no attribution possible)."""

    def test_importance_normalizes(self):
        from modeling.hyperparam_utils import _surrogate_importance
        rng = np.random.default_rng(0)
        X = rng.uniform(0, 1, size=(60, 2))
        y = 3 * X[:, 0] + rng.normal(0, 0.01, 60)  # target driven by param 0
        imp = _surrogate_importance(X, y, ['p0', 'p1'])
        assert abs(sum(imp.values()) - 1.0) < 1e-6
        assert imp['p0'] > imp['p1']

    def test_constant_target_zero_importance(self):
        from modeling.hyperparam_utils import _surrogate_importance
        X = np.random.default_rng(0).uniform(0, 1, size=(40, 2))
        y = np.full(40, 0.5)
        imp = _surrogate_importance(X, y, ['p0', 'p1'])
        assert imp == {'p0': 0.0, 'p1': 0.0}

@pytest.mark.unit
class TestHyperparamSearchEngine:
    """End-to-end engine on tiny synthetic data: produces best-metric points,
    validation curves, param emphasis and guidance — and is strict-JSON safe."""

    def test_full_search_outputs(self):
        from modeling.hyperparam_utils import (
            run_hyperparam_search_with_progress, METRIC_NAMES)
        Xtr, ytr, Xte, yte = _hp_synthetic()
        msgs = []
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=8, cv_folds=2, n_jobs=1, validation_curve_points=4,
            search_method='random', random_state=42,
            status_callback=lambda p: msgs.append(p.get('message')),
        )
        assert res['status'] == 'completed'
        assert res['n_trials'] == 8
        # Best metric "space points" for every catalogued metric.
        for m in ('roc_auc', 'pr_auc', 'f1', 'f2', 'precision', 'recall', 'accuracy', 'mcc'):
            assert m in res['best_points']
            assert 'params' in res['best_points'][m]
        # One validation curve per enabled param with aligned arrays.
        assert {c['param'] for c in res['validation_curves']} == {'max_depth', 'learning_rate'}
        for c in res['validation_curves']:
            assert len(c['values']) == len(c['cv_mean']) == len(c['train_mean'])
        # Emphasis + guidance present.
        assert set(res['emphasized']) == {'most_cv_gain', 'most_overfitting', 'most_shrinkage'}
        assert isinstance(res['guidance'], list)
        assert len(msgs) > 0

    def test_strict_json_serializable(self):
        import json
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth'),
            n_iter=4, cv_folds=2, n_jobs=1, validation_curve_points=3, random_state=1,
        )
        # NaN must not appear: allow_nan=False mirrors the browser's JSON.parse.
        from modeling.views import _hp_sanitize_json
        json.dumps(_hp_sanitize_json(res), allow_nan=False)

    def test_stop_flag_halts_search(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        stop = {'stop_requested': True}
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth'),
            n_iter=6, cv_folds=2, n_jobs=1, validation_curve_points=3,
            random_state=2, stop_flag=stop,
        )
        assert res['status'] == 'stopped'

@pytest.mark.unit
class TestHyperparamSearchMethod:
    """Search-method selection: the exhaustive-grid fit-count heuristic
    (< 100 fits/worker -> grid, <= 500 -> random, else bayesian) and that the
    engine honors an explicit method and resolves 'auto'."""

    def test_recommend_grid_for_small_space(self):
        from modeling.hyperparam_utils import recommend_search_method
        rec = recommend_search_method(_hp_space('max_depth'), cv_folds=3, n_jobs=3)
        assert rec['method'] == 'grid'
        assert rec['fits_per_job'] < 100

    def test_recommend_random_for_mid_space(self):
        from modeling.hyperparam_utils import recommend_search_method
        # 3 params @ 5 pts = 125 candidates * 3 cv / 1 worker = 375 fits/worker -> random.
        rec = recommend_search_method(_hp_space('max_depth', 'learning_rate', 'subsample'),
                                      cv_folds=3, n_jobs=1)
        assert rec['method'] == 'random'
        assert 100 <= rec['fits_per_job'] <= 500

    def test_recommend_bayesian_for_large_space(self):
        from modeling.hyperparam_utils import recommend_search_method
        rec = recommend_search_method(
            _hp_space('n_estimators', 'max_depth', 'learning_rate',
                      'min_child_weight', 'subsample', 'colsample_bytree'),
            cv_folds=3, n_jobs=3)
        assert rec['method'] == 'bayesian'
        assert rec['fits_per_job'] > 500

    def test_estimate_grid_candidates_product(self):
        from modeling.hyperparam_utils import estimate_grid_candidates
        # 2 params at 4 points each -> 16 candidate configs.
        assert estimate_grid_candidates(_hp_space('max_depth', 'learning_rate'),
                                        grid_points_per_param=4) == 16

    def test_njobs_shifts_recommendation(self):
        from modeling.hyperparam_utils import recommend_search_method
        sp = _hp_space('max_depth', 'learning_rate', 'subsample')  # 125 candidates
        assert recommend_search_method(sp, 3, 1)['method'] == 'random'   # 375 fits/worker
        assert recommend_search_method(sp, 3, 8)['method'] == 'grid'     # ~47 fits/worker

    def test_engine_runs_grid_and_reports_method(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=8, cv_folds=2, n_jobs=1, validation_curve_points=3,
            search_method='grid', grid_points_per_param=4, random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method'] == 'grid'
        # Grid evaluates the full product (~4x4=16), independent of n_iter.
        assert res['n_trials'] >= 9
        assert res['n_search_evals'] == res['n_trials']

    def test_engine_runs_bayesian(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=10, cv_folds=2, n_jobs=2, validation_curve_points=3,
            search_method='bayesian', random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method'] == 'bayesian'
        assert res['n_trials'] == 10  # SMBO evaluates exactly n_iter configs

    def test_engine_auto_resolves_to_grid_for_one_small_param(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth'),
            n_iter=6, cv_folds=2, n_jobs=2, validation_curve_points=3,
            search_method='auto', grid_points_per_param=4, random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method'] == 'grid'
        assert res['search_method_requested'] == 'auto'
        assert res['recommendation']['method'] == 'grid'

    def test_engine_invalid_method_falls_back_to_auto(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth'),
            n_iter=4, cv_folds=2, n_jobs=2, validation_curve_points=3,
            search_method='nonsense', grid_points_per_param=4, random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method_requested'] == 'auto'

@pytest.mark.unit
class TestHyperparamPointsMap:
    """Per-param checkpoint overrides (the UI Walk_Step column -> points_map)
    flow through the estimate, the recommendation, the grid enumeration, and
    the full engine run; a malformed map is sanitized rather than fatal."""

    def test_estimate_uses_points_map_per_param(self):
        from modeling.hyperparam_utils import estimate_grid_candidates
        sp = _hp_space('max_depth', 'learning_rate')   # scalar 5 would give 5x5=25
        # max_depth (2..10) -> 3 distinct ints; learning_rate keeps the scalar 5 -> 15.
        assert estimate_grid_candidates(
            sp, grid_points_per_param=5, points_map={'max_depth': 3}) == 15

    def test_estimate_map_caps_int_range(self):
        from modeling.hyperparam_utils import estimate_grid_candidates
        sp = _hp_space('max_depth')   # 2..10 -> at most 9 distinct ints
        assert estimate_grid_candidates(sp, points_map={'max_depth': 50}) == 9

    def test_recommend_respects_points_map(self):
        from modeling.hyperparam_utils import recommend_search_method
        sp = _hp_space('max_depth', 'learning_rate', 'subsample')
        # Coarse map (2 each) -> 8 candidates -> grid (default 5 -> 125 -> random).
        rec = recommend_search_method(
            sp, 3, 1, points_map={'max_depth': 2, 'learning_rate': 2, 'subsample': 2})
        assert rec['grid_candidates'] == 8
        assert rec['method'] == 'grid'

    def test_grid_configs_honor_points_map(self):
        from modeling.hyperparam_utils import _grid_configs, DEFAULT_FIXED_PARAMS
        sp = _hp_space('max_depth', 'learning_rate')
        rng = np.random.default_rng(0)
        configs, truncated = _grid_configs(
            sp, DEFAULT_FIXED_PARAMS, grid_points_per_param=5, max_candidates=2000,
            rng=rng, points_map={'max_depth': 3, 'learning_rate': 4})
        assert truncated is False
        assert len(configs) == 12   # 3 x 4
        assert len({c['max_depth'] for c in configs}) == 3
        assert len({c['learning_rate'] for c in configs}) == 4

    def test_engine_runs_with_points_map(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=8, cv_folds=2, n_jobs=1, validation_curve_points=3,
            search_method='grid', grid_points_per_param=5,
            grid_points_per_param_map={'max_depth': 3, 'learning_rate': 4},
            random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method'] == 'grid'
        assert res['grid_points_per_param_map'] == {'max_depth': 3, 'learning_rate': 4}
        assert res['recommendation']['grid_candidates'] == 12   # 3 x 4
        assert res['n_search_evals'] == 12

    def test_engine_sanitizes_bad_points_map(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=6, cv_folds=2, n_jobs=1, validation_curve_points=3,
            search_method='grid', grid_points_per_param=4,
            grid_points_per_param_map={'max_depth': 'oops', 'unknown_param': 9, 'learning_rate': 1},
            random_state=0)
        # 'oops' (non-int) dropped, 'unknown_param' (not in space) dropped, 1 clamped up to 2.
        assert res['grid_points_per_param_map'] == {'learning_rate': 2}
        assert res['status'] == 'completed'
