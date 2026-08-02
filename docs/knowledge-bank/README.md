# DeclarAI Knowledge Bank

This folder is the source of truth for platform guidance that the DeclarAI
assistant can retrieve during chat turns. The assistant uses these documents
when its intent classifier adds the `R` retrieval label to a user query.

## Documents

- `platform-guideline-user-manual.md` explains the platform flow, user-facing
  capabilities, dependencies between stages, settings, and assistant usage.
- `technical-disclosure.md` explains the data-science decisions, calculations,
  assumptions, and rationale behind each pipeline step.
- `terminology-glossary.md` defines the technical terms, metrics, abbreviations,
  and platform labels that users see in the product.
- `assistant-usage-and-action-guide.md` explains how to work with the assistant,
  including when it answers, when it retrieves knowledge, when it uses live
  pipeline tools, and when it proposes executable actions.
- `model-governance-review-checklist.md` gives a practical review checklist for
  analysts and validators before they rely on or export a model.

## Retrieval Contract

The knowledge bank is intentionally versioned with the application. It should
describe DeclarAI's actual behavior, not generic AutoML behavior. When a
workflow, calculation, threshold, or action path changes, update the relevant
knowledge-bank document in the same pull request as the product change.

The assistant retrieval layer chunks Markdown sections by heading, embeds them
with OpenAI (`text-embedding-3-small` by default), stores vectors in a local
Chroma index (`backend/.chroma/knowledge-bank`), and retrieves with hybrid
ranking (Chroma cosine + lexical Reciprocal Rank Fusion). Compact cited
snippets are injected into the chat prompt only when the classifier includes
`R`. Snippets are labeled `[KB1]…[KBn]`; the model is instructed to cite those
markers when using knowledge-bank facts, and the API returns `rag_sources` for
the chat UI source list. When embeddings are unavailable, retrieval falls back
to the lexical scorer.

### Index lifecycle

- Rebuild manually: `python manage.py index_knowledge_bank`
- Chat lazily refreshes the index when the content fingerprint changes
- Docker backend entrypoint runs `index_knowledge_bank` on boot when
  `OPENAI_API_KEY` is set (failure is non-fatal; lexical fallback remains)
- Compose mounts a named volume `chroma-data` at `/app/backend/.chroma` so the
  vector store survives container recreation

### Embedding cache

Per-text embedding vectors are cached in Redis under
`ai:embedding:{model}:{sha256}` (TTL `EMBEDDING_CACHE_TTL`, default 7 days)
and emit Prometa `cache_lookup(kind="embedding")` hit/miss spans.

This keeps ordinary status or execution turns focused on live pipeline
artifacts while still giving documentation-grade answers for manual, glossary,
and disclosure questions.
