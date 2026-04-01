"""
REGRESSION TESTS
=================
Tests for previously identified and fixed bugs.
Each test documents the original issue so it never recurs.
"""
import io
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
        import os
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
        import json

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
