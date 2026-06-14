"""
MCP server integration for the DeclarAI Auto-ML assistant.

The package intentionally keeps the MCP SDK import inside
``server.create_mcp_server`` so helper modules remain importable in test
environments before dependencies are installed.
"""
