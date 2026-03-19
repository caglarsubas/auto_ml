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
