"""Core execution and error semantics remain available without the optional SDK."""
import builtins

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def missing_sdk(monkeypatch):
    real_import = builtins.__import__
    def without_sdk(name, *args, **kwargs):
        if name == 'prometa' or name.startswith('prometa.'):
            raise ModuleNotFoundError("Optional SDK is absent", name=name)
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', without_sdk)
    from ai_assistant import prometa_config as pc
    monkeypatch.setattr(pc, '_initialized', False)
    monkeypatch.setattr(pc, '_prometa', None)
    return pc


def test_configured_endpoint_does_not_make_sdk_mandatory(missing_sdk, monkeypatch):
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    monkeypatch.delenv('PROMETA_DISABLE', raising=False)
    monkeypatch.setenv('PROMETA_ENDPOINT_STAGING', 'http://unused.invalid/otlp')
    monkeypatch.setenv('PROMETA_API_KEY_STAGING', 'unused-test-key')
    assert missing_sdk.get_prometa() is None
    assert missing_sdk.get_prometa() is None


def test_lazy_workflow_preserves_return_values_and_errors_without_sdk(missing_sdk):
    @missing_sdk.workflow(name='test-core-operation')
    def operation(value):
        if value < 0:
            raise ValueError('invalid input')
        return value * 2
    assert operation(3) == 6
    with pytest.raises(ValueError, match='invalid input'):
        operation(-1)


@pytest.mark.parametrize('helper,args,kwargs', [
    ('schema_validate', ('test@v1',), {}),
    ('plan_generate', ('test-plan',), {}),
    ('cache_lookup', ('tool_call',), {'key': 'version-1'}),
    ('model_route', ('native',), {'candidates_considered': ['native'], 'routing_reason': 'declared'}),
    ('retrieval_query', ('keyword',), {'query_text': 'test', 'top_k': 2}),
    ('prompt_render', (), {'template_version': 'test@v1'}),
])
def test_optional_context_does_not_swallow_application_errors(missing_sdk, helper, args, kwargs):
    with pytest.raises(RuntimeError, match='application failure'):
        with getattr(missing_sdk, helper)(*args, **kwargs):
            raise RuntimeError('application failure')


@pytest.mark.parametrize('helper,args,kwargs,error', [
    ('cache_lookup', ('invalid',), {'key': 'test'}, 'kind must be one of'),
    ('retrieval_query', ('lexical',), {'query_text': 'test', 'top_k': 2}, 'system must be one of'),
])
def test_invalid_metadata_is_rejected_without_sdk(missing_sdk, helper, args, kwargs, error):
    with pytest.raises(ValueError, match=error):
        with getattr(missing_sdk, helper)(*args, **kwargs):
            pytest.fail('Invalid declarations must fail before the operation body')
