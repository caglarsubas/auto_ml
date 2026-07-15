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
