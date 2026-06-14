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

    def test_catalog_documents_prometa_scope_and_guardrail_binding(self):
        from ai_assistant.mcp_server.registry import build_tool_catalog

        catalog = build_tool_catalog(include_direct_actions=True)
        by_name = {tool["name"]: tool for tool in catalog["tools"]}

        assert catalog["catalog_version"] == "declarai-mcp-tools-v1"
        assert by_name["declarai.get_mcp_tool_catalog"]["required_scopes"] == [
            "declarai.pipeline.read"
        ]
        assert by_name["declarai.get_data_dictionary"]["required_scopes"] == [
            "declarai.pipeline.read"
        ]
        assert by_name["declarai.prepare.execute_code"]["required_scopes"] == [
            "declarai.action.prepare"
        ]
        assert by_name["declarai.prepare.execute_code"]["guardrails_required"] == [
            "review_action_block"
        ]
        direct_execute = by_name["declarai.action.execute_code"]
        assert direct_execute["required_scopes"] == ["declarai.dataset.write"]
        assert direct_execute["destructive"] is True
        assert direct_execute["guardrails_required"] == [
            "human_approval",
            "risk_gate",
            "dataset_backup",
        ]


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

    def test_prepare_action_stamps_mcp_span_attributes(self, monkeypatch):
        monkeypatch.delenv("DECLARAI_MCP_SCOPES", raising=False)
        from ai_assistant.mcp_server import actions

        stamped = []
        monkeypatch.setattr(
            actions,
            "stamp_mcp_context",
            lambda **kwargs: stamped.append(kwargs),
        )

        actions.prepare_action(
            42,
            "update_notes",
            {"action": "add", "content": "Review note"},
        )

        assert stamped[0]["operation"] == "prepare_action"
        assert stamped[0]["tool_name"] == "declarai.prepare.update_notes"
        assert stamped[0]["file_id"] == 42
        assert stamped[0]["required_scopes"] == ["declarai.action.prepare"]
        assert stamped[-1]["ok"] is True


@pytest.mark.unit
class TestMcpServer:
    def test_create_server_registers_read_and_prepare_tools_by_default(self):
        pytest.importorskip("mcp")
        from ai_assistant.mcp_server.server import create_mcp_server

        mcp = create_mcp_server(include_direct_actions=False)
        tools = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in tools}

        assert "declarai.get_mcp_tool_catalog" in names
        assert "declarai.get_data_dictionary" in names
        assert "declarai.prepare.start_sfs" in names
        assert "declarai.action.start_sfs" not in names

        by_name = {tool.name: tool for tool in tools}
        assert by_name["declarai.get_data_dictionary"].meta[
            "declarai.required_scopes"
        ] == ["declarai.pipeline.read"]
        assert by_name["declarai.prepare.start_sfs"].meta[
            "declarai.guardrails_required"
        ] == ["review_action_block"]

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

    def test_catalog_tool_can_be_invoked_through_fastmcp(self, monkeypatch):
        pytest.importorskip("mcp")
        monkeypatch.delenv("DECLARAI_MCP_SCOPES", raising=False)
        from ai_assistant.mcp_server.server import create_mcp_server

        mcp = create_mcp_server(include_direct_actions=False)
        _, structured = asyncio.run(
            mcp.call_tool("declarai.get_mcp_tool_catalog", {})
        )
        by_name = {tool["name"]: tool for tool in structured["tools"]}

        assert structured["direct_actions_registered"] is False
        assert "declarai.action.update_notes" not in by_name
        assert by_name["declarai.prepare.update_notes"]["target_action_risk"] == "low"

    def test_create_server_can_register_direct_actions(self, monkeypatch):
        pytest.importorskip("mcp")
        monkeypatch.setenv("DECLARAI_MCP_ENABLE_DIRECT_ACTIONS", "true")
        from ai_assistant.mcp_server.server import create_mcp_server

        mcp = create_mcp_server(include_direct_actions=True)
        tools = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in tools}

        assert "declarai.action.update_notes" in names

        by_name = {tool.name: tool for tool in tools}
        update_notes = by_name["declarai.action.update_notes"]
        execute_code = by_name["declarai.action.execute_code"]
        assert update_notes.annotations.destructiveHint is False
        assert update_notes.meta["declarai.required_scopes"] == ["declarai.notes.write"]
        assert execute_code.annotations.destructiveHint is True
        assert execute_code.meta["declarai.guardrails_required"] == [
            "human_approval",
            "risk_gate",
            "dataset_backup",
        ]

    def test_direct_actions_flag_still_requires_env_gate(self, monkeypatch):
        pytest.importorskip("mcp")
        monkeypatch.delenv("DECLARAI_MCP_ENABLE_DIRECT_ACTIONS", raising=False)
        from ai_assistant.mcp_server.server import create_mcp_server

        mcp = create_mcp_server(include_direct_actions=True)
        tools = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in tools}

        assert "declarai.action.update_notes" not in names
