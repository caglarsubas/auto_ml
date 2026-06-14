"""
Unit tests for the DeclarAI MCP server facade.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.unit
class TestMcpRegistry:
    def test_read_tool_specs_are_prefixed_and_require_file_id(self):
        from ai_assistant.mcp_server.registry import get_read_tool_specs
        from ai_assistant.tool_definitions import PIPELINE_TOOLS

        specs = get_read_tool_specs()
        assert len(specs) == len(PIPELINE_TOOLS)
        assert specs[0].mcp_name.startswith("declarai.")
        by_internal = {spec.internal_name: spec for spec in specs}
        assert "get_data_dictionary" in by_internal
        schema = by_internal["get_data_dictionary"].input_schema
        assert schema["properties"]["file_id"]["type"] == "integer"
        assert schema["required"][0] == "file_id"

    def test_action_specs_track_existing_dispatcher(self):
        from ai_assistant.action_executor import HANDLERS
        from ai_assistant.mcp_server.registry import get_action_specs

        spec_names = [spec.action_type for spec in get_action_specs()]
        assert spec_names == list(HANDLERS.keys())


@pytest.mark.unit
class TestMcpActionHelpers:
    def test_prepare_action_returns_reviewable_action_block(self, monkeypatch):
        monkeypatch.delenv("DECLARAI_MCP_SCOPES", raising=False)
        from ai_assistant.mcp_server.actions import prepare_action

        result = prepare_action(
            42,
            "update_notes",
            {"action": "add", "position": "after_sfs", "content": "Review note"},
        )

        assert result["status"] == "prepared"
        assert result["file_id"] == 42
        assert result["action_type"] == "update_notes"
        assert result["requires_approval"] is True
        assert result["side_effects"] is False
        assert "<<<ACTION:update_notes>>>" in result["action_block"]
        assert "<<<END_ACTION>>>" in result["action_block"]

    def test_prepare_action_rejects_unknown_action(self, monkeypatch):
        monkeypatch.delenv("DECLARAI_MCP_SCOPES", raising=False)
        from ai_assistant.mcp_server.actions import prepare_action

        with pytest.raises(ValueError, match="Unknown DeclarAI action type"):
            prepare_action(42, "not_real", {})

    def test_direct_action_is_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("DECLARAI_MCP_ENABLE_DIRECT_ACTIONS", raising=False)
        from ai_assistant.mcp_server.actions import execute_direct_action

        with pytest.raises(PermissionError, match="Direct MCP action execution is disabled"):
            execute_direct_action(
                42,
                "update_notes",
                {"action": "add"},
                approval_id="approval-1",
            )

    def test_direct_action_requires_scope_and_approval(self, monkeypatch):
        monkeypatch.setenv("DECLARAI_MCP_ENABLE_DIRECT_ACTIONS", "true")
        monkeypatch.setenv("DECLARAI_MCP_SCOPES", "declarai.pipeline.read")
        from ai_assistant.mcp_server.actions import execute_direct_action

        with pytest.raises(PermissionError, match="declarai.notes.write"):
            execute_direct_action(
                42,
                "update_notes",
                {"action": "add"},
                approval_id="approval-1",
            )

        monkeypatch.setenv("DECLARAI_MCP_SCOPES", "declarai.notes.write")
        with pytest.raises(PermissionError, match="requires approval_id"):
            execute_direct_action(42, "update_notes", {"action": "add"}, approval_id="")

    def test_direct_action_dispatches_when_enabled(self, monkeypatch):
        monkeypatch.setenv("DECLARAI_MCP_ENABLE_DIRECT_ACTIONS", "true")
        monkeypatch.setenv("DECLARAI_MCP_SCOPES", "declarai.notes.write")
        calls = []

        from ai_assistant.mcp_server import actions

        def fake_dispatch(file_id, action_type, payload, parent_span_id):
            calls.append((file_id, action_type, payload, parent_span_id))
            return {"status": "success", "action_type": action_type}

        monkeypatch.setattr(actions, "_dispatch_action", fake_dispatch)
        result = actions.execute_direct_action(
            42,
            "update_notes",
            {"action": "add"},
            approval_id="approval-1",
            parent_span_id="span-1",
        )

        assert result["status"] == "executed"
        assert result["approval_id"] == "approval-1"
        assert result["result"]["status"] == "success"
        assert calls == [(42, "update_notes", {"action": "add"}, "span-1")]


@pytest.mark.unit
class TestMcpServer:
    def test_create_server_registers_read_and_prepare_tools_by_default(self):
        pytest.importorskip("mcp")
        from ai_assistant.mcp_server.server import create_mcp_server

        mcp = create_mcp_server(include_direct_actions=False)
        tools = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in tools}

        assert "declarai.get_data_dictionary" in names
        assert "declarai.prepare.start_sfs" in names
        assert "declarai.action.start_sfs" not in names

    def test_prepare_tool_can_be_invoked_through_fastmcp(self, monkeypatch):
        pytest.importorskip("mcp")
        monkeypatch.delenv("DECLARAI_MCP_SCOPES", raising=False)
        from ai_assistant.mcp_server.server import create_mcp_server

        mcp = create_mcp_server(include_direct_actions=False)
        _, structured = asyncio.run(
            mcp.call_tool(
                "declarai.prepare.update_notes",
                {
                    "file_id": 42,
                    "payload": {"action": "add", "content": "Review note"},
                },
            )
        )

        assert structured["status"] == "prepared"
        assert structured["action_type"] == "update_notes"
        assert structured["side_effects"] is False

    def test_create_server_can_register_direct_actions(self, monkeypatch):
        pytest.importorskip("mcp")
        monkeypatch.setenv("DECLARAI_MCP_ENABLE_DIRECT_ACTIONS", "true")
        from ai_assistant.mcp_server.server import create_mcp_server

        mcp = create_mcp_server(include_direct_actions=True)
        tools = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in tools}

        assert "declarai.action.update_notes" in names

    def test_direct_actions_flag_still_requires_env_gate(self, monkeypatch):
        pytest.importorskip("mcp")
        monkeypatch.delenv("DECLARAI_MCP_ENABLE_DIRECT_ACTIONS", raising=False)
        from ai_assistant.mcp_server.server import create_mcp_server

        mcp = create_mcp_server(include_direct_actions=True)
        tools = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in tools}

        assert "declarai.action.update_notes" not in names
