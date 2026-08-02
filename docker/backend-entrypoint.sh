#!/bin/sh
# Backend container entrypoint: migrate → optional KB index → runserver.
set -eu

python backend/manage.py migrate

if [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "Indexing knowledge bank (OPENAI_API_KEY present)..."
  if ! python backend/manage.py index_knowledge_bank; then
    echo "WARNING: index_knowledge_bank failed; chat will lazily index or fall back to lexical RAG." >&2
  fi
else
  echo "Skipping knowledge-bank index (OPENAI_API_KEY unset); lexical RAG fallback remains available."
fi

exec python backend/manage.py runserver 0.0.0.0:8001
