"""
Root conftest for the backend test suite.
Provides shared fixtures used across all test categories.
"""
import io
import os
import random

# Disable Prometa OTLP export for the entire test session so test runs don't
# emit sessions like `declarai-file-99999` into the platform's Session Explorer.
# Set before any test module imports the AI assistant (decorators init lazily,
# but the env check runs at first decorated-call, which can be during a test
# fixture rather than the test body — so PYTEST_CURRENT_TEST alone isn't enough).
os.environ.setdefault('PROMETA_DISABLE', '1')

import pytest
import pandas as pd
import numpy as np
from django.conf import settings

# Fixed seed so that fixtures built on numpy/random produce the same data every
# run. This removes a class of "passes locally, fails in CI" flakiness for tests
# that assert on generated values. Individual tests that need fresh entropy can
# reseed inside their own body.
RANDOM_SEED = 42


@pytest.fixture(autouse=True)
def _seed_randomness():
    """Seed numpy and stdlib RNGs before every test for deterministic data."""
    np.random.seed(RANDOM_SEED)
    random.seed(RANDOM_SEED)
    yield


@pytest.fixture
def sample_csv_bytes():
    """Generate a simple CSV file as bytes for upload testing."""
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
    return buf


@pytest.fixture
def sample_dataframe():
    """Provide an in-memory DataFrame for unit-level testing."""
    return pd.DataFrame({
        'id_col': range(1, 51),
        'float_col': np.random.uniform(0, 100, 50).round(4),
        'int_col': np.random.randint(1, 20, 50),
        'cat_col': np.random.choice(['cat', 'dog', 'bird'], 50),
        'target': np.random.choice([0, 1], 50),
        'date_col': pd.date_range('2024-01-01', periods=50, freq='D').strftime('%d/%m/%Y %I:%M:%S %p'),
    })


@pytest.fixture
def media_root(tmp_path):
    """Provide a temporary MEDIA_ROOT for test isolation."""
    media = tmp_path / 'media'
    media.mkdir()
    (media / 'data_files').mkdir()
    (media / 'configs').mkdir()
    (media / 'data_quality').mkdir()
    return media


@pytest.fixture
def _use_tmp_media(settings, media_root):
    """Automatically redirect MEDIA_ROOT to a temp directory."""
    settings.MEDIA_ROOT = str(media_root)


@pytest.fixture
def authenticated_api_client(db, django_user_model):
    """Authenticated API actor for handler tests; boundary tests use real sessions."""
    from rest_framework.test import APIClient
    user = django_user_model.objects.create_user(username='handler-test-actor', password=None)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def mcp_identity(django_user_model, monkeypatch):
    """Real installation actor/grant for MCP handler tests; no runtime bypass."""
    from access_control.models import MCPDatasetGrant
    from declaration.models import Declaration
    actor = django_user_model.objects.create_user(username='mcp-handler-test', password=None)
    dataset = Declaration.objects.create(pk=42, name='mcp-fixture', original_name='mcp.csv', file='data_files/mcp.csv')
    grant = MCPDatasetGrant.objects.create(actor=actor, dataset=dataset, role='prepare')
    monkeypatch.setenv('DECLARAI_MCP_ACTOR_USER_ID', str(actor.pk))
    monkeypatch.delenv('DECLARAI_MCP_SCOPES', raising=False)
    return actor, dataset, grant
