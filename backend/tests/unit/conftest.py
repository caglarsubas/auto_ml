"""Shared fixtures for the unit test suite.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


@pytest.fixture(autouse=True)
def _isolate_handler_unit_tests_from_authentication(request, monkeypatch):
    """Scientific handler unit tests use no session; boundary tests use the real policy.

    This is test-only isolation, never a runtime configuration or bypass.
    Authentication/CSRF regressions explicitly opt into the production defaults.
    """
    if request.node.get_closest_marker('auth_boundary'):
        return
    from rest_framework.permissions import AllowAny
    from rest_framework.views import APIView
    from access_control.storage import ManagedRequestReferences
    monkeypatch.setattr(APIView, 'permission_classes', [AllowAny, ManagedRequestReferences])


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


@pytest.fixture
def sdk_stub(monkeypatch):
    """An import boundary for wrapper unit tests, never an SDK implementation.

    Tests supply the exact callable they are checking. Installed-SDK version
    and instrumentation tests remain separate and use the optional real SDK.
    """
    import sys
    from types import ModuleType
    module = ModuleType('prometa')
    module.Prometa = object
    for name in list(sys.modules):
        if name.startswith('prometa.'):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, 'prometa', module)
    return module
