"""Hybrid / vector retrieval over the Chroma knowledge-bank index."""
from __future__ import annotations

import os
from typing import Callable

from ai_assistant.knowledge_bank import (
    DEFAULT_MAX_CHUNKS,
    DEFAULT_MAX_CONTEXT_CHARS,
    KnowledgeChunk,
    _clip_snippet,
    _format_context,
    _score_chunk,
    _tokenize,
    load_knowledge_chunks,
)
from ai_assistant.prometa_config import set_span_attr
from ai_assistant.rag.embeddings import embed_query, embeddings_available
from ai_assistant.rag.indexer import ensure_index, search_index


RRF_K = 60
VECTOR_CANDIDATES = 12
LEXICAL_CANDIDATES = 12


def _rag_mode() -> str:
    try:
        from django.conf import settings
        mode = getattr(settings, "RAG_MODE", "hybrid")
    except Exception:
        mode = os.environ.get("RAG_MODE", "hybrid")
    mode = (mode or "hybrid").strip().lower()
    if mode not in {"hybrid", "vector", "lexical"}:
        return "hybrid"
    return mode


def _chunk_lookup() -> dict[str, KnowledgeChunk]:
    return {chunk.chunk_id: chunk for chunk in load_knowledge_chunks()}


def _lexical_ranked(
    query: str,
    *,
    limit: int = LEXICAL_CANDIDATES,
) -> list[tuple[str, float]]:
    query_terms = _tokenize(query or "")
    ranked: list[tuple[str, float]] = []
    for chunk in load_knowledge_chunks():
        score = _score_chunk(chunk, query_terms)
        if score > 0:
            ranked.append((chunk.chunk_id, score))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked[:limit]


def _rrf_merge(
    rankings: list[list[tuple[str, float]]],
    *,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, (chunk_id, _) in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def _materialize_results(
    ranked_ids: list[tuple[str, float]],
    *,
    chunks_by_id: dict[str, KnowledgeChunk],
    vector_hits: dict[str, dict] | None = None,
    max_chunks: int,
    max_context_chars: int,
) -> list[dict]:
    results: list[dict] = []
    used_chars = 0
    vector_hits = vector_hits or {}

    for chunk_id, score in ranked_ids:
        chunk = chunks_by_id.get(chunk_id)
        hit = vector_hits.get(chunk_id)
        if chunk is None and hit is None:
            continue

        content = chunk.content if chunk is not None else (hit or {}).get("content", "")
        snippet = _clip_snippet(content)
        next_chars = len(snippet)
        if results and used_chars + next_chars > max_context_chars:
            break

        results.append({
            "chunk_id": chunk_id,
            "source": (
                chunk.source if chunk is not None
                else (hit or {}).get("source", "")
            ),
            "title": (
                chunk.title if chunk is not None
                else (hit or {}).get("title", "")
            ),
            "heading": (
                chunk.heading if chunk is not None
                else (hit or {}).get("heading", "")
            ),
            "score": round(float(score), 3),
            "snippet": snippet,
        })
        used_chars += next_chars
        if len(results) >= max_chunks:
            break
    return results


def retrieve_vector_context(
    query: str,
    *,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    mode: str | None = None,
    lexical_fallback: Callable[..., dict] | None = None,
) -> dict:
    """Retrieve knowledge-bank snippets via vector / hybrid search.

    Falls back to ``lexical_fallback`` (or empty results) when embeddings
    are unavailable or indexing/query fails.
    """
    resolved_mode = (mode or _rag_mode()).strip().lower()
    if resolved_mode not in {"hybrid", "vector", "lexical"}:
        resolved_mode = "hybrid"

    set_span_attr("declarai.rag.backend", "chroma")
    set_span_attr("declarai.rag.mode", resolved_mode)

    if resolved_mode == "lexical":
        if lexical_fallback is not None:
            return lexical_fallback(
                query,
                max_chunks=max_chunks,
                max_context_chars=max_context_chars,
            )
        return {"query": query or "", "results": [], "context": ""}

    if not embeddings_available():
        set_span_attr("declarai.rag.fallback", "no_api_key")
        if lexical_fallback is not None:
            return lexical_fallback(
                query,
                max_chunks=max_chunks,
                max_context_chars=max_context_chars,
            )
        return {"query": query or "", "results": [], "context": ""}

    try:
        ensure_index()
        query_embedding = embed_query(query or "")
        vector_results = search_index(
            query_embedding,
            n_results=max(VECTOR_CANDIDATES, max_chunks),
        )
        vector_ranked = [
            (item["chunk_id"], float(item.get("score") or 0.0))
            for item in vector_results
        ]
        vector_hits = {item["chunk_id"]: item for item in vector_results}

        if resolved_mode == "hybrid":
            lexical_ranked = _lexical_ranked(query)
            merged = _rrf_merge([vector_ranked, lexical_ranked])
        else:
            merged = vector_ranked

        results = _materialize_results(
            merged,
            chunks_by_id=_chunk_lookup(),
            vector_hits=vector_hits,
            max_chunks=max_chunks,
            max_context_chars=max_context_chars,
        )
        context = _format_context(results)
        set_span_attr("declarai.rag.called", True)
        set_span_attr("declarai.rag.query_chars", len(query or ""))
        set_span_attr("declarai.rag.result_count", len(results))
        set_span_attr("declarai.rag.context_chars", len(context))
        set_span_attr(
            "declarai.rag.sources",
            ",".join(dict.fromkeys(item["source"] for item in results)),
        )
        set_span_attr(
            "declarai.rag.chunk_ids",
            ",".join(item["chunk_id"] for item in results),
        )
        return {
            "query": query or "",
            "results": results,
            "context": context,
        }
    except Exception as exc:
        set_span_attr("declarai.rag.fallback", "error")
        set_span_attr("declarai.rag.fallback_error", type(exc).__name__)
        if lexical_fallback is not None:
            return lexical_fallback(
                query,
                max_chunks=max_chunks,
                max_context_chars=max_context_chars,
            )
        raise
