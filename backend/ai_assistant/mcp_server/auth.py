"""Process scope configuration; exact execution approvals remain unavailable."""

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
    """Unverified approval strings cannot confer execution authority."""
    return False


def require_direct_actions_enabled() -> None:
    raise PermissionError('mcp_exact_approval_unavailable: Direct MCP action execution is disabled until exact approvals are verified.')


def approval_required() -> bool:
    return True


def require_approval(action_type: str, approval_id: str | None) -> None:
    require_direct_actions_enabled()


def require_transport(transport):
    if transport != 'stdio':
        raise PermissionError('mcp_http_identity_unavailable: Network MCP transport requires authenticated per-client identity and is disabled.')
