"""
Redis-backed cache for AI Assistant pipeline artifacts.

Stores pipeline data (DQ summary, split validation, VIF decomposition, etc.)
keyed by file_id + artifact_type so the LLM can fetch them on demand via
tool calls instead of having everything pre-stuffed into the context window.

Configuration:
    REDIS_URL  — Redis connection URL (default: redis://localhost:6379/0)

All values are stored as JSON with a configurable TTL (default 24h).
Reads/writes are fail-safe — if Redis is unavailable the app keeps working.
"""

import json
import logging
import os
from typing import Any, Optional

from .prometa_config import (
    child_only_tool,
    set_span_attr,
    span_timer,
    cache_lookup,
    stamp_mcp_tool_marker,
)

# ---------------------------------------------------------------------------
# Tracing policy for cache ops (v2.22.3+)
# ---------------------------------------------------------------------------
# Cache helpers use ``@child_only_tool`` instead of ``@prometa_tool``: they
# emit a Prometa span only when called from inside an active parent span
# (the chat workflow in ``ai_assistant.views`` or the action handler in
# ``ai_assistant.action_executor``).  When called standalone — from the
# ``/api/ai/cache_push/`` REST endpoint, the ``declaration/views.py``
# data-dictionary push hook, or an ad-hoc shell script — they run plain,
# producing NO trace at all.
#
# Two complementary cleanups arrived together:
#
#   * v2.22.2 removed ``_stamp_session`` from every cache op so they
#     stopped tagging server-side writes with ``declarai-file-<id>``
#     (which had been polluting Session Explorer).
#   * v2.22.3 stops cache ops from creating standalone root traces in
#     Trace Explorer when there's no user-facing parent workflow.
#
# Together: cache I/O is fully visible WITHIN a chat or action trace
# (child ``redis-*`` spans inside ``declarai-chat`` / ``declarai-action``)
# but completely invisible OUTSIDE one (no clutter from background
# writes the user never initiated).
#
# Session ids continue to live on the user-facing root span only and
# propagate to children via OTLP trace context.
#
# For ad-hoc scripts that should not touch Prometa at all, set
# ``PROMETA_DISABLE=1`` before running.

logger = logging.getLogger(__name__)

_redis_client = None
_redis_initialized = False

# Default TTL for cached artifacts (24 hours)
DEFAULT_TTL = 60 * 60 * 24


def _get_redis():
    """Return a singleton Redis client, or None if unavailable."""
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client
    _redis_initialized = True

    url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    try:
        import redis as redis_lib
        _redis_client = redis_lib.from_url(url, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        logger.info("AI Assistant cache connected — %s", url)
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — AI cache disabled: %s", url, exc)
        _redis_client = None

    return _redis_client


def _key(file_id: int, artifact: str) -> str:
    """Build a namespaced Redis key."""
    return f"ai:pipeline:{file_id}:{artifact}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@child_only_tool(name="redis-set")
def cache_put(file_id: int, artifact: str, data: Any, ttl: int = DEFAULT_TTL) -> bool:
    """Store a pipeline artifact in the cache. Returns True on success.

    Emits a ``redis-set`` child span when called inside an active parent
    workflow (chat / action).  When called standalone (cache_push REST
    endpoint, declaration data-dict push, ad-hoc scripts) it runs plain
    — no trace, no Trace Explorer clutter.  See the policy note at the
    top of this module.  Span attributes when emitted:
      - declarai.cache.file_id     pipeline file id
      - declarai.cache.artifact    artifact key (e.g. 'data_dictionary')
      - declarai.cache.bytes       serialized payload size
      - declarai.cache.ttl         ttl seconds
      - declarai.cache.ok          whether the write succeeded
      - declarai.cache.elapsed_us  elapsed time in microseconds
      - declarai.cache.elapsed_ms  elapsed time in milliseconds
    """
    with span_timer('declarai.cache'):
        stamp_mcp_tool_marker('redis-set')
        set_span_attr('declarai.cache.file_id', file_id)
        set_span_attr('declarai.cache.artifact', artifact)
        set_span_attr('declarai.cache.ttl', ttl)
        r = _get_redis()
        if not r:
            set_span_attr('declarai.cache.ok', False)
            set_span_attr('declarai.cache.reason', 'redis-unavailable')
            return False
        try:
            payload = json.dumps(data, default=str)
            set_span_attr('declarai.cache.bytes', len(payload))
            r.setex(_key(file_id, artifact), ttl, payload)
            set_span_attr('declarai.cache.ok', True)
            return True
        except Exception as exc:
            set_span_attr('declarai.cache.ok', False)
            set_span_attr('declarai.cache.reason', str(exc)[:200])
            logger.warning("cache_put failed (%s/%s): %s", file_id, artifact, exc)
            return False


@child_only_tool(name="redis-get")
def cache_get(file_id: int, artifact: str) -> Optional[Any]:
    """Retrieve a pipeline artifact from the cache. Returns None if missing.

    Emits a ``redis-get`` child span only when called inside an active
    parent workflow.  See the policy note at the top of this module.
    Span attributes when emitted:
      - declarai.cache.file_id     pipeline file id
      - declarai.cache.artifact    artifact key (e.g. 'pipeline_config')
      - declarai.cache.hit         True when a value was returned
      - declarai.cache.bytes       raw payload size on hit
      - declarai.cache.reason      error / miss reason (when applicable)
      - declarai.cache.elapsed_us  elapsed time in microseconds
      - declarai.cache.elapsed_ms  elapsed time in milliseconds

    v2.32.0 (Phase 3b): also emits a Prometa ``cache.lookup`` AML span
    (catalog B1) as a PARENT of the ``redis-get`` tool span.  The AML
    span carries the canonical ``cache.kind='tool_call'`` / ``cache.key``
    attributes and stamps hit/miss via the SDK handle (``ch.hit()`` /
    ``ch.miss()``).  Hit/miss attribution is propagated to BOTH spans:
    the legacy ``declarai.cache.hit`` boolean (for Trace Explorer back-
    compat) AND the canonical ``cache.hit`` attribute (for AML B1).
    """
    cache_key = _key(file_id, artifact)
    # v2.32.0: outer cache.lookup AML span wraps the redis-get tool span.
    # When the SDK is unconfigured (no PROMETA_ENDPOINT) or unavailable,
    # ``ch`` is a _NoOpAMLHandle and the with-block is a transparent no-op
    # — the existing legacy span shape continues unchanged.
    with cache_lookup('tool_call', key=cache_key) as ch:
        with span_timer('declarai.cache'):
            stamp_mcp_tool_marker('redis-get')
            set_span_attr('declarai.cache.file_id', file_id)
            set_span_attr('declarai.cache.artifact', artifact)
            r = _get_redis()
            if not r:
                set_span_attr('declarai.cache.hit', False)
                set_span_attr('declarai.cache.reason', 'redis-unavailable')
                # Redis unavailable IS a logical cache miss for AML scoring.
                ch.miss()
                return None
            try:
                raw = r.get(cache_key)
                if raw is None:
                    set_span_attr('declarai.cache.hit', False)
                    ch.miss()
                    return None
                set_span_attr('declarai.cache.hit', True)
                set_span_attr('declarai.cache.bytes', len(raw))
                # ttl_remaining_seconds is optional; we skip it to avoid
                # an extra Redis op per get.  The TTL is a write-time
                # constant (DEFAULT_TTL=24h) so the platform can infer
                # remaining TTL from span start_time if needed.
                ch.hit()
                return json.loads(raw)
            except Exception as exc:
                set_span_attr('declarai.cache.hit', False)
                set_span_attr('declarai.cache.reason', str(exc)[:200])
                # Parse / decode errors are logical misses too.
                ch.miss()
                logger.warning("cache_get failed (%s/%s): %s", file_id, artifact, exc)
                return None


@child_only_tool(name="redis-set-bulk")
def cache_put_bulk(file_id: int, artifacts: dict[str, Any], ttl: int = DEFAULT_TTL) -> bool:
    """Store multiple artifacts at once using a Redis pipeline.

    Emits a ``redis-set-bulk`` child span only when called inside an
    active parent workflow.  The ``/api/ai/cache_push/`` REST endpoint
    invokes this from a non-chat context and therefore produces no
    trace — which is the entire point of v2.22.3.  Span attributes
    when emitted:
      - declarai.cache.file_id      pipeline file id
      - declarai.cache.keys         artifact keys written (comma separated)
      - declarai.cache.key_count    number of keys written
      - declarai.cache.bytes        total serialized payload size
      - declarai.cache.ttl          ttl seconds
      - declarai.cache.ok           whether the pipelined write succeeded
      - declarai.cache.elapsed_us   elapsed time in microseconds
      - declarai.cache.elapsed_ms   elapsed time in milliseconds
    """
    with span_timer('declarai.cache'):
        stamp_mcp_tool_marker('redis-set-bulk')
        set_span_attr('declarai.cache.file_id', file_id)
        set_span_attr('declarai.cache.keys', ','.join(artifacts.keys()))
        set_span_attr('declarai.cache.key_count', len(artifacts))
        set_span_attr('declarai.cache.ttl', ttl)
        r = _get_redis()
        if not r:
            set_span_attr('declarai.cache.ok', False)
            set_span_attr('declarai.cache.reason', 'redis-unavailable')
            return False
        try:
            pipe = r.pipeline()
            total_bytes = 0
            for artifact, data in artifacts.items():
                payload = json.dumps(data, default=str)
                total_bytes += len(payload)
                pipe.setex(_key(file_id, artifact), ttl, payload)
            pipe.execute()
            set_span_attr('declarai.cache.bytes', total_bytes)
            set_span_attr('declarai.cache.ok', True)
            return True
        except Exception as exc:
            set_span_attr('declarai.cache.ok', False)
            set_span_attr('declarai.cache.reason', str(exc)[:200])
            logger.warning("cache_put_bulk failed (file_id=%s): %s", file_id, exc)
            return False


@child_only_tool(name="redis-delete")
def cache_delete(file_id: int, artifact: str) -> bool:
    """Remove a specific artifact from the cache.

    Emits a ``redis-delete`` child span only when called inside an
    active parent workflow.  See the policy note at the top of this
    module.  Span attributes when emitted:
      - declarai.cache.file_id     pipeline file id
      - declarai.cache.artifact    artifact key being evicted
      - declarai.cache.ok          whether the delete succeeded
      - declarai.cache.elapsed_us  elapsed time in microseconds
      - declarai.cache.elapsed_ms  elapsed time in milliseconds
    """
    with span_timer('declarai.cache'):
        stamp_mcp_tool_marker('redis-delete')
        set_span_attr('declarai.cache.file_id', file_id)
        set_span_attr('declarai.cache.artifact', artifact)
        r = _get_redis()
        if not r:
            set_span_attr('declarai.cache.ok', False)
            set_span_attr('declarai.cache.reason', 'redis-unavailable')
            return False
        try:
            r.delete(_key(file_id, artifact))
            set_span_attr('declarai.cache.ok', True)
            return True
        except Exception as exc:
            set_span_attr('declarai.cache.ok', False)
            set_span_attr('declarai.cache.reason', str(exc)[:200])
            logger.warning("cache_delete failed (%s/%s): %s", file_id, artifact, exc)
            return False


@child_only_tool(name="redis-list")
def cache_list_artifacts(file_id: int) -> list[str]:
    """List all cached artifact types for a given file_id.

    Emits a ``redis-list`` child span only when called inside an
    active parent workflow.  The ``/api/ai/cache_status/`` REST
    endpoint invokes this standalone and therefore produces no trace.
    Span attributes when emitted:
      - declarai.cache.file_id     pipeline file id
      - declarai.cache.prefix      key prefix scanned
      - declarai.cache.key_count   number of matching keys
      - declarai.cache.keys        matching artifact names (comma separated)
      - declarai.cache.elapsed_us  elapsed time in microseconds
      - declarai.cache.elapsed_ms  elapsed time in milliseconds
    """
    with span_timer('declarai.cache'):
        stamp_mcp_tool_marker('redis-list')
        set_span_attr('declarai.cache.file_id', file_id)
        prefix = f"ai:pipeline:{file_id}:"
        set_span_attr('declarai.cache.prefix', prefix)
        r = _get_redis()
        if not r:
            set_span_attr('declarai.cache.key_count', 0)
            set_span_attr('declarai.cache.reason', 'redis-unavailable')
            return []
        try:
            keys = r.keys(f"{prefix}*")
            artifacts = [k.replace(prefix, '') for k in keys]
            set_span_attr('declarai.cache.key_count', len(artifacts))
            set_span_attr('declarai.cache.keys', ','.join(artifacts))
            return artifacts
        except Exception as exc:
            set_span_attr('declarai.cache.key_count', 0)
            set_span_attr('declarai.cache.reason', str(exc)[:200])
            logger.warning("cache_list_artifacts failed (file_id=%s): %s", file_id, exc)
            return []


# ---------------------------------------------------------------------------
# Artifact type constants (used by tool executor and cache push endpoint)
# ---------------------------------------------------------------------------

ARTIFACT_SPLIT_VALIDATION = 'split_validation'
ARTIFACT_DQ_SUMMARY = 'dq_summary'
ARTIFACT_FEATURE_STATS = 'feature_stats'
ARTIFACT_VIF_DECOMPOSITION = 'vif_decomposition'
ARTIFACT_ENCODING_PLAN = 'encoding_plan'
ARTIFACT_SFS_RESULTS = 'sfs_results'
ARTIFACT_SHAP_DETAILS = 'shap_details'
ARTIFACT_SELECTED_FEATURES = 'selected_features'
ARTIFACT_PIPELINE_CONFIG = 'pipeline_config'
ARTIFACT_PIPELINE_NOTES = 'pipeline_notes'
ARTIFACT_PIPELINE_CODELINES = 'pipeline_codelines'
ARTIFACT_MODEL_INFO = 'model_info'
ARTIFACT_CV_RESULTS = 'cv_results'
ARTIFACT_DATA_DICTIONARY = 'data_dictionary'

ALL_ARTIFACTS = [
    ARTIFACT_SPLIT_VALIDATION,
    ARTIFACT_DQ_SUMMARY,
    ARTIFACT_FEATURE_STATS,
    ARTIFACT_VIF_DECOMPOSITION,
    ARTIFACT_ENCODING_PLAN,
    ARTIFACT_SFS_RESULTS,
    ARTIFACT_SHAP_DETAILS,
    ARTIFACT_SELECTED_FEATURES,
    ARTIFACT_PIPELINE_CONFIG,
    ARTIFACT_PIPELINE_NOTES,
    ARTIFACT_PIPELINE_CODELINES,
    ARTIFACT_MODEL_INFO,
    ARTIFACT_CV_RESULTS,
    ARTIFACT_DATA_DICTIONARY,
]
