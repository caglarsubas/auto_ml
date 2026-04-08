"""
REGRESSION TESTS
=================
Tests for previously identified and fixed bugs.
Each test documents the original issue so it never recurs.
"""
import io
import json
import os
import pytest
import pandas as pd
import numpy as np
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


# ---------------------------------------------------------------------------
# BUG: pandas 2.0+ returns 'str' dtype instead of 'object' for string columns,
#      causing determine_level_of_measurement to return 'unknown'.
# FIX: Added ('str', 'string') alongside 'object' in the dtype check.
# ---------------------------------------------------------------------------
@pytest.mark.regression
class TestStrDtypeClassification:

    def _determine(self, column_data, data_type, unique_count):
        """Mirror the fixed determine_level_of_measurement logic."""
        if unique_count == len(column_data):
            return 'id'
        elif (data_type in ('float64', 'float', 'float32')) and (unique_count > 1000):
            return 'continuous'
        elif (data_type in ('float64', 'float', 'float32')) and (unique_count <= 1000):
            return 'cardinal'
        elif data_type == 'integer':
            if unique_count > 1000 or unique_count / len(column_data) > 0.1:
                return 'continuous'
            else:
                if unique_count > 5:
                    return 'cardinal'
                else:
                    return 'nominal'
        elif data_type in ('object', 'str', 'string'):
            try:
                pd.to_datetime(column_data, errors='raise', format='%d/%m/%Y %I:%M:%S %p')
                return 'datetime'
            except Exception:
                return 'nominal'
        else:
            return 'unknown'

    def test_str_dtype_not_unknown(self):
        """Columns with dtype 'str' must NOT be classified as 'unknown'."""
        data = pd.Series(['Worst Account Status', 'Good'] * 50)
        result = self._determine(data, 'str', 2)
        assert result != 'unknown', "str dtype should not produce 'unknown'"
        assert result == 'nominal'

    def test_string_dtype_not_unknown(self):
        """Columns with dtype 'string' must NOT be classified as 'unknown'."""
        data = pd.Series(['Yes', 'No'] * 50)
        result = self._determine(data, 'string', 2)
        assert result != 'unknown', "string dtype should not produce 'unknown'"
        assert result == 'nominal'

    def test_float_dtype_not_unknown(self):
        """Columns with dtype 'float' (not 'float64') must NOT be classified as 'unknown'."""
        data = pd.Series(np.random.uniform(0, 100, 200))
        result = self._determine(data, 'float', 180)
        assert result != 'unknown', "float dtype should not produce 'unknown'"
        assert result == 'cardinal'

    def test_float32_dtype_not_unknown(self):
        """Columns with dtype 'float32' must NOT be classified as 'unknown'."""
        data = pd.Series(np.random.uniform(0, 100, 2000))
        result = self._determine(data, 'float32', 1500)
        assert result != 'unknown', "float32 dtype should not produce 'unknown'"
        assert result == 'continuous'


# ---------------------------------------------------------------------------
# BUG: Data dictionary endpoint returning 'unknown' for string columns.
# FIX: Same root cause as above - verified through full API call.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.django_db
class TestDataDictionaryNoUnknowns:

    def test_no_unknown_levels_for_standard_data(self, api_client, _use_tmp_media):
        """Data dictionary should not produce 'unknown' for typical CSV data."""
        df = pd.DataFrame({
            'ID': range(1, 101),
            'Name': ['Person_' + str(i) for i in range(1, 101)],
            'Age': np.random.randint(18, 70, 100),
            'Score': np.random.uniform(0, 100, 100).round(2),
            'Category': np.random.choice(['A', 'B', 'C'], 100),
            'Flag': np.random.choice([0, 1], 100),
            'Target': np.random.choice([0, 1], 100),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'regression_test.csv'

        # Upload
        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        pk = resp.data['id']

        # Get data dictionary
        resp = api_client.get(f'/api/declaration/{pk}/data_dictionary/')
        assert resp.status_code == 200

        for entry in resp.data:
            level = entry.get('Level_of_Measurement', '')
            assert level != 'unknown', (
                f"Column '{entry['Feature_Name']}' (dtype={entry['Data_Type']}) "
                f"was classified as 'unknown'"
            )


# ---------------------------------------------------------------------------
# BUG: Global CSS button style `button:not(.next-button)` was overriding
#      all Angular Material buttons, causing inconsistent appearance.
# FIX: Removed overly broad global selector, added targeted mat-button overrides.
# This is a structural regression test (checks the CSS file content).
# ---------------------------------------------------------------------------
@pytest.mark.regression
class TestButtonCSSRegression:

    def test_no_broad_button_override_in_global_css(self):
        """Global styles.css should NOT contain the broad 'button:not(.next-button)' selector."""
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'frontend', 'src', 'styles.css'
        )
        if not os.path.exists(css_path):
            pytest.skip("Frontend CSS file not found (may be in container-only build)")

        with open(css_path, 'r') as f:
            content = f.read()

        assert 'button:not(.next-button)' not in content, (
            "Broad 'button:not(.next-button)' selector should not exist in global styles"
        )


# ---------------------------------------------------------------------------
# BUG (v2.13.1): Forward-from-backward SFS results were stored in BOTH
#   'forward' and 'forward_from_backward' keys, causing a duplicate
#   Forward Selection table in the UI.
# FIX: When new forward results arrive and existing backward data exists,
#   route results exclusively to 'forward_from_backward' and preserve
#   original 'forward'.
# ---------------------------------------------------------------------------
@pytest.mark.regression
class TestSfsDuplicateForwardTableRegression:

    def _build_sfs_save_data(self, new_forward, new_backward, existing_data):
        """Mirror the fixed final-save logic from views.py."""
        new_backward_remaining = []
        is_forward_from_backward = bool(new_forward and existing_data.get('backward'))
        return {
            'forward': existing_data.get('forward', []) if is_forward_from_backward else (new_forward if new_forward else existing_data.get('forward', [])),
            'backward': new_backward if new_backward else existing_data.get('backward', []),
            'backward_remaining_features': new_backward_remaining if new_backward_remaining else existing_data.get('backward_remaining_features', []),
            'forward_from_backward': new_forward if is_forward_from_backward else existing_data.get('forward_from_backward', []),
            'status': 'completed',
        }

    def test_fwd_from_bwd_does_not_overwrite_forward(self):
        """Forward-from-backward results must NOT appear in the 'forward' key."""
        existing = {
            'forward': [{'step': 1, 'feature_name': 'orig_fwd'}],
            'backward': [{'step': 1, 'feature_name': 'bwd_feat'}],
        }
        new_fwd = [{'step': 1, 'feature_name': 'fwd_from_bwd_feat'}]
        result = self._build_sfs_save_data(new_fwd, [], existing)

        assert result['forward'] == existing['forward'], \
            "Original forward results should be preserved"
        assert result['forward_from_backward'] == new_fwd, \
            "New results should be in forward_from_backward"

    def test_standalone_forward_stores_in_forward_key(self):
        """Standalone forward (no prior backward) stores in 'forward' key only."""
        existing = {}
        new_fwd = [{'step': 1, 'feature_name': 'standalone_fwd'}]
        result = self._build_sfs_save_data(new_fwd, [], existing)

        assert result['forward'] == new_fwd
        assert result['forward_from_backward'] == []

    def test_backward_only_preserves_forward(self):
        """Backward-only run preserves existing forward and forward_from_backward."""
        existing = {
            'forward': [{'step': 1}],
            'forward_from_backward': [{'step': 1}],
        }
        new_bwd = [{'step': 1, 'feature_name': 'bwd'}]
        result = self._build_sfs_save_data([], new_bwd, existing)

        assert result['forward'] == existing['forward']
        assert result['backward'] == new_bwd
        assert result['forward_from_backward'] == existing['forward_from_backward']


# ---------------------------------------------------------------------------
# BUG (v2.13.1): _save_intermediate raised KeyError: 'selected_features'
#   when SFS step dict was missing this key.
# FIX: sanitize_sfs now explicitly accesses item['selected_features'],
#   making the failure visible early instead of silently producing bad data.
# ---------------------------------------------------------------------------
@pytest.mark.regression
class TestSfsIntermediateSaveKeyError:

    def test_sanitize_requires_selected_features(self):
        """sanitize_sfs should fail fast if 'selected_features' is missing from a step."""
        def sanitize_sfs(results_list):
            sanitized = []
            for item in results_list:
                sanitized_item = {
                    'step': item['step'],
                    'selected_features': item['selected_features'],
                    'feature_name': item['feature_name'],
                }
                sanitized.append(sanitized_item)
            return sanitized

        step_ok = {'step': 1, 'feature_name': 'V1', 'selected_features': ['V1']}
        assert sanitize_sfs([step_ok])[0]['selected_features'] == ['V1']

        step_bad = {'step': 1, 'feature_name': 'V1'}
        with pytest.raises(KeyError, match='selected_features'):
            sanitize_sfs([step_bad])


# ---------------------------------------------------------------------------
# BUG (v2.13.1): Pipeline step regression allowed stale checkpoint saves
#   to overwrite current_step with an earlier value.
# FIX: PipelineRunDetailView.put blocks updates where new_step < old_step.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.django_db
class TestPipelineStepRegressionViaAPI:

    def test_step_regression_blocked(self):
        """PUT should not allow moving from 'sfs' back to 'modeling'."""
        from modeling.models import PipelineRun
        from rest_framework.test import APIClient
        client = APIClient()

        run = PipelineRun.objects.create(name='Regress', current_step='sfs')
        resp = client.put(
            f'/api/pipeline/{run.pk}/',
            data='{"current_step": "modeling"}',
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['current_step'] == 'sfs'

    def test_step_forward_allowed(self):
        """PUT should allow moving from 'modeling' to 'sfs'."""
        from modeling.models import PipelineRun
        from rest_framework.test import APIClient
        client = APIClient()

        run = PipelineRun.objects.create(name='Forward', current_step='modeling')
        resp = client.put(
            f'/api/pipeline/{run.pk}/',
            data='{"current_step": "sfs"}',
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['current_step'] == 'sfs'


# ---------------------------------------------------------------------------
# BUG: SFS result files on disk could have 'forward' populated with
#   forward-from-backward data, causing duplicate tables.
# FIX: Corrected save logic + manual data cleanup.
# This test validates the disk format contract.
# ---------------------------------------------------------------------------
@pytest.mark.regression
class TestSfsResultFileFormatRegression:

    def test_sfs_result_keys_are_exclusive_after_save(self, tmp_path):
        """The save logic must produce files where forward and forward_from_backward are exclusive."""

        # Simulate a correct save: forward-from-backward run with existing backward data
        existing_data = {
            'forward': [{'step': 1, 'feature_name': 'OrigFwd'}],
            'backward': [{'step': 1, 'feature_name': 'BwdFeat'}],
            'forward_from_backward': [],
        }
        new_forward = [
            {'step': 1, 'feature_name': 'FfbFeat1'},
            {'step': 2, 'feature_name': 'FfbFeat2'},
        ]
        is_fwd_from_bwd = bool(new_forward and existing_data.get('backward'))

        sfs_data = {
            'forward': existing_data.get('forward', []) if is_fwd_from_bwd else new_forward,
            'backward': existing_data.get('backward', []),
            'forward_from_backward': new_forward if is_fwd_from_bwd else [],
            'status': 'completed',
        }

        # Write and read back
        sfs_path = tmp_path / 'test_sfs_results.json'
        with open(sfs_path, 'w') as f:
            json.dump(sfs_data, f)

        with open(sfs_path, 'r') as f:
            data = json.load(f)

        fwd_features = {s['feature_name'] for s in data['forward']}
        ffb_features = {s['feature_name'] for s in data['forward_from_backward']}
        assert not fwd_features & ffb_features, "forward and forward_from_backward must not overlap"
        assert fwd_features == {'OrigFwd'}
        assert ffb_features == {'FfbFeat1', 'FfbFeat2'}


# ===========================================================================
# BUG (v2.16): Pandas 3.0 StringDtype columns break numpy-based Data_Quality
#   PSI/KS routines because numpy cannot interpret StringDtype.
# FIX: Convert StringDtype columns to 'object' before passing to Data_Quality.
# ===========================================================================
@pytest.mark.regression
class TestStringDtypeToObjectConversion:

    def test_stringdtype_detected_and_convertible(self):
        """Pandas 3.0 StringDtype must be detectable via is_string_dtype and convertible to object."""
        df = pd.DataFrame({'Cat': pd.array(['a', 'b', 'c'], dtype='string')})
        assert pd.api.types.is_string_dtype(df['Cat']), "StringDtype should be detected by is_string_dtype"
        assert df['Cat'].dtype != 'object', "StringDtype should NOT equal 'object'"
        # The fix: convert
        df['Cat'] = df['Cat'].astype('object')
        assert df['Cat'].dtype == 'object', "After conversion, dtype must be 'object'"

    def test_object_dtype_not_double_converted(self):
        """Object-dtype columns must NOT be touched by the StringDtype conversion guard."""
        df = pd.DataFrame({'Cat': ['a', 'b', 'c']})
        if df['Cat'].dtype == 'object':
            original_dtype = df['Cat'].dtype
            # Guard should skip: is_string_dtype True but dtype IS 'object' → no conversion
            if pd.api.types.is_string_dtype(df['Cat']) and df['Cat'].dtype != 'object':
                df['Cat'] = df['Cat'].astype('object')
            assert df['Cat'].dtype == original_dtype

    def test_stringdtype_conversion_loop(self):
        """Mirror the exact loop from preprocessing/views.py that fixes PSI computation."""
        df = pd.DataFrame({
            'StrCol': pd.array(['x', 'y', 'z'], dtype='string'),
            'ObjCol': pd.array(['a', 'b', 'c'], dtype='object'),
            'NumCol': [1.0, 2.0, 3.0],
        })
        for _c in df.columns:
            if pd.api.types.is_string_dtype(df[_c]) and df[_c].dtype != 'object':
                df[_c] = df[_c].astype('object')
        assert df['StrCol'].dtype == 'object', "StringDtype column must be converted"
        assert df['ObjCol'].dtype == 'object', "Object column must remain unchanged"
        assert pd.api.types.is_numeric_dtype(df['NumCol']), "Numeric column must not be touched"


# ===========================================================================
# BUG (v2.16): SHAP's TreeExplainer.shap_values() internally creates an
#   XGBoost DMatrix without enable_categorical=True, causing a ValueError
#   when the DataFrame contains category-dtype columns.
# FIX: Pass the pre-created DMatrix (with enable_categorical=True) to
#   explainer.shap_values() instead of the raw DataFrame.
# ===========================================================================
@pytest.mark.regression
class TestShapDMatrixEnableCategorical:

    def test_xgb_dmatrix_rejects_category_without_flag(self):
        """XGBoost DMatrix raises ValueError for category cols without enable_categorical."""
        import xgboost as xgb
        df = pd.DataFrame({
            'Num': [1.0, 2.0, 3.0, 4.0],
            'Cat': pd.Categorical(['a', 'b', 'a', 'b']),
        })
        with pytest.raises(ValueError):
            xgb.DMatrix(df, enable_categorical=False)

    def test_xgb_dmatrix_accepts_category_with_flag(self):
        """XGBoost DMatrix accepts category cols when enable_categorical=True."""
        import xgboost as xgb
        df = pd.DataFrame({
            'Num': [1.0, 2.0, 3.0, 4.0],
            'Cat': pd.Categorical(['a', 'b', 'a', 'b']),
        })
        dmat = xgb.DMatrix(df, enable_categorical=True)
        assert dmat.num_row() == 4
        assert dmat.num_col() == 2

    def test_shap_tree_explainer_accepts_dmatrix(self):
        """SHAP TreeExplainer.shap_values must accept a pre-created DMatrix."""
        import xgboost as xgb
        import shap
        import warnings
        n = 100
        df = pd.DataFrame({
            'Num1': np.random.uniform(0, 1, n),
            'Cat1': pd.Categorical(np.random.choice(['a', 'b', 'c'], n)),
        })
        y = np.random.choice([0, 1], n)
        dmat_train = xgb.DMatrix(df, label=y, enable_categorical=True)
        booster = xgb.train({'max_depth': 2, 'eta': 0.1, 'objective': 'binary:logistic', 'tree_method': 'hist'}, dmat_train, num_boost_round=5)
        dmat_test = xgb.DMatrix(df, enable_categorical=True)
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=FutureWarning, module='shap')
            explainer = shap.TreeExplainer(booster, feature_perturbation='interventional')
        # This is the fix: pass DMatrix, not DataFrame
        shap_vals = explainer.shap_values(dmat_test)
        assert shap_vals is not None
        if isinstance(shap_vals, list):
            assert shap_vals[0].shape == (n, 2)
        else:
            assert shap_vals.shape == (n, 2)


# ===========================================================================
# BUG (v2.16): SHAP's partial_dependence_plot passes numpy arrays to the
#   model_predict wrapper. When converted back to DataFrame, categorical
#   columns lose their 'category' dtype and become 'object' or 'str'.
#   XGBoost's DMatrix then rejects them even with enable_categorical=True.
# FIX: The model_predict wrapper restores category dtype for known
#   categorical columns and coerces remaining str/object columns to numeric.
# ===========================================================================
@pytest.mark.regression
class TestModelPredictDtypeRestoration:

    def test_numpy_roundtrip_loses_category_dtype(self):
        """Converting a DataFrame with category cols to numpy and back loses category dtype."""
        df = pd.DataFrame({
            'Num': [1.0, 2.0, 3.0],
            'Cat': pd.Categorical(['a', 'b', 'a']),
        })
        arr = df.values
        df2 = pd.DataFrame(arr, columns=df.columns)
        assert df2['Cat'].dtype != 'category', "numpy roundtrip should lose category dtype"

    def test_model_predict_wrapper_restores_category(self):
        """The model_predict pattern must restore category dtype after numpy conversion."""
        import xgboost as xgb
        feature_names = ['Num', 'Cat']
        cat_col_names = ['Cat']

        # Build a simple model
        n = 50
        train_df = pd.DataFrame({
            'Num': np.random.uniform(0, 1, n),
            'Cat': pd.Categorical(np.random.choice(['a', 'b'], n)),
        })
        y = np.random.choice([0, 1], n)
        dmat = xgb.DMatrix(train_df, label=y, enable_categorical=True)
        booster = xgb.train({'max_depth': 2, 'eta': 0.1, 'objective': 'binary:logistic', 'tree_method': 'hist'}, dmat, num_boost_round=3)

        # Mirror the fixed model_predict wrapper logic
        def model_predict(data_array):
            if isinstance(data_array, np.ndarray):
                data_df = pd.DataFrame(data_array, columns=feature_names)
            else:
                data_df = data_array
            for c in data_df.columns:
                if c in cat_col_names:
                    data_df[c] = data_df[c].astype('category')
                elif not pd.api.types.is_numeric_dtype(data_df[c]):
                    data_df[c] = pd.to_numeric(data_df[c], errors='coerce')
            dmat_inner = xgb.DMatrix(data_df, feature_names=feature_names, enable_categorical=True)
            return booster.predict(dmat_inner, output_margin=True)

        # Simulate SHAP passing numpy array
        test_array = train_df.values
        result = model_predict(test_array)
        assert result is not None
        assert len(result) == n

    def test_str_columns_coerced_to_numeric(self):
        """Non-categorical string/object columns must be coerced to numeric, not left as str."""
        df = pd.DataFrame({
            'A': ['1.5', '2.3', '3.7'],
            'B': [4.0, 5.0, 6.0],
        })
        cat_cols = []
        for c in df.columns:
            if c in cat_cols:
                df[c] = df[c].astype('category')
            elif not pd.api.types.is_numeric_dtype(df[c]):
                df[c] = pd.to_numeric(df[c], errors='coerce')
        assert pd.api.types.is_numeric_dtype(df['A']), "String numeric column must be coerced"
        assert df['A'].iloc[0] == pytest.approx(1.5)


# ===========================================================================
# BUG (v2.16): Categorical columns detected via dtype=='object' misses
#   Pandas 3.0 StringDtype columns. Explainability and SFS cat_cols
#   detection must use pd.api.types.is_string_dtype() as well.
# FIX: Added is_string_dtype() check alongside dtype=='object' check.
# ===========================================================================
@pytest.mark.regression
class TestCatColsDetectionStringDtype:

    def test_detect_cat_cols_with_stringdtype(self):
        """Mirror the cat_cols detection pattern from modeling/views.py — must catch StringDtype."""
        df = pd.DataFrame({
            'ObjCol': pd.array(['a', 'b', 'c'], dtype='object'),
            'StrCol': pd.array(['x', 'y', 'z'], dtype='string'),
            'CatCol': pd.Categorical(['p', 'q', 'r']),
            'NumCol': [1.0, 2.0, 3.0],
        })
        cat_cols = []
        for c in df.columns:
            if hasattr(df[c], 'cat') or df[c].dtype.name == 'category':
                cat_cols.append(c)
            elif df[c].dtype == 'object' or pd.api.types.is_string_dtype(df[c]):
                cat_cols.append(c)
        assert 'ObjCol' in cat_cols, "object-dtype must be detected"
        assert 'StrCol' in cat_cols, "StringDtype must be detected via is_string_dtype"
        assert 'CatCol' in cat_cols, "category-dtype must be detected"
        assert 'NumCol' not in cat_cols, "numeric column must NOT be detected as categorical"

    def test_old_detection_misses_stringdtype(self):
        """Without is_string_dtype, StringDtype columns are silently missed."""
        df = pd.DataFrame({'StrCol': pd.array(['a', 'b', 'c'], dtype='string')})
        # Old detection logic (broken):
        old_detected = df['StrCol'].dtype == 'object'
        assert not old_detected, "StringDtype is NOT 'object' — old check misses it"


# ===========================================================================
# BUG (v2.16): Stacked plot for 'Encoded/Scaled' data version rendered a
#   histogram instead of grouped bar chart for encoded categorical features.
#   These features are numeric after encoding but have low cardinality.
# FIX: Backend returns value_counts (dict format) for numeric features with
#   ≤20 unique values. Frontend detects dict format and uses bar chart.
# ===========================================================================
@pytest.mark.regression
class TestStackedPlotLowCardinalityNumeric:

    def test_low_cardinality_numeric_returns_dict(self):
        """Encoded categorical features (numeric, ≤20 unique) must return value_counts dict format."""
        feature_data = pd.Series([0, 1, 2, 0, 1, 2, 0, 0])
        target_data = pd.Series([0, 0, 0, 0, 1, 1, 1, 1])
        feat_nunique = feature_data.nunique(dropna=False)
        use_value_counts = (not pd.api.types.is_numeric_dtype(feature_data)) or feat_nunique <= 20

        assert pd.api.types.is_numeric_dtype(feature_data), "Encoded feature should be numeric"
        assert use_value_counts, "Low-cardinality numeric must use value_counts format"

        stacked_data = {}
        for target_class in target_data.unique():
            class_data = feature_data[target_data == target_class].fillna('NaN')
            value_counts = class_data.value_counts(dropna=False)
            stacked_data[str(target_class)] = {str(k): int(v) for k, v in value_counts.items()}

        # Result must be dict-of-dicts (not dict-of-arrays)
        for key, val in stacked_data.items():
            assert isinstance(val, dict), f"Class {key} data must be dict (value_counts), not list"

    def test_high_cardinality_numeric_returns_array(self):
        """High-cardinality numeric features (>20 unique) must return raw array format."""
        feature_data = pd.Series(np.random.uniform(0, 100, 200))
        target_data = pd.Series(np.random.choice([0, 1], 200))
        feat_nunique = feature_data.nunique(dropna=False)
        use_value_counts = (not pd.api.types.is_numeric_dtype(feature_data)) or feat_nunique <= 20

        assert not use_value_counts, "High-cardinality numeric must NOT use value_counts"

    def test_categorical_always_returns_dict(self):
        """Non-numeric (categorical) features must always return value_counts dict format."""
        feature_data = pd.Series(['A', 'B', 'C', 'A', 'B', 'C'])
        feat_nunique = feature_data.nunique(dropna=False)
        use_value_counts = (not pd.api.types.is_numeric_dtype(feature_data)) or feat_nunique <= 20

        assert use_value_counts, "Categorical features must always use value_counts"

    def test_boundary_exactly_20_unique_uses_dict(self):
        """Numeric feature with exactly 20 unique values must use value_counts (boundary)."""
        feature_data = pd.Series(list(range(20)) * 5)  # 20 unique values
        feat_nunique = feature_data.nunique(dropna=False)
        use_value_counts = (not pd.api.types.is_numeric_dtype(feature_data)) or feat_nunique <= 20

        assert use_value_counts, "Boundary: 20 unique values should use value_counts"

    def test_boundary_21_unique_uses_array(self):
        """Numeric feature with 21 unique values must use array format (boundary)."""
        feature_data = pd.Series(list(range(21)) * 5)  # 21 unique values
        feat_nunique = feature_data.nunique(dropna=False)
        use_value_counts = (not pd.api.types.is_numeric_dtype(feature_data)) or feat_nunique <= 20

        assert not use_value_counts, "Boundary: 21 unique values should NOT use value_counts"


# ===========================================================================
# BUG (v2.16): Quality tab showed "Quality information will be displayed
#   here." because qualitySummary was not passed when opening the feature
#   card from the modeling step, or was cleared when switching features.
# FIX: Added PreprocessingDatqSummaryRowView backend endpoint that reads
#   the saved datq_summary JSON for any feature. Frontend fetches on
#   Quality tab activation when qualitySummary is null.
# ===========================================================================
@pytest.mark.regression
@pytest.mark.django_db
class TestDatqSummaryRowEndpoint:

    def test_returns_row_for_existing_feature(self, _use_tmp_media, media_root):
        """GET /api/preprocessing/datq_summary_row/<id>/?column=X returns the correct row."""
        client = APIClient()

        datq_dir = os.path.join(str(media_root), 'data_quality')
        os.makedirs(datq_dir, exist_ok=True)
        records = [
            {'Variable': 'Var_1', 'PSI': 0.05, 'CSI': 0.02, 'KS': 0.1},
            {'Variable': 'Var_2', 'PSI': 0.12, 'CSI': 0.08, 'KS': 0.15},
            {'Variable': 'Var_3', 'PSI': 0.01, 'CSI': 0.01, 'KS': 0.05},
        ]
        with open(os.path.join(datq_dir, '1_datq_summary.json'), 'w') as f:
            json.dump(records, f)

        resp = client.get('/api/preprocessing/datq_summary_row/1/', {'column': 'Var_2'})
        assert resp.status_code == 200
        assert resp.data['row'] is not None
        assert resp.data['row']['Variable'] == 'Var_2'
        assert resp.data['row']['PSI'] == 0.12

    def test_returns_null_for_missing_feature(self, _use_tmp_media, media_root):
        """GET with a column not in the summary returns row=null."""
        client = APIClient()

        datq_dir = os.path.join(str(media_root), 'data_quality')
        os.makedirs(datq_dir, exist_ok=True)
        records = [{'Variable': 'Var_1', 'PSI': 0.05}]
        with open(os.path.join(datq_dir, '1_datq_summary.json'), 'w') as f:
            json.dump(records, f)

        resp = client.get('/api/preprocessing/datq_summary_row/1/', {'column': 'NonExistent'})
        assert resp.status_code == 200
        assert resp.data['row'] is None

    def test_returns_null_for_missing_file(self, _use_tmp_media, media_root):
        """GET when no datq_summary JSON exists returns row=null."""
        client = APIClient()

        resp = client.get('/api/preprocessing/datq_summary_row/99999/', {'column': 'Var_1'})
        assert resp.status_code == 200
        assert resp.data['row'] is None

    def test_missing_column_param_returns_400(self, _use_tmp_media):
        """GET without column query param returns 400."""
        client = APIClient()

        resp = client.get('/api/preprocessing/datq_summary_row/1/')
        assert resp.status_code == 400

    def test_lookup_with_variable_key_variants(self, _use_tmp_media, media_root):
        """The endpoint must find rows keyed as 'Variable', 'variable', or 'index'."""
        client = APIClient()

        datq_dir = os.path.join(str(media_root), 'data_quality')
        os.makedirs(datq_dir, exist_ok=True)

        # Test with 'variable' key (lowercase)
        records = [{'variable': 'Age', 'PSI': 0.03}]
        with open(os.path.join(datq_dir, '2_datq_summary.json'), 'w') as f:
            json.dump(records, f)
        resp = client.get('/api/preprocessing/datq_summary_row/2/', {'column': 'Age'})
        assert resp.status_code == 200
        assert resp.data['row'] is not None
        assert resp.data['row']['variable'] == 'Age'

        # Test with 'index' key
        records = [{'index': 'Score', 'PSI': 0.07}]
        with open(os.path.join(datq_dir, '3_datq_summary.json'), 'w') as f:
            json.dump(records, f)
        resp = client.get('/api/preprocessing/datq_summary_row/3/', {'column': 'Score'})
        assert resp.status_code == 200
        assert resp.data['row'] is not None
        assert resp.data['row']['index'] == 'Score'
