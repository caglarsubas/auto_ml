"""OpenAI embedding helpers for knowledge-bank RAG."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Sequence

from ai_assistant.cache import _get_redis
from ai_assistant.prometa_config import cache_lookup, set_span_attr


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_BATCH_SIZE = 64
DEFAULT_EMBEDDING_CACHE_TTL = 60 * 60 * 24 * 7  # 7 days

logger = logging.getLogger(__name__)


def _embedding_model() -> str:
    try:
        from django.conf import settings
        return getattr(settings, "OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    except Exception:
        return os.environ.get("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def _api_key() -> str:
    try:
        from django.conf import settings
        return getattr(settings, "OPENAI_API_KEY", "") or os.environ.get(
            "OPENAI_API_KEY", ""
        )
    except Exception:
        return os.environ.get("OPENAI_API_KEY", "")


def _cache_ttl() -> int:
    try:
        from django.conf import settings
        ttl = getattr(settings, "EMBEDDING_CACHE_TTL", None)
        if ttl is not None:
            return int(ttl)
    except Exception:
        pass
    raw = os.environ.get("EMBEDDING_CACHE_TTL", str(DEFAULT_EMBEDDING_CACHE_TTL))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_EMBEDDING_CACHE_TTL


def embeddings_available() -> bool:
    """Return True when an OpenAI API key is configured for embeddings."""
    return bool(_api_key())


def _normalize_text(text: str) -> str:
    return (text or "").strip() or " "


def _embedding_cache_key(model: str, text: str) -> str:
    digest = hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()
    return f"ai:embedding:{model}:{digest}"


def _cache_get_vector(model: str, text: str) -> list[float] | None:
    """Return a cached embedding vector, or None. Emits cache_lookup AML."""
    cache_key = _embedding_cache_key(model, text)
    with cache_lookup("embedding", key=cache_key) as ch:
        r = _get_redis()
        if r is None:
            ch.miss()
            return None
        try:
            raw = r.get(cache_key)
        except Exception as exc:
            logger.debug("Embedding cache get failed for %s: %s", cache_key, exc)
            ch.miss()
            return None
        if raw is None:
            ch.miss()
            return None
        try:
            vector = json.loads(raw)
            if not isinstance(vector, list) or not vector:
                ch.miss()
                return None
            ch.hit()
            return [float(x) for x in vector]
        except Exception:
            ch.miss()
            return None


def _cache_put_vector(model: str, text: str, vector: list[float]) -> None:
    r = _get_redis()
    if r is None or not vector:
        return
    cache_key = _embedding_cache_key(model, text)
    try:
        r.setex(cache_key, _cache_ttl(), json.dumps(vector))
    except Exception as exc:
        logger.debug("Embedding cache put failed for %s: %s", cache_key, exc)


def embed_texts(
    texts: Sequence[str],
    *,
    model: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[list[float]]:
    """Embed texts with OpenAI ``text-embedding-3-small`` (or configured model).

    Per-text Redis cache (``ai:embedding:{model}:{sha256}``) with AML
    ``cache_lookup(kind='embedding')`` hit/miss signals. Fail-open when
    Redis is unavailable.
    """
    api_key = _api_key()
    if not api_key:
        raise EnvironmentError(
            "OpenAI API key not configured. Set OPENAI_API_KEY for vector RAG."
        )

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model_name = model or _embedding_model()
    clean = [_normalize_text(t) for t in texts]
    vectors: list[list[float] | None] = [None] * len(clean)
    miss_indices: list[int] = []

    for idx, text in enumerate(clean):
        cached = _cache_get_vector(model_name, text)
        if cached is not None:
            vectors[idx] = cached
        else:
            miss_indices.append(idx)

    if miss_indices:
        step = max(batch_size, 1)
        for start in range(0, len(miss_indices), step):
            batch_idxs = miss_indices[start:start + step]
            batch = [clean[i] for i in batch_idxs]
            response = client.embeddings.create(model=model_name, input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            for local_i, item in enumerate(ordered):
                idx = batch_idxs[local_i]
                vector = list(item.embedding)
                vectors[idx] = vector
                _cache_put_vector(model_name, clean[idx], vector)

    result = [v if v is not None else [] for v in vectors]
    set_span_attr("declarai.rag.embedding_model", model_name)
    set_span_attr("declarai.rag.embedding_count", len(result))
    set_span_attr("declarai.rag.embedding_cache_hits", len(clean) - len(miss_indices))
    set_span_attr("declarai.rag.embedding_cache_misses", len(miss_indices))
    return result


def embed_query(query: str, *, model: str | None = None) -> list[float]:
    """Embed a single query string."""
    vectors = embed_texts([query or ""], model=model)
    return vectors[0]
