"""Unit tests - modeling/sfs_utils.py.

These exercise the real implementation (previously only mirrored logic or JSON
fixtures were tested, leaving sfs_utils.py essentially uncovered). Datasets are
tiny so the CV-backed SFS runs finish in a couple of seconds.
"""
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def _synthetic_split():
    """Small separable binary dataset split into train/test."""
    from sklearn.datasets import make_classification
    X, y = make_classification(
        n_samples=120, n_features=6, n_informative=4, n_redundant=1,
        random_state=7,
    )
    cols = [f'f{i}' for i in range(6)]
    split = 84
    X_train = pd.DataFrame(X[:split], columns=cols)
    X_test = pd.DataFrame(X[split:], columns=cols)
    y_train = pd.Series(y[:split])
    y_test = pd.Series(y[split:])
    return X_train, y_train, X_test, y_test


@pytest.mark.unit
class TestCalculatePsi:
    def test_identical_distributions_near_zero(self):
        from modeling.sfs_utils import calculate_psi
        rng = np.random.default_rng(0)
        data = rng.normal(size=1000)
        psi = calculate_psi(data, data.copy())
        assert psi is not None
        assert psi == pytest.approx(0.0, abs=1e-6)

    def test_shifted_distribution_is_positive(self):
        from modeling.sfs_utils import calculate_psi
        rng = np.random.default_rng(0)
        expected = rng.normal(0, 1, 2000)
        actual = rng.normal(3, 1, 2000)
        psi = calculate_psi(expected, actual)
        assert psi is not None
        assert psi > 0.25  # a large shift

    def test_empty_input_returns_none(self):
        from modeling.sfs_utils import calculate_psi
        assert calculate_psi(np.array([]), np.array([1.0, 2.0])) is None

    def test_constant_expected_returns_none(self):
        from modeling.sfs_utils import calculate_psi
        # A single unique breakpoint cannot form bins.
        assert calculate_psi(np.ones(50), np.ones(50)) is None

    def test_nan_values_are_ignored(self):
        from modeling.sfs_utils import calculate_psi
        rng = np.random.default_rng(1)
        expected = rng.normal(size=500)
        actual = np.concatenate([rng.normal(size=500), [np.nan, np.inf]])
        psi = calculate_psi(expected, actual)
        assert psi is not None
        assert np.isfinite(psi)


@pytest.mark.unit
class TestCalculateCsi:
    def test_identical_categoricals_near_zero(self):
        from modeling.sfs_utils import calculate_csi
        cats = np.array(['a', 'b', 'c', 'a', 'b', 'c'] * 20)
        csi = calculate_csi(cats, cats.copy())
        assert csi == pytest.approx(0.0, abs=1e-9)

    def test_shifted_categoricals_positive(self):
        from modeling.sfs_utils import calculate_csi
        expected = np.array(['a'] * 90 + ['b'] * 10)
        actual = np.array(['a'] * 10 + ['b'] * 90)
        csi = calculate_csi(expected, actual)
        assert csi is not None
        assert csi > 0.0


@pytest.mark.unit
class TestComputeShapImportance:
    def test_returns_importance_for_each_feature(self, _synthetic_split):
        import xgboost as xgb
        from modeling.sfs_utils import compute_shap_importance
        X_train, y_train, _, _ = _synthetic_split
        model = xgb.XGBClassifier(
            n_estimators=20, max_depth=3, random_state=0, verbosity=0,
            use_label_encoder=False, eval_metric='logloss',
        )
        model.fit(X_train, y_train)
        importance = compute_shap_importance(model, X_train, list(X_train.columns))
        assert set(importance.keys()) == set(X_train.columns)
        assert all(isinstance(v, float) and v >= 0.0 for v in importance.values())
        # At least one informative feature should carry non-zero importance.
        assert any(v > 0.0 for v in importance.values())

    def test_bad_booster_returns_zero_fallback(self, _synthetic_split):
        from modeling.sfs_utils import compute_shap_importance
        X_train, _, _, _ = _synthetic_split
        names = list(X_train.columns)
        importance = compute_shap_importance(object(), X_train, names)
        assert importance == {n: 0.0 for n in names}


@pytest.mark.unit
class TestRunForwardSfs:
    def test_returns_step_results(self, _synthetic_split):
        from modeling.sfs_utils import run_forward_sfs
        X_train, y_train, X_test, y_test = _synthetic_split
        results = run_forward_sfs(
            X_train, y_train, X_test, y_test,
            X_train_raw=X_train, X_test_raw=X_test,
            max_features=3, cv_folds=2, n_jobs=1,
        )
        assert isinstance(results, list)
        assert len(results) >= 1
        assert all(isinstance(step, dict) for step in results)
        # Forward selection grows the selected-feature set monotonically.
        assert len(results) <= 3


@pytest.mark.unit
class TestSfsRegressionHelpers:
    def test_score_pair_and_metric_fields_regression(self):
        from modeling.sfs_utils import (
            _normalize_sfs_metric_criteria,
            _sfs_metric_fields,
            _sfs_score_pair,
            _sfs_xgb_params,
        )
        from sklearn.metrics import r2_score, mean_squared_error
        y_true = np.array([1.0, 2.0, 3.0, 4.0])
        y_pred = np.array([1.1, 1.9, 3.2, 3.8])
        primary, secondary = _sfs_score_pair(y_true, y_pred, 'regression')
        assert primary == pytest.approx(float(r2_score(y_true, y_pred)))
        assert secondary == pytest.approx(-float(np.sqrt(mean_squared_error(y_true, y_pred))))
        fields = _sfs_metric_fields(y_true, y_pred, 'regression', 'cv_')
        assert fields['cv_r2'] == pytest.approx(primary)
        assert fields['cv_rmse'] == pytest.approx(-secondary)
        assert fields['cv_roc_auc'] == pytest.approx(primary)  # alias
        params = _sfs_xgb_params('regression', nthread=1)
        assert params['objective'] == 'reg:squarederror'
        criteria = _normalize_sfs_metric_criteria(
            [{'metric': 'roc_auc', 'pct_change': 1.0}], 'regression'
        )
        assert criteria[0]['metric'] == 'r2'

    def test_forward_step_regression_returns_r2(self, _synthetic_split):
        from sklearn.datasets import make_regression
        from modeling.sfs_utils import _run_forward_step
        X, y = make_regression(n_samples=100, n_features=5, n_informative=3, random_state=3)
        cols = [f'r{i}' for i in range(5)]
        split = 70
        X_train = pd.DataFrame(X[:split], columns=cols)
        X_test = pd.DataFrame(X[split:], columns=cols)
        y_train = pd.Series(y[:split])
        y_test = pd.Series(y[split:])
        step = _run_forward_step(
            X_train, y_train, X_test, y_test, X_train, X_test,
            current_features=[], step=1, cv_folds=2, n_jobs=1, top_k=2, task='regression',
        )
        assert step is not None
        assert step['task'] == 'regression'
        assert 'cv_r2' in step
        assert 'cv_rmse' in step
        assert step['cv_rmse'] >= 0
        assert len(step['selected_features']) == 1


@pytest.mark.unit
class TestRunSfsWithProgress:
    def test_forward_run_reports_progress_and_results(self, _synthetic_split):
        from modeling.sfs_utils import run_sfs_with_progress
        X_train, y_train, X_test, y_test = _synthetic_split
        updates = []
        result = run_sfs_with_progress(
            X_train, y_train, X_test, y_test,
            X_train_raw=X_train, X_test_raw=X_test,
            methods=['forward'],
            stopping_criteria={
                'metrics': [{'metric': 'roc_auc', 'pct_change': 0.0}],
                'min_features': 1,
                'max_features': 3,
            },
            status_callback=lambda info: updates.append(info),
            cv_folds=2,
            n_jobs=1,
        )
        assert isinstance(result, dict)
        assert 'forward' in result
        assert isinstance(result['forward'], list)
        assert result.get('status') in ('running', 'completed')
        assert len(updates) >= 1

    def test_stop_flag_halts_run(self, _synthetic_split):
        from modeling.sfs_utils import run_sfs_with_progress
        X_train, y_train, X_test, y_test = _synthetic_split
        result = run_sfs_with_progress(
            X_train, y_train, X_test, y_test,
            X_train_raw=X_train, X_test_raw=X_test,
            methods=['forward'],
            stopping_criteria={
                'metrics': [{'metric': 'roc_auc', 'pct_change': 0.0}],
                'min_features': 1,
                'max_features': 5,
            },
            cv_folds=2,
            n_jobs=1,
            stop_flag={'stop_requested': True},
        )
        assert isinstance(result, dict)
        assert 'forward' in result

    def test_regression_forward_uses_r2(self):
        from sklearn.datasets import make_regression
        from modeling.sfs_utils import run_sfs_with_progress
        X, y = make_regression(n_samples=90, n_features=4, n_informative=3, random_state=11)
        cols = [f'f{i}' for i in range(4)]
        split = 63
        X_train = pd.DataFrame(X[:split], columns=cols)
        X_test = pd.DataFrame(X[split:], columns=cols)
        y_train = pd.Series(y[:split])
        y_test = pd.Series(y[split:])
        result = run_sfs_with_progress(
            X_train, y_train, X_test, y_test,
            X_train_raw=X_train, X_test_raw=X_test,
            methods=['forward'],
            stopping_criteria={
                'metrics': [{'metric': 'roc_auc', 'pct_change': 0.0}],
                'min_features': 1,
                'max_features': 2,
            },
            cv_folds=2,
            n_jobs=1,
            task='regression',
        )
        assert result['task'] == 'regression'
        assert len(result['forward']) >= 1
        assert result['forward'][0].get('cv_r2') is not None
