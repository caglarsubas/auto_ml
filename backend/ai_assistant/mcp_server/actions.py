"""
Action preparation and execution helpers for the DeclarAI MCP server.
"""

from __future__ import annotations

import json
from typing import Any

from ai_assistant.mcp_server import auth
from ai_assistant.mcp_server.registry import get_action_spec


def prepare_action(
    file_id: int,
    action_type: str,
    payload: dict[str, Any] | None,
    *,
    parent_span_id: str | None = None,
) -> dict[str, Any]:
    """Return a reviewable action payload without mutating platform state."""
    auth.require_scope(auth.SCOPE_ACTION_PREPARE)
    spec = get_action_spec(action_type)
    if spec is None:
        raise ValueError(f"Unknown DeclarAI action type: {action_type}")
    payload = _coerce_payload(payload)
    action_block = _format_action_block(action_type, payload)
    out: dict[str, Any] = {
        "status": "prepared",
        "file_id": file_id,
        "action_type": action_type,
        "payload": payload,
        "risk": spec.risk,
        "requires_approval": True,
        "side_effects": False,
        "direct_tool": spec.direct_name,
        "action_block": action_block,
    }
    if parent_span_id:
        out["parent_span_id"] = parent_span_id
    return out


def execute_direct_action(
    file_id: int,
    action_type: str,
    payload: dict[str, Any] | None,
    *,
    approval_id: str | None,
    parent_span_id: str | None = None,
) -> dict[str, Any]:
    """Execute a side-effecting DeclarAI action through the existing dispatcher."""
    auth.require_direct_actions_enabled()
    spec = get_action_spec(action_type)
    if spec is None:
        raise ValueError(f"Unknown DeclarAI action type: {action_type}")
    auth.require_scope(spec.scope)
    auth.require_approval(action_type, approval_id)
    payload = _coerce_payload(payload)
    result = _dispatch_action(file_id, action_type, payload, parent_span_id)
    return {
        "status": "executed",
        "file_id": file_id,
        "action_type": action_type,
        "approval_id": approval_id,
        "risk": spec.risk,
        "side_effects": True,
        "result": result,
    }


def _dispatch_action(
    file_id: int,
    action_type: str,
    payload: dict[str, Any],
    parent_span_id: str | None,
) -> dict[str, Any]:
    """Import lazily so helper tests do not need Django model imports up front."""
    from ai_assistant.action_executor import dispatch_action

    return dispatch_action(
        file_id,
        action_type,
        payload,
        parent_span_id=parent_span_id,
    )


def _coerce_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("MCP action payload must be a JSON object.")
    return payload


def _format_action_block(action_type: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return f"<<<ACTION:{action_type}>>>\n{body}\n<<<END_ACTION>>>"
