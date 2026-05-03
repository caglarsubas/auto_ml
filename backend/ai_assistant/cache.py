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

def cache_put(file_id: int, artifact: str, data: Any, ttl: int = DEFAULT_TTL) -> bool:
    """Store a pipeline artifact in the cache. Returns True on success."""
    r = _get_redis()
    if not r:
        return False
    try:
        r.setex(_key(file_id, artifact), ttl, json.dumps(data, default=str))
        return True
    except Exception as exc:
        logger.warning("cache_put failed (%s/%s): %s", file_id, artifact, exc)
        return False


def cache_get(file_id: int, artifact: str) -> Optional[Any]:
    """Retrieve a pipeline artifact from the cache. Returns None if missing."""
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(_key(file_id, artifact))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("cache_get failed (%s/%s): %s", file_id, artifact, exc)
        return None


def cache_put_bulk(file_id: int, artifacts: dict[str, Any], ttl: int = DEFAULT_TTL) -> bool:
    """Store multiple artifacts at once using a Redis pipeline."""
    r = _get_redis()
    if not r:
        return False
    try:
        pipe = r.pipeline()
        for artifact, data in artifacts.items():
            pipe.setex(_key(file_id, artifact), ttl, json.dumps(data, default=str))
        pipe.execute()
        return True
    except Exception as exc:
        logger.warning("cache_put_bulk failed (file_id=%s): %s", file_id, exc)
        return False


def cache_delete(file_id: int, artifact: str) -> bool:
    """Remove a specific artifact from the cache."""
    r = _get_redis()
    if not r:
        return False
    try:
        r.delete(_key(file_id, artifact))
        return True
    except Exception as exc:
        logger.warning("cache_delete failed (%s/%s): %s", file_id, artifact, exc)
        return False


def cache_list_artifacts(file_id: int) -> list[str]:
    """List all cached artifact types for a given file_id."""
    r = _get_redis()
    if not r:
        return []
    try:
        prefix = f"ai:pipeline:{file_id}:"
        keys = r.keys(f"{prefix}*")
        return [k.replace(prefix, '') for k in keys]
    except Exception as exc:
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
