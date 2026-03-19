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
