"""
Action preparation and execution helpers for the DeclarAI MCP server.
"""

from __future__ import annotations

import json
from typing import Any

from ai_assistant.mcp_server import auth
from access_control.authority import authorized_access
from ai_assistant.mcp_server.observability import (
    stamp_mcp_context,
    span_timer,
    workflow,
)
from ai_assistant.mcp_server.registry import get_action_spec


@workflow(name="declarai-mcp-prepare-action")
def prepare_action(
    file_id: int,
    action_type: str,
    payload: dict[str, Any] | None,
    *,
    parent_span_id: str | None = None,
) -> dict[str, Any]:
    """Return a reviewable action payload without mutating platform state."""
    spec = get_action_spec(action_type)
    with span_timer("declarai.mcp"):
        stamp_mcp_context(
            operation="prepare_action",
            tool_name=spec.prepare_name if spec else f"declarai.prepare.{action_type}",
            file_id=file_id,
            action_type=action_type,
            required_scopes=[auth.SCOPE_ACTION_PREPARE],
            risk="low",
            side_effects=False,
            destructive=False,
        )
        try:
            with authorized_access(file_id, 'prepare_action', spec.prepare_name if spec else str(action_type)[:200],
                    auth.SCOPE_ACTION_PREPARE, payload) as receipt:
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
                out['access_receipt'] = receipt
                out['execution_available'] = False
                out['execution_blocker'] = 'mcp_exact_approval_unavailable'
            stamp_mcp_context(
                operation="prepare_action",
                ok=True,
                result_chars=len(action_block),
            )
            return out
        except Exception as exc:
            stamp_mcp_context(
                operation="prepare_action",
                ok=False,
                error=str(exc),
            )
            raise


@workflow(name="declarai-mcp-direct-action")
def execute_direct_action(
    file_id: int,
    action_type: str,
    payload: dict[str, Any] | None,
    *,
    approval_id: str | None,
    parent_span_id: str | None = None,
) -> dict[str, Any]:
    """Reject direct execution until exact action approval authority is available."""
    spec = get_action_spec(action_type)
    with span_timer("declarai.mcp"):
        stamp_mcp_context(
            operation="direct_action",
            tool_name=spec.direct_name if spec else f"declarai.action.{action_type}",
            file_id=file_id,
            action_type=action_type,
            required_scopes=[spec.scope] if spec else [],
            risk=spec.risk if spec else "unknown",
            side_effects=True,
            destructive=spec.destructive if spec else None,
            approval_id=approval_id,
        )
        try:
            with authorized_access(file_id, 'direct_action', spec.direct_name if spec else str(action_type)[:200],
                    spec.scope if spec else auth.SCOPE_ACTION_PREPARE, payload):
                auth.require_direct_actions_enabled()
        except Exception as exc:
            stamp_mcp_context(
                operation="direct_action",
                ok=False,
                error=str(exc),
            )
            raise


def _coerce_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("MCP action payload must be a JSON object.")
    return payload


def _format_action_block(action_type: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return f"<<<ACTION:{action_type}>>>\n{body}\n<<<END_ACTION>>>"
