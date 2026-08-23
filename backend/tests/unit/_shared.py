"""Shared helpers for the unit test suite.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
from pathlib import Path

import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


def backend_root() -> Path:
    """Return the backend package root (the dir holding requirements.txt).

    Walks upward from this file so tests keep working regardless of how deeply
    they are nested under ``tests/`` (they used to live directly in
    ``tests/test_unit.py`` and hard-coded ``parent.parent``).
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "requirements.txt").exists() and (parent / "manage.py").exists():
            return parent
    return Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    """Return the repository root (the dir holding the ``frontend/`` tree)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "frontend").is_dir():
            return parent
    return Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# v2.43.3 — engine context-window overflow on multi-turn tool calling
# ---------------------------------------------------------------------------
# Symptom (production): every feature-engineering question to an engine
# model (nemotron-3-nano:30b, ~8K-token window) returned "AI Assistant
# error: Internal Server Error".  Root cause: the follow-up tool call's
# prompt — lite system prompt + slim context + the auto-injected ~2K-token
# skill playbook + the 15 tool schemas (~2.3K tokens) + the tool result —
# crossed the model's context window, and the engine returned a bare HTTP
# 500 (not a graceful context_length_exceeded 400).  Reproduced against the
# live engine at the exact production prompt sizes.
#
# Two-part fix:
#   1. Provider-aware skill injection — engine models no longer pre-load the
#      full playbook (they pull it on demand via invoke_skill); cloud models
#      keep it.  TestSkillAutoInjectionProviderAware pins this.
#   2. Graceful degradation — if the engine still 5xx's mid tool-loop (e.g.
#      the model calls both invoke_skill AND get_data_dictionary), drop the
#      tool schemas and fall through to the synthesis pass instead of
#      surfacing a raw 500.  TestChatWorkflowEngineOverflowDegrades pins it.
# ---------------------------------------------------------------------------


def _engine_or_cloud_cfg(provider, reasoning=False):
    """Minimal model_cfg matching what get_model_config returns."""
    return {
        'provider': provider,
        'model_id': 'nemotron-3-nano:30b' if provider == 'engine' else 'gpt-5.5',
        'supports_tools': True,
        'max_tokens': 4096,
        'temperature': 0.4,
        'reasoning': reasoning,
    }

def _tool_call_response(name='get_data_dictionary', call_id='c1'):
    """A response that asks for one tool call (content empty — the normal
    shape for a tool-calling round)."""
    return {
        'choices': [{
            'finish_reason': 'tool_calls',
            'message': {
                'role': 'assistant',
                'content': None,
                'tool_calls': [{
                    'id': call_id, 'type': 'function',
                    'function': {'name': name, 'arguments': '{}'},
                }],
            },
        }],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
    }

def _text_response(text):
    """A plain final answer (no tool calls, no action blocks)."""
    return {
        'choices': [{'finish_reason': 'stop',
                     'message': {'role': 'assistant', 'content': text}}],
        'usage': {'prompt_tokens': 8, 'completion_tokens': 4, 'total_tokens': 12},
    }

def _run_chat_workflow(monkeypatch, *, provider, call_llm,
                       user_message='please derive new features from the existing ones',
                       file_id=1, reasoning=False, history=None,
                       span_id=None, trace_id=None,
                       intent_labels_for_turn=None,
                       context=None, source=None):
    """Execute the real _chat_workflow body with its external collaborators
    mocked.  ``call_llm(idx, messages, tools)`` scripts each LLM round.

    Returns {result, llm_calls, skill_calls} so tests can assert on the
    response AND on what was sent to the model each round."""
    from ai_assistant import views

    monkeypatch.setattr(views, 'get_model_config',
                        lambda k: _engine_or_cloud_cfg(provider, reasoning))
    monkeypatch.setattr(views, 'cache_list_artifacts',
                        lambda fid: ['data_dictionary'])
    monkeypatch.setattr(views, '_build_slim_context',
                        lambda fid, sec: 'Pipeline: boosting\nTarget: good/bad flag')
    monkeypatch.setattr(views, 'execute_tool_call',
                        lambda fid, name, args: f'TOOL_RESULT[{name}]')
    # Observability helpers → silent no-ops (they are no-ops under pytest
    # anyway; pinning them keeps the test independent of SDK state).
    monkeypatch.setattr(views, 'set_span_attr', lambda *a, **kw: None)
    monkeypatch.setattr(views, 'set_session_id', lambda *a, **kw: None)
    monkeypatch.setattr(views, 'set_customer_id', lambda *a, **kw: None)
    monkeypatch.setattr(views, 'current_span_id', lambda: span_id)
    monkeypatch.setattr(views, 'current_trace_id', lambda: trace_id)

    def fake_resolve_intent(user_message, **_kwargs):
        from ai_assistant.intent_classifier import INTENT_LABEL_NAMES
        labels = intent_labels_for_turn
        if labels is None:
            if 'max_features' in user_message and 'start SFS' in user_message:
                labels = ['D', 'E']
            elif 'PSI' in user_message:
                labels = ['A', 'R']
            else:
                labels = ['A']
        return {
            'labels': labels,
            'label_names': [
                INTENT_LABEL_NAMES[label]
                for label in labels
            ],
            'source': 'llm_classifier',
            'preclassified': False,
            'classifier_version': 'intent-v3-llm-rag',
            'confidence': 'high',
            'uncertain': False,
            'fallback_reason': '',
            'decomposition': [{'segment': user_message, 'labels': labels}],
        }
    monkeypatch.setattr(views, 'resolve_intent_classification', fake_resolve_intent)

    skill_calls = []

    def fake_load_skill(name):
        skill_calls.append(name)
        return f'SKILL_PLAYBOOK_BODY for {name}'
    monkeypatch.setattr(views, '_load_skill_traced', fake_load_skill)

    llm_calls = []

    def fake_call_llm(messages, model_key, tools=None):
        idx = len(llm_calls)
        llm_calls.append({
            'messages': [dict(m) for m in messages],
            'tools': tools,
            'model_key': model_key,
        })
        return call_llm(idx, messages, tools)
    monkeypatch.setattr(views, '_call_llm', fake_call_llm)

    fn = views._chat_workflow.__wrapped__ \
        if hasattr(views._chat_workflow, '__wrapped__') else views._chat_workflow
    result = fn(user_message, context or {}, 'general', history or [],
                file_id=file_id, model='engine-x', source=source)
    return {'result': result, 'llm_calls': llm_calls, 'skill_calls': skill_calls}

# ---------------------------------------------------------------------------
# Redis-level spans (Option D): cache_get/cache_put/cache_list_artifacts
# now each emit their own trace span via @prometa_tool.
# ---------------------------------------------------------------------------

class _SpanCapture:
    """Tiny helper that replays the sequence of set_span_attr(key, value)
    calls across span boundaries by snapshotting on each new span start.

    Tests that only need the aggregate final attribute map can use
    ``captured`` directly; tests that care about per-span grouping can
    walk ``by_span``.
    """

    def __init__(self):
        self.captured: dict = {}
        self.by_span: list[dict] = []
        self._current: dict = {}

    def set_attr(self, key, value):
        self.captured[key] = value
        self._current[key] = value

    def snapshot(self):
        if self._current:
            self.by_span.append(self._current)
            self._current = {}

def _patch_span_attr(monkeypatch, *modules, capture: _SpanCapture):
    """Replace ``set_span_attr`` in each target module with the capture hook.

    Always also patches ``ai_assistant.prometa_config.set_span_attr`` because
    the shared ``stamp_elapsed`` / ``span_timer`` helpers live there and call
    their own module-level reference — without patching it, elapsed-time
    attributes would silently bypass the test capture.
    """
    import importlib
    targets = list(modules) + ['ai_assistant.prometa_config']
    for mod_name in targets:
        mod = importlib.import_module(mod_name)
        monkeypatch.setattr(mod, 'set_span_attr', capture.set_attr)

# ---------------------------------------------------------------------------
# v2.27.2 — Empty-response synthesis pass + actionable fallback (Patch A)
# ---------------------------------------------------------------------------
# Pre-v2.27.2 the chat workflow could exit its tool-call loop with an
# assistant message that had `tool_calls` populated but `content=null`.
# This happened when the model kept calling tools through the very last
# round (the no-tools forced round): we executed those tool calls inside
# the loop body, then broke naturally without ever asking the model for a
# final text answer.  The user saw the bare string "No response received."
# in the chat UI, and tracing showed real tool work that produced no
# visible output.
#
# v2.27.2 fixes this with two layers of defence:
#   1. A synthesis pass — when the loop exits with empty content but tool
#      work happened, run ONE more no-tools call so the model verbalizes
#      what it found.  All tool results are already in `messages` so this
#      is cheap.
#   2. An actionable fallback — if the synthesis pass also fails (network
#      error, model truly returns blank), surface a meaningful message
#      that tells the user what to do next.  Two flavours: one for the
#      "tool work happened, ran out of room" case and one for the "model
#      returned nothing at all" case.
#
# The tests below script the exact LLM response sequences that triggered
# the bug pre-v2.27.2 and assert that v2.27.2 always returns a meaningful
# `message` to the API caller.
def _mock_llm_response(content=None, tool_calls=None, tokens=10):
    """Build an OpenAI-style /v1/chat/completions response payload.

    `content=None` + non-empty `tool_calls` is the exact shape that
    triggered the original "No response received." bug.
    """
    msg = {'role': 'assistant', 'content': content}
    if tool_calls is not None:
        msg['tool_calls'] = tool_calls
    finish = 'tool_calls' if tool_calls else 'stop'
    return {
        'choices': [{'finish_reason': finish, 'message': msg}],
        'usage': {
            'prompt_tokens': tokens,
            'completion_tokens': tokens,
            'total_tokens': tokens * 2,
        },
    }

def _purifier_tool_call(call_id):
    """A canned tool_call invocation against get_purifier_options — the
    handler is static and side-effect-free, so it works inside any test
    without Redis or DB fixtures."""
    return [{
        'id': call_id,
        'type': 'function',
        'function': {'name': 'get_purifier_options', 'arguments': '{}'},
    }]

# ---------------------------------------------------------------------------
# Hyperparameter tuning engine (modeling/hyperparam_utils.py)
# ---------------------------------------------------------------------------
def _hp_synthetic(n=160, seed=0):
    """Small separable binary dataset for fast engine unit tests."""
    from sklearn.datasets import make_classification
    X, y = make_classification(n_samples=n, n_features=6, n_informative=4,
                               n_redundant=0, random_state=seed)
    cols = [f'Var_{i}' for i in range(6)]
    split = int(n * 0.7)
    Xtr = pd.DataFrame(X[:split], columns=cols)
    Xte = pd.DataFrame(X[split:], columns=cols)
    return Xtr, pd.Series(y[:split]), Xte, pd.Series(y[split:])

def _hp_space(*enabled):
    """Default space with only the named params enabled."""
    from modeling.hyperparam_utils import DEFAULT_PARAM_SPACE
    space = {k: dict(v) for k, v in DEFAULT_PARAM_SPACE.items()}
    for k in space:
        space[k]['enabled'] = k in enabled
    return space
