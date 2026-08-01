"""Local Chroma persistence for DeclarAI knowledge-bank chunks."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

COLLECTION_NAME = "declarai-knowledge-bank"
FINGERPRINT_META_ID = "__kb_fingerprint__"


def _persist_dir() -> Path:
    try:
        from django.conf import settings
        raw = getattr(settings, "CHROMA_PERSIST_DIR", "") or ""
    except Exception:
        raw = os.environ.get("CHROMA_PERSIST_DIR", "")
    if raw:
        return Path(raw)
    # backend/ai_assistant/rag/chroma_store.py -> backend/.chroma/knowledge-bank
    return Path(__file__).resolve().parents[2] / ".chroma" / "knowledge-bank"


def get_client(persist_dir: Path | None = None):
    """Return a persistent Chroma client."""
    import chromadb
    from chromadb.config import Settings

    path = Path(persist_dir) if persist_dir is not None else _persist_dir()
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(path),
        settings=Settings(anonymized_telemetry=False),
    )


def get_collection(persist_dir: Path | None = None, *, reset: bool = False):
    """Open or create the knowledge-bank collection."""
    client = get_client(persist_dir)
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def stored_fingerprint(collection) -> str | None:
    """Read the content fingerprint stored as a sentinel document."""
    try:
        got = collection.get(ids=[FINGERPRINT_META_ID], include=["metadatas"])
    except Exception:
        return None
    ids = got.get("ids") or []
    if not ids:
        return None
    metadatas = got.get("metadatas") or []
    if not metadatas:
        return None
    meta = metadatas[0] or {}
    value = meta.get("fingerprint")
    return str(value) if value else None


def write_fingerprint(collection, fingerprint: str, *, dim: int) -> None:
    """Upsert a zero-vector sentinel carrying the corpus fingerprint."""
    embedding = [0.0] * max(int(dim), 1)
    collection.upsert(
        ids=[FINGERPRINT_META_ID],
        embeddings=[embedding],
        documents=["knowledge-bank fingerprint sentinel"],
        metadatas=[{
            "fingerprint": fingerprint,
            "is_fingerprint": True,
            "source": "__meta__",
            "title": "fingerprint",
            "heading": "fingerprint",
        }],
    )


def upsert_chunks(
    collection,
    *,
    ids: Sequence[str],
    embeddings: Sequence[Sequence[float]],
    documents: Sequence[str],
    metadatas: Sequence[dict[str, Any]],
) -> None:
    """Upsert chunk vectors and metadata into the collection."""
    if not ids:
        return
    collection.upsert(
        ids=list(ids),
        embeddings=[list(vec) for vec in embeddings],
        documents=list(documents),
        metadatas=list(metadatas),
    )


def query_collection(
    collection,
    *,
    query_embedding: Sequence[float],
    n_results: int = 8,
) -> list[dict[str, Any]]:
    """Query Chroma by embedding; skip the fingerprint sentinel."""
    if n_results <= 0:
        return []

    # Fetch a few extra in case the sentinel lands in the top-k.
    raw = collection.query(
        query_embeddings=[list(query_embedding)],
        n_results=min(max(n_results + 2, n_results), 50),
        include=["documents", "metadatas", "distances"],
    )

    ids = (raw.get("ids") or [[]])[0]
    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    dists = (raw.get("distances") or [[]])[0]

    results: list[dict[str, Any]] = []
    for chunk_id, document, meta, distance in zip(ids, docs, metas, dists):
        meta = meta or {}
        if chunk_id == FINGERPRINT_META_ID or meta.get("is_fingerprint"):
            continue
        # Cosine distance → similarity in [approx -inf, 1]; clamp for scoring.
        try:
            similarity = 1.0 - float(distance)
        except (TypeError, ValueError):
            similarity = 0.0
        results.append({
            "chunk_id": chunk_id,
            "source": meta.get("source", ""),
            "title": meta.get("title", ""),
            "heading": meta.get("heading", ""),
            "content": document or meta.get("content", ""),
            "score": similarity,
        })
        if len(results) >= n_results:
            break
    return results
