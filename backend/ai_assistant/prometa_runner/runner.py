"""
DeclarAI execution-plane runner for Prometa signed deployment bundles.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ai_assistant.prometa_config import set_span_attr, span_timer
from ai_assistant.prometa_runner.client import fetch_bundle
from ai_assistant.prometa_runner.context import (
    reset_current_bundle_identity,
    set_current_bundle_identity,
)
from ai_assistant.prometa_runner.policy import (
    BundlePolicyError,
    find_tool,
    guardrails_required_for_tool,
    preflight_bundle,
    require_tool_call_allowed,
)
from ai_assistant.prometa_runner.signature import verify_bundle_signature
from ai_assistant.prometa_runner.telemetry import stamp_bundle_identity


class PrometaOnPremBundleRunner:
    """Verify, preflight, and execute a Prometa bundle against local MCP tools."""

    def __init__(
        self,
        envelope: Mapping[str, Any],
        *,
        require_signature: bool = True,
        mcp_server=None,
    ) -> None:
        self.envelope = dict(envelope)
        verify_bundle_signature(self.envelope, require_signature=require_signature)
        content = self.envelope.get("content")
        if not isinstance(content, Mapping):
            raise BundlePolicyError("Prometa bundle content must be an object.")
        self.content: Mapping[str, Any] = content
        preflight_bundle(self.content)
        self.agent_id = str(self.content["manifest"]["agentId"])
        solution_id = self.content["manifest"].get("solutionId")
        self.solution_id = solution_id if isinstance(solution_id, str) else None
        self._mcp_server = mcp_server
        self._owns_mcp_server = mcp_server is None
        self._direct_actions_registered = False

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        require_signature: bool = True,
        mcp_server=None,
    ) -> "PrometaOnPremBundleRunner":
        with Path(path).open("r", encoding="utf-8") as handle:
            envelope = json.load(handle)
        if not isinstance(envelope, Mapping):
            raise BundlePolicyError("Prometa bundle file must contain a JSON object.")
        return cls(
            envelope,
            require_signature=require_signature,
            mcp_server=mcp_server,
        )

    @classmethod
    def from_prometa(
        cls,
        *,
        base_url: str,
        manifest_id: str,
        token: str | None = None,
        timeout: float = 30.0,
        require_signature: bool = True,
        mcp_server=None,
    ) -> "PrometaOnPremBundleRunner":
        return cls(
            fetch_bundle(
                base_url=base_url,
                manifest_id=manifest_id,
                token=token,
                timeout=timeout,
            ),
            require_signature=require_signature,
            mcp_server=mcp_server,
        )

    def summary(self) -> dict[str, Any]:
        tools = [
            {
                "name": tool.get("name"),
                "operation": tool.get("operation"),
                "riskLevel": tool.get("riskLevel"),
                "scopes": tool.get("scopes") or [],
                "requiredGuardrails": guardrails_required_for_tool(tool),
            }
            for tool in self._bundle_tools()
        ]
        return {
            "agentId": self.agent_id,
            "solutionId": self.solution_id,
            "manifest": self.content.get("manifest"),
            "signed": bool(self.envelope.get("signed")),
            "algorithm": self.envelope.get("algorithm"),
            "canonicalization": self.envelope.get("canonicalization")
            or "json-sorted-keys-utf8",
            "tools": tools,
        }

    async def call_tool_async(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        *,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute one bundled MCP operation through the local MCP server."""
        if not isinstance(arguments, Mapping):
            raise BundlePolicyError("MCP tool arguments must be an object.")
        tool = find_tool(self.content, operation)
        require_tool_call_allowed(
            self.content,
            tool,
            approval_id=approval_id,
        )
        call_args = dict(arguments)
        if approval_id and operation.startswith("declarai.action."):
            call_args.setdefault("approval_id", approval_id)
        return await self._call_local_mcp_tool(operation, call_args)

    def call_tool(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        *,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        return asyncio.run(
            self.call_tool_async(
                operation,
                arguments,
                approval_id=approval_id,
            )
        )

    async def _call_local_mcp_tool(
        self,
        operation: str,
        call_args: dict[str, Any],
    ) -> dict[str, Any]:
        with span_timer("declarai.prometa.bundle"):
            stamp_bundle_identity(self.agent_id, self.solution_id)
            set_span_attr("declarai.prometa.bundle.operation", operation)
            token = set_current_bundle_identity(self.agent_id, self.solution_id)
            try:
                mcp_server = self._get_mcp_server(operation)
                content_items, structured = await mcp_server.call_tool(
                    operation,
                    call_args,
                )
                stamp_bundle_identity(self.agent_id, self.solution_id)
                set_span_attr("declarai.prometa.bundle.ok", True)
                return {
                    "operation": operation,
                    "structured": structured,
                    "content": [
                        getattr(item, "text", str(item))
                        for item in (content_items or [])
                    ],
                }
            except Exception as exc:
                set_span_attr("declarai.prometa.bundle.ok", False)
                set_span_attr("declarai.prometa.bundle.error", str(exc)[:200])
                raise
            finally:
                reset_current_bundle_identity(token)

    def _get_mcp_server(self, operation: str):
        needs_direct_actions = operation.startswith("declarai.action.")
        if self._mcp_server is None or (
            self._owns_mcp_server
            and needs_direct_actions
            and not self._direct_actions_registered
        ):
            from ai_assistant.mcp_server.server import create_mcp_server

            self._mcp_server = create_mcp_server(
                include_direct_actions=needs_direct_actions,
            )
            self._direct_actions_registered = needs_direct_actions
        return self._mcp_server

    def _bundle_tools(self) -> list[Mapping[str, Any]]:
        tools = self.content.get("tools")
        if not isinstance(tools, list):
            return []
        return [tool for tool in tools if isinstance(tool, Mapping)]
