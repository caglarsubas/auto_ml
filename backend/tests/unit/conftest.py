"""Shared fixtures for the unit test suite.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


# ---------------------------------------------------------------------------
# Model registry tests
# ---------------------------------------------------------------------------
@pytest.fixture
def _stub_engine_models(monkeypatch):
    """Inject a deterministic engine /v1/models payload so tests don't need a
    live engine.  Mirrors the previous hard-coded ``llama3.2:3b`` /
    ``llama3.2:1b`` pair so historical assertions still mean something —
    just routed through the dynamic-discovery code path."""
    from ai_assistant import model_registry as mr
    fake = {
        'engine-llama3.2-3b': {
            'provider': 'engine',
            'model_id': 'llama3.2:3b',
            'display_name': 'llama3.2:3b (Inference Engine)',
            'temperature': 0.4,
            'max_tokens': 4096,
            'supports_tools': True,
            'architecture': 'dense',
            'reasoning': False,
            'thinking': False,
            'thinking_level': None,
            'ram_gb': 3,
            'tool_calling_mode': 'text',
        },
        'engine-llama3.2-1b': {
            'provider': 'engine',
            'model_id': 'llama3.2:1b',
            'display_name': 'llama3.2:1b (Inference Engine)',
            'temperature': 0.4,
            'max_tokens': 4096,
            'supports_tools': True,
            'architecture': 'dense',
            'reasoning': False,
            'thinking': False,
            'thinking_level': None,
            'ram_gb': 2,
            'tool_calling_mode': 'text',
        },
    }
    monkeypatch.setattr(mr, '_fetch_engine_models', lambda: fake)
    mr.invalidate_engine_cache()
    yield fake
    mr.invalidate_engine_cache()
