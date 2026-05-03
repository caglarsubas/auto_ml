"""
Model registry for the AI Assistant.

Defines supported LLM providers (OpenAI, Ollama, local Inference Engine) and
their model configurations. Each model entry specifies the provider, model id,
display name, and default generation parameters. The _call_llm() helper selects
the right SDK at runtime.

The ``engine`` provider routes calls to a local llm-inference-engine instance
via its OpenAI-compatible ``/v1/chat/completions`` endpoint. We intentionally
talk to it through the OpenAI Python SDK so the prometa-sdk's openai
auto-instrumentation captures gen_ai.* spans on the assistant side — agentic-
hook-v2 stays decoupled from any specific inference backend.
"""

import os
import logging

logger = logging.getLogger(__name__)

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
    # ── Google Gemma 4 (Ollama / local) ───────────────────────────────
    'gemma-4-e2b': {
        'provider': 'ollama',
        'model_id': 'gemma4:e2b',
        'display_name': 'Gemma 4 — E2B',
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': False,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': 5,
    },
    'gemma-4-e4b': {
        'provider': 'ollama',
        'model_id': 'gemma4:e4b',
        'display_name': 'Gemma 4 — E4B',
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': False,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': 7,
    },
    'gemma-4-26b': {
        'provider': 'ollama',
        'model_id': 'gemma4:26b',
        'display_name': 'Gemma 4 — 26B',
        'temperature': 0.4,
        'max_tokens': 8192,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': True,
        'thinking': True,
        'thinking_level': 'med',
        'ram_gb': 19,
    },
    'gemma-4-31b': {
        'provider': 'ollama',
        'model_id': 'gemma4:31b',
        'display_name': 'Gemma 4 — 31B',
        'temperature': 0.4,
        'max_tokens': 8192,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': True,
        'thinking': True,
        'thinking_level': 'high',
        'ram_gb': 21,
    },
    # ── Alibaba Qwen 3.6 (Ollama / local) ────────────────────────────
    'qwen-3.6-27b': {
        'provider': 'ollama',
        'model_id': 'qwen3.6:27b',
        'display_name': 'Qwen 3.6 — 27B',
        'temperature': 0.4,
        'max_tokens': 8192,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': True,
        'thinking': True,
        'thinking_level': 'high',
        'ram_gb': 18,
    },
    # ── MiniMax M2.7 (Ollama cloud) ──────────────────────────────────
    'minimax-m2.7': {
        'provider': 'ollama',
        'model_id': 'minimax-m2.7:cloud',
        'display_name': 'MiniMax M2.7',
        'temperature': 0.4,
        'max_tokens': 8192,
        'supports_tools': True,
        'architecture': 'moe',
        'reasoning': True,
        'thinking': True,
        'thinking_level': 'high',
        'ram_gb': 1,
    },
    # ── Mistral — Ministral 3 (Ollama / local) ───────────────────────
    'ministral-3-14b': {
        'provider': 'ollama',
        'model_id': 'ministral-3:14b',
        'display_name': 'Ministral 3 — 14B',
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': 10,
    },
    'ministral-3-8b': {
        'provider': 'ollama',
        'model_id': 'ministral-3:8b',
        'display_name': 'Ministral 3 — 8B',
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': 6,
    },
    'ministral-3-3b': {
        'provider': 'ollama',
        'model_id': 'ministral-3:3b',
        'display_name': 'Ministral 3 — 3B',
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': False,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': 3,
    },
    # ── NVIDIA Nemotron 3 Nano (Ollama / local) ────────────────────────
    'nemotron-3-nano-30b': {
        'provider': 'ollama',
        'model_id': 'nemotron-3-nano:30b',
        'display_name': 'Nemotron 3 Nano — 30B',
        'temperature': 0.4,
        'max_tokens': 8192,
        'supports_tools': True,
        'architecture': 'moe',
        'reasoning': True,
        'thinking': True,
        'thinking_level': 'high',
        'ram_gb': 20,
    },
    # ── NVIDIA Nemotron 3 Omni (Ollama / local) ────────────────────────
    'nemotron-3-omni-33b': {
        'provider': 'ollama',
        'model_id': 'nemotron3:33b',
        'display_name': 'Nemotron 3 Omni — 33B',
        'temperature': 0.4,
        'max_tokens': 8192,
        'supports_tools': True,
        'architecture': 'moe',
        'reasoning': True,
        'thinking': True,
        'thinking_level': 'high',
        'ram_gb': 22,
    },
    # ── Meta Llama 3.2 (Ollama / local) ────────────────────────────────
    'llama-3.2-1b': {
        'provider': 'ollama',
        'model_id': 'llama3.2:1b',
        'display_name': 'Llama 3.2 — 1B',
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': 2,
    },
    'llama-3.2-3b': {
        'provider': 'ollama',
        'model_id': 'llama3.2:3b',
        'display_name': 'Llama 3.2 — 3B',
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': 3,
    },
    # ── Local Inference Engine (llm-inference-engine) ─────────────────
    # Routes through the engine's OpenAI-compatible /v1/chat/completions.
    # The model_id is the engine's qualified name (backend-agnostic — the
    # engine resolves it to llama_cpp / mlx / vllm / ollama internally).
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
    'engine-qwen-3.6-27b': {
        'provider': 'engine',
        'model_id': 'qwen3.6:27b',
        'display_name': 'Qwen 3.6 — 27B (Inference Engine)',
        'temperature': 0.4,
        'max_tokens': 8192,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': True,
        'thinking': True,
        'thinking_level': 'high',
        'ram_gb': 18,
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


def call_ollama(messages: list, model_cfg: dict) -> dict:
    """Call Ollama REST API (OpenAI-compatible /v1/chat/completions)."""
    import urllib.request
    import urllib.error
    import json

    base_url = os.environ.get('OLLAMA_BASE_URL', 'http://ollama:11434')

    payload = {
        'model': model_cfg['model_id'],
        'messages': messages,
        'stream': False,
        'options': {
            'temperature': model_cfg.get('temperature', 0.4),
            'num_predict': model_cfg.get('max_tokens', 4096),
        },
    }

    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f'{base_url}/api/chat',
        data=body,
        method='POST',
        headers={'Content-Type': 'application/json'},
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        error_body = ''
        try:
            error_body = exc.read().decode('utf-8', errors='replace')
        except Exception:
            pass
        if 'requires more system memory' in error_body or exc.code == 500:
            ram_needed = model_cfg.get('ram_gb', '?')
            raise EnvironmentError(
                f"Ollama model '{model_cfg['model_id']}' requires ~{ram_needed} GB RAM but the "
                f"Docker VM does not have enough memory. "
                f"Increase Docker Desktop memory: Settings → Resources → Memory "
                f"(set to at least {ram_needed + 2 if isinstance(ram_needed, int) else '?'} GB), "
                f"then restart Docker Desktop."
            ) from exc
        raise

    # Normalize Ollama response to OpenAI-compatible shape
    message = data.get('message', {})
    usage_info = {
        'prompt_tokens': data.get('prompt_eval_count', 0),
        'completion_tokens': data.get('eval_count', 0),
        'total_tokens': data.get('prompt_eval_count', 0) + data.get('eval_count', 0),
    }

    return {
        'choices': [{
            'message': {
                'role': message.get('role', 'assistant'),
                'content': message.get('content', ''),
            },
            'finish_reason': 'stop',
        }],
        'model': data.get('model', model_cfg['model_id']),
        'usage': usage_info,
    }


def ensure_ollama_model(model_id: str) -> bool:
    """Pull an Ollama model if not already available. Returns True on success."""
    import urllib.request
    import json

    base_url = os.environ.get('OLLAMA_BASE_URL', 'http://ollama:11434')

    # Check if model exists
    try:
        req = urllib.request.Request(f'{base_url}/api/tags', method='GET')
        with urllib.request.urlopen(req, timeout=10) as resp:
            tags = json.loads(resp.read().decode('utf-8'))
        existing = [m.get('name', '') for m in tags.get('models', [])]
        if any(model_id in name for name in existing):
            return True
    except Exception:
        pass

    # Pull the model
    logger.info("Pulling Ollama model '%s' (first-time download)...", model_id)
    try:
        payload = json.dumps({'name': model_id, 'stream': False}).encode('utf-8')
        req = urllib.request.Request(
            f'{base_url}/api/pull',
            data=payload,
            method='POST',
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=1800) as resp:
            resp.read()
        logger.info("Ollama model '%s' pulled successfully.", model_id)
        return True
    except Exception as exc:
        logger.warning("Failed to pull Ollama model '%s': %s", model_id, exc)
        return False
