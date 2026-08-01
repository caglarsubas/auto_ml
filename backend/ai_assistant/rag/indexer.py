"""Build and refresh the Chroma index for the knowledge bank."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ai_assistant.knowledge_bank import (
    KNOWLEDGE_BANK_DIR,
    KnowledgeChunk,
    load_knowledge_chunks,
)
from ai_assistant.prometa_config import set_span_attr
from ai_assistant.rag.chroma_store import (
    get_collection,
    query_collection,
    stored_fingerprint,
    upsert_chunks,
    write_fingerprint,
)
from ai_assistant.rag.embeddings import embed_texts


def corpus_fingerprint(knowledge_dir: Path | None = None) -> str:
    """SHA-256 over sorted Markdown filenames and contents."""
    root = Path(knowledge_dir) if knowledge_dir is not None else KNOWLEDGE_BANK_DIR
    digest = hashlib.sha256()
    if not root.exists():
        digest.update(b"")
        return digest.hexdigest()

    for path in sorted(root.glob("*.md")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _chunk_document(chunk: KnowledgeChunk) -> str:
    return f"{chunk.title}\n{chunk.heading}\n{chunk.content}"


def _chunk_metadata(chunk: KnowledgeChunk) -> dict:
    return {
        "source": chunk.source,
        "title": chunk.title,
        "heading": chunk.heading,
        "is_fingerprint": False,
    }


def rebuild_index(
    *,
    persist_dir: Path | None = None,
    knowledge_dir: Path | None = None,
    chunks: tuple[KnowledgeChunk, ...] | None = None,
) -> dict:
    """Rebuild the Chroma collection from knowledge-bank chunks."""
    if knowledge_dir is not None:
        # Bypass the process-wide lru_cache when a custom dir is supplied.
        from ai_assistant.knowledge_bank import _parse_markdown

        root = Path(knowledge_dir)
        loaded: list[KnowledgeChunk] = []
        if root.exists():
            for path in sorted(root.glob("*.md")):
                loaded.extend(_parse_markdown(path))
        chunk_list = tuple(loaded)
    else:
        chunk_list = chunks if chunks is not None else load_knowledge_chunks()

    fingerprint = corpus_fingerprint(
        knowledge_dir if knowledge_dir is not None else KNOWLEDGE_BANK_DIR
    )
    collection = get_collection(persist_dir, reset=True)

    if not chunk_list:
        write_fingerprint(collection, fingerprint, dim=8)
        set_span_attr("declarai.rag.index_rebuilt", True)
        set_span_attr("declarai.rag.index_chunk_count", 0)
        return {
            "fingerprint": fingerprint,
            "chunk_count": 0,
            "rebuilt": True,
        }

    documents = [_chunk_document(chunk) for chunk in chunk_list]
    embeddings = embed_texts(documents)
    upsert_chunks(
        collection,
        ids=[chunk.chunk_id for chunk in chunk_list],
        embeddings=embeddings,
        documents=[chunk.content for chunk in chunk_list],
        metadatas=[_chunk_metadata(chunk) for chunk in chunk_list],
    )
    write_fingerprint(collection, fingerprint, dim=len(embeddings[0]))

    set_span_attr("declarai.rag.index_rebuilt", True)
    set_span_attr("declarai.rag.index_chunk_count", len(chunk_list))
    return {
        "fingerprint": fingerprint,
        "chunk_count": len(chunk_list),
        "rebuilt": True,
    }


def ensure_index(
    *,
    persist_dir: Path | None = None,
    knowledge_dir: Path | None = None,
    force: bool = False,
) -> dict:
    """Ensure the Chroma index matches the current knowledge-bank fingerprint."""
    fingerprint = corpus_fingerprint(
        knowledge_dir if knowledge_dir is not None else KNOWLEDGE_BANK_DIR
    )
    collection = get_collection(persist_dir, reset=False)
    current = stored_fingerprint(collection)

    if not force and current == fingerprint and collection.count() > 0:
        set_span_attr("declarai.rag.index_rebuilt", False)
        return {
            "fingerprint": fingerprint,
            "chunk_count": max(collection.count() - 1, 0),
            "rebuilt": False,
        }

    return rebuild_index(
        persist_dir=persist_dir,
        knowledge_dir=knowledge_dir,
    )


def search_index(
    query_embedding: list[float],
    *,
    n_results: int = 8,
    persist_dir: Path | None = None,
) -> list[dict]:
    """Query the ensured collection by embedding."""
    collection = get_collection(persist_dir, reset=False)
    return query_collection(
        collection,
        query_embedding=query_embedding,
        n_results=n_results,
    )
