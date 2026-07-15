"""Unit tests - AI assistant engine/model-registry/reasoning.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

from tests.unit._shared import (
    _run_chat_workflow,
    _text_response,
)


@pytest.mark.unit
class TestModelRegistry:
    """Test the model_registry module — model configs, list, and defaults."""

    def test_list_models_returns_all(self, _stub_engine_models):
        from ai_assistant.model_registry import list_models, MODEL_REGISTRY
        models = list_models()
        # Cloud entries (static) + engine entries (dynamic stub)
        expected_count = len(MODEL_REGISTRY) + len(_stub_engine_models)
        assert len(models) == expected_count
        keys = [m['key'] for m in models]
        for k in MODEL_REGISTRY:
            assert k in keys
        for k in _stub_engine_models:
            assert k in keys

    def test_list_models_structure(self, _stub_engine_models):
        from ai_assistant.model_registry import list_models
        models = list_models()
        for m in models:
            assert 'key' in m
            assert 'display_name' in m
            assert 'provider' in m

    def test_get_model_config_known(self):
        from ai_assistant.model_registry import get_model_config
        cfg = get_model_config('gpt-5.5')
        assert cfg['provider'] == 'openai'
        assert cfg['model_id'] == 'gpt-5.5'
        assert cfg['supports_tools'] is True
        assert cfg['is_reasoning_model'] is True
        assert 'temperature' not in cfg

    def test_get_model_config_gpt_mini(self):
        from ai_assistant.model_registry import get_model_config
        cfg = get_model_config('gpt-5.4-mini')
        assert cfg['provider'] == 'openai'
        assert cfg['model_id'] == 'gpt-5.4-mini'
        assert cfg['supports_tools'] is True
        assert cfg['is_reasoning_model'] is True
        assert 'temperature' not in cfg

    def test_get_model_config_engine_llama_3b(self, _stub_engine_models):
        from ai_assistant.model_registry import get_model_config
        # Dynamic-discovery key: engine-{id with ':' replaced by '-'}
        cfg = get_model_config('engine-llama3.2-3b')
        assert cfg['provider'] == 'engine'
        assert cfg['model_id'] == 'llama3.2:3b'
        assert cfg['supports_tools'] is True

    def test_get_model_config_unknown_falls_back(self):
        from ai_assistant.model_registry import get_model_config, DEFAULT_MODEL, MODEL_REGISTRY
        cfg = get_model_config('nonexistent-model-xyz')
        assert cfg == MODEL_REGISTRY[DEFAULT_MODEL]

    def test_default_model_exists_in_registry(self):
        from ai_assistant.model_registry import DEFAULT_MODEL, MODEL_REGISTRY
        assert DEFAULT_MODEL in MODEL_REGISTRY

    def test_all_models_have_required_fields(self):
        from ai_assistant.model_registry import MODEL_REGISTRY
        required = {
            'provider', 'model_id', 'display_name', 'max_tokens',
            'supports_tools', 'architecture', 'reasoning', 'thinking',
            'thinking_level',
        }
        for key, cfg in MODEL_REGISTRY.items():
            missing = required - set(cfg.keys())
            assert not missing, f"Model '{key}' missing fields: {missing}"

    def test_all_models_valid_architecture(self):
        from ai_assistant.model_registry import MODEL_REGISTRY
        for key, cfg in MODEL_REGISTRY.items():
            assert cfg['architecture'] in ('dense', 'moe'), f"{key}: bad architecture"

    def test_all_models_valid_thinking_level(self):
        from ai_assistant.model_registry import MODEL_REGISTRY
        valid = {None, 'low', 'med', 'high'}
        for key, cfg in MODEL_REGISTRY.items():
            assert cfg['thinking_level'] in valid, f"{key}: bad thinking_level"

    def test_reasoning_models_skip_temperature(self):
        """Reasoning models (gpt-5.5) should not have temperature in config."""
        from ai_assistant.model_registry import get_model_config
        for key in ('gpt-5.5', 'gpt-5.4-mini'):
            cfg = get_model_config(key)
            assert cfg.get('is_reasoning_model') is True
            assert 'temperature' not in cfg

    def test_engine_models_have_temperature(self, _stub_engine_models):
        """Engine-routed models should expose temperature for inference control."""
        from ai_assistant.model_registry import get_model_config
        for key in ('engine-llama3.2-1b', 'engine-llama3.2-3b'):
            cfg = get_model_config(key)
            assert 'temperature' in cfg
            assert not cfg.get('is_reasoning_model')

    def test_list_models_includes_meta_flags(self):
        """list_models() should expose architecture/reasoning/thinking flags."""
        from ai_assistant.model_registry import list_models
        models = list_models()
        for m in models:
            assert 'architecture' in m
            assert 'reasoning' in m
            assert 'thinking' in m
            assert 'thinking_level' in m

    def test_engine_models_have_ram_gb(self, _stub_engine_models):
        """All engine-routed models should declare their ram_gb requirement."""
        from ai_assistant.model_registry import _registry_snapshot
        for key, cfg in _registry_snapshot().items():
            if cfg['provider'] == 'engine':
                assert 'ram_gb' in cfg, f"Engine model '{key}' missing ram_gb"
                assert isinstance(cfg['ram_gb'], (int, float)), f"{key}: ram_gb must be numeric"
                assert cfg['ram_gb'] > 0, f"{key}: ram_gb must be positive"

    def test_list_models_includes_ram_gb(self, _stub_engine_models):
        """list_models() should expose ram_gb for engine-routed models."""
        from ai_assistant.model_registry import list_models
        models = list_models()
        engine_models = [m for m in models if m['provider'] == 'engine']
        assert len(engine_models) > 0
        for m in engine_models:
            assert 'ram_gb' in m, f"Model '{m['key']}' missing ram_gb in list output"

    def test_openai_models_have_native_tool_calling_mode(self):
        """OpenAI models should declare tool_calling_mode='native'."""
        from ai_assistant.model_registry import MODEL_REGISTRY
        for key, cfg in MODEL_REGISTRY.items():
            if cfg['provider'] == 'openai':
                assert cfg.get('tool_calling_mode') == 'native', f"{key}: expected native tool calling"

    def test_engine_models_have_tool_calling_mode(self, _stub_engine_models):
        """Engine models should declare tool_calling_mode (default 'text')."""
        from ai_assistant.model_registry import list_models
        models = list_models()
        engine_models = [m for m in models if m['provider'] == 'engine']
        for m in engine_models:
            assert 'tool_calling_mode' in m, f"Model '{m['key']}' missing tool_calling_mode"
            assert m['tool_calling_mode'] in ('native', 'text'), f"{m['key']}: invalid tool_calling_mode"

    def test_list_models_surfaces_tool_calling_mode(self):
        """list_models() should include tool_calling_mode for all models."""
        from ai_assistant.model_registry import list_models
        models = list_models()
        for m in models:
            assert 'tool_calling_mode' in m, f"Model '{m['key']}' missing tool_calling_mode in list output"

    def test_fetch_engine_models_uses_configured_bearer_key(self, monkeypatch):
        """Engine discovery must send the deployment-provided bearer key."""
        from ai_assistant import model_registry as mr
        import urllib.request

        captured = {}

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return (
                    b'{"data":[{"id":"llama3.2:3b",'
                    b'"size_bytes":2147483648}]}'
                )

        def _fake_urlopen(req, timeout):
            captured['url'] = req.full_url
            captured['authorization'] = req.get_header('Authorization')
            captured['timeout'] = timeout
            return _FakeResponse()

        monkeypatch.setenv('LLM_ENGINE_BASE_URL', 'http://engine.local:8080/v1/')
        monkeypatch.setenv('LLM_ENGINE_API_KEY', 'sk-dec-test-key')
        monkeypatch.setattr(urllib.request, 'urlopen', _fake_urlopen)
        monkeypatch.setattr(mr, '_ENGINE_MODELS_TIMEOUT', 12.0)

        models = mr._fetch_engine_models()

        assert captured == {
            'url': 'http://engine.local:8080/v1/models',
            'authorization': 'Bearer sk-dec-test-key',
            'timeout': 12.0,
        }
        assert 'engine-llama3.2-3b' in models

# ---------------------------------------------------------------------------
# v2.43.1: Nemotron CoT-leak fix — reasoning-family models must opt into
# chat_template_kwargs={'enable_thinking': True} on the engine call so the
# GGUF template pre-emits ``<think>\n`` and the engine's response normalizer
# can route the prelude to ``reasoning_content`` instead of dumping it into
# ``content``.  Two contracts to pin:
#   1. _build_engine_entry mirrors the engine's reasoning/thinking/level
#      flags from /v1/models into the DeclarAI registry (was hard-coded
#      False before this fix, which made bug #2 invisible).
#   2. call_engine passes chat_template_kwargs.enable_thinking via
#      OpenAI SDK's extra_body iff model_cfg['reasoning'] is True.
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEngineEntryReasoningCapability:
    """_build_engine_entry must mirror the engine's reasoning flags."""

    def test_reasoning_flag_propagated_from_engine_payload(self):
        from ai_assistant.model_registry import _build_engine_entry
        cfg = _build_engine_entry({
            'id': 'nemotron-3-nano:30b',
            'reasoning': True,
            'thinking': True,
            'thinking_level': 'med',
            'tool_calling_mode': 'native',
            'size_bytes': 24 * 1024 ** 3,
        })
        assert cfg['reasoning'] is True
        assert cfg['thinking'] is True
        assert cfg['thinking_level'] == 'med'

    def test_non_reasoning_flag_propagated_from_engine_payload(self):
        from ai_assistant.model_registry import _build_engine_entry
        cfg = _build_engine_entry({
            'id': 'llama3.2:3b',
            'reasoning': False,
            'thinking': False,
            'thinking_level': None,
            'tool_calling_mode': 'text',
            'size_bytes': 2 * 1024 ** 3,
        })
        assert cfg['reasoning'] is False
        assert cfg['thinking'] is False
        assert cfg['thinking_level'] is None

    def test_missing_capability_fields_default_to_non_reasoning(self):
        """Older engine builds that pre-date the capability surface must keep
        working — every reasoning/thinking field has to default off so we
        don't accidentally opt non-reasoning models into enable_thinking."""
        from ai_assistant.model_registry import _build_engine_entry
        cfg = _build_engine_entry({
            'id': 'mystery-model:1b',
            'size_bytes': 1024 ** 3,
        })
        assert cfg['reasoning'] is False
        assert cfg['thinking'] is False
        assert cfg['thinking_level'] is None

@pytest.mark.unit
class TestCallEngineEnableThinking:
    """call_engine must opt reasoning models into enable_thinking on the
    OpenAI-extension extra_body, and must NOT touch the body for non-
    reasoning models (so we don't double-template Llama / Gemma)."""

    @pytest.fixture
    def _fake_openai_client(self, monkeypatch):
        """Patch openai.OpenAI so the test can intercept the create() kwargs
        without actually hitting the engine."""
        captured = {}

        class _FakeCompletions:
            def create(self, **kwargs):
                captured['kwargs'] = kwargs

                class _FakeResp:
                    def model_dump(self_inner):
                        return {'id': 'test', 'choices': []}
                return _FakeResp()

        class _FakeChat:
            def __init__(self):
                self.completions = _FakeCompletions()

        class _FakeOpenAI:
            def __init__(self, **kwargs):
                captured['init_kwargs'] = kwargs
                self.chat = _FakeChat()

        import openai
        monkeypatch.setattr(openai, 'OpenAI', _FakeOpenAI)
        return captured

    def test_reasoning_model_gets_enable_thinking_true(self, _fake_openai_client):
        from ai_assistant.model_registry import call_engine
        cfg = {
            'provider': 'engine',
            'model_id': 'nemotron-3-nano:30b',
            'max_tokens': 4096,
            'temperature': 0.4,
            'supports_tools': True,
            'reasoning': True,
        }
        call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        sent = _fake_openai_client['kwargs']
        assert sent.get('extra_body') == {
            'chat_template_kwargs': {'enable_thinking': True}
        }, "reasoning models must opt into enable_thinking via extra_body"

    def test_call_engine_uses_configured_engine_auth(self, monkeypatch, _fake_openai_client):
        from ai_assistant.model_registry import call_engine
        monkeypatch.setenv('LLM_ENGINE_BASE_URL', 'http://engine.local:8080/v1')
        monkeypatch.setenv('LLM_ENGINE_API_KEY', 'sk-dec-test-key')
        cfg = {
            'provider': 'engine',
            'model_id': 'llama3.2:3b',
            'max_tokens': 4096,
            'temperature': 0.4,
            'supports_tools': True,
            'reasoning': False,
        }

        call_engine([{'role': 'user', 'content': 'hi'}], cfg)

        assert _fake_openai_client['init_kwargs']['api_key'] == 'sk-dec-test-key'
        assert _fake_openai_client['init_kwargs']['base_url'] == 'http://engine.local:8080/v1'

    def test_non_reasoning_model_omits_extra_body(self, _fake_openai_client):
        from ai_assistant.model_registry import call_engine
        cfg = {
            'provider': 'engine',
            'model_id': 'llama3.2:3b',
            'max_tokens': 4096,
            'temperature': 0.4,
            'supports_tools': True,
            'reasoning': False,
        }
        call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        sent = _fake_openai_client['kwargs']
        assert 'extra_body' not in sent, (
            "non-reasoning models must NOT receive chat_template_kwargs — "
            "Llama/Gemma chat templates have no enable_thinking branch, and "
            "an unknown kwarg can change their rendering behavior on engine "
            "builds that pass it through to Jinja unconditionally"
        )

    def test_reasoning_flag_missing_omits_extra_body(self, _fake_openai_client):
        """Defensive: if model_cfg has no ``reasoning`` key at all (e.g. a
        hand-built test config or a legacy registry entry) we must not
        accidentally opt-in."""
        from ai_assistant.model_registry import call_engine
        cfg = {
            'provider': 'engine',
            'model_id': 'engine-only:7b',
            'max_tokens': 4096,
            'temperature': 0.4,
            'supports_tools': True,
        }
        call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        assert 'extra_body' not in _fake_openai_client['kwargs']

    def test_reasoning_model_with_tools_keeps_both(self, _fake_openai_client):
        """Tools and extra_body must co-exist — the failing UI scenario has
        15 tools + Nemotron + enable_thinking all at once."""
        from ai_assistant.model_registry import call_engine
        cfg = {
            'provider': 'engine',
            'model_id': 'nemotron-3-nano:30b',
            'max_tokens': 4096,
            'temperature': 0.4,
            'supports_tools': True,
            'reasoning': True,
        }
        tools = [{'type': 'function', 'function': {
            'name': 'get_data_dictionary',
            'description': 'x',
            'parameters': {'type': 'object', 'properties': {}},
        }}]
        call_engine([{'role': 'user', 'content': 'hi'}], cfg, tools=tools)
        sent = _fake_openai_client['kwargs']
        assert sent.get('tools') == tools
        assert sent.get('tool_choice') == 'auto'
        assert sent.get('extra_body') == {
            'chat_template_kwargs': {'enable_thinking': True}
        }

# ---------------------------------------------------------------------------
# v2.43.2: client-side reasoning_content recovery.
#
# The llm-inference-engine team (PR fix/blocking-normalizer-reasoning-prelude)
# adopted the AGGRESSIVE blocking-path policy: unanchored text on a
# reasoning-family model routes to ``reasoning_content`` regardless of
# finish_reason, to stay byte-for-byte symmetric with the streaming
# normalizer.  Their rationale assumed DeclarAI renders reasoning
# collapsed-by-default and could recover a misrouted answer — but every
# DeclarAI consumer reads only ``message.content``.  Without this guard a
# real answer with no ``<think>`` markers is silently dropped (empty
# content → synthesis pass → _EMPTY_RESPONSE_FALLBACK).
#
# _recover_reasoning_content promotes reasoning_content into content when
# content is blank AND there are no tool_calls.  These tests pin that
# contract and its integration into call_engine.
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestRecoverReasoningContent:
    """_recover_reasoning_content salvages a misrouted answer in-place."""

    def _resp(self, *, content, reasoning=None, tool_calls=None,
              finish_reason='stop'):
        msg = {'role': 'assistant', 'content': content}
        if reasoning is not None:
            msg['reasoning_content'] = reasoning
        if tool_calls is not None:
            msg['tool_calls'] = tool_calls
        return {'choices': [{'finish_reason': finish_reason, 'message': msg}]}

    def test_promotes_reasoning_when_content_empty(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(
            self._resp(content='', reasoning='The real answer is 42.')
        )
        msg = out['choices'][0]['message']
        assert msg['content'] == 'The real answer is 42.'
        # Original preserved for any future collapsed-CoT renderer
        assert msg['reasoning_content'] == 'The real answer is 42.'
        assert out['choices'][0]['declarai_reasoning_recovered'] is True

    def test_promotes_when_content_is_none(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(
            self._resp(content=None, reasoning='Answer here.')
        )
        assert out['choices'][0]['message']['content'] == 'Answer here.'

    def test_promotes_when_content_is_whitespace(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(
            self._resp(content='   \n  ', reasoning='Answer here.')
        )
        assert out['choices'][0]['message']['content'] == 'Answer here.'

    def test_does_not_touch_real_content(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(
            self._resp(content='A genuine reply.', reasoning='internal CoT')
        )
        msg = out['choices'][0]['message']
        assert msg['content'] == 'A genuine reply.'
        assert 'declarai_reasoning_recovered' not in out['choices'][0]

    def test_leaves_tool_call_round_alone(self):
        """A tool-call round legitimately has empty content — promoting
        reasoning_content there would corrupt the multi-turn loop."""
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(self._resp(
            content='',
            reasoning='thinking about which tool to call',
            tool_calls=[{'id': 'c1', 'function': {'name': 'get_cv_results',
                                                  'arguments': '{}'}}],
            finish_reason='tool_calls',
        ))
        msg = out['choices'][0]['message']
        assert msg['content'] == ''  # untouched
        assert 'declarai_reasoning_recovered' not in out['choices'][0]

    def test_noop_when_both_empty(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(self._resp(content='', reasoning=''))
        assert out['choices'][0]['message']['content'] == ''
        assert 'declarai_reasoning_recovered' not in out['choices'][0]

    def test_noop_when_no_reasoning_key(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(self._resp(content=''))
        assert out['choices'][0]['message']['content'] == ''

    def test_promotes_on_stop_skips_on_length(self):
        """v2.44.0 contract refinement (supersedes the v2.43.2 'promote
        regardless of finish_reason' policy): a COMPLETE answer the engine
        misrouted into reasoning_content finishes with 'stop' and IS promoted;
        an UNFINISHED chain-of-thought finishes with 'length' and must NOT be
        promoted — promoting it leaks raw CoT to the user (the reproduced
        screenshot bug).  The length case is tagged
        ``declarai_reasoning_truncated`` and left for the finalization pass."""
        from ai_assistant.model_registry import _recover_reasoning_content
        # stop → promote (complete answer misrouted to reasoning_content)
        out = _recover_reasoning_content(
            self._resp(content='', reasoning='ans', finish_reason='stop')
        )
        assert out['choices'][0]['message']['content'] == 'ans'
        assert out['choices'][0].get('declarai_reasoning_recovered') is True
        # length → skip (truncated CoT); content stays empty + tagged truncated
        out2 = _recover_reasoning_content(
            self._resp(content='', reasoning='Okay, let me think…',
                       finish_reason='length')
        )
        msg2 = out2['choices'][0]['message']
        assert msg2['content'] == ''  # NOT promoted
        assert 'declarai_reasoning_recovered' not in out2['choices'][0]
        assert out2['choices'][0].get('declarai_reasoning_truncated') is True
        # original reasoning preserved for any future collapsed-CoT renderer
        assert msg2['reasoning_content'] == 'Okay, let me think…'

    def test_idempotent(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        r = self._resp(content='', reasoning='ans')
        once = _recover_reasoning_content(r)
        twice = _recover_reasoning_content(once)
        assert twice['choices'][0]['message']['content'] == 'ans'

    def test_defensive_against_malformed_shapes(self):
        """Never raise — a salvage helper must not be able to break chat."""
        from ai_assistant.model_registry import _recover_reasoning_content
        assert _recover_reasoning_content({}) == {}
        assert _recover_reasoning_content({'choices': None}) == {'choices': None}
        assert _recover_reasoning_content({'choices': [None, 'x']}) == {
            'choices': [None, 'x']
        }
        # choice without a dict message
        assert _recover_reasoning_content(
            {'choices': [{'message': 'not-a-dict'}]}
        ) == {'choices': [{'message': 'not-a-dict'}]}

    def test_handles_multiple_choices(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        resp = {'choices': [
            {'finish_reason': 'stop',
             'message': {'content': '', 'reasoning_content': 'first'}},
            {'finish_reason': 'stop',
             'message': {'content': 'real', 'reasoning_content': 'cot'}},
        ]}
        out = _recover_reasoning_content(resp)
        assert out['choices'][0]['message']['content'] == 'first'
        assert out['choices'][1]['message']['content'] == 'real'

@pytest.mark.unit
class TestCallEngineRecoversReasoning:
    """call_engine must run the recovery pass on the engine's response so the
    rest of the app (which reads only message.content) sees the answer."""

    def _patch_openai(self, monkeypatch, fake_response: dict):
        class _FakeCompletions:
            def create(self, **kwargs):
                class _FakeResp:
                    def model_dump(self_inner):
                        return fake_response
                return _FakeResp()

        class _FakeChat:
            def __init__(self):
                self.completions = _FakeCompletions()

        class _FakeOpenAI:
            def __init__(self, **_):
                self.chat = _FakeChat()

        import openai
        monkeypatch.setattr(openai, 'OpenAI', _FakeOpenAI)

    def test_call_engine_promotes_reasoning_content(self, monkeypatch):
        from ai_assistant.model_registry import call_engine
        self._patch_openai(monkeypatch, {
            'id': 't',
            'choices': [{
                'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': '',
                            'reasoning_content': 'Recovered answer.'},
            }],
        })
        cfg = {'provider': 'engine', 'model_id': 'nemotron-3-nano:30b',
               'max_tokens': 4096, 'temperature': 0.4,
               'supports_tools': True, 'reasoning': True}
        out = call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        assert out['choices'][0]['message']['content'] == 'Recovered answer.'

    def test_call_engine_leaves_normal_response_unchanged(self, monkeypatch):
        from ai_assistant.model_registry import call_engine
        self._patch_openai(monkeypatch, {
            'id': 't',
            'choices': [{
                'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': 'Direct reply.'},
            }],
        })
        cfg = {'provider': 'engine', 'model_id': 'llama3.2:3b',
               'max_tokens': 4096, 'temperature': 0.4,
               'supports_tools': True, 'reasoning': False}
        out = call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        assert out['choices'][0]['message']['content'] == 'Direct reply.'

@pytest.mark.unit
class TestIsEngineServerError:
    """_is_engine_server_error gates the graceful-degradation path: True only
    for server-side 5xx (the engine's context-overflow 500), False for 4xx /
    connection / timeout / programming errors so genuine failures propagate."""

    def test_status_code_500_is_server_error(self):
        from ai_assistant.views import _is_engine_server_error

        class E(Exception):
            status_code = 500
        assert _is_engine_server_error(E()) is True

    def test_status_code_503_is_server_error(self):
        from ai_assistant.views import _is_engine_server_error

        class E(Exception):
            status_code = 503
        assert _is_engine_server_error(E()) is True

    def test_status_code_400_is_not_server_error(self):
        from ai_assistant.views import _is_engine_server_error

        class E(Exception):
            status_code = 400
        assert _is_engine_server_error(E()) is False

    def test_status_attr_variant_502(self):
        from ai_assistant.views import _is_engine_server_error

        class E(Exception):
            status = 502
        assert _is_engine_server_error(E()) is True

    def test_internalservererror_classname_without_status(self):
        from ai_assistant.views import _is_engine_server_error

        class InternalServerError(Exception):
            pass
        assert _is_engine_server_error(InternalServerError()) is True

    def test_plain_exception_is_not_server_error(self):
        from ai_assistant.views import _is_engine_server_error
        assert _is_engine_server_error(ValueError('boom')) is False

    def test_connection_error_classname_is_not_server_error(self):
        from ai_assistant.views import _is_engine_server_error

        class APIConnectionError(Exception):
            pass
        assert _is_engine_server_error(APIConnectionError()) is False

# ---------------------------------------------------------------------------
# v2.44.0: engine reply normalization + CoT-leak detection helpers.
#
# Reasoning-family engine models (nemotron-3-nano:30b, …) leak chain-of-thought
# into content and emit code in the wrong format (vendor <function=...> XML or
# bare markdown fences) instead of the <<<ACTION:execute_code>>> block the chat
# panel renders as an Apply button.  These helpers clean that up.
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEngineReplyNormalization:
    """_strip_reasoning_markers / _convert_vendor_tool_xml_to_actions /
    _normalize_engine_reply / _looks_like_cot_leak."""

    def test_strip_paired_think_block(self):
        from ai_assistant.views import _strip_reasoning_markers
        assert _strip_reasoning_markers('<think>plan</think>The answer.') == 'The answer.'
        assert _strip_reasoning_markers('A.<think>plan</think>') == 'A.'

    def test_strip_orphan_close(self):
        from ai_assistant.views import _strip_reasoning_markers
        # reasoning prelude then answer, only the close tag present
        assert _strip_reasoning_markers('reasoning prose</think>The answer.') == 'The answer.'

    def test_strip_orphan_open_truncated(self):
        from ai_assistant.views import _strip_reasoning_markers
        # truncated CoT — open tag, never closed → drop from <think> on
        assert _strip_reasoning_markers('Answer.<think>still thinking') == 'Answer.'
        assert _strip_reasoning_markers('<think>only thinking, no answer') == ''

    def test_strip_noop_without_markers(self):
        from ai_assistant.views import _strip_reasoning_markers
        assert _strip_reasoning_markers('Plain answer.') == 'Plain answer.'

    def test_vendor_exec_xml_becomes_action_block(self):
        from ai_assistant.views import (
            _convert_vendor_tool_xml_to_actions, _extract_actions,
        )
        raw = ("Here is the code:\n<function=execute_code>\n"
               "<parameter=code>\ndf['X'] = df['A'] / df['B']\n"
               "</parameter>\n</function>")
        out = _convert_vendor_tool_xml_to_actions(raw)
        assert '<<<ACTION:execute_code>>>' in out
        actions, clean = _extract_actions(out)
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert actions[0]['payload']['code'] == "df['X'] = df['A'] / df['B']"
        assert 'Here is the code:' in clean

    def test_vendor_exec_xml_without_param_wrapper(self):
        from ai_assistant.views import _convert_vendor_tool_xml_to_actions
        raw = "<function=execute_code>df['Y'] = 2</function>"
        out = _convert_vendor_tool_xml_to_actions(raw)
        assert '<<<ACTION:execute_code>>>' in out
        assert "df['Y'] = 2" in out

    def test_markdown_json_execute_code_becomes_action_block(self):
        from ai_assistant.views import _normalize_engine_reply, _extract_actions
        raw = '''The error suggests the first code-run failed. Here's the corrected action block:

```json
{
  "code": "
Extract years from Var_6 and Var_9 using a simple suffix slice.
df['Var_6_year'] = pd.to_numeric(df['Var_6'].astype(str).str[-4:], errors='coerce').fillna(0)
df['Var_9_year'] = pd.to_numeric(df['Var_9'].astype(str).str[-4:], errors='coerce').fillna(2024)
",
  "description": "Create corrected year extraction helper columns"
}
```'''
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        assert '<<<ACTION:execute_code>>>' in out
        actions, clean = _extract_actions(out)
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert "df['Var_6_year']" in actions[0]['payload']['code']
        assert actions[0]['payload']['description'] == (
            'Create corrected year extraction helper columns'
        )
        assert 'The error suggests' in clean

    def test_single_backtick_markdown_json_execute_code_becomes_action_block(self):
        from ai_assistant.views import _normalize_engine_reply, _extract_actions
        raw = '''Here's the corrected action block:

`json
{
  "code": "
df['Debt_to_Income_Ratio'] = df['Var_19'] / df['Var_24'].replace(0, 1)
",
  "description": "Create DTI"
}
`'''
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        actions, clean = _extract_actions(out)
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert "df['Debt_to_Income_Ratio']" in actions[0]['payload']['code']
        assert 'corrected action block' in clean

    def test_markdown_json_conversion_requires_action_hint(self):
        from ai_assistant.views import _convert_markdown_execute_code_json_to_actions
        raw = '''Example payload:

```json
{"code": "df['X'] = 1", "description": "Example only"}
```'''
        assert _convert_markdown_execute_code_json_to_actions(raw) == raw

    def test_action_heading_markdown_json_blocks_become_multiple_actions(self):
        from ai_assistant.views import _normalize_engine_reply, _extract_actions
        raw = '''Action: Optimized Purification
```json
{
  "purifier_options": [1, 2, 3, 4, 29, 8, 18, 33],
  "split": {"strategy": "random", "percent": 25},
  "description": "Run optimized purification."
}
```

Action: Exclude Critical Features from Missingness Drop
```json
{
  "updates": [
    {"key": "feature_usage", "column": "Var_24", "value": "drop", "reason": "protect signal"}
  ],
  "description": "Mark critical feature for exclusion from SFS."
}
```

Action: Add Temporal Validation for Dates
```json
{
  "code": "df['Valid_Date_Flag'] = df['Var_6'].notna().astype(int)",
  "description": "Create valid-date flag."
}
```

I will now execute these actions in sequence.'''
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        actions, clean = _extract_actions(out)
        assert [a['type'] for a in actions] == [
            'start_data_purifier',
            'update_config',
            'execute_code',
        ]
        assert actions[0]['payload']['split']['percent'] == 25
        assert actions[1]['payload']['updates'][0]['key'] == 'feature_usage'
        assert "df['Valid_Date_Flag']" in actions[2]['payload']['code']
        assert 'I will now execute these actions' in clean

    def test_python_code_fence_becomes_execute_code_action(self):
        from ai_assistant.views import _normalize_engine_reply, _extract_actions
        raw = '''The error occurs because Var_3 contains non-numeric values.

Here's the corrected code block:

---
`python
**Parse timestamps (if not already datetime)**
df['Application_Datetime'] = pd.to_datetime(df['Application_Datetime'],
    errors='coerce')
df['Var_6'] = pd.to_datetime(df['Var_6'], errors='coerce')

**Convert Var_3 to numeric (0/1) and handle non-numeric values**
df['Var_3_numeric'] = pd.to_numeric(df['Var_3'], errors='coerce').fillna(0).astype(int)

**Legal Action Risk (recency): Use years since last legal action (0 if no action)**
df['legal_action_risk'] = df['Var_3_numeric'] * (
    (df['Application_Datetime'] - df['Var_6']).dt.days / 365
).replace([np.inf, -np.inf], 0).fillna(0)
`'''
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        actions, clean = _extract_actions(out)
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        code = actions[0]['payload']['code']
        assert "df['Var_3_numeric']" in code
        assert "df['legal_action_risk']" in code
        assert '# Parse timestamps' in code
        assert '**Parse timestamps' not in code
        assert 'corrected code block' in clean

    def test_standalone_python_mutation_fence_becomes_execute_code_action(self):
        from ai_assistant.views import _normalize_engine_reply, _extract_actions
        raw = '''`python
Create Debt_to_Income ratio
df['Debt_to_Income'] = df['Var_19'] / df['Var_24'].replace(0, 1)

Create Credit_Utilization ratio
df['Credit_Utilization'] = df['Var_18'] / df['Var_17'].replace(0, 1)
`'''
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        actions, clean = _extract_actions(out)
        assert clean == ''
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        code = actions[0]['payload']['code']
        assert "df['Debt_to_Income']" in code
        assert '# Create Debt_to_Income ratio' in code

    def test_explanatory_python_fence_without_action_hint_stays_markdown(self):
        from ai_assistant.views import _normalize_engine_reply, _extract_actions
        raw = '''Example only:

`python
df['Debt_to_Income'] = df['Var_19'] / df['Var_24'].replace(0, 1)
`

Do not run this yet.'''
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        actions, clean = _extract_actions(out)
        assert actions == []
        assert "df['Debt_to_Income']" in clean

    def test_vendor_conversion_noop_without_function_tag(self):
        from ai_assistant.views import _convert_vendor_tool_xml_to_actions
        assert _convert_vendor_tool_xml_to_actions('no tags here') == 'no tags here'

    def test_normalize_is_noop_for_cloud(self):
        from ai_assistant.views import _normalize_engine_reply
        raw = '<think>cot</think>answer'
        # provider='openai' → untouched even though markers are present
        assert _normalize_engine_reply(raw, {'provider': 'openai'}) == raw

    def test_normalize_engine_strips_and_converts(self):
        from ai_assistant.views import _normalize_engine_reply, _extract_actions
        raw = ("<think>deciding</think>Create a ratio.\n"
               "<function=execute_code><parameter=code>df['R']=df['A']/df['B']"
               "</parameter></function>")
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        assert '<think>' not in out
        actions, clean = _extract_actions(out)
        assert actions and actions[0]['payload']['code'] == "df['R']=df['A']/df['B']"
        assert 'Create a ratio.' in clean

    def test_normalize_drops_leaked_non_exec_function_xml(self):
        from ai_assistant.views import _normalize_engine_reply
        raw = 'Summary text.\n<function=get_feature_stats>\n</function>'
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        assert '<function' not in out
        assert out == 'Summary text.'

    def test_cot_leak_detected_on_thinking_openers(self):
        from ai_assistant.views import _looks_like_cot_leak
        assert _looks_like_cot_leak("Okay, let's tackle this. The user wants…")
        assert _looks_like_cot_leak('We need to derive several features first.')
        assert _looks_like_cot_leak('The user wants new columns.')
        assert _looks_like_cot_leak('Let me think about which ratios help.')

    def test_cot_leak_not_flagged_for_clean_answer(self):
        from ai_assistant.views import _looks_like_cot_leak
        assert not _looks_like_cot_leak('**Proposed features**\n- Debt_to_Income')
        assert not _looks_like_cot_leak('Here are 5 derived features you can add.')
        assert not _looks_like_cot_leak('')

    def test_cot_leak_ignored_when_action_block_present(self):
        from ai_assistant.views import _looks_like_cot_leak
        # Even with a CoT opener, an action block makes the reply usable.
        assert not _looks_like_cot_leak(
            "Okay, here.\n<<<ACTION:execute_code>>>\n{}\n<<<END_ACTION>>>")

    # ── v2.44.1: code-only / thin-rationale detection ──────────────────
    def test_prose_without_actions_strips_block(self):
        from ai_assistant.views import _prose_without_actions
        txt = ('Intro line.\n<<<ACTION:execute_code>>>\n{"code": "df[\'X\']=1"}\n'
               '<<<END_ACTION>>>\nTrailing note.')
        out = _prose_without_actions(txt)
        assert '<<<ACTION' not in out
        assert 'Intro line.' in out and 'Trailing note.' in out

    def test_code_only_true_for_bare_exec_action(self):
        from ai_assistant.views import _is_code_only_reply
        # An execute_code block with no surrounding explanation.
        assert _is_code_only_reply(
            '<<<ACTION:execute_code>>>\n'
            '{"code": "df[\'DTI\']=df[\'A\']/df[\'B\']", "description": "DTI"}\n'
            '<<<END_ACTION>>>')
        # A one-line intro is still too thin to count as a rationale.
        assert _is_code_only_reply(
            'Here is the code:\n<<<ACTION:execute_code>>>\n'
            '{"code": "df[\'X\']=1"}\n<<<END_ACTION>>>')

    def test_code_only_false_when_well_explained(self):
        from ai_assistant.views import _is_code_only_reply
        rich = ('The debt-to-income ratio divides committed debt by income to '
                'capture repayment burden, a classic credit-risk signal that '
                'helps the boosting model rank applicants by default risk more '
                'reliably across the whole population.')
        assert not _is_code_only_reply(
            rich + '\n<<<ACTION:execute_code>>>\n{"code": "df[\'X\']=1"}\n<<<END_ACTION>>>')

    def test_code_only_false_without_exec_action(self):
        from ai_assistant.views import _is_code_only_reply
        # No execute_code at all → never a code-only reply.
        assert not _is_code_only_reply('Just a plain text answer with no code.')
        # A config action (not execute_code) is a one-liner by design.
        assert not _is_code_only_reply(
            'Dropping Var_3.\n<<<ACTION:update_config>>>\n'
            '{"updates": []}\n<<<END_ACTION>>>')

    # ── v2.45.1: partial-success detection for non-reasoning engine models ──
    def test_partial_success_detects_trailing_table_header(self):
        from ai_assistant.views import _looks_like_incomplete_success_reply
        msg = (
            'Below is a table of proposed features.\n\n'
            '| Feature | Formula | Meaning'
        )
        assert _looks_like_incomplete_success_reply(
            msg,
            'create these suggested features in our dataset',
        )

    def test_partial_success_detects_promised_missing_action(self):
        from ai_assistant.views import _looks_like_incomplete_success_reply
        msg = (
            'Below is a table of proposed features. I will implement these '
            'using execute_code next.'
        )
        assert _looks_like_incomplete_success_reply(
            msg,
            'derive and create new features in the dataset',
        )

    def test_partial_success_ignores_complete_table_without_mutation(self):
        from ai_assistant.views import _looks_like_incomplete_success_reply
        msg = (
            '| Feature | Formula | Meaning |\n'
            '| --- | --- | --- |\n'
            '| DTI | debt / income | repayment burden |'
        )
        assert not _looks_like_incomplete_success_reply(
            msg,
            'which features could help the model?',
        )

@pytest.mark.unit
class TestOpenAICompatibilityToolCallNormalizer:
    """Model-agnostic compatibility layer for local models that emit tool calls
    as text instead of OpenAI ``message.tool_calls``."""

    def test_args_marker_becomes_openai_tool_call(self):
        import json as _json
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        from ai_assistant.views import _normalize_llm_response_schema

        out = _normalize_llm_response_schema(
            _text_response('get_split_validation[ARGS]()'),
            {'provider': 'engine'},
            PIPELINE_TOOLS,
        )

        choice = out['choices'][0]
        msg = choice['message']
        assert choice['finish_reason'] == 'tool_calls'
        assert msg['content'] is None
        assert msg['tool_calls'][0]['function']['name'] == 'get_split_validation'
        assert _json.loads(msg['tool_calls'][0]['function']['arguments']) == {}

    def test_named_args_are_schema_validated_and_coerced(self):
        import json as _json
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        from ai_assistant.views import _normalize_llm_response_schema

        out = _normalize_llm_response_schema(
            _text_response('get_selected_features[ARGS](top_n=5)'),
            {'provider': 'engine'},
            PIPELINE_TOOLS,
        )

        tc = out['choices'][0]['message']['tool_calls'][0]
        assert tc['function']['name'] == 'get_selected_features'
        assert _json.loads(tc['function']['arguments']) == {'top_n': 5}

    def test_vendor_xml_tool_marker_becomes_openai_tool_call(self):
        import json as _json
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        from ai_assistant.views import _normalize_llm_response_schema

        out = _normalize_llm_response_schema(
            _text_response(
                '<tool_call><function=get_dq_summary>'
                '<parameter=feature>Income</parameter>'
                '</function></tool_call>'
            ),
            {'provider': 'engine'},
            PIPELINE_TOOLS,
        )

        tc = out['choices'][0]['message']['tool_calls'][0]
        assert tc['function']['name'] == 'get_dq_summary'
        assert _json.loads(tc['function']['arguments']) == {'feature': 'Income'}

    def test_missing_required_args_are_not_guessed(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        from ai_assistant.views import _normalize_llm_response_schema

        out = _normalize_llm_response_schema(
            _text_response('get_feature_stats[ARGS]()'),
            {'provider': 'engine'},
            PIPELINE_TOOLS,
        )

        choice = out['choices'][0]
        msg = choice['message']
        assert choice['finish_reason'] == 'stop'
        assert msg.get('tool_calls') is None
        assert msg['content'] == 'get_feature_stats[ARGS]()'

    def test_chat_workflow_executes_text_tool_marker_before_answering(self, monkeypatch):
        def call_llm(idx, messages, tools):
            if idx == 0:
                return _text_response('get_split_validation[ARGS]()')
            assert any(
                m.get('role') == 'tool'
                and m.get('content') == 'TOOL_RESULT[get_split_validation]'
                for m in messages
            )
            return _text_response('The split validation looks balanced.')

        out = _run_chat_workflow(
            monkeypatch,
            provider='engine',
            user_message='check the train test split validation',
            call_llm=call_llm,
        )

        assert len(out['llm_calls']) == 2
        assert out['result']['message'] == 'The split validation looks balanced.'

# ---------------------------------------------------------------------------
# v2.43.0: gen_ai.vendor + Ollama-tag normalization for prometa-platform's
# pricing-registry matcher.
#
# Background: prometa-platform's models.ts uses ``startsWith(registryKey)``
# against the raw ``gen_ai.request.model`` attribute.  Our Ollama-style
# tags (``gemma4:26b``, ``nemotron-3-nano:30b``) never match because:
#   1. The ``:variant`` suffix isn't stripped.
#   2. The family/parameter-size split isn't surfaced.
#   3. There's no vendor hint to route the lookup into the right catalog
#      (cloud OpenAI vs self-hosted Ollama).
# v2.43.0 ships ``parse_ollama_tag()`` and stamps three new span
# attributes (``gen_ai.vendor``, ``gen_ai.model.family``,
# ``gen_ai.model.tag``, ``gen_ai.model.parameter_size``) so the matcher
# has the signals it needs.  These tests pin the contract on both sides
# of the boundary — the parser AND the call site.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseOllamaTag:
    """``parse_ollama_tag`` must split an Ollama model id into
    ``{family, tag, parameter_size}`` without raising on any input."""

    def test_canonical_family_colon_size_tag(self):
        """The common case: ``family:Nb`` where N is the parameter count."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('gemma4:26b')
        assert result == {
            'family': 'gemma4',
            'tag': '26b',
            'parameter_size': '26b',
        }

    def test_hyphenated_family(self):
        """Multi-segment families like nemotron-3-nano keep their hyphens."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('nemotron-3-nano:30b')
        assert result == {
            'family': 'nemotron-3-nano',
            'tag': '30b',
            'parameter_size': '30b',
        }

    def test_dotted_family(self):
        """Families with version dots (llama3.2, qwen3.6) round-trip."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('llama3.2:3b')
        assert result == {
            'family': 'llama3.2',
            'tag': '3b',
            'parameter_size': '3b',
        }

    def test_decimal_parameter_size(self):
        """Sub-billion sizes like 1.5b extract cleanly."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('ministral-3:1.5b')
        assert result == {
            'family': 'ministral-3',
            'tag': '1.5b',
            'parameter_size': '1.5b',
        }

    def test_gemma_embedded_variant(self):
        """Gemma's ``eNb`` (embedded) tags surface a numeric param_size
        even though the tag itself is ``e2b`` / ``e4b``.  The full tag
        is preserved in ``tag`` so registry consumers can match either
        the raw variant or the normalized parameter size."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('gemma4:e2b')
        assert result['family'] == 'gemma4'
        assert result['tag'] == 'e2b'
        assert result['parameter_size'] == '2b'

    def test_non_numeric_tag_yields_none_parameter_size(self):
        """``cloud`` / ``latest`` / ``q4_0`` aren't parameter sizes —
        ``parameter_size`` must be None so the registry doesn't index
        a meaningless string."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('minimax-m2.7:cloud')
        assert result == {
            'family': 'minimax-m2.7',
            'tag': 'cloud',
            'parameter_size': None,
        }

    def test_quantization_suffix_falls_through(self):
        """Quant-only tags like ``q4_0`` don't carry a parameter count;
        the parser refuses to invent one."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('llama3.2:q4_0')
        assert result['family'] == 'llama3.2'
        assert result['tag'] == 'q4_0'
        assert result['parameter_size'] is None

    def test_size_with_quantization_suffix(self):
        """When the tag is ``Nb-quant`` (e.g. ``26b-q4``) the leading
        size segment wins — we want the cost matcher to find the size
        even when an operator pulls a quantized variant."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('gemma4:26b-q4_0')
        assert result['family'] == 'gemma4'
        assert result['tag'] == '26b-q4_0'
        assert result['parameter_size'] == '26b'

    def test_no_colon_returns_none_tag(self):
        """If the model id has no ``:`` we still return family but
        leave tag + parameter_size as None — the caller will then
        stamp only the family attribute (graceful degradation)."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('llama3.2')
        assert result == {
            'family': 'llama3.2',
            'tag': None,
            'parameter_size': None,
        }

    def test_empty_string_returns_safe_shape(self):
        """Empty input must return the canonical shape with empty/None
        fields — never raise — so the call site can stamp nothing
        instead of crashing the LLM call."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('')
        assert result == {
            'family': '',
            'tag': None,
            'parameter_size': None,
        }

    def test_non_string_input_returns_safe_shape(self):
        """Defensive: a None / int / dict input must not raise.  We
        return the canonical empty shape so callers stay no-op."""
        from ai_assistant.model_registry import parse_ollama_tag
        assert parse_ollama_tag(None) == {
            'family': '', 'tag': None, 'parameter_size': None,
        }
        assert parse_ollama_tag(42) == {
            'family': '', 'tag': None, 'parameter_size': None,
        }

    def test_uppercase_parameter_size_normalized_to_lowercase(self):
        """The parameter_size is normalized to lowercase so the
        registry can match without per-call casing."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('gemma4:26B')
        assert result['parameter_size'] == '26b'

    # ── family-side fallback (MLX / HF converted ids) ──────────────────

    def test_mlx_converted_id_extracts_size_from_family(self):
        """Engine occasionally surfaces MLX-converted ids like
        ``Llama-3.2-1B-Instruct-4bit:mlx`` where the parameter size is
        encoded in the family string instead of the tag.  The
        family-side fallback must recover the size so prometa's
        registry can match on it."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('Llama-3.2-1B-Instruct-4bit:mlx')
        assert result['family'] == 'Llama-3.2-1B-Instruct-4bit'
        assert result['tag'] == 'mlx'
        assert result['parameter_size'] == '1b'

    def test_family_fallback_does_not_overrule_explicit_tag_size(self):
        """When the tag carries an explicit size (the common case) the
        family-side fallback MUST NOT fire and overwrite it with a
        spurious match from the family name.  Pinning the precedence
        order so future refactors can't silently swap it."""
        from ai_assistant.model_registry import parse_ollama_tag
        # Contrived: family contains "5B", tag contains "3b".  The
        # parser must report 3b (from the tag), not 5b (from family).
        result = parse_ollama_tag('llama-5B-something:3b')
        assert result['tag'] == '3b'
        assert result['parameter_size'] == '3b'

    def test_family_fallback_yields_none_when_neither_side_has_size(self):
        """Both family and tag are size-free → parameter_size must
        remain None.  ``minimax-m2.7:cloud`` is the live example —
        ``m2.7`` looks numeric but lacks the required ``[bm]`` suffix
        so the regex correctly refuses to match."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('minimax-m2.7:cloud')
        assert result['parameter_size'] is None

    def test_family_fallback_works_without_tag(self):
        """When the model id has no colon at all (no tag), the
        fallback still runs against the family string."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('Llama-3.2-1B-Instruct')
        assert result['family'] == 'Llama-3.2-1B-Instruct'
        assert result['tag'] is None
        assert result['parameter_size'] == '1b'
