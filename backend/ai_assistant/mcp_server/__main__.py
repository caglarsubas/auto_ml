"""Module entry point for running the DeclarAI MCP server."""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DeclarAI Auto-ML MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.environ.get("DECLARAI_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.environ.get("DECLARAI_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DECLARAI_MCP_PORT", "8000")),
    )
    parser.add_argument(
        "--direct-actions",
        action="store_true",
        help="Register side-effecting direct action tools when env gates also allow them.",
    )
    parser.add_argument("--json-response", dest="json_response", action="store_true", default=True)
    parser.add_argument("--no-json-response", dest="json_response", action="store_false")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django

    django.setup()

    from ai_assistant.mcp_server.server import create_mcp_server

    mcp = create_mcp_server(
        host=args.host,
        port=args.port,
        json_response=args.json_response,
        include_direct_actions=args.direct_actions or None,
    )
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
