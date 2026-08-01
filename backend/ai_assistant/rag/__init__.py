"""Vector RAG over DeclarAI's curated knowledge bank (OpenAI + Chroma)."""

from .retriever import retrieve_vector_context

__all__ = ["retrieve_vector_context"]
