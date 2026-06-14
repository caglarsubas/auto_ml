"""
Minimal local authorization helpers for the DeclarAI MCP server.

Production Streamable HTTP deployments should put a real MCP/OAuth resource
server in front of these checks.  These helpers still give local and stdio
deployments a deterministic scope gate, and keep direct action tools disabled
unless an operator explicitly opts in.
"""

from __future__ import annotations

import os


SCOPE_PIPELINE_READ = "declarai.pipeline.read"
SCOPE_ACTION_PREPARE = "declarai.action.prepare"
SCOPE_NOTES_WRITE = "declarai.notes.write"
SCOPE_METADATA_WRITE = "declarai.metadata.write"
SCOPE_CONFIG_WRITE = "declarai.config.write"
SCOPE_DATASET_WRITE = "declarai.dataset.write"
SCOPE_PIPELINE_RUN = "declarai.pipeline.run"

DEFAULT_SCOPES = frozenset({SCOPE_PIPELINE_READ, SCOPE_ACTION_PREPARE})
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _truthy_env(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


def configured_scopes() -> set[str]:
    """Return scopes granted to the local MCP server process."""
    raw = os.environ.get("DECLARAI_MCP_SCOPES")
    if raw is None:
        return set(DEFAULT_SCOPES)
    return {scope.strip() for scope in raw.split(",") if scope.strip()}


def require_scope(scope: str) -> None:
    """Raise when the configured MCP process scopes do not include ``scope``."""
    scopes = configured_scopes()
    if scope not in scopes:
        granted = ", ".join(sorted(scopes)) or "(none)"
        raise PermissionError(
            f"MCP scope '{scope}' is required; granted scopes: {granted}."
        )


def direct_actions_enabled() -> bool:
    """Whether side-effecting direct action tools should be registered."""
    return _truthy_env("DECLARAI_MCP_ENABLE_DIRECT_ACTIONS", default=False)


def require_direct_actions_enabled() -> None:
    """Raise unless direct action execution was explicitly enabled."""
    if not direct_actions_enabled():
        raise PermissionError(
            "Direct MCP action execution is disabled. Set "
            "DECLARAI_MCP_ENABLE_DIRECT_ACTIONS=true and grant the required "
            "DECLARAI_MCP_SCOPES to expose side-effecting tools."
        )


def approval_required() -> bool:
    """Whether direct action calls must carry an approval identifier."""
    return _truthy_env("DECLARAI_MCP_REQUIRE_APPROVAL", default=True)


def require_approval(action_type: str, approval_id: str | None) -> None:
    """Require an explicit approval id before executing side-effecting actions."""
    if approval_required() and not (approval_id or "").strip():
        raise PermissionError(
            f"Direct MCP action '{action_type}' requires approval_id. "
            "The MCP host should collect human approval and pass its approval "
            "record id here, or set DECLARAI_MCP_REQUIRE_APPROVAL=false for "
            "trusted local-only automation."
        )
