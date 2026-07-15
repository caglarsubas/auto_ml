"""Unit tests - MCP auth helpers and management commands.

Covers ai_assistant/mcp_server/auth.py scope/approval gates plus the
declaration.fix_file_paths and ai_assistant.run_mcp_server management commands.
"""
from io import StringIO

import pytest


@pytest.mark.unit
class TestMcpAuthScopes:
    def test_default_scopes_when_env_unset(self, monkeypatch):
        from ai_assistant.mcp_server import auth
        monkeypatch.delenv('DECLARAI_MCP_SCOPES', raising=False)
        scopes = auth.configured_scopes()
        assert auth.SCOPE_PIPELINE_READ in scopes
        assert auth.SCOPE_ACTION_PREPARE in scopes

    def test_scopes_parsed_from_env(self, monkeypatch):
        from ai_assistant.mcp_server import auth
        monkeypatch.setenv('DECLARAI_MCP_SCOPES', ' a , b ,, c ')
        assert auth.configured_scopes() == {'a', 'b', 'c'}

    def test_require_scope_passes_when_granted(self, monkeypatch):
        from ai_assistant.mcp_server import auth
        monkeypatch.setenv('DECLARAI_MCP_SCOPES', auth.SCOPE_PIPELINE_READ)
        assert auth.require_scope(auth.SCOPE_PIPELINE_READ) is None

    def test_require_scope_raises_when_missing(self, monkeypatch):
        from ai_assistant.mcp_server import auth
        monkeypatch.setenv('DECLARAI_MCP_SCOPES', auth.SCOPE_PIPELINE_READ)
        with pytest.raises(PermissionError):
            auth.require_scope(auth.SCOPE_CONFIG_WRITE)


@pytest.mark.unit
class TestMcpDirectActionsGate:
    def test_direct_actions_disabled_by_default(self, monkeypatch):
        from ai_assistant.mcp_server import auth
        monkeypatch.delenv('DECLARAI_MCP_ENABLE_DIRECT_ACTIONS', raising=False)
        assert auth.direct_actions_enabled() is False
        with pytest.raises(PermissionError):
            auth.require_direct_actions_enabled()

    def test_direct_actions_enabled_via_env(self, monkeypatch):
        from ai_assistant.mcp_server import auth
        monkeypatch.setenv('DECLARAI_MCP_ENABLE_DIRECT_ACTIONS', 'true')
        assert auth.direct_actions_enabled() is True
        assert auth.require_direct_actions_enabled() is None


@pytest.mark.unit
class TestMcpApprovalGate:
    def test_approval_required_by_default(self, monkeypatch):
        from ai_assistant.mcp_server import auth
        monkeypatch.delenv('DECLARAI_MCP_REQUIRE_APPROVAL', raising=False)
        assert auth.approval_required() is True
        with pytest.raises(PermissionError):
            auth.require_approval('apply_config', approval_id=None)

    def test_approval_passes_with_id(self, monkeypatch):
        from ai_assistant.mcp_server import auth
        monkeypatch.setenv('DECLARAI_MCP_REQUIRE_APPROVAL', 'true')
        assert auth.require_approval('apply_config', approval_id='appr-123') is None

    def test_approval_disabled_via_env(self, monkeypatch):
        from ai_assistant.mcp_server import auth
        monkeypatch.setenv('DECLARAI_MCP_REQUIRE_APPROVAL', 'false')
        assert auth.approval_required() is False
        assert auth.require_approval('apply_config', approval_id=None) is None


@pytest.mark.unit
@pytest.mark.django_db
class TestFixFilePathsCommand:
    def test_runs_cleanly_with_empty_db(self, _use_tmp_media):
        from django.core.management import call_command
        out = StringIO()
        # No Declaration rows -> the command iterates nothing and exits 0.
        call_command('fix_file_paths', stdout=out)


@pytest.mark.unit
class TestRunMcpServerCommand:
    def test_wires_arguments_into_server(self, monkeypatch):
        from django.core.management import call_command
        import ai_assistant.management.commands.run_mcp_server as cmd_mod

        captured = {}

        class _FakeServer:
            def run(self, transport):
                captured['transport'] = transport

        def _fake_create(**kwargs):
            captured['kwargs'] = kwargs
            return _FakeServer()

        monkeypatch.setattr(cmd_mod, 'create_mcp_server', _fake_create)
        call_command('run_mcp_server', '--transport', 'stdio', '--port', '9123')

        assert captured['transport'] == 'stdio'
        assert captured['kwargs']['port'] == 9123
