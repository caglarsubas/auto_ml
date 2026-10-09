"""Run the DeclarAI Auto-ML MCP server."""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError
from access_control.authority import configured_actor
from ai_assistant.mcp_server import auth

from ai_assistant.mcp_server.server import create_mcp_server


class Command(BaseCommand):
    help = "Run the scoped DeclarAI MCP server over stdio; network transport is blocked pending per-client identity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--transport",
            choices=("stdio", "streamable-http"),
            default=os.environ.get("DECLARAI_MCP_TRANSPORT", "stdio"),
            help="MCP transport to use. Defaults to stdio.",
        )
        parser.add_argument(
            "--host",
            default=os.environ.get("DECLARAI_MCP_HOST", "127.0.0.1"),
            help="Host for Streamable HTTP transport.",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.environ.get("DECLARAI_MCP_PORT", "8000")),
            help="Port for Streamable HTTP transport.",
        )
        parser.add_argument(
            "--direct-actions",
            action="store_true",
            help=(
                "Unsupported pending verified exact approvals; fails closed."
            ),
        )
        parser.add_argument(
            "--json-response",
            dest="json_response",
            action="store_true",
            default=True,
            help="Use JSON responses for Streamable HTTP transport.",
        )
        parser.add_argument(
            "--no-json-response",
            dest="json_response",
            action="store_false",
            help="Allow SSE-style streaming responses for Streamable HTTP.",
        )

    def handle(self, *args, **options):
        try:
            auth.require_transport(options['transport'])
            configured_actor()
            if options['direct_actions']:
                auth.require_direct_actions_enabled()
        except PermissionError as exc:
            raise CommandError(str(exc)) from exc
        mcp = create_mcp_server(
            host=options["host"],
            port=options["port"],
            json_response=options["json_response"],
            include_direct_actions=options["direct_actions"] or None,
        )
        # Do not write to stdout before stdio transport starts; stdout is the
        # protocol channel.  Errors still surface through Django/SDK logging.
        mcp.run(transport=options["transport"])
