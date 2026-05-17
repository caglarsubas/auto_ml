"""
FUNCTIONAL TESTS
=================
Test API endpoint behavior and business logic through HTTP requests.
Each test targets a single endpoint and validates request/response contracts.
"""
import io
import json
import os
import pytest
import pandas as pd
import numpy as np
from django.test import override_settings
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def uploaded_declaration(api_client, _use_tmp_media, media_root):
    """Upload a CSV file and return the created declaration data."""
    df = pd.DataFrame({
        'AppID': range(1, 101),
        'Age': np.random.randint(18, 70, 100),
        'Income': np.random.uniform(20000, 150000, 100).round(2),
        'Category': np.random.choice(['A', 'B', 'C'], 100),
        'Target': np.random.choice([0, 1], 100),
    })
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    buf.name = 'test_data.csv'

    response = api_client.post(
        '/api/declaration/',
        {'file': buf, 'column_separator': 'comma'},
        format='multipart',
    )
    assert response.status_code == 201, f"Upload failed: {response.data}"
    return response.data


# ---------------------------------------------------------------------------
# Declaration API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestDeclarationAPI:

    def test_upload_csv_success(self, api_client, _use_tmp_media):
        """POST /api/declaration/ with valid CSV returns 201."""
        df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'simple.csv'

        response = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert response.status_code == 201
        assert 'id' in response.data

    def test_upload_csv_with_headers_sets_has_header_true(self, api_client, _use_tmp_media):
        """CSV with text headers should result in has_header=True."""
        buf = io.BytesIO(b"AppID,Age,Income,Target\n1,25,50000,0\n2,30,60000,1\n")
        buf.name = 'with_header.csv'
        response = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert response.status_code == 201
        assert response.data['has_header'] is True
        assert 'auto_detected_no_header' not in response.data

    def test_upload_csv_without_headers_auto_detects(self, api_client, _use_tmp_media):
        """CSV without headers should auto-detect and set has_header=False."""
        buf = io.BytesIO(
            b"0,1/1/2020,0,0,1750,1\n"
            b"1,2/1/2020,0,0,1300,12\n"
            b"2,3/1/2020,1,1,0,0\n"
        )
        buf.name = 'no_header.csv'
        response = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert response.status_code == 201
        assert response.data['has_header'] is False
        assert response.data.get('auto_detected_no_header') is True

    def test_upload_no_file_returns_400(self, api_client, _use_tmp_media):
        """POST /api/declaration/ without a file returns 400."""
        response = api_client.post('/api/declaration/', {}, format='multipart')
        assert response.status_code == 400

    def test_list_declarations(self, api_client, uploaded_declaration):
        """GET /api/declaration/ returns a list containing uploaded declarations."""
        response = api_client.get('/api/declaration/')
        assert response.status_code == 200
        ids = [d['id'] for d in response.data]
        assert uploaded_declaration['id'] in ids

    def test_retrieve_declaration(self, api_client, uploaded_declaration):
        """GET /api/declaration/<id>/ returns the specific declaration."""
        pk = uploaded_declaration['id']
        response = api_client.get(f'/api/declaration/{pk}/')
        assert response.status_code == 200
        assert response.data['id'] == pk

    def test_delete_declaration(self, api_client, uploaded_declaration):
        """DELETE /api/declaration/<id>/ removes the declaration."""
        pk = uploaded_declaration['id']
        response = api_client.delete(f'/api/declaration/{pk}/')
        assert response.status_code == 204
        response = api_client.get(f'/api/declaration/{pk}/')
        assert response.status_code == 404


@pytest.mark.functional
@pytest.mark.django_db
class TestPreviewAPI:

    def test_preview_returns_expected_keys(self, api_client, uploaded_declaration):
        """GET /api/declaration/<id>/preview/ returns file preview data."""
        pk = uploaded_declaration['id']
        response = api_client.get(f'/api/declaration/{pk}/preview/')
        assert response.status_code == 200
        data = response.data
        assert 'total_rows' in data
        assert 'total_columns' in data
        assert 'columns' in data
        assert data['total_rows'] == 100
        assert data['total_columns'] == 5

    def test_preview_nonexistent_returns_404(self, api_client, _use_tmp_media):
        """Preview of a nonexistent declaration returns 404."""
        response = api_client.get('/api/declaration/99999/preview/')
        assert response.status_code == 404


@pytest.mark.functional
@pytest.mark.django_db
class TestDataDictionaryAPI:

    def test_data_dictionary_returns_columns(self, api_client, uploaded_declaration):
        """GET /api/declaration/<id>/data_dictionary/ returns dictionary with all columns."""
        pk = uploaded_declaration['id']
        response = api_client.get(f'/api/declaration/{pk}/data_dictionary/')
        assert response.status_code == 200
        data = response.data
        assert isinstance(data, list)
        feature_names = [d['Feature_Name'] for d in data]
        assert 'AppID' in feature_names
        assert 'Age' in feature_names
        assert 'Target' in feature_names

    def test_data_dictionary_contains_expected_fields(self, api_client, uploaded_declaration):
        """Each entry in data_dictionary has required keys."""
        pk = uploaded_declaration['id']
        response = api_client.get(f'/api/declaration/{pk}/data_dictionary/')
        assert response.status_code == 200
        for entry in response.data:
            assert 'Feature_Name' in entry
            assert 'Data_Type' in entry
            assert '#_of_Unique_Value' in entry
            assert 'Level_of_Measurement' in entry
            assert 'Missing_Ratio' in entry
            assert 'Mode_Ratio' in entry
            assert 'Model_Usage_YN' in entry

    def test_data_dictionary_handles_inf_and_nan_columns(self, api_client, _use_tmp_media):
        """Columns with inf or all-NaN values must not crash the data_dictionary endpoint."""
        df = pd.DataFrame({
            'Normal': [1, 2, 3, 4, 5],
            'Has_Inf': [1.0, float('inf'), -float('inf'), 4.0, 5.0],
            'All_NaN': [float('nan')] * 5,
            'LogSigned_X': [0.0, 0.693, -0.693, 1.386, float('nan')],
            'A_to_B': [2.0, float('inf'), 0.5, float('nan'), 1.0],
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'inf_nan_test.csv'

        resp = api_client.post(
            '/api/declaration/',
            {'file': buf, 'column_separator': 'comma'},
            format='multipart',
        )
        assert resp.status_code == 201
        pk = resp.data['id']

        resp = api_client.get(f'/api/declaration/{pk}/data_dictionary/')
        assert resp.status_code == 200
        names = [d['Feature_Name'] for d in resp.data]
        assert len(names) == 5
        assert 'Has_Inf' in names
        assert 'All_NaN' in names
        assert 'LogSigned_X' in names
        assert 'A_to_B' in names


# ---------------------------------------------------------------------------
# Preprocessing API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestPreprocessingApplyAPI:

    def test_apply_valid_options(self, api_client, uploaded_declaration, _use_tmp_media):
        """POST /api/preprocessing/apply/ with valid payload succeeds."""
        pk = uploaded_declaration['id']
        response = api_client.post(
            '/api/preprocessing/apply/',
            data=json.dumps({'file_id': pk, 'options': [1, 2, 3]}),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['status'] == 'ok'

    def test_apply_missing_file_id(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/apply/ without file_id returns 400."""
        response = api_client.post(
            '/api/preprocessing/apply/',
            data=json.dumps({'options': [1]}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_apply_invalid_options_type(self, api_client, uploaded_declaration, _use_tmp_media):
        """POST /api/preprocessing/apply/ with non-integer options returns 400."""
        pk = uploaded_declaration['id']
        response = api_client.post(
            '/api/preprocessing/apply/',
            data=json.dumps({'file_id': pk, 'options': ['a', 'b']}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_apply_nonexistent_file(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/apply/ with nonexistent file_id returns 404."""
        response = api_client.post(
            '/api/preprocessing/apply/',
            data=json.dumps({'file_id': 99999, 'options': [1]}),
            content_type='application/json',
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# v2.27.0 — Preprocessing Options Catalog API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestPreprocessingOptionsAPI:
    """GET /api/preprocessing/options/ exposes the canonical 34-option
    purifier catalog so the frontend (and the v2.27.1 AI catalog tool)
    can pull labels/thresholds from a single source of truth instead of
    duplicating them in TypeScript.

    These tests guard the response shape and confirm key IDs that the
    pre-v2.27.0 contract bug had misaligned.
    """

    def test_options_endpoint_returns_200_and_expected_shape(self, api_client):
        response = api_client.get('/api/preprocessing/options/')
        assert response.status_code == 200
        body = response.data
        assert 'options' in body
        assert 'default_selected_ids' in body
        assert isinstance(body['options'], list)
        assert isinstance(body['default_selected_ids'], list)

    def test_options_endpoint_returns_exactly_34_entries(self, api_client):
        response = api_client.get('/api/preprocessing/options/')
        assert response.status_code == 200
        assert len(response.data['options']) == 34

    def test_options_endpoint_entries_have_required_keys(self, api_client):
        response = api_client.get('/api/preprocessing/options/')
        assert response.status_code == 200
        required = {'id', 'name', 'kind', 'group', 'threshold', 'quantile_range'}
        for entry in response.data['options']:
            missing = required - set(entry.keys())
            assert not missing, f"entry id={entry.get('id')} missing keys: {missing}"

    def test_options_endpoint_pins_outlier_quantile_29_to_0_05_0_95(self, api_client):
        """The exact request that triggered the v2.27.0 dig: 'change
        outlier cleaning interval for numerical features to 0.05-0.95'
        must resolve to option ID 29 in the catalog.  v2.27.1's AI
        catalog tool will read this same shape.
        """
        response = api_client.get('/api/preprocessing/options/')
        assert response.status_code == 200
        by_id = {e['id']: e for e in response.data['options']}
        assert by_id[29]['kind'] == 'outlier_quantile_clip'
        # JSON renders tuples as lists.
        assert by_id[29]['quantile_range'] == [0.05, 0.95]

    def test_options_endpoint_pins_post_v2_27_0_realigned_ids(self, api_client):
        """ID labels for the pre-v2.27.0 misaligned slots must match the
        frontend's UI text.  Pinning these in a functional test means
        any future drift on either side trips immediately rather than
        silently routing the user's checkbox to the wrong transform.
        """
        response = api_client.get('/api/preprocessing/options/')
        assert response.status_code == 200
        by_id = {e['id']: e for e in response.data['options']}
        expected_labels = {
            9:  'Corr-drop threshold = 0.75',
            11: 'Sparsity-drop threshold = 0.95',
            17: 'Missing-drop threshold = 0.95',
            23: '[Sparsity+Missing]-drop threshold = 0.95',
            24: '[Sparsity+Missing]-drop threshold = 0.90',
            27: '[Sparsity+Missing]-drop threshold = 0.75',
            29: 'Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]',
        }
        for opt_id, label in expected_labels.items():
            assert by_id[opt_id]['name'] == label, \
                f"id={opt_id} label drifted from v2.27.0 contract"

    def test_options_endpoint_default_selected_ids_subset_of_catalog(self, api_client):
        response = api_client.get('/api/preprocessing/options/')
        assert response.status_code == 200
        catalog_ids = {e['id'] for e in response.data['options']}
        for opt_id in response.data['default_selected_ids']:
            assert opt_id in catalog_ids, f"default id {opt_id} not in catalog"


# ---------------------------------------------------------------------------
# Preprocessing Run API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestPreprocessingRunAPI:

    def test_run_missing_file_id(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/run/ without file_id returns 400."""
        response = api_client.post(
            '/api/preprocessing/run/',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_run_nonexistent_file(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/run/ with nonexistent file returns 404."""
        response = api_client.post(
            '/api/preprocessing/run/',
            data=json.dumps({'file_id': 99999}),
            content_type='application/json',
        )
        assert response.status_code in (400, 404)


# ---------------------------------------------------------------------------
# Preprocessing Status API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestPreprocessingStatusAPI:

    def test_status_no_result(self, api_client, _use_tmp_media):
        """GET /api/preprocessing/status/<id>/ when no run exists returns appropriate status."""
        response = api_client.get('/api/preprocessing/status/99999/')
        assert response.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Modeling Start API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestModelingStartAPI:

    def test_start_missing_file_id(self, api_client, _use_tmp_media):
        """POST /api/modeling/start/ without file_id returns 400."""
        response = api_client.post(
            '/api/modeling/start/',
            data=json.dumps({'processed_file': 'some/path.csv'}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_start_missing_processed_file(self, api_client, _use_tmp_media):
        """POST /api/modeling/start/ without processed_file returns 400."""
        response = api_client.post(
            '/api/modeling/start/',
            data=json.dumps({'file_id': 1}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_start_nonexistent_declaration(self, api_client, _use_tmp_media):
        """POST /api/modeling/start/ with nonexistent file_id returns 404."""
        response = api_client.post(
            '/api/modeling/start/',
            data=json.dumps({'file_id': 99999, 'processed_file': 'some/path.csv'}),
            content_type='application/json',
        )
        assert response.status_code == 404

    def test_start_nonexistent_processed_file(self, api_client, uploaded_declaration, _use_tmp_media):
        """POST /api/modeling/start/ with nonexistent processed file returns 404."""
        pk = uploaded_declaration['id']
        response = api_client.post(
            '/api/modeling/start/',
            data=json.dumps({'file_id': pk, 'processed_file': 'nonexistent/file.csv'}),
            content_type='application/json',
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Modeling Status API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestModelingStatusAPI:

    def test_status_no_training(self, api_client, _use_tmp_media):
        """GET /api/modeling/status/<id>/ when no training exists returns appropriate response."""
        response = api_client.get('/api/modeling/status/99999/')
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            data = response.data
            assert 'status' in data


# ---------------------------------------------------------------------------
# SFS Results API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestSFSResultsAPI:

    def test_sfs_results_no_data(self, api_client, _use_tmp_media):
        """GET /api/modeling/sfs/<id>/ when no SFS results exist returns 404."""
        response = api_client.get('/api/modeling/sfs/99999/')
        assert response.status_code == 404

    def test_sfs_results_with_data(self, api_client, _use_tmp_media, media_root):
        """GET /api/modeling/sfs/<id>/ returns stored SFS results."""
        sfs_dir = os.path.join(str(media_root), 'sfs_results')
        os.makedirs(sfs_dir, exist_ok=True)
        sfs_data = {
            'forward': [{'step': 1, 'feature_name': 'Var_1', 'cv_roc_auc': 0.75}],
            'backward': [],
            'forward_from_backward': [],
            'status': 'completed',
        }
        with open(os.path.join(sfs_dir, '1_sfs_results.json'), 'w') as f:
            json.dump(sfs_data, f)

        response = api_client.get('/api/modeling/sfs/1/')
        assert response.status_code == 200
        data = response.data
        assert 'forward' in data
        assert len(data['forward']) == 1


# ---------------------------------------------------------------------------
# SFS Start API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestSFSStartAPI:

    def test_start_sfs_missing_file_id(self, api_client, _use_tmp_media):
        """POST /api/modeling/sfs/start/ without file_id returns 400."""
        response = api_client.post(
            '/api/modeling/sfs/start/',
            data=json.dumps({'methods': ['backward']}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_start_sfs_missing_methods(self, api_client, _use_tmp_media):
        """POST /api/modeling/sfs/start/ with explicit empty methods returns 400."""
        response = api_client.post(
            '/api/modeling/sfs/start/',
            data=json.dumps({'file_id': 1, 'methods': []}),
            content_type='application/json',
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# SFS Status API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestSFSStatusAPI:

    def test_sfs_status_no_run(self, api_client, _use_tmp_media):
        """GET /api/modeling/sfs/status/<id>/ when no SFS is running returns idle."""
        response = api_client.get('/api/modeling/sfs/status/99999/')
        assert response.status_code == 200
        assert 'status' in response.data


# ---------------------------------------------------------------------------
# SFS Stop API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestSFSStopAPI:

    def test_stop_sfs_no_run(self, api_client, _use_tmp_media):
        """POST /api/modeling/sfs/stop/<id>/ when no SFS is running returns 404."""
        response = api_client.post('/api/modeling/sfs/stop/99999/', {}, content_type='application/json')
        assert response.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Encoding Analyze API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestEncodingAnalyzeAPI:

    def test_analyze_missing_processed_file(self, api_client, _use_tmp_media):
        """POST /api/encoding/analyze/ without processed_file returns 400."""
        response = api_client.post(
            '/api/encoding/analyze/',
            data=json.dumps({'file_id': 1}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_analyze_nonexistent_file(self, api_client, _use_tmp_media):
        """POST /api/encoding/analyze/ with nonexistent file returns 404."""
        response = api_client.post(
            '/api/encoding/analyze/',
            data=json.dumps({'file_id': 1, 'processed_file': 'nonexistent/file.csv'}),
            content_type='application/json',
        )
        assert response.status_code == 404

    def test_analyze_success(self, api_client, _use_tmp_media, media_root):
        """POST /api/encoding/analyze/ with valid CSV returns encoding plan."""
        df = pd.DataFrame({
            'Region': ['North', 'South', 'East'] * 10,
            'Score': np.random.uniform(0, 1, 30),
            'Target': np.random.choice([0, 1], 30),
        })
        csv_dir = os.path.join(str(media_root), 'processed')
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, 'test_proc.csv')
        df.to_csv(csv_path, index=False)
        rel_path = os.path.relpath(csv_path, str(media_root))

        data_dict = [
            {'Feature_Name': 'Region', 'Level_of_Measurement': 'nominal'},
            {'Feature_Name': 'Score', 'Level_of_Measurement': 'continuous'},
        ]
        response = api_client.post(
            '/api/encoding/analyze/',
            data=json.dumps({
                'file_id': 1,
                'processed_file': rel_path,
                'data_dictionary': data_dict,
            }),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert 'plan' in response.data
        assert response.data['categorical_count'] >= 1


# ---------------------------------------------------------------------------
# Encoding Apply API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestEncodingApplyAPI:

    def test_apply_missing_processed_file(self, api_client, _use_tmp_media):
        """POST /api/encoding/apply/ without processed_file returns 400."""
        response = api_client.post(
            '/api/encoding/apply/',
            data=json.dumps({'file_id': 1, 'plan': []}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_apply_nonexistent_file(self, api_client, _use_tmp_media):
        """POST /api/encoding/apply/ with nonexistent file returns 404."""
        response = api_client.post(
            '/api/encoding/apply/',
            data=json.dumps({'file_id': 1, 'processed_file': 'nonexistent.csv', 'plan': []}),
            content_type='application/json',
        )
        assert response.status_code == 404

    def test_apply_empty_plan(self, api_client, _use_tmp_media, media_root):
        """POST /api/encoding/apply/ with empty plan succeeds (no-op encoding)."""
        df = pd.DataFrame({'Score': [0.5, 0.7, 0.3], 'Target': [0, 1, 0]})
        csv_dir = os.path.join(str(media_root), 'processed')
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, 'enc_test.csv')
        df.to_csv(csv_path, index=False)
        rel_path = os.path.relpath(csv_path, str(media_root))

        response = api_client.post(
            '/api/encoding/apply/',
            data=json.dumps({'file_id': 1, 'processed_file': rel_path, 'plan': []}),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert 'encoded_file' in response.data
        assert response.data['summary']['total_encoded'] == 0

    def test_apply_with_plan(self, api_client, _use_tmp_media, media_root):
        """POST /api/encoding/apply/ with a plan encodes categorical features."""
        df = pd.DataFrame({
            'Region': ['North', 'South', 'East'] * 10,
            'Score': np.random.uniform(0, 1, 30),
            'Target': np.random.choice([0, 1], 30),
        })
        csv_dir = os.path.join(str(media_root), 'processed')
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, 'enc_plan_test.csv')
        df.to_csv(csv_path, index=False)
        rel_path = os.path.relpath(csv_path, str(media_root))

        plan = [{
            'feature': 'Region',
            'original_lom': 'nominal',
            'user_lom': 'nominal',
            'nunique': 3,
        }]
        response = api_client.post(
            '/api/encoding/apply/',
            data=json.dumps({'file_id': 1, 'processed_file': rel_path, 'plan': plan}),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['summary']['total_encoded'] == 1
        assert 'report' in response.data


# ---------------------------------------------------------------------------
# Pipeline CRUD API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestPipelineListAPI:

    def test_list_empty(self, api_client, _use_tmp_media):
        """GET /api/pipeline/ returns empty list when no runs exist."""
        response = api_client.get('/api/pipeline/')
        assert response.status_code == 200
        assert isinstance(response.data, list)

    def test_list_returns_created_runs(self, api_client, _use_tmp_media):
        """GET /api/pipeline/ returns created runs."""
        from modeling.models import PipelineRun
        PipelineRun.objects.create(name='Run1')
        PipelineRun.objects.create(name='Run2')
        response = api_client.get('/api/pipeline/')
        assert response.status_code == 200
        assert len(response.data) >= 2
        names = [r['name'] for r in response.data]
        assert 'Run1' in names
        assert 'Run2' in names

    def test_list_contains_detailed_step(self, api_client, _use_tmp_media):
        """Pipeline list includes the detailed_step field."""
        from modeling.models import PipelineRun
        PipelineRun.objects.create(name='DetailedTest', current_step='preprocessing')
        response = api_client.get('/api/pipeline/')
        assert response.status_code == 200
        run = next(r for r in response.data if r['name'] == 'DetailedTest')
        assert 'detailed_step' in run


@pytest.mark.functional
@pytest.mark.django_db
class TestPipelineCreateAPI:

    def test_create_with_name(self, api_client, _use_tmp_media):
        """POST /api/pipeline/create/ with name creates a new run."""
        response = api_client.post(
            '/api/pipeline/create/',
            data=json.dumps({'name': 'My Pipeline', 'pipeline_type': 'boosting'}),
            content_type='application/json',
        )
        assert response.status_code == 201
        assert response.data['name'] == 'My Pipeline'
        assert response.data['status'] == 'active'

    def test_create_auto_name(self, api_client, _use_tmp_media):
        """POST /api/pipeline/create/ without name auto-generates name."""
        response = api_client.post(
            '/api/pipeline/create/',
            data=json.dumps({'pipeline_type': 'boosting'}),
            content_type='application/json',
        )
        assert response.status_code == 201
        assert 'boosting' in response.data['name']

    def test_create_with_state(self, api_client, _use_tmp_media):
        """POST /api/pipeline/create/ with state stores it."""
        state = {'declaration': {'file_id': 5}}
        response = api_client.post(
            '/api/pipeline/create/',
            data=json.dumps({'name': 'Stateful', 'state': state}),
            content_type='application/json',
        )
        assert response.status_code == 201


@pytest.mark.functional
@pytest.mark.django_db
class TestPipelineDetailAPI:

    def _create_run(self):
        from modeling.models import PipelineRun
        return PipelineRun.objects.create(name='Detail Test', pipeline_type='boosting')

    def test_get_pipeline_run(self, api_client, _use_tmp_media):
        """GET /api/pipeline/<pk>/ retrieves a specific run."""
        run = self._create_run()
        response = api_client.get(f'/api/pipeline/{run.pk}/')
        assert response.status_code == 200
        assert response.data['name'] == 'Detail Test'
        assert 'state' in response.data

    def test_get_nonexistent_returns_404(self, api_client, _use_tmp_media):
        """GET /api/pipeline/<pk>/ for nonexistent run returns 404."""
        response = api_client.get('/api/pipeline/99999/')
        assert response.status_code == 404

    def test_update_pipeline_run(self, api_client, _use_tmp_media):
        """PUT /api/pipeline/<pk>/ updates name and step."""
        run = self._create_run()
        response = api_client.put(
            f'/api/pipeline/{run.pk}/',
            data=json.dumps({'name': 'Updated', 'current_step': 'preprocessing'}),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['name'] == 'Updated'
        assert response.data['current_step'] == 'preprocessing'

    def test_update_step_regression_blocked(self, api_client, _use_tmp_media):
        """PUT /api/pipeline/<pk>/ blocks step regression (e.g. modeling → declaration)."""
        from modeling.models import PipelineRun
        run = PipelineRun.objects.create(name='Regression Test', current_step='modeling')
        response = api_client.put(
            f'/api/pipeline/{run.pk}/',
            data=json.dumps({'current_step': 'declaration'}),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['current_step'] == 'modeling'  # unchanged

    def test_update_same_step_allowed(self, api_client, _use_tmp_media):
        """PUT /api/pipeline/<pk>/ allows updates within the same step."""
        from modeling.models import PipelineRun
        run = PipelineRun.objects.create(name='Same Step', current_step='modeling')
        response = api_client.put(
            f'/api/pipeline/{run.pk}/',
            data=json.dumps({'current_step': 'modeling', 'state': {'modeling': {'substep': 'encoding_completed'}}}),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['current_step'] == 'modeling'

    def test_delete_pipeline_run(self, api_client, _use_tmp_media):
        """DELETE /api/pipeline/<pk>/ removes the run."""
        run = self._create_run()
        response = api_client.delete(f'/api/pipeline/{run.pk}/')
        assert response.status_code == 200
        response = api_client.get(f'/api/pipeline/{run.pk}/')
        assert response.status_code == 404

    def test_delete_nonexistent_returns_404(self, api_client, _use_tmp_media):
        """DELETE /api/pipeline/<pk>/ for nonexistent run returns 404."""
        response = api_client.delete('/api/pipeline/99999/')
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Pipeline Report API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestPipelineReportAPI:

    def test_report_nonexistent_returns_404(self, api_client, _use_tmp_media):
        """GET /api/pipeline/<pk>/report/ for nonexistent run returns 404."""
        response = api_client.get('/api/pipeline/99999/report/')
        assert response.status_code == 404

    def test_report_html_download(self, api_client, _use_tmp_media):
        """GET /api/pipeline/<pk>/report/ returns HTML attachment."""
        from modeling.models import PipelineRun
        run = PipelineRun.objects.create(name='Report Test', state={'declaration': {}})
        response = api_client.get(f'/api/pipeline/{run.pk}/report/')
        assert response.status_code == 200
        assert 'text/html' in response['Content-Type']
        assert 'attachment' in response.get('Content-Disposition', '')

    def test_report_print_format(self, api_client, _use_tmp_media):
        """GET /api/pipeline/<pk>/report/?output=print returns inline HTML with print script."""
        from modeling.models import PipelineRun
        run = PipelineRun.objects.create(name='Print Test', state={})
        response = api_client.get(f'/api/pipeline/{run.pk}/report/?output=print')
        assert response.status_code == 200
        assert 'text/html' in response['Content-Type']
        content = response.content.decode('utf-8')
        assert 'window.print()' in content


# ---------------------------------------------------------------------------
# Feature Explainability API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestFeatureExplainabilityAPI:

    def test_explainability_missing_fields(self, api_client, _use_tmp_media):
        """POST /api/modeling/feature-explainability/ without required fields returns 400."""
        response = api_client.post(
            '/api/modeling/feature-explainability/',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_explainability_feature_not_in_model(self, api_client, _use_tmp_media):
        """POST with feature not in selected_features returns 404."""
        response = api_client.post(
            '/api/modeling/feature-explainability/',
            data=json.dumps({
                'file_id': 1,
                'feature_name': 'Age',
                'selected_features': ['Income', 'Score'],
            }),
            content_type='application/json',
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# VIF Detail API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestVifDetailAPI:

    def test_vif_missing_fields(self, api_client, _use_tmp_media):
        """POST /api/modeling/vif-detail/ without required fields returns 400."""
        response = api_client.post(
            '/api/modeling/vif-detail/',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Feature Card Stacked Data API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestFeatureCardStackedDataAPI:

    def test_stacked_data_nonexistent_file(self, api_client, _use_tmp_media):
        """GET stacked feature data for nonexistent file returns appropriate error."""
        response = api_client.get('/api/feature-card/99999/get_stacked_feature_data/', {'column': 'Age'})
        assert response.status_code in (400, 404, 500)

    def test_stacked_data_success(self, api_client, _use_tmp_media):
        """GET stacked feature data with valid file returns stacked_data and target_averages."""
        n = 100
        df = pd.DataFrame({
            'Category': np.random.choice(['A', 'B', 'C'], n),
            'Target': np.random.choice([0, 1], n),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'stacked_test.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        response = api_client.get(
            f'/api/feature-card/{file_id}/get_stacked_feature_data/',
            {'column': 'Category'},
        )
        assert response.status_code == 200
        data = response.json()
        assert 'stacked_data' in data
        assert 'target_averages' in data
        # stacked_data should have keys for each target class
        assert '0' in data['stacked_data'] or '1' in data['stacked_data']
        # target_averages should be a list with category entries
        assert isinstance(data['target_averages'], list)
        if data['target_averages']:
            entry = data['target_averages'][0]
            assert 'category' in entry
            assert 'count' in entry
            assert 'volume_share' in entry
            assert 'target_average' in entry

    def test_stacked_data_missing_column(self, api_client, _use_tmp_media):
        """GET stacked feature data with missing column returns 404."""
        df = pd.DataFrame({'X': [1, 2], 'Target': [0, 1]})
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'stacked_missing.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        response = api_client.get(
            f'/api/feature-card/{file_id}/get_stacked_feature_data/',
            {'column': 'NonExistent'},
        )
        assert response.status_code == 404

    def test_stacked_data_no_column_param(self, api_client, _use_tmp_media):
        """GET stacked feature data without column param returns 400."""
        df = pd.DataFrame({'X': [1], 'Target': [0]})
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'stacked_no_col.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        response = api_client.get(f'/api/feature-card/{file_id}/get_stacked_feature_data/')
        assert response.status_code == 400

    def test_stacked_data_numeric_high_cardinality(self, api_client, _use_tmp_media):
        """GET stacked data for numeric column with >20 unique returns array format."""
        n = 100
        df = pd.DataFrame({
            'Score': np.random.uniform(0, 100, n),
            'Target': np.random.choice([0, 1], n),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'stacked_numeric.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        response = api_client.get(
            f'/api/feature-card/{file_id}/get_stacked_feature_data/',
            {'column': 'Score'},
        )
        assert response.status_code == 200
        data = response.json()
        # High-cardinality numeric → array format (no target_averages)
        assert 'stacked_data' in data
        assert data['target_averages'] is None


# ---------------------------------------------------------------------------
# Feature Card get_feature_info API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestFeatureCardInfoAPI:

    def test_feature_info_numeric_success(self, api_client, _use_tmp_media):
        """GET /api/feature-card/<id>/get_feature_info/ returns stats for numeric column."""
        df = pd.DataFrame({
            'Age': np.random.randint(18, 70, 200),
            'Name': np.random.choice(['Alice', 'Bob'], 200),
            'Target': np.random.choice([0, 1], 200),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'fc_numeric.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        response = api_client.get(f'/api/feature-card/{file_id}/get_feature_info/', {'column': 'Age'})
        assert response.status_code == 200
        assert response.data['Feature_Name'] == 'Age'
        assert 'Descriptive_Stats' in response.data
        stats = response.data['Descriptive_Stats']
        assert 'Mean' in stats
        assert 'Min' in stats
        assert 'Max' in stats
        assert 'Std' in stats

    def test_feature_info_categorical_success(self, api_client, _use_tmp_media):
        """GET /api/feature-card/<id>/get_feature_info/ returns stats for categorical column."""
        df = pd.DataFrame({
            'Color': np.random.choice(['Red', 'Blue', 'Green'], 100),
            'Target': np.random.choice([0, 1], 100),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'fc_categorical.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        response = api_client.get(f'/api/feature-card/{file_id}/get_feature_info/', {'column': 'Color'})
        assert response.status_code == 200
        assert response.data['Feature_Name'] == 'Color'
        stats = response.data['Descriptive_Stats']
        assert '#_of_Categories' in stats
        assert 'Mode_Value' in stats
        assert 'value_counts' in stats

    def test_feature_info_no_column_returns_400(self, api_client, _use_tmp_media):
        """GET /api/feature-card/<id>/get_feature_info/ without column returns 400."""
        df = pd.DataFrame({'X': [1], 'Target': [0]})
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'fc_no_col.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        response = api_client.get(f'/api/feature-card/{file_id}/get_feature_info/')
        assert response.status_code == 400

    def test_feature_info_missing_column_returns_404(self, api_client, _use_tmp_media):
        """GET /api/feature-card/<id>/get_feature_info/ with nonexistent column returns 404."""
        df = pd.DataFrame({'A': [1, 2], 'Target': [0, 1]})
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'fc_bad_col.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        response = api_client.get(f'/api/feature-card/{file_id}/get_feature_info/', {'column': 'Nonexistent'})
        assert response.status_code == 404

    def test_feature_info_file_override(self, api_client, _use_tmp_media, media_root):
        """GET /api/feature-card/<id>/get_feature_info/ with file_override uses override file."""
        df_orig = pd.DataFrame({'X': [1, 2], 'Target': [0, 1]})
        buf = io.BytesIO()
        df_orig.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'fc_override_orig.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        # Create override file with different data
        override_dir = os.path.join(str(media_root), 'processed')
        os.makedirs(override_dir, exist_ok=True)
        df_override = pd.DataFrame({'Age': np.random.randint(18, 70, 50), 'Target': np.random.choice([0, 1], 50)})
        override_path = os.path.join(override_dir, 'override_fc.csv')
        df_override.to_csv(override_path, index=False)
        rel_path = os.path.relpath(override_path, str(media_root))

        response = api_client.get(
            f'/api/feature-card/{file_id}/get_feature_info/',
            {'column': 'Age', 'file_override': rel_path},
        )
        assert response.status_code == 200
        assert response.data['Feature_Name'] == 'Age'


# ---------------------------------------------------------------------------
# Preprocessing DatqDetail API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestDatqDetailAPI:

    def test_datq_detail_missing_file_id(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/datq_detail/ without file_id returns 400."""
        response = api_client.post(
            '/api/preprocessing/datq_detail/',
            data=json.dumps({'processed_file': 'x.csv', 'column': 'A'}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_datq_detail_missing_processed_file(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/datq_detail/ without processed_file returns 400."""
        response = api_client.post(
            '/api/preprocessing/datq_detail/',
            data=json.dumps({'file_id': 1, 'column': 'A'}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_datq_detail_missing_column(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/datq_detail/ without column returns 400."""
        response = api_client.post(
            '/api/preprocessing/datq_detail/',
            data=json.dumps({'file_id': 1, 'processed_file': 'x.csv'}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_datq_detail_nonexistent_declaration(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/datq_detail/ with nonexistent file_id returns 404."""
        response = api_client.post(
            '/api/preprocessing/datq_detail/',
            data=json.dumps({'file_id': 99999, 'processed_file': 'x.csv', 'column': 'A'}),
            content_type='application/json',
        )
        assert response.status_code == 404

    def test_datq_detail_nonexistent_file(self, api_client, uploaded_declaration, _use_tmp_media):
        """POST /api/preprocessing/datq_detail/ with nonexistent processed_file returns 404."""
        pk = uploaded_declaration['id']
        response = api_client.post(
            '/api/preprocessing/datq_detail/',
            data=json.dumps({'file_id': pk, 'processed_file': 'nonexistent.csv', 'column': 'Age'}),
            content_type='application/json',
        )
        assert response.status_code == 404

    def test_datq_detail_column_not_in_file(self, api_client, uploaded_declaration, _use_tmp_media, media_root):
        """POST /api/preprocessing/datq_detail/ with column not in file returns 400."""
        pk = uploaded_declaration['id']
        # Create a small CSV as "processed" file
        df = pd.DataFrame({'Score': [1, 2, 3], 'Target': [0, 1, 0]})
        csv_dir = os.path.join(str(media_root), 'processed')
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, 'datq_detail_test.csv')
        df.to_csv(csv_path, index=False)
        rel_path = os.path.relpath(csv_path, str(media_root))

        response = api_client.post(
            '/api/preprocessing/datq_detail/',
            data=json.dumps({'file_id': pk, 'processed_file': rel_path, 'column': 'NonExistent'}),
            content_type='application/json',
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Preprocessing DatqTimeseries API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestDatqTimeseriesAPI:

    def test_timeseries_missing_file_id(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/datq_timeseries/ without file_id returns 400."""
        response = api_client.post(
            '/api/preprocessing/datq_timeseries/',
            data=json.dumps({'processed_file': 'x.csv', 'column': 'A', 'date_column': 'D'}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_timeseries_missing_processed_file(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/datq_timeseries/ without processed_file returns 400."""
        response = api_client.post(
            '/api/preprocessing/datq_timeseries/',
            data=json.dumps({'file_id': 1, 'column': 'A', 'date_column': 'D'}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_timeseries_missing_column(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/datq_timeseries/ without column returns 400."""
        response = api_client.post(
            '/api/preprocessing/datq_timeseries/',
            data=json.dumps({'file_id': 1, 'processed_file': 'x.csv', 'date_column': 'D'}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_timeseries_missing_date_column(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/datq_timeseries/ without date_column returns 400."""
        response = api_client.post(
            '/api/preprocessing/datq_timeseries/',
            data=json.dumps({'file_id': 1, 'processed_file': 'x.csv', 'column': 'A'}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_timeseries_nonexistent_declaration(self, api_client, _use_tmp_media):
        """POST /api/preprocessing/datq_timeseries/ with nonexistent file_id returns 404."""
        response = api_client.post(
            '/api/preprocessing/datq_timeseries/',
            data=json.dumps({
                'file_id': 99999, 'processed_file': 'x.csv',
                'column': 'A', 'date_column': 'D',
            }),
            content_type='application/json',
        )
        assert response.status_code == 404

    def test_timeseries_nonexistent_file(self, api_client, uploaded_declaration, _use_tmp_media):
        """POST /api/preprocessing/datq_timeseries/ with nonexistent processed_file returns 404."""
        pk = uploaded_declaration['id']
        response = api_client.post(
            '/api/preprocessing/datq_timeseries/',
            data=json.dumps({
                'file_id': pk, 'processed_file': 'nonexistent.csv',
                'column': 'Age', 'date_column': 'Date',
            }),
            content_type='application/json',
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Preprocessing DatqSummaryRow API (functional coverage)
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestDatqSummaryRowFunctionalAPI:

    def test_summary_row_missing_column_param(self, api_client, _use_tmp_media):
        """GET /api/preprocessing/datq_summary_row/<id>/ without column returns 400."""
        response = api_client.get('/api/preprocessing/datq_summary_row/1/')
        assert response.status_code == 400

    def test_summary_row_nonexistent_file_returns_null(self, api_client, _use_tmp_media, media_root):
        """GET /api/preprocessing/datq_summary_row/<id>/ with no saved JSON returns {row: None}."""
        response = api_client.get('/api/preprocessing/datq_summary_row/99999/', {'column': 'Age'})
        assert response.status_code == 200
        assert response.data['row'] is None

    def test_summary_row_success(self, api_client, _use_tmp_media, media_root):
        """GET /api/preprocessing/datq_summary_row/<id>/ with existing JSON returns data."""
        dq_dir = os.path.join(str(media_root), 'data_quality')
        os.makedirs(dq_dir, exist_ok=True)
        summary = [
            {'Variable': 'Age', 'PSI': 0.05, 'Datq_Decision': 'Accept'},
            {'Variable': 'Income', 'PSI': 0.30, 'Datq_Decision': 'Review'},
        ]
        with open(os.path.join(dq_dir, '42_datq_summary.json'), 'w') as f:
            json.dump(summary, f)

        response = api_client.get('/api/preprocessing/datq_summary_row/42/', {'column': 'Age'})
        assert response.status_code == 200
        row = response.data['row']
        assert row is not None
        assert row['Variable'] == 'Age'
        assert row['PSI'] == 0.05

    def test_summary_row_feature_not_found_returns_null(self, api_client, _use_tmp_media, media_root):
        """GET /api/preprocessing/datq_summary_row/<id>/ with missing feature returns {row: None}."""
        dq_dir = os.path.join(str(media_root), 'data_quality')
        os.makedirs(dq_dir, exist_ok=True)
        summary = [{'Variable': 'Age', 'PSI': 0.05}]
        with open(os.path.join(dq_dir, '43_datq_summary.json'), 'w') as f:
            json.dump(summary, f)

        response = api_client.get('/api/preprocessing/datq_summary_row/43/', {'column': 'NonExistent'})
        assert response.status_code == 200
        assert response.data['row'] is None


# ---------------------------------------------------------------------------
# AI Assistant Chat API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestAIAssistantChatAPI:

    def test_chat_missing_message(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/chat/ without message returns 400."""
        response = api_client.post(
            '/api/ai-assistant/chat/',
            data=json.dumps({'context': {}, 'section': 'general'}),
            content_type='application/json',
        )
        assert response.status_code == 400
        assert 'error' in response.data

    def test_chat_empty_message(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/chat/ with empty message returns 400."""
        response = api_client.post(
            '/api/ai-assistant/chat/',
            data=json.dumps({'message': '', 'context': {}}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_chat_no_api_key_returns_503(self, api_client, _use_tmp_media, monkeypatch):
        """POST /api/ai-assistant/chat/ without OPENAI_API_KEY returns 503."""
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)
        response = api_client.post(
            '/api/ai-assistant/chat/',
            data=json.dumps({'message': 'Hello', 'context': {}, 'section': 'general'}),
            content_type='application/json',
        )
        assert response.status_code == 503
        assert 'API key' in response.data['error']


# ---------------------------------------------------------------------------
# AI Action Execute API
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestAIActionExecuteAPI:

    def test_execute_missing_file_id(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/execute-action/ without file_id returns 400."""
        response = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({'action_type': 'update_notes', 'payload': {}}),
            content_type='application/json',
        )
        assert response.status_code == 400
        assert response.data['status'] == 'error'

    def test_execute_missing_action_type(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/execute-action/ without action_type returns 400."""
        response = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({'file_id': 1, 'payload': {}}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_execute_unknown_action_type(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/execute-action/ with unknown action returns 400."""
        response = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({'file_id': 1, 'action_type': 'totally_bogus', 'payload': {}}),
            content_type='application/json',
        )
        assert response.status_code == 400
        assert 'Unknown action type' in response.data['error']

    def test_execute_update_notes_success(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/execute-action/ update_notes succeeds without DB."""
        response = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': 1,
                'action_type': 'update_notes',
                'payload': {
                    'action': 'add',
                    'position': 'after_data_preview',
                    'content': 'Test note',
                },
            }),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['status'] == 'success'
        assert response.data['action_type'] == 'update_notes'
        assert response.data['content'] == 'Test note'

    def test_execute_update_notes_invalid_position(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/execute-action/ update_notes with invalid position returns error."""
        response = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': 1,
                'action_type': 'update_notes',
                'payload': {'action': 'add', 'position': 'invalid_position', 'content': 'x'},
            }),
            content_type='application/json',
        )
        assert response.status_code == 400
        assert 'Invalid note position' in response.data['error']

    def test_execute_update_metadata_no_updates(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/execute-action/ update_metadata with no updates returns error."""
        response = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': 1,
                'action_type': 'update_metadata',
                'payload': {'updates': []},
            }),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_execute_update_config_no_updates(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/execute-action/ update_config with no updates returns error."""
        response = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': 1,
                'action_type': 'update_config',
                'payload': {'updates': []},
            }),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_execute_code_nonexistent_file(self, api_client, _use_tmp_media):
        """POST /api/ai-assistant/execute-action/ execute_code with missing file returns error."""
        response = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': 99999,
                'action_type': 'execute_code',
                'payload': {'code': 'df["New"] = 1', 'description': 'test'},
            }),
            content_type='application/json',
        )
        assert response.status_code == 400
        assert 'not found' in response.data['error']


# ---------------------------------------------------------------------------
# AI Model List Endpoint Tests
# ---------------------------------------------------------------------------
@pytest.mark.functional
@pytest.mark.django_db
class TestAIModelListAPI:

    def test_models_endpoint_returns_200(self, api_client, _use_tmp_media):
        """GET /api/ai-assistant/models/ returns 200."""
        response = api_client.get('/api/ai-assistant/models/')
        assert response.status_code == 200

    def test_models_endpoint_returns_list(self, api_client, _use_tmp_media):
        """GET /api/ai-assistant/models/ returns a list of models."""
        response = api_client.get('/api/ai-assistant/models/')
        assert 'models' in response.data
        assert isinstance(response.data['models'], list)
        # 3 OpenAI (gpt-5.5, gpt-5.4-mini, gpt-4.1-mini) — engine entries are
        # now discovered dynamically and may or may not be present in the
        # test environment depending on whether the engine is reachable.
        assert len(response.data['models']) >= 3

    def test_models_endpoint_returns_default(self, api_client, _use_tmp_media):
        """GET /api/ai-assistant/models/ returns a default model key."""
        response = api_client.get('/api/ai-assistant/models/')
        assert 'default' in response.data
        assert response.data['default'] == 'gpt-5.5'

    def test_models_have_expected_keys(self, api_client, _use_tmp_media):
        """Each model in the response has key, display_name, and provider."""
        response = api_client.get('/api/ai-assistant/models/')
        for m in response.data['models']:
            assert 'key' in m
            assert 'display_name' in m
            assert 'provider' in m

    def test_engine_models_present(self, api_client, _use_tmp_media):
        """Engine-routed local models are included in the response.

        Engine entries are now discovered dynamically from the engine's
        ``/v1/models`` endpoint, so this test only asserts that *some*
        engine-routed models show up — naming follows the
        ``engine-{id with ':' → '-'}`` convention.  Asserting specific keys
        would couple the test to whichever ollama models happen to be on
        the engine's disk in CI.
        """
        response = api_client.get('/api/ai-assistant/models/')
        engine_keys = [m['key'] for m in response.data['models']
                       if m['provider'] == 'engine']
        assert engine_keys, "expected at least one engine-routed model"
        for k in engine_keys:
            assert k.startswith('engine-')

    def test_models_include_meta_flags(self, api_client, _use_tmp_media):
        """Each model in the response includes architecture/reasoning/thinking flags."""
        response = api_client.get('/api/ai-assistant/models/')
        for m in response.data['models']:
            assert 'architecture' in m
            assert 'reasoning' in m
            assert 'thinking' in m
            assert 'thinking_level' in m

    def test_chat_with_model_param_missing_key(self, api_client, _use_tmp_media, monkeypatch):
        """POST /api/ai-assistant/chat/ with unknown model falls back to default (503 without key)."""
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)
        response = api_client.post(
            '/api/ai-assistant/chat/',
            data=json.dumps({
                'message': 'Hello',
                'context': {},
                'section': 'general',
                'model': 'unknown-model-xyz',
            }),
            content_type='application/json',
        )
        # Falls back to gpt-4.1 which requires OPENAI_API_KEY
        assert response.status_code == 503
