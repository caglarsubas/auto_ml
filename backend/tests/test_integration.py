"""
INTEGRATION TESTS
==================
Multi-component workflow tests that verify components work together correctly.
These tests simulate real user workflows spanning multiple API calls.
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


@pytest.fixture
def _create_csv_on_disk(media_root):
    """Helper to write a CSV directly to the temp media directory."""
    def _create(filename, df):
        path = os.path.join(str(media_root), 'data_files', filename)
        df.to_csv(path, index=False)
        return path
    return _create


# ---------------------------------------------------------------------------
# Upload → Preview → Data Dictionary workflow
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestUploadPreviewDictionaryWorkflow:

    def test_full_upload_to_dictionary_flow(self, api_client, _use_tmp_media):
        """Upload CSV → preview → data dictionary returns consistent metadata."""
        df = pd.DataFrame({
            'CustomerID': range(1, 201),
            'Age': np.random.randint(18, 65, 200),
            'Salary': np.random.uniform(30000, 120000, 200).round(2),
            'Region': np.random.choice(['North', 'South', 'East', 'West'], 200),
            'Target': np.random.choice([0, 1], 200),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'integration_test.csv'

        # Step 1: Upload
        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        pk = resp.data['id']

        # Step 2: Preview
        resp = api_client.get(f'/api/declaration/{pk}/preview/')
        assert resp.status_code == 200
        assert resp.data['total_rows'] == 200
        assert resp.data['total_columns'] == 5
        assert set(resp.data['columns']) == {'CustomerID', 'Age', 'Salary', 'Region', 'Target'}

        # Step 3: Data Dictionary
        resp = api_client.get(f'/api/declaration/{pk}/data_dictionary/')
        assert resp.status_code == 200
        assert len(resp.data) == 5

        # Verify classification consistency
        dd_map = {d['Feature_Name']: d for d in resp.data}
        assert dd_map['CustomerID']['Level_of_Measurement'] == 'id'
        assert dd_map['Region']['Level_of_Measurement'] == 'nominal'
        assert dd_map['Target']['Level_of_Measurement'] == 'nominal'
        assert dd_map['CustomerID']['Model_Usage_YN'] == 'No'
        assert dd_map['Target']['Model_Usage_YN'] == 'No'


# ---------------------------------------------------------------------------
# Upload → Apply Preprocessing workflow
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestUploadApplyPreprocessingWorkflow:

    def test_upload_then_apply_preprocessing(self, api_client, _use_tmp_media):
        """Upload file, then configure preprocessing options successfully."""
        df = pd.DataFrame({
            'A': range(50),
            'B': np.random.uniform(0, 1, 50),
            'Target': np.random.choice([0, 1], 50),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'preprocess_test.csv'

        # Upload
        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        pk = resp.data['id']

        # Apply preprocessing options
        resp = api_client.post(
            '/api/preprocessing/apply/',
            data=json.dumps({'file_id': pk, 'options': [1, 2, 3, 5]}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['file_id'] == pk
        assert resp.data['options'] == [1, 2, 3, 5]


# ---------------------------------------------------------------------------
# Multiple file upload and merge workflow
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestMultiFileUploadWorkflow:

    def test_upload_multiple_csv_row_merge(self, api_client, _use_tmp_media):
        """Uploading multiple CSV files with row-wise merge combines them."""
        df1 = pd.DataFrame({'X': [1, 2], 'Y': [3, 4]})
        df2 = pd.DataFrame({'X': [5, 6], 'Y': [7, 8]})

        buf1 = io.BytesIO()
        df1.to_csv(buf1, index=False)
        buf1.seek(0)
        buf1.name = 'part1.csv'

        buf2 = io.BytesIO()
        df2.to_csv(buf2, index=False)
        buf2.seek(0)
        buf2.name = 'part2.csv'

        resp = api_client.post(
            '/api/declaration/',
            {'file': buf1, 'file2': buf2, 'merge_column_wise': 'false', 'column_separator': 'comma'},
            format='multipart',
        )
        assert resp.status_code == 201
        pk = resp.data['id']

        # Preview should show merged data
        resp = api_client.get(f'/api/declaration/{pk}/preview/')
        assert resp.status_code == 200
        assert resp.data['total_rows'] == 4
        assert resp.data['total_columns'] == 2


# ---------------------------------------------------------------------------
# Config persistence integration test
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestPreprocessingConfigPersistence:

    def test_config_file_written_to_disk(self, api_client, _use_tmp_media, media_root):
        """Preprocessing apply writes config JSON to media/configs/."""
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )

        resp = api_client.post(
            '/api/preprocessing/apply/',
            data=json.dumps({'file_id': decl.pk, 'options': [1, 3, 5]}),
            content_type='application/json',
        )
        assert resp.status_code == 200

        cfg_path = os.path.join(str(media_root), 'configs', f'preprocess_{decl.pk}.json')
        assert os.path.exists(cfg_path), "Config file was not written"

        with open(cfg_path) as f:
            cfg = json.load(f)
        assert cfg['file_id'] == decl.pk
        assert cfg['options'] == [1, 3, 5]


# ---------------------------------------------------------------------------
# Pipeline lifecycle: Create → Update → Restore → Delete
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestPipelineLifecycleWorkflow:

    def test_full_pipeline_lifecycle(self, api_client, _use_tmp_media):
        """Create a pipeline, update it through multiple steps, restore state, delete it."""
        # Step 1: Create
        resp = api_client.post(
            '/api/pipeline/create/',
            data=json.dumps({'name': 'Lifecycle Test', 'pipeline_type': 'boosting'}),
            content_type='application/json',
        )
        assert resp.status_code == 201
        pk = resp.data['id']
        assert resp.data['status'] == 'active'
        assert resp.data['current_step'] == 'declaration'

        # Step 2: Update to preprocessing
        state_v1 = {'declaration': {'file_id': 42}, 'detailed_step': '2a_purifier_declaration'}
        resp = api_client.put(
            f'/api/pipeline/{pk}/',
            data=json.dumps({'current_step': 'preprocessing', 'state': state_v1}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['current_step'] == 'preprocessing'

        # Step 3: Update to modeling
        state_v2 = {**state_v1, 'modeling': {'substep': 'encoding_completed'}}
        resp = api_client.put(
            f'/api/pipeline/{pk}/',
            data=json.dumps({'current_step': 'modeling', 'state': state_v2}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['current_step'] == 'modeling'

        # Step 4: Restore state
        resp = api_client.get(f'/api/pipeline/{pk}/')
        assert resp.status_code == 200
        assert resp.data['state']['declaration']['file_id'] == 42
        assert resp.data['state']['modeling']['substep'] == 'encoding_completed'

        # Step 5: Verify step regression is blocked
        resp = api_client.put(
            f'/api/pipeline/{pk}/',
            data=json.dumps({'current_step': 'declaration'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['current_step'] == 'modeling'  # NOT declaration

        # Step 6: Delete
        resp = api_client.delete(f'/api/pipeline/{pk}/')
        assert resp.status_code == 200
        resp = api_client.get(f'/api/pipeline/{pk}/')
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Upload → Encoding Analyze → Encoding Apply workflow
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestUploadEncodingWorkflow:

    def test_upload_analyze_apply_encoding(self, api_client, _use_tmp_media, media_root):
        """Upload CSV → analyze categorical features → apply encoding."""
        # Upload CSV with categorical and numeric features
        df = pd.DataFrame({
            'Region': np.random.choice(['North', 'South', 'East', 'West'], 100),
            'Risk': np.random.choice(['Low', 'Medium', 'High'], 100),
            'Score': np.random.uniform(0, 1, 100).round(4),
            'Amount': np.random.uniform(1000, 50000, 100).round(2),
            'Target': np.random.choice([0, 1], 100),
        })
        csv_dir = os.path.join(str(media_root), 'processed')
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, 'enc_workflow.csv')
        df.to_csv(csv_path, index=False)
        rel_path = os.path.relpath(csv_path, str(media_root))

        data_dict = [
            {'Feature_Name': 'Region', 'Level_of_Measurement': 'nominal'},
            {'Feature_Name': 'Risk', 'Level_of_Measurement': 'nominal'},
            {'Feature_Name': 'Score', 'Level_of_Measurement': 'continuous'},
            {'Feature_Name': 'Amount', 'Level_of_Measurement': 'continuous'},
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
        assert resp.data['categorical_count'] >= 2

        # Step 2: Apply encoding
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
        assert 'encoded_file' in resp.data
        summary = resp.data['summary']
        assert summary['total_encoded'] >= 2
        assert summary['encoded_shape'][0] == 100  # rows preserved

        # Step 3: Verify encoded file exists on disk
        encoded_file = resp.data['encoded_file']
        encoded_abs = os.path.join(str(media_root), encoded_file)
        assert os.path.exists(encoded_abs), "Encoded file was not written"

        # Step 4: Verify sidecar metadata was created
        meta_path = encoded_abs.replace('.csv', '.meta.json')
        assert os.path.exists(meta_path), "Encoding metadata sidecar was not written"
        with open(meta_path) as f:
            meta = json.load(f)
        assert 'categorical_columns' in meta
        assert len(meta['categorical_columns']) >= 2


# ---------------------------------------------------------------------------
# SFS results file read-back workflow
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestSfsResultsReadbackWorkflow:

    def test_write_then_read_sfs_results(self, api_client, _use_tmp_media, media_root):
        """Write SFS results JSON to disk, then read back via API."""
        sfs_dir = os.path.join(str(media_root), 'sfs_results')
        os.makedirs(sfs_dir, exist_ok=True)

        sfs_data = {
            'forward': [],
            'backward': [
                {'step': 1, 'feature_name': 'Var_A', 'cv_roc_auc': 0.85, 'selected_features': ['Var_B', 'Var_C']},
                {'step': 2, 'feature_name': 'Var_B', 'cv_roc_auc': 0.82, 'selected_features': ['Var_C']},
            ],
            'forward_from_backward': [
                {'step': 1, 'feature_name': 'Var_C', 'cv_roc_auc': 0.80, 'selected_features': ['Var_C']},
            ],
            'backward_remaining_features': ['Var_B', 'Var_C'],
            'status': 'completed',
            'error': None,
        }

        file_id = 777
        with open(os.path.join(sfs_dir, f'{file_id}_sfs_results.json'), 'w') as f:
            json.dump(sfs_data, f)

        resp = api_client.get(f'/api/modeling/sfs/{file_id}/')
        assert resp.status_code == 200
        data = resp.data
        assert data['sfs_completed'] is True
        assert len(data['backward']) == 2
        assert len(data['forward_from_backward']) == 1
        assert data['forward'] == []


# ---------------------------------------------------------------------------
# Pipeline report generation workflow
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestPipelineReportWorkflow:

    def test_create_pipeline_then_generate_report(self, api_client, _use_tmp_media):
        """Create pipeline with state → generate report → verify HTML content."""
        state = {
            'declaration': {'file_id': 1},
            'modeling': {'substep': 'modeling_completed'},
            'pipeline_notes': {'after_data_preview': 'Data looks clean'},
        }
        resp = api_client.post(
            '/api/pipeline/create/',
            data=json.dumps({'name': 'Report Workflow', 'pipeline_type': 'boosting', 'state': state}),
            content_type='application/json',
        )
        assert resp.status_code == 201
        pk = resp.data['id']

        # Generate HTML report
        resp = api_client.get(f'/api/pipeline/{pk}/report/')
        assert resp.status_code == 200
        html = resp.content.decode('utf-8')
        assert 'Report Workflow' in html
        assert '<html' in html.lower()

        # Generate print-ready report
        resp = api_client.get(f'/api/pipeline/{pk}/report/?output=print')
        assert resp.status_code == 200
        html = resp.content.decode('utf-8')
        assert 'window.print()' in html
