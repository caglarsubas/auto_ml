"""
Model registry for the AI Assistant.

Defines supported LLM providers (OpenAI, local Inference Engine) and their
model configurations. Each model entry specifies the provider, model id,
display name, and default generation parameters. The _call_llm() helper selects
the right SDK at runtime.

The ``engine`` provider routes calls to a local llm-inference-engine instance
via its OpenAI-compatible ``/v1/chat/completions`` endpoint. We intentionally
talk to it through the OpenAI Python SDK so the prometa-sdk's openai
auto-instrumentation captures gen_ai.* spans on the assistant side — agentic-
hook-v2 stays decoupled from any specific inference backend.
"""

import os

# ---------------------------------------------------------------------------
# Registry: model_key → config
# ---------------------------------------------------------------------------
# Architecture / capability tags exposed to the frontend model selector.
#   architecture:    'dense' | 'moe'
#   reasoning:       model is optimised for chain-of-thought reasoning
#   thinking:        model can emit an explicit thinking / scratchpad block
#   thinking_level:  None | 'low' | 'med' | 'high'

MODEL_REGISTRY = {
    # ── OpenAI (cloud) ────────────────────────────────────────────────
    'gpt-5.5': {
        'provider': 'openai',
        'model_id': 'gpt-5.5',
        'display_name': 'GPT-5.5 (OpenAI)',
        'max_tokens': 16384,
        'supports_tools': True,
        'is_reasoning_model': True,
        'architecture': 'moe',
        'reasoning': True,
        'thinking': True,
        'thinking_level': 'high',
    },
    'gpt-5.4-mini': {
        'provider': 'openai',
        'model_id': 'gpt-5.4-mini',
        'display_name': 'GPT-5.4 Mini (OpenAI)',
        'max_tokens': 16384,
        'supports_tools': True,
        'is_reasoning_model': True,
        'architecture': 'moe',
        'reasoning': True,
        'thinking': True,
        'thinking_level': 'med',
    },
    'gpt-4.1-mini': {
        'provider': 'openai',
        'model_id': 'gpt-4.1-mini',
        'display_name': 'GPT-4.1 Mini (OpenAI)',
        'max_tokens': 16384,
        'supports_tools': True,
        'is_reasoning_model': False,
        'architecture': 'moe',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
    },
    # ── Local Inference Engine (llm-inference-engine) ─────────────────
    # Routes through the engine's OpenAI-compatible /v1/chat/completions.
    # The model_id is the engine's qualified name (backend-agnostic — the
    # engine resolves it to llama_cpp / mlx / vllm internally).
    'engine-llama-3.2-3b': {
        'provider': 'engine',
        'model_id': 'llama3.2:3b',
        'display_name': 'Llama 3.2 — 3B (Inference Engine)',
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': 3,
    },
    'engine-llama-3.2-1b': {
        'provider': 'engine',
        'model_id': 'llama3.2:1b',
        'display_name': 'Llama 3.2 — 1B (Inference Engine)',
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': 2,
    },
}

DEFAULT_MODEL = 'gpt-5.5'

# Metadata keys surfaced to the frontend model selector
_MODEL_META_KEYS = (
    'architecture', 'reasoning', 'thinking', 'thinking_level', 'ram_gb',
)


def get_model_config(model_key: str) -> dict:
    """Return config for a model key, falling back to default."""
    return MODEL_REGISTRY.get(model_key, MODEL_REGISTRY[DEFAULT_MODEL])


def list_models() -> list:
    """Return list of available models for the frontend selector."""
    return [
        {
            'key': k,
            'display_name': v['display_name'],
            'provider': v['provider'],
            **{mk: v.get(mk) for mk in _MODEL_META_KEYS},
        }
        for k, v in MODEL_REGISTRY.items()
    ]


# ---------------------------------------------------------------------------
# Unified LLM caller
# ---------------------------------------------------------------------------

def call_openai(api_key: str, messages: list, model_cfg: dict,
                tools: list = None) -> dict:
    """Call OpenAI chat completions API."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key, timeout=90.0)

    kwargs = {
        'model': model_cfg['model_id'],
        'messages': messages,
        'max_completion_tokens': model_cfg.get('max_tokens', 8192),
    }
    # Reasoning models (gpt-5.x) don't support custom temperature
    if not model_cfg.get('is_reasoning_model'):
        kwargs['temperature'] = model_cfg.get('temperature', 0.4)
    if tools and model_cfg.get('supports_tools'):
        kwargs['tools'] = tools
        kwargs['tool_choice'] = 'auto'

    response = client.chat.completions.create(**kwargs)
    return response.model_dump()


def call_engine(messages: list, model_cfg: dict, tools: list = None) -> dict:
    """Call the local llm-inference-engine via its OpenAI-compatible API.

    We use the OpenAI Python SDK with a custom ``base_url`` (rather than
    raw HTTP) for one specific reason: the prometa-sdk's openai integration
    auto-instruments ``Completions.create``, so every engine call emits the
    same ``gen_ai.*`` spans (prompt, completion, tokens) that the cloud
    GPT path emits today. agentic-hook-v2 receives all observability data
    from the assistant side; the engine itself stays free of any
    prometa/agentic-hook-v2 dependency.

    Configuration is via env vars:
      LLM_ENGINE_BASE_URL  — defaults to http://llm-engine:8080/v1
      LLM_ENGINE_API_KEY   — bearer token (engine accepts any value when
                              its AUTH_ENABLED=false; required when on)
    """
    from openai import OpenAI

    base_url = os.environ.get('LLM_ENGINE_BASE_URL', 'http://llm-engine:8080/v1')
    # The engine accepts any token when AUTH_ENABLED=false; the OpenAI SDK
    # rejects an empty api_key, so we pass a placeholder when none is set.
    api_key = os.environ.get('LLM_ENGINE_API_KEY', 'sk-engine-local')

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=300.0)

    kwargs = {
        'model': model_cfg['model_id'],
        'messages': messages,
        'max_tokens': model_cfg.get('max_tokens', 4096),
        'temperature': model_cfg.get('temperature', 0.4),
    }
    if tools and model_cfg.get('supports_tools'):
        kwargs['tools'] = tools
        kwargs['tool_choice'] = 'auto'

    response = client.chat.completions.create(**kwargs)
    return response.model_dump()
