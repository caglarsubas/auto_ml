"""
UAT (User Acceptance) TESTS
=============================
End-to-end scenarios that mirror real user journeys through the application.
These tests validate that the system behaves correctly from the user's perspective.
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
# Scenario 1: New user uploads data and inspects it
# ---------------------------------------------------------------------------
@pytest.mark.uat
@pytest.mark.django_db
class TestUserDataInspectionJourney:

    def test_user_uploads_csv_and_inspects_data_dictionary(self, api_client, _use_tmp_media):
        """
        Scenario: A user uploads a credit-scoring CSV, previews it,
        and checks the auto-generated data dictionary.

        Expected: All columns correctly classified, Target excluded from model,
        ID excluded from model, numeric columns get descriptive stats.
        """
        # Create realistic credit data
        n = 500
        df = pd.DataFrame({
            'AppID': range(1, n + 1),
            'Application_Date': pd.date_range('2023-01-01', periods=n, freq='D')
                                 .strftime('%d/%m/%Y %I:%M:%S %p'),
            'Age': np.random.randint(18, 70, n),
            'Income': np.random.uniform(20000, 200000, n).round(2),
            'Employment_Years': np.random.randint(0, 40, n),
            'Loan_Amount': np.random.uniform(5000, 100000, n).round(2),
            'Credit_Score': np.random.randint(300, 850, n),
            'Region': np.random.choice(['North', 'South', 'East', 'West'], n),
            'Risk_Flag': np.random.choice(['Low', 'Medium', 'High'], n),
            'Target': np.random.choice([0, 1], n),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'credit_data.csv'

        # Step 1: Upload
        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201, f"Upload failed: {resp.data}"
        file_id = resp.data['id']

        # Step 2: Preview
        resp = api_client.get(f'/api/declaration/{file_id}/preview/')
        assert resp.status_code == 200
        assert resp.data['total_rows'] == n
        assert resp.data['total_columns'] == 10
        assert 'AppID' in resp.data['columns']
        assert 'Target' in resp.data['columns']

        # Step 3: Data Dictionary
        resp = api_client.get(f'/api/declaration/{file_id}/data_dictionary/')
        assert resp.status_code == 200
        dd = {d['Feature_Name']: d for d in resp.data}

        # Validate auto-classifications
        assert dd['AppID']['Level_of_Measurement'] == 'id'
        assert dd['AppID']['Model_Usage_YN'] == 'No'
        assert dd['Target']['Model_Usage_YN'] == 'No'
        assert dd['Region']['Level_of_Measurement'] == 'nominal'
        assert dd['Risk_Flag']['Level_of_Measurement'] == 'nominal'

        # Numeric columns should not be 'unknown'
        for col in ['Age', 'Income', 'Employment_Years', 'Loan_Amount', 'Credit_Score']:
            assert dd[col]['Level_of_Measurement'] != 'unknown', (
                f"Numeric column '{col}' should not be classified as 'unknown'"
            )

        # Missing ratio should be 0 for clean data
        for entry in resp.data:
            assert entry['Missing_Ratio'] == 0.0


# ---------------------------------------------------------------------------
# Scenario 2: User configures preprocessing pipeline
# ---------------------------------------------------------------------------
@pytest.mark.uat
@pytest.mark.django_db
class TestUserPreprocessingConfigJourney:

    def test_user_uploads_and_configures_preprocessing(self, api_client, _use_tmp_media, media_root):
        """
        Scenario: User uploads data, then selects preprocessing options
        (duplicate drop, zero-variance drop, correlation drop).

        Expected: Config is persisted and retrievable.
        """
        df = pd.DataFrame({
            'ID': range(200),
            'Feature1': np.random.uniform(0, 1, 200),
            'Feature2': np.random.randint(0, 10, 200),
            'Constant': [42] * 200,  # zero-variance column
            'Target': np.random.choice([0, 1], 200),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'preprocessing_journey.csv'

        # Upload
        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        # Select preprocessing options
        selected_options = [1, 2, 3, 4, 5]  # Column dup, Row dup, Zero-var, Perfect-corr, Corr threshold
        resp = api_client.post(
            '/api/preprocessing/apply/',
            data=json.dumps({'file_id': file_id, 'options': selected_options}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['options'] == selected_options

        # Verify config persisted
        cfg_path = os.path.join(str(media_root), 'configs', f'preprocess_{file_id}.json')
        assert os.path.exists(cfg_path)
        with open(cfg_path) as f:
            cfg = json.load(f)
        assert cfg['options'] == selected_options


# ---------------------------------------------------------------------------
# Scenario 3: User handles data with missing values
# ---------------------------------------------------------------------------
@pytest.mark.uat
@pytest.mark.django_db
class TestUserMissingDataJourney:

    def test_data_dictionary_reports_missing_ratios(self, api_client, _use_tmp_media):
        """
        Scenario: User uploads data with missing values.

        Expected: Data dictionary correctly reports missing ratios.
        """
        n = 200
        df = pd.DataFrame({
            'ID': range(n),
            'Complete': np.random.uniform(0, 1, n),
            'HalfMissing': [np.nan if i % 2 == 0 else i for i in range(n)],
            'Target': np.random.choice([0, 1], n),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'missing_data.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        resp = api_client.get(f'/api/declaration/{file_id}/data_dictionary/')
        assert resp.status_code == 200
        dd = {d['Feature_Name']: d for d in resp.data}

        assert dd['Complete']['Missing_Ratio'] == 0.0
        assert dd['HalfMissing']['Missing_Ratio'] == pytest.approx(50.0, abs=1.0)


# ---------------------------------------------------------------------------
# Scenario 4: User explores feature card details
# ---------------------------------------------------------------------------
@pytest.mark.uat
@pytest.mark.django_db
class TestUserFeatureCardJourney:

    def test_feature_card_returns_stats(self, api_client, _use_tmp_media):
        """
        Scenario: User clicks a feature name to see its detailed statistics.

        Expected: Feature card API returns descriptive stats for the column.
        """
        n = 300
        df = pd.DataFrame({
            'Age': np.random.randint(18, 70, n),
            'Income': np.random.uniform(20000, 150000, n).round(2),
            'Category': np.random.choice(['A', 'B', 'C', 'D'], n),
            'Target': np.random.choice([0, 1], n),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'feature_card_test.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        # Get feature card for 'Age'
        resp = api_client.get(
            f'/api/feature-card/{file_id}/get_feature_info/',
            {'column': 'Age'},
        )
        assert resp.status_code == 200
        assert resp.data['Feature_Name'] == 'Age'
        assert 'Descriptive_Stats' in resp.data
        stats = resp.data['Descriptive_Stats']
        assert 'Mean' in stats
        assert 'Min' in stats
        assert 'Max' in stats

    def test_feature_card_missing_column_returns_404(self, api_client, _use_tmp_media):
        """Feature card for a nonexistent column returns 404."""
        df = pd.DataFrame({'A': [1, 2, 3], 'Target': [0, 1, 0]})
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'fc_missing.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        resp = api_client.get(
            f'/api/feature-card/{file_id}/get_feature_info/',
            {'column': 'NonExistent'},
        )
        assert resp.status_code == 404
