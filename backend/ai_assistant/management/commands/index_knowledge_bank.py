"""Build or refresh the Chroma index for the DeclarAI knowledge bank."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from ai_assistant.rag.embeddings import embeddings_available
from ai_assistant.rag.indexer import ensure_index, rebuild_index


class Command(BaseCommand):
    help = (
        "Index docs/knowledge-bank Markdown into the local Chroma vector store "
        "using OpenAI embeddings."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild even when the content fingerprint is unchanged.",
        )
        parser.add_argument(
            "--persist-dir",
            default="",
            help="Override CHROMA_PERSIST_DIR for this run.",
        )

    def handle(self, *args, **options):
        if not embeddings_available():
            raise CommandError(
                "OPENAI_API_KEY is not configured; cannot build the vector index."
            )

        persist_dir = options.get("persist_dir") or None
        force = bool(options.get("force"))

        if force:
            result = rebuild_index(persist_dir=persist_dir or None)
        else:
            result = ensure_index(
                persist_dir=persist_dir or None,
                force=False,
            )

        rebuilt = result.get("rebuilt")
        chunk_count = result.get("chunk_count", 0)
        fingerprint = result.get("fingerprint", "")
        status = "rebuilt" if rebuilt else "up-to-date"
        self.stdout.write(
            self.style.SUCCESS(
                f"Knowledge bank index {status}: "
                f"{chunk_count} chunks (fingerprint={fingerprint[:12]}…)"
            )
        )
