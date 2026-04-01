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
