"""
Root conftest for the backend test suite.
Provides shared fixtures used across all test categories.
"""
import io
import os
import pytest
import pandas as pd
import numpy as np
from django.conf import settings


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
    return media


@pytest.fixture
def _use_tmp_media(settings, media_root):
    """Automatically redirect MEDIA_ROOT to a temp directory."""
    settings.MEDIA_ROOT = str(media_root)
