"""OpenAI embedding helpers for knowledge-bank RAG."""
from __future__ import annotations

import os
from typing import Sequence

from ai_assistant.prometa_config import set_span_attr


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_BATCH_SIZE = 64


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


def embeddings_available() -> bool:
    """Return True when an OpenAI API key is configured for embeddings."""
    return bool(_api_key())


def embed_texts(
    texts: Sequence[str],
    *,
    model: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[list[float]]:
    """Embed texts with OpenAI ``text-embedding-3-small`` (or configured model)."""
    api_key = _api_key()
    if not api_key:
        raise EnvironmentError(
            "OpenAI API key not configured. Set OPENAI_API_KEY for vector RAG."
        )

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model_name = model or _embedding_model()
    clean = [((t or "").strip() or " ") for t in texts]
    vectors: list[list[float]] = []

    for start in range(0, len(clean), max(batch_size, 1)):
        batch = clean[start:start + max(batch_size, 1)]
        response = client.embeddings.create(model=model_name, input=batch)
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend([list(item.embedding) for item in ordered])

    set_span_attr("declarai.rag.embedding_model", model_name)
    set_span_attr("declarai.rag.embedding_count", len(vectors))
    return vectors


def embed_query(query: str, *, model: str | None = None) -> list[float]:
    """Embed a single query string."""
    vectors = embed_texts([query or ""], model=model)
    return vectors[0]
