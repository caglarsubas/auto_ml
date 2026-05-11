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

from .prometa_config import tool as prometa_tool, set_span_attr, set_session_id, span_timer


def _stamp_session(file_id: int) -> None:
    """Tag the current cache span with the file's session id.

    Cache helpers are called from two contexts: inside the chat workflow
    (child span — session already set, this is an idempotent re-set) and
    from the standalone /api/ai/cache_push/ endpoint (root span — without
    this call the span lands in Trace Explorer with no session and
    pollutes the view next to real user traces).
    """
    if file_id is None:
        return
    try:
        set_session_id(f'declarai-file-{int(file_id)}')
    except (TypeError, ValueError):
        pass

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

@prometa_tool(name="redis-set")
def cache_put(file_id: int, artifact: str, data: Any, ttl: int = DEFAULT_TTL) -> bool:
    """Store a pipeline artifact in the cache. Returns True on success.

    Emits a ``redis-set`` span with attributes:
      - declarai.cache.file_id     pipeline file id
      - declarai.cache.artifact    artifact key (e.g. 'data_dictionary')
      - declarai.cache.bytes       serialized payload size
      - declarai.cache.ttl         ttl seconds
      - declarai.cache.ok          whether the write succeeded
      - declarai.cache.elapsed_us  elapsed time in microseconds
      - declarai.cache.elapsed_ms  elapsed time in milliseconds
    """
    with span_timer('declarai.cache'):
        _stamp_session(file_id)
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


@prometa_tool(name="redis-get")
def cache_get(file_id: int, artifact: str) -> Optional[Any]:
    """Retrieve a pipeline artifact from the cache. Returns None if missing.

    Emits a ``redis-get`` span with attributes:
      - declarai.cache.file_id     pipeline file id
      - declarai.cache.artifact    artifact key (e.g. 'pipeline_config')
      - declarai.cache.hit         True when a value was returned
      - declarai.cache.bytes       raw payload size on hit
      - declarai.cache.reason      error / miss reason (when applicable)
      - declarai.cache.elapsed_us  elapsed time in microseconds
      - declarai.cache.elapsed_ms  elapsed time in milliseconds
    """
    with span_timer('declarai.cache'):
        _stamp_session(file_id)
        set_span_attr('declarai.cache.file_id', file_id)
        set_span_attr('declarai.cache.artifact', artifact)
        r = _get_redis()
        if not r:
            set_span_attr('declarai.cache.hit', False)
            set_span_attr('declarai.cache.reason', 'redis-unavailable')
            return None
        try:
            raw = r.get(_key(file_id, artifact))
            if raw is None:
                set_span_attr('declarai.cache.hit', False)
                return None
            set_span_attr('declarai.cache.hit', True)
            set_span_attr('declarai.cache.bytes', len(raw))
            return json.loads(raw)
        except Exception as exc:
            set_span_attr('declarai.cache.hit', False)
            set_span_attr('declarai.cache.reason', str(exc)[:200])
            logger.warning("cache_get failed (%s/%s): %s", file_id, artifact, exc)
            return None


@prometa_tool(name="redis-set-bulk")
def cache_put_bulk(file_id: int, artifacts: dict[str, Any], ttl: int = DEFAULT_TTL) -> bool:
    """Store multiple artifacts at once using a Redis pipeline.

    Emits a ``redis-set-bulk`` span with attributes:
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
        _stamp_session(file_id)
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


@prometa_tool(name="redis-delete")
def cache_delete(file_id: int, artifact: str) -> bool:
    """Remove a specific artifact from the cache.

    Emits a ``redis-delete`` span with attributes:
      - declarai.cache.file_id     pipeline file id
      - declarai.cache.artifact    artifact key being evicted
      - declarai.cache.ok          whether the delete succeeded
      - declarai.cache.elapsed_us  elapsed time in microseconds
      - declarai.cache.elapsed_ms  elapsed time in milliseconds
    """
    with span_timer('declarai.cache'):
        _stamp_session(file_id)
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


@prometa_tool(name="redis-list")
def cache_list_artifacts(file_id: int) -> list[str]:
    """List all cached artifact types for a given file_id.

    Emits a ``redis-list`` span with attributes:
      - declarai.cache.file_id     pipeline file id
      - declarai.cache.prefix      key prefix scanned
      - declarai.cache.key_count   number of matching keys
      - declarai.cache.keys        matching artifact names (comma separated)
      - declarai.cache.elapsed_us  elapsed time in microseconds
      - declarai.cache.elapsed_ms  elapsed time in milliseconds
    """
    with span_timer('declarai.cache'):
        _stamp_session(file_id)
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
    ARTIFACT_MODEL_INFO,
    ARTIFACT_CV_RESULTS,
    ARTIFACT_DATA_DICTIONARY,
]
