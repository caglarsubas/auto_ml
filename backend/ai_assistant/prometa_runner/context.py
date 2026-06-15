"""
Request-local Prometa bundle identity for MCP calls.
"""

from __future__ import annotations

from contextvars import ContextVar


BundleIdentity = tuple[str, str | None, str | None, str | None]


_bundle_identity: ContextVar[BundleIdentity | None] = ContextVar(
    "declarai_prometa_bundle_identity",
    default=None,
)


def set_current_bundle_identity(
    agent_id: str,
    solution_id: str | None = None,
    solution_name: str | None = None,
    agent_name: str | None = None,
):
    return _bundle_identity.set((agent_id, solution_id, solution_name, agent_name))


def reset_current_bundle_identity(token) -> None:
    _bundle_identity.reset(token)


def get_current_bundle_identity() -> BundleIdentity | None:
    return _bundle_identity.get()
