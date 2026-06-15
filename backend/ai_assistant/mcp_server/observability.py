"""
Prometa span helpers for the DeclarAI MCP facade.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from ai_assistant.prometa_config import (
    set_customer_id,
    set_session_id,
    set_span_attr,
    span_timer,
    workflow,
)
from ai_assistant.prometa_runner.context import get_current_bundle_identity
from ai_assistant.prometa_runner.telemetry import stamp_bundle_identity


def stamp_mcp_context(
    *,
    operation: str,
    tool_name: str | None = None,
    file_id: int | None = None,
    action_type: str | None = None,
    required_scopes: Iterable[str] | None = None,
    risk: str | None = None,
    side_effects: bool | None = None,
    destructive: bool | None = None,
    approval_id: str | None = None,
    ok: bool | None = None,
    error: str | None = None,
    result_chars: int | None = None,
) -> None:
    """Stamp DeclarAI MCP attributes on the active Prometa span."""
    set_span_attr("declarai.mcp.operation", operation)
    if tool_name:
        set_span_attr("declarai.mcp.tool_name", tool_name)
    if file_id is not None:
        set_span_attr("declarai.mcp.file_id", file_id)
        set_session_id(f"declarai-file-{file_id}")
        set_customer_id(str(file_id))
    if action_type:
        set_span_attr("declarai.mcp.action_type", action_type)
    scopes = list(required_scopes or [])
    if scopes:
        set_span_attr("declarai.mcp.required_scopes", ",".join(scopes))
    if risk:
        set_span_attr("declarai.mcp.risk", risk)
    if side_effects is not None:
        set_span_attr("declarai.mcp.side_effects", side_effects)
    if destructive is not None:
        set_span_attr("declarai.mcp.destructive", destructive)
    if approval_id:
        set_span_attr("declarai.mcp.approval_id", approval_id)
    if ok is not None:
        set_span_attr("declarai.mcp.ok", ok)
    if error:
        set_span_attr("declarai.mcp.error", error[:200])
    if result_chars is not None:
        set_span_attr("declarai.mcp.result_chars", result_chars)

    bundle_identity = get_current_bundle_identity()
    if bundle_identity is not None:
        stamp_bundle_identity(*bundle_identity)

    client_id = os.environ.get("DECLARAI_MCP_CLIENT_ID")
    if client_id:
        set_span_attr("declarai.mcp.client_id", client_id)
    session_id = os.environ.get("DECLARAI_MCP_SESSION_ID")
    if session_id:
        set_span_attr("declarai.mcp.session_id", session_id)
    transport = os.environ.get("DECLARAI_MCP_TRANSPORT")
    if transport:
        set_span_attr("declarai.mcp.transport", transport)
