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

Engine models are **discovered dynamically** from the engine's
``GET /v1/models`` endpoint rather than hard-coded.  The engine itself
probe-loads each GGUF and only lists ones llama.cpp can actually open, so
DeclarAI's UI surfaces only models that will actually answer.  A small
in-process TTL cache keeps Django request latency unaffected by the extra
RTT.
"""

import logging
import os
import re
import threading
import time

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
        'tool_calling_mode': 'native',
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
        'tool_calling_mode': 'native',
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
        'tool_calling_mode': 'native',
    },
    # Engine entries (provider='engine') are populated dynamically from
    # ``GET {LLM_ENGINE_BASE_URL}/models`` — see ``_refresh_engine_models()``.
    # Keys follow the convention ``engine-{engine_id_with_colons_dashed}``,
    # so ``llama3.2:3b`` becomes ``engine-llama3.2-3b``.
}

DEFAULT_MODEL = 'gpt-5.5'

# Metadata keys surfaced to the frontend model selector
_MODEL_META_KEYS = (
    'architecture', 'reasoning', 'thinking', 'thinking_level', 'ram_gb',
    'tool_calling_mode',
)

# Registry shape kept identical to the static entries above so the rest of
# the code (views, tests, frontend payloads) doesn't need to know whether a
# given engine entry was hard-coded or fetched.
_logger = logging.getLogger(__name__)

# TTL controls how often we re-poll the engine's /v1/models endpoint.  Long
# enough to make repeated Django requests free, short enough that pulling a
# new ollama model becomes visible to DeclarAI within a minute without a
# server restart.  Override via env for tests.
_ENGINE_MODELS_TTL_SECONDS = float(os.environ.get('LLM_ENGINE_MODELS_TTL', '60'))
_ENGINE_MODELS_TIMEOUT = float(os.environ.get('LLM_ENGINE_MODELS_TIMEOUT', '5.0'))

_engine_cache_lock = threading.Lock()
_engine_cache: dict[str, dict] = {}
_engine_cache_expires_at: float = 0.0


# Parameter-size pattern: optional digits + optional decimal + b/m suffix.
# Matches "26b", "3b", "1.5b", "8b", "e2b" (gemma's embedded variant — the
# leading 'e' is rejected by \d+ so the scan resumes at '2b'), "e4b", "70b",
# "1m" (tiny test models).  Anchored to end-of-string with an optional
# ``[-_].*`` tail so suffixes like "26b-q4" still extract "26b" cleanly
# (the leading numeric run wins) and an embedded "1B" inside a family
# string like ``Llama-3.2-1B-Instruct-4bit`` matches because the trailing
# ``-Instruct-4bit`` is absorbed by the optional ``[-_].*`` tail.
_OLLAMA_PARAM_SIZE_RE = re.compile(r'(\d+(?:\.\d+)?[bm])(?:[-_].*)?$', re.IGNORECASE)


def parse_ollama_tag(model_id: str) -> dict:
    """Split an Ollama-style model id into ``{family, tag, parameter_size}``.

    The local llm-inference-engine surfaces models with names of the form
    ``family:variant`` — for example ``gemma4:26b``, ``llama3.2:3b``,
    ``nemotron-3-nano:30b``, ``minimax-m2.7:cloud``.  Prometa's pricing
    registry uses a ``startsWith(registryKey)`` matcher that doesn't
    understand the ``:variant`` suffix or the family/size split, so it
    treats every self-hosted span as ``cost=0`` silent-zero (see thread
    with prometa-platform team 2026-05-28).

    Returning the components separately lets ``_call_llm`` stamp them as
    individual span attributes (``gen_ai.model.family``,
    ``gen_ai.model.tag``, ``gen_ai.model.parameter_size``) so the
    matcher can route on whichever facet it prefers without us breaking
    the canonical ``gen_ai.request.model`` wire format.

    Shape:
        ``family``         — substring before the first ``:`` (or the
                             whole id when no colon is present).  Always
                             a string; empty input yields ``''``.
        ``tag``            — substring after the first ``:``, or
                             ``None`` when no colon is present.
        ``parameter_size`` — extracted via regex.  Tried first on the
                             tag (typical Ollama-style: ``family:26b``),
                             then on the family as a fallback so MLX/HF
                             converted ids like
                             ``Llama-3.2-1B-Instruct-4bit:mlx`` still
                             surface ``parameter_size=1b``.  ``None``
                             when neither side carries a ``<digits>[bm]``
                             segment.  Normalized to lowercase.  Examples:
                                 ``gemma4:26b``                → ``"26b"``
                                 ``gemma4:e2b``                → ``"2b"``
                                 ``ministral-3:1.5b``          → ``"1.5b"``
                                 ``minimax-m2.7:cloud``        → ``None``
                                 ``Llama-3.2-1B-Instruct:mlx`` → ``"1b"``

    The function never raises on malformed input — callers can stamp
    whichever subset of fields came back non-empty without guarding.
    """
    if not isinstance(model_id, str) or not model_id:
        return {'family': '', 'tag': None, 'parameter_size': None}
    head, sep, tail = model_id.partition(':')
    family = head
    tag = tail if sep else None
    parameter_size = None
    # Try the tag first — that's where Ollama puts the size for
    # vanilla pulls (``family:26b``).  Fall back to scanning the
    # family for MLX/HF converted ids that encode the size in the
    # family string (``Llama-3.2-1B-Instruct-4bit:mlx``).
    if tag:
        match = _OLLAMA_PARAM_SIZE_RE.search(tag)
        if match:
            parameter_size = match.group(1).lower()
    if parameter_size is None and family:
        match = _OLLAMA_PARAM_SIZE_RE.search(family)
        if match:
            parameter_size = match.group(1).lower()
    return {'family': family, 'tag': tag, 'parameter_size': parameter_size}


def _engine_key(engine_id: str) -> str:
    """Map an engine model id (e.g. ``llama3.2:3b``) to a DeclarAI key.

    Convention: prefix with ``engine-`` and replace ``:`` separators with
    ``-`` so the key is URL/path safe, while preserving the original ``id``
    structure so the round-trip is unambiguous (no two distinct ollama tags
    can collide after the substitution because ``-`` is otherwise legal).
    """
    return f"engine-{engine_id.replace(':', '-')}"


def _display_name_for(engine_id: str) -> str:
    """Pretty label shown in the model selector — derived, not configured.

    Operators can pull arbitrary models into ollama; we don't get to write a
    bespoke display string for each one.  Keeping the engine id verbatim is
    honest and makes provenance obvious to users (they can grep it against
    ``ollama list``).
    """
    return f"{engine_id} (Inference Engine)"


def _ram_gb_estimate(size_bytes: int) -> int:
    """Coarse RAM hint shown in the UI.

    The engine reports ``size_bytes`` (the GGUF blob size).  Resident
    footprint at runtime is dominated by weights + KV cache; for a quick UI
    hint we use ceil(size_bytes / 1 GB) which over-estimates slightly on
    quantised weights — preferable to under-estimating and OOM-ing the host.
    """
    if size_bytes <= 0:
        return 0
    gb = size_bytes / (1024 ** 3)
    return max(1, int(gb + 0.999))


def _build_engine_entry(model_data: dict) -> dict:
    """Translate one entry from the engine's ``/v1/models`` payload.

    Capability metadata (architecture, reasoning, thinking_level) isn't
    surfaced by the engine today, so we fill safe defaults that match the
    historical hard-coded entries: dense, non-reasoning, non-thinking, tools
    on (the engine routes tool calls through the same code path regardless
    of whether the underlying model supports them).
    """
    engine_id = model_data['id']
    # The engine may surface tool_calling_mode per model; default to 'text'
    # since most open-source models use text-based action blocks.
    tcm = model_data.get('tool_calling_mode', 'text')
    return {
        'provider': 'engine',
        'model_id': engine_id,
        'display_name': _display_name_for(engine_id),
        'temperature': 0.4,
        'max_tokens': 4096,
        'supports_tools': True,
        'architecture': 'dense',
        'reasoning': False,
        'thinking': False,
        'thinking_level': None,
        'ram_gb': _ram_gb_estimate(int(model_data.get('size_bytes', 0))),
        'tool_calling_mode': tcm,
    }


def _fetch_engine_models() -> dict[str, dict] | None:
    """Hit ``GET {LLM_ENGINE_BASE_URL}/models`` and translate the response.

    Returns ``None`` (not ``{}``) on failure so the caller can keep serving
    the previous cached snapshot rather than wiping the UI when the engine
    is briefly unreachable.
    """
    base_url = os.environ.get('LLM_ENGINE_BASE_URL', 'http://llm-engine:8080/v1')
    api_key = os.environ.get('LLM_ENGINE_API_KEY', 'sk-engine-local')
    url = base_url.rstrip('/') + '/models'

    # Use the stdlib HTTP client to avoid pulling httpx into Django's import
    # graph — DeclarAI already imports openai for the actual chat path.
    import urllib.request
    import urllib.error
    import json
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {api_key}'})
    try:
        with urllib.request.urlopen(req, timeout=_ENGINE_MODELS_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        _logger.warning("engine /v1/models fetch failed: %s", exc)
        return None

    out: dict[str, dict] = {}
    for entry in payload.get('data') or []:
        try:
            cfg = _build_engine_entry(entry)
        except (KeyError, TypeError, ValueError) as exc:
            _logger.warning("engine model entry malformed (%s): %r", exc, entry)
            continue
        out[_engine_key(cfg['model_id'])] = cfg

    unavailable = payload.get('unavailable') or []
    if unavailable:
        _logger.info(
            "engine reports %d unavailable model(s): %s",
            len(unavailable),
            ", ".join(f"{u.get('id')} ({u.get('reason')})" for u in unavailable),
        )
    return out


def _refresh_engine_models(force: bool = False) -> dict[str, dict]:
    """Return the engine entries, refreshing the cache if the TTL elapsed.

    On a fetch failure we return the previous snapshot (possibly empty on
    cold boot) — DeclarAI degrades to "no engine models" but stays up.  The
    OpenAI block in ``MODEL_REGISTRY`` keeps the assistant usable.
    """
    global _engine_cache, _engine_cache_expires_at
    now = time.monotonic()
    with _engine_cache_lock:
        if not force and now < _engine_cache_expires_at:
            return _engine_cache

        fetched = _fetch_engine_models()
        if fetched is None:
            # Keep the old cache but back off briefly so we don't hammer a
            # restarting engine on every Django request.
            _engine_cache_expires_at = now + min(_ENGINE_MODELS_TTL_SECONDS, 5.0)
            return _engine_cache

        _engine_cache = fetched
        _engine_cache_expires_at = now + _ENGINE_MODELS_TTL_SECONDS
        return _engine_cache


def _registry_snapshot() -> dict[str, dict]:
    """Merged view: static cloud entries + dynamic engine entries.

    Keyed by DeclarAI key.  Cloud entries always win on collision since the
    engine is unlikely to ever advertise a key starting with ``gpt-``; we
    enforce it anyway as defense-in-depth.
    """
    snapshot = dict(_refresh_engine_models())
    snapshot.update(MODEL_REGISTRY)
    return snapshot


def get_model_config(model_key: str) -> dict:
    """Return config for a model key, falling back to default."""
    snapshot = _registry_snapshot()
    return snapshot.get(model_key, snapshot[DEFAULT_MODEL])


def list_models() -> list:
    """Return list of available models for the frontend selector."""
    snapshot = _registry_snapshot()
    return [
        {
            'key': k,
            'display_name': v['display_name'],
            'provider': v['provider'],
            **{mk: v.get(mk) for mk in _MODEL_META_KEYS},
        }
        for k, v in snapshot.items()
    ]


def invalidate_engine_cache() -> None:
    """Drop the engine model cache — useful for tests and ops poking."""
    global _engine_cache_expires_at
    with _engine_cache_lock:
        _engine_cache_expires_at = 0.0


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
