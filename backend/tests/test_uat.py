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


# ---------------------------------------------------------------------------
# Scenario 5: User manages pipeline runs
# ---------------------------------------------------------------------------
@pytest.mark.uat
@pytest.mark.django_db
class TestUserPipelineManagementJourney:

    def test_user_creates_and_manages_pipeline(self, api_client, _use_tmp_media):
        """
        Scenario: User creates a pipeline, progresses through steps,
        saves checkpoint state, lists saved pipelines, and deletes one.

        Expected: Full CRUD lifecycle works correctly with state persistence.
        """
        # Create two pipelines
        resp1 = api_client.post(
            '/api/pipeline/create/',
            data=json.dumps({'name': 'Credit Risk Model', 'pipeline_type': 'boosting'}),
            content_type='application/json',
        )
        assert resp1.status_code == 201
        pk1 = resp1.data['id']

        resp2 = api_client.post(
            '/api/pipeline/create/',
            data=json.dumps({'name': 'Fraud Detection', 'pipeline_type': 'boosting'}),
            content_type='application/json',
        )
        assert resp2.status_code == 201
        pk2 = resp2.data['id']

        # Progress first pipeline to modeling step with state
        state = {
            'declaration': {'file_id': 10},
            'modeling': {'substep': 'modeling_completed'},
            'detailed_step': '3b_modeling',
            'pipeline_notes': {'after_data_preview': 'Good distribution'},
            'pipeline_codelines': {
                'after_data_preview': {
                    'id': 'cl-test-1',
                    'position': 'after_data_preview',
                    'mode': 'code',
                    'code': 'print(df.shape)',
                    'intent': '',
                    'updatedAt': '2026-07-20T00:00:00Z',
                }
            },
        }
        resp = api_client.put(
            f'/api/pipeline/{pk1}/',
            data=json.dumps({'current_step': 'modeling', 'state': state, 'file_id': 10}),
            content_type='application/json',
        )
        assert resp.status_code == 200

        # List all pipelines
        resp = api_client.get('/api/pipeline/')
        assert resp.status_code == 200
        names = [r['name'] for r in resp.data]
        assert 'Credit Risk Model' in names
        assert 'Fraud Detection' in names

        # Restore first pipeline's state
        resp = api_client.get(f'/api/pipeline/{pk1}/')
        assert resp.status_code == 200
        assert resp.data['current_step'] == 'modeling'
        assert resp.data['state']['pipeline_notes']['after_data_preview'] == 'Good distribution'
        assert resp.data['state']['pipeline_codelines']['after_data_preview']['code'] == 'print(df.shape)'

        # Delete second pipeline
        resp = api_client.delete(f'/api/pipeline/{pk2}/')
        assert resp.status_code == 200

        # Verify only first remains
        resp = api_client.get('/api/pipeline/')
        assert resp.status_code == 200
        remaining_names = [r['name'] for r in resp.data]
        assert 'Credit Risk Model' in remaining_names
        assert 'Fraud Detection' not in remaining_names


# ---------------------------------------------------------------------------
# Scenario 6: User encodes categorical features
# ---------------------------------------------------------------------------
@pytest.mark.uat
@pytest.mark.django_db
class TestUserEncodingJourney:

    def test_user_analyzes_and_encodes_features(self, api_client, _use_tmp_media, media_root):
        """
        Scenario: User has a processed CSV with categorical features.
        They analyze the data to get an encoding plan, review it,
        and apply encoding.

        Expected: Encoding plan identifies categoricals, apply produces
        encoded file with metadata sidecar.
        """
        n = 200
        df = pd.DataFrame({
            'Region': np.random.choice(['North', 'South', 'East', 'West'], n),
            'Product_Type': np.random.choice(['A', 'B', 'C', 'D', 'E'], n),
            'Amount': np.random.uniform(100, 10000, n).round(2),
            'Score': np.random.uniform(0, 1, n).round(4),
            'Target': np.random.choice([0, 1], n),
        })
        csv_dir = os.path.join(str(media_root), 'processed')
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, 'uat_enc.csv')
        df.to_csv(csv_path, index=False)
        rel_path = os.path.relpath(csv_path, str(media_root))

        data_dict = [
            {'Feature_Name': 'Region', 'Level_of_Measurement': 'nominal'},
            {'Feature_Name': 'Product_Type', 'Level_of_Measurement': 'nominal'},
            {'Feature_Name': 'Amount', 'Level_of_Measurement': 'continuous'},
            {'Feature_Name': 'Score', 'Level_of_Measurement': 'continuous'},
        ]

        # Step 1: Analyze
        resp = api_client.post(
            '/api/encoding/analyze/',
            data=json.dumps({
                'file_id': 1,
                'processed_file': rel_path,
                'data_dictionary': data_dict,
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200
        plan = resp.data['plan']
        cat_features = [p['feature'] for p in plan]
        assert 'Region' in cat_features
        assert 'Product_Type' in cat_features
        assert 'Amount' not in cat_features
        assert 'Score' not in cat_features

        # Step 2: Apply
        resp = api_client.post(
            '/api/encoding/apply/',
            data=json.dumps({
                'file_id': 1,
                'processed_file': rel_path,
                'plan': plan,
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200
        summary = resp.data['summary']
        assert summary['total_encoded'] >= 2
        assert summary['original_shape'][0] == n
        assert summary['encoded_shape'][0] == n

        # Verify report has per-feature details
        report = resp.data['report']
        report_features = [r['feature'] for r in report]
        assert 'Region' in report_features
        assert 'Product_Type' in report_features


# ---------------------------------------------------------------------------
# Scenario 7: User inspects SFS results
# ---------------------------------------------------------------------------
@pytest.mark.uat
@pytest.mark.django_db
class TestUserSfsInspectionJourney:

    def test_user_views_backward_and_forward_from_backward_results(self, api_client, _use_tmp_media, media_root):
        """
        Scenario: After running backward SFS followed by forward-from-backward,
        the user fetches SFS results and sees three distinct result sets
        (forward, backward, forward_from_backward) without duplication.

        Expected: Each result set is independent. forward_from_backward does
        not duplicate forward. Backward results are preserved.
        """
        sfs_dir = os.path.join(str(media_root), 'sfs_results')
        os.makedirs(sfs_dir, exist_ok=True)

        sfs_data = {
            'forward': [
                {'step': 1, 'direction': 'forward', 'feature_name': 'FwdVar1',
                 'cv_roc_auc': 0.78, 'selected_features': ['FwdVar1']},
            ],
            'backward': [
                {'step': 1, 'direction': 'backward', 'feature_name': 'BwdRemoved1',
                 'cv_roc_auc': 0.90, 'selected_features': ['A', 'B', 'C']},
                {'step': 2, 'direction': 'backward', 'feature_name': 'BwdRemoved2',
                 'cv_roc_auc': 0.88, 'selected_features': ['A', 'B']},
            ],
            'forward_from_backward': [
                {'step': 1, 'direction': 'forward', 'feature_name': 'FfbVar1',
                 'cv_roc_auc': 0.85, 'selected_features': ['FfbVar1']},
                {'step': 2, 'direction': 'forward', 'feature_name': 'FfbVar2',
                 'cv_roc_auc': 0.87, 'selected_features': ['FfbVar1', 'FfbVar2']},
            ],
            'backward_remaining_features': ['A', 'B'],
            'status': 'completed',
            'error': None,
        }

        file_id = 888
        with open(os.path.join(sfs_dir, f'{file_id}_sfs_results.json'), 'w') as f:
            json.dump(sfs_data, f)

        resp = api_client.get(f'/api/modeling/sfs/{file_id}/')
        assert resp.status_code == 200
        data = resp.data

        # Verify all three result sets exist and are independent
        assert len(data['forward']) == 1
        assert len(data['backward']) == 2
        assert len(data['forward_from_backward']) == 2

        # Verify no feature name overlap between forward and forward_from_backward
        fwd_names = {s['feature_name'] for s in data['forward']}
        ffb_names = {s['feature_name'] for s in data['forward_from_backward']}
        assert not fwd_names & ffb_names, "forward and forward_from_backward should not share features"

        # Verify backward results are preserved
        assert data['backward'][0]['feature_name'] == 'BwdRemoved1'
        assert data['backward_remaining_features'] == ['A', 'B']


# ---------------------------------------------------------------------------
# Scenario 8: User downloads pipeline report
# ---------------------------------------------------------------------------
@pytest.mark.uat
@pytest.mark.django_db
class TestUserPipelineReportJourney:

    def test_user_generates_and_downloads_report(self, api_client, _use_tmp_media):
        """
        Scenario: User creates a pipeline, progresses it to completion,
        then downloads the pipeline report as HTML.

        Expected: Report contains pipeline name, is valid HTML,
        and can be generated in both download and print formats.
        """
        # Create and progress pipeline
        resp = api_client.post(
            '/api/pipeline/create/',
            data=json.dumps({
                'name': 'Final Credit Model v3',
                'pipeline_type': 'boosting',
                'current_step': 'evaluation',
                'state': {
                    'declaration': {'file_id': 5},
                    'modeling': {'substep': 'modeling_completed'},
                    'detailed_step': '3b_modeling',
                },
            }),
            content_type='application/json',
        )
        assert resp.status_code == 201
        pk = resp.data['id']

        # Download report
        resp = api_client.get(f'/api/pipeline/{pk}/report/')
        assert resp.status_code == 200
        html = resp.content.decode('utf-8')
        assert 'Final Credit Model v3' in html
        assert '<!DOCTYPE html>' in html or '<html' in html.lower()
        assert 'Content-Disposition' in resp

        # Print-ready report
        resp = api_client.get(f'/api/pipeline/{pk}/report/?output=print')
        assert resp.status_code == 200
        html = resp.content.decode('utf-8')
        assert 'window.print()' in html
        assert 'Content-Disposition' not in resp
