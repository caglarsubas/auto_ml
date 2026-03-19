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
