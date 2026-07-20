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


# ---------------------------------------------------------------------------
# Upload → Feature Card → Stacked Data workflow
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestUploadFeatureCardStackedWorkflow:

    def test_upload_feature_info_stacked_data(self, api_client, _use_tmp_media):
        """Upload CSV → get feature info → get stacked data for same column."""
        n = 200
        df = pd.DataFrame({
            'Region': np.random.choice(['North', 'South', 'East', 'West'], n),
            'Score': np.random.uniform(0, 100, n).round(2),
            'Target': np.random.choice([0, 1], n),
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'fc_stacked_workflow.csv'

        # Step 1: Upload
        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        # Step 2: Feature info for categorical
        resp = api_client.get(f'/api/feature-card/{file_id}/get_feature_info/', {'column': 'Region'})
        assert resp.status_code == 200
        assert resp.data['Feature_Name'] == 'Region'
        assert resp.data['Level_of_Measurement'] == 'nominal'
        assert '#_of_Categories' in resp.data['Descriptive_Stats']

        # Step 3: Stacked data for same column
        resp = api_client.get(f'/api/feature-card/{file_id}/get_stacked_feature_data/', {'column': 'Region'})
        assert resp.status_code == 200
        data = resp.json()
        assert 'stacked_data' in data
        assert 'target_averages' in data
        assert isinstance(data['target_averages'], list)
        assert len(data['target_averages']) == 4  # North, South, East, West

        # Step 4: Feature info for numeric
        resp = api_client.get(f'/api/feature-card/{file_id}/get_feature_info/', {'column': 'Score'})
        assert resp.status_code == 200
        assert resp.data['Level_of_Measurement'] == 'continuous'
        assert 'Mean' in resp.data['Descriptive_Stats']

    def test_upload_feature_card_with_file_override(self, api_client, _use_tmp_media, media_root):
        """Upload CSV → create processed file → use file_override to switch data versions."""
        n = 100
        # Original (raw) data
        df_raw = pd.DataFrame({
            'Income': np.random.uniform(20000, 150000, n).round(2),
            'Region': np.random.choice(['A', 'B', 'C'], n),
            'Target': np.random.choice([0, 1], n),
        })
        buf = io.BytesIO()
        df_raw.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'version_test.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        # Create "processed" version with different stats
        proc_dir = os.path.join(str(media_root), 'processed')
        os.makedirs(proc_dir, exist_ok=True)
        df_proc = df_raw.copy()
        df_proc['Income'] = df_proc['Income'] / 1000  # scale down
        proc_path = os.path.join(proc_dir, 'processed_version.csv')
        df_proc.to_csv(proc_path, index=False)
        rel_path = os.path.relpath(proc_path, str(media_root))

        # Get feature info from RAW
        resp_raw = api_client.get(f'/api/feature-card/{file_id}/get_feature_info/', {'column': 'Income'})
        assert resp_raw.status_code == 200
        mean_raw = resp_raw.data['Descriptive_Stats']['Mean']

        # Get feature info from PROCESSED via file_override
        resp_proc = api_client.get(
            f'/api/feature-card/{file_id}/get_feature_info/',
            {'column': 'Income', 'file_override': rel_path},
        )
        assert resp_proc.status_code == 200
        mean_proc = resp_proc.data['Descriptive_Stats']['Mean']

        # Processed should have ~1000x smaller mean
        assert mean_raw > mean_proc * 500, "file_override should produce different stats"


# ---------------------------------------------------------------------------
# AI Action Execute end-to-end workflow
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestAIActionExecuteWorkflow:

    def test_upload_then_execute_code(self, api_client, _use_tmp_media):
        """Upload CSV → execute AI code action → verify changes."""
        df = pd.DataFrame({
            'A': [10, 20, 30, 40, 50],
            'B': [1, 2, 3, 4, 5],
            'Target': [0, 1, 0, 1, 0],
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'ai_code_test.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        # Execute code to add a new column
        resp = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': file_id,
                'action_type': 'execute_code',
                'payload': {
                    'code': 'df["Ratio"] = df["A"] / df["B"]',
                    'description': 'Add A/B ratio column',
                },
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'
        assert 'Ratio' in resp.data['changes']['columns_added']
        assert resp.data['changes']['rows_before'] == 5
        assert resp.data['changes']['rows_after'] == 5

        # Verify the new column is visible via preview
        resp = api_client.get(f'/api/declaration/{file_id}/preview/')
        assert resp.status_code == 200
        assert 'Ratio' in resp.data['columns']

    def test_execute_code_new_cols_appear_in_dictionary(self, api_client, _use_tmp_media):
        """After AI creates columns, data_dictionary GET must return them all."""
        df = pd.DataFrame({
            'A': [10, 20, 30, 40, 50],
            'B': [1, 2, 3, 4, 5],
            'Target': [0, 1, 0, 1, 0],
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'dict_sync_test.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        # Execute code that adds a new column
        code = 'df["Log1p_A"] = np.log1p(df["A"])\ndf["A_to_B"] = df["A"] / df["B"].replace(0, np.nan)'
        resp = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': file_id,
                'action_type': 'execute_code',
                'payload': {'code': code, 'description': 'Add features'},
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'

        # Data dictionary must now return all 5 columns
        resp = api_client.get(f'/api/declaration/{file_id}/data_dictionary/')
        assert resp.status_code == 200
        names = [d['Feature_Name'] for d in resp.data]
        assert len(names) == 5  # A, B, Target, Log1p_A, A_to_B
        assert 'Log1p_A' in names
        assert 'A_to_B' in names

        # New columns should have feature-specific descriptions from DataDictionary
        dd_map = {d['Feature_Name']: d for d in resp.data}
        log1p_desc = dd_map['Log1p_A'].get('Feature_Description', '')
        assert 'ln(1 + A)' in log1p_desc or 'log' in log1p_desc.lower()

    def test_execute_code_with_nested_function(self, api_client, _use_tmp_media):
        """Nested functions (closures) inside executed code must see `df`."""
        df = pd.DataFrame({
            'A': [10, 20, 30, 40, 50],
            'B': [1, 2, 3, 4, 5],
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'closure_test.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        code = (
            'def safe_ratio(a, b):\n'
            '    return pd.to_numeric(df[a], errors="coerce") / pd.to_numeric(df[b], errors="coerce").replace(0, np.nan)\n'
            'df["A_to_B"] = safe_ratio("A", "B")\n'
        )

        resp = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': file_id,
                'action_type': 'execute_code',
                'payload': {'code': code, 'description': 'Nested closure test'},
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'
        assert 'A_to_B' in resp.data['changes']['columns_added']

    def test_execute_code_exploratory_does_not_mutate(self, api_client, _use_tmp_media):
        """Exploratory Codeline runs must not persist dataset changes."""
        df = pd.DataFrame({
            'A': [10, 20, 30, 40, 50],
            'B': [1, 2, 3, 4, 5],
            'Target': [0, 1, 0, 1, 0],
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'exploratory_code_test.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        resp = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': file_id,
                'action_type': 'execute_code',
                'payload': {
                    'code': 'print(df.shape)\ndf["Ratio"] = df["A"] / df["B"]\nresult = df[["A", "Ratio"]].head(2)',
                    'description': 'Exploratory ratio check',
                    'mode': 'exploratory',
                },
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'
        assert resp.data['mode'] == 'exploratory'
        assert resp.data['changes'] is None
        assert '5' in (resp.data.get('stdout') or '')
        assert resp.data.get('preview') is not None
        assert 'Ratio' in resp.data['preview']['columns']

        # Dataset on disk must remain unchanged
        resp = api_client.get(f'/api/declaration/{file_id}/preview/')
        assert resp.status_code == 200
        assert 'Ratio' not in resp.data['columns']
        assert set(resp.data['columns']) == {'A', 'B', 'Target'}

    def test_execute_code_apply_still_mutates(self, api_client, _use_tmp_media):
        """Explicit apply mode (default) still mutates the dataset."""
        df = pd.DataFrame({
            'A': [10, 20, 30],
            'B': [1, 2, 3],
        })
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'apply_code_test.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        resp = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': file_id,
                'action_type': 'execute_code',
                'payload': {
                    'code': 'df["Sum"] = df["A"] + df["B"]',
                    'description': 'Apply sum column',
                    'mode': 'apply',
                },
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'
        assert resp.data['mode'] == 'apply'
        assert 'Sum' in resp.data['changes']['columns_added']

        resp = api_client.get(f'/api/declaration/{file_id}/preview/')
        assert resp.status_code == 200
        assert 'Sum' in resp.data['columns']

    def test_upload_then_update_metadata(self, api_client, _use_tmp_media):
        """Upload CSV → update metadata description via AI action."""
        df = pd.DataFrame({'Age': [25, 30], 'Target': [0, 1]})
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        buf.name = 'ai_meta_test.csv'

        resp = api_client.post('/api/declaration/', {'file': buf, 'column_separator': 'comma'}, format='multipart')
        assert resp.status_code == 201
        file_id = resp.data['id']

        resp = api_client.post(
            '/api/ai-assistant/execute-action/',
            data=json.dumps({
                'file_id': file_id,
                'action_type': 'update_metadata',
                'payload': {
                    'updates': [{'column': 'Age', 'field': 'Feature_Description', 'value': 'Customer age in years'}],
                },
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'
        assert len(resp.data['applied']) == 1
        assert resp.data['applied'][0]['value'] == 'Customer age in years'


# ---------------------------------------------------------------------------
# Hyperparameter tuning workflow
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.django_db
class TestHyperparamWorkflow:
    """Persisted-results read-back via API, and a bounded end-to-end run that
    exercises the real start -> background thread -> persist -> results path."""

    @pytest.fixture(autouse=True)
    def _reset_progress(self):
        from modeling import views
        views.HYPERPARAM_PROGRESS.clear()
        yield
        views.HYPERPARAM_PROGRESS.clear()

    def test_write_then_read_results(self, api_client, _use_tmp_media, media_root):
        """Write a hyperparam results JSON to disk, then read it back via API."""
        hp_dir = os.path.join(str(media_root), 'hyperparam_results')
        os.makedirs(hp_dir, exist_ok=True)
        file_id = 8123
        hp_data = {
            'status': 'completed',
            'primary_metric': 'roc_auc',
            'best_points': {'roc_auc': {'params': {'max_depth': 4}, 'cv_mean': 0.91,
                                        'cv_std': 0.01, 'test': 0.89, 'train': 0.97}},
            'validation_curves': [{'param': 'max_depth', 'type': 'int',
                                   'values': [2, 4, 6], 'cv_mean': [0.85, 0.91, 0.88],
                                   'cv_std': [0.01, 0.01, 0.02],
                                   'train_mean': [0.9, 0.95, 0.99],
                                   'train_std': [0.01, 0.01, 0.01], 'best_value': 4}],
            'emphasized': {'most_cv_gain': 'max_depth', 'most_overfitting': 'max_depth',
                           'most_shrinkage': 'max_depth'},
            'guidance': [{'param': 'max_depth', 'type': 'zoom_in',
                          'suggested_range': [2, 6], 'rationale': 'peak interior'}],
        }
        with open(os.path.join(hp_dir, f'{file_id}_hyperparam.json'), 'w') as f:
            json.dump(hp_data, f)

        resp = api_client.get(f'/api/modeling/hyperparam/{file_id}/')
        assert resp.status_code == 200
        assert resp.data['hyperparam_completed'] is True
        assert resp.data['best_points']['roc_auc']['cv_mean'] == 0.91
        assert resp.data['validation_curves'][0]['param'] == 'max_depth'
        assert resp.data['emphasized']['most_cv_gain'] == 'max_depth'

    def test_start_poll_results_lifecycle(self, api_client, _use_tmp_media, media_root, monkeypatch):
        """Bounded real run: POST start -> results ready synchronously -> GET results.

        The production endpoint runs the search in a daemon thread. Here we
        replace ``threading`` in the modeling view so the worker executes
        synchronously inside the request. This removes the previous 180s
        poll-with-skip loop and makes the outcome deterministic regardless of
        machine load.
        """
        import pickle
        import types
        from sklearn.datasets import make_classification
        from modeling import views as modeling_views

        class _SyncThread:
            """Run the worker inline so results exist when start() returns."""
            def __init__(self, target=None, *args, **kwargs):
                self._target = target
                self.daemon = False

            def start(self):
                if self._target is not None:
                    self._target()

            def join(self, *args, **kwargs):
                pass

        monkeypatch.setattr(
            modeling_views, 'threading', types.SimpleNamespace(Thread=_SyncThread)
        )

        file_id = 8124
        X, y = make_classification(n_samples=80, n_features=5, n_informative=3,
                                   n_redundant=0, random_state=0)
        cols = [f'Var_{i}' for i in range(5)]
        Xtr = pd.DataFrame(X[:56], columns=cols)
        Xte = pd.DataFrame(X[56:], columns=cols)
        ytr, yte = pd.Series(y[:56]), pd.Series(y[56:])
        td_dir = os.path.join(str(media_root), 'train_data')
        os.makedirs(td_dir, exist_ok=True)
        with open(os.path.join(td_dir, f'{file_id}_train_data.pkl'), 'wb') as f:
            pickle.dump({'X_train': Xtr, 'y_train': ytr, 'X_valid': Xte, 'y_valid': yte,
                         'X_train_raw': Xtr, 'X_valid_raw': Xte}, f)

        start = api_client.post(
            '/api/modeling/hyperparam/start/',
            data=json.dumps({'file_id': file_id, 'n_iter': 4, 'cv_folds': 2,
                             'n_jobs': 1, 'validation_curve_points': 3,
                             'param_space': {'max_depth': {'enabled': True}}}),
            content_type='application/json',
        )
        assert start.status_code == 200
        assert start.data['status'] == 'started'

        # The worker ran synchronously (patched threading), so the status is
        # already terminal and the results JSON has been written.
        st = api_client.get(f'/api/modeling/hyperparam/status/{file_id}/')
        terminal = st.data.get('status')
        assert terminal == 'completed', (
            f'tuning did not complete (status={terminal}, '
            f'message={st.data.get("message")})'
        )

        resp = api_client.get(f'/api/modeling/hyperparam/{file_id}/')
        assert resp.status_code == 200
        assert resp.data['hyperparam_completed'] is True
        assert 'roc_auc' in resp.data['best_points']
        # validate_param_space merges onto defaults, so the default-enabled
        # params are tuned too; max_depth (explicitly enabled) must be present.
        curve_params = {c['param'] for c in resp.data['validation_curves']}
        assert len(curve_params) >= 1
        assert 'max_depth' in curve_params
