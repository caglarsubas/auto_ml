"""Real actor/grant/audit boundary; no permission monkeypatch for MCP entrypoints."""
import asyncio
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command, CommandError
from django.utils import timezone

from access_control.authority import authorized_access
from access_control.models import MCPAccessEvent, MCPDatasetGrant
from ai_assistant.mcp_server import actions, auth, server

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


def read(file_id=42):
    return server._run_read_tool(file_id, 'declarai.get_data_dictionary', 'get_data_dictionary', {})


@pytest.mark.parametrize('state,code', [('missing', 'identity_required'), ('invalid', 'identity_required'),
    ('deleted', 'identity_unavailable'), ('inactive', 'identity_unavailable')])
def test_missing_or_inactive_actor_blocks_before_dispatch(mcp_identity, monkeypatch, state, code):
    actor, _, _ = mcp_identity
    if state == 'missing':
        monkeypatch.delenv('DECLARAI_MCP_ACTOR_USER_ID')
    elif state == 'invalid':
        monkeypatch.setenv('DECLARAI_MCP_ACTOR_USER_ID', 'not-an-actor')
    elif state == 'deleted':
        actor.delete()
    else:
        actor.is_active = False
        actor.save()
    def forbidden(*args):
        raise AssertionError('Customer data cannot dispatch before authorization')
    monkeypatch.setattr('ai_assistant.tool_executor.execute_tool_call', forbidden)
    with pytest.raises(PermissionError, match=code):
        read()
    event = MCPAccessEvent.objects.get()
    assert event.outcome == 'denied'
    if state == 'inactive':
        assert event.actor_id == actor.pk and event.actor_snapshot['username'] == actor.username


@pytest.mark.parametrize('state', ['other_dataset', 'revoked', 'expired', 'missing_grant', 'scope_denied'])
def test_ungranted_expired_revoked_and_process_scope_denials(mcp_identity, monkeypatch, state):
    _, _, grant = mcp_identity
    file_id = 42
    if state == 'other_dataset':
        file_id = 999
    elif state == 'revoked':
        grant.active = False
        grant.save()
    elif state == 'expired':
        grant.expires_at = timezone.now() - timedelta(seconds=1)
        grant.save()
    elif state == 'missing_grant':
        grant.delete()
    else:
        monkeypatch.setenv('DECLARAI_MCP_SCOPES', 'declarai.action.prepare')
    calls = []
    monkeypatch.setattr('ai_assistant.tool_executor.execute_tool_call', lambda *a: calls.append(a))
    with pytest.raises(PermissionError):
        read(file_id)
    assert not calls
    assert MCPAccessEvent.objects.get().outcome == 'denied'


@pytest.mark.parametrize('value', [True, -1, 0, 1.5, '42', 2**64])
def test_invalid_identifiers_cannot_dispatch(mcp_identity, value):
    with pytest.raises(PermissionError, match='identifier_invalid'):
        read(value)
    assert MCPAccessEvent.objects.get().outcome == 'denied'


def test_read_only_actor_can_read_but_cannot_prepare(mcp_identity, monkeypatch):
    _, _, grant = mcp_identity
    grant.role = 'read'
    grant.save()
    monkeypatch.setattr('ai_assistant.tool_executor.execute_tool_call', lambda *a: 'allowed data')
    assert read() == 'allowed data'
    with pytest.raises(PermissionError, match='role_denied'):
        actions.prepare_action(42, 'update_notes', {'content': 'candidate'})
    assert list(MCPAccessEvent.objects.order_by('started_at').values_list('outcome', flat=True)) == ['completed', 'denied']


def test_preparation_retains_receipt_and_no_execution_authority(mcp_identity):
    actor, _, grant = mcp_identity
    result = actions.prepare_action(42, 'update_notes', {'content': 'private-proposal-text'})
    assert result['execution_available'] is False
    receipt = result['access_receipt']
    assert receipt['actor']['id'] == actor.pk
    assert receipt['grant']['revision'] == str(grant.revision)
    event = MCPAccessEvent.objects.get(pk=receipt['access_event_id'])
    assert event.outcome == 'completed'
    assert event.arguments_sha256
    assert 'private-proposal-text' not in str(event.__dict__)
    actor_id = actor.pk
    actor.delete()
    event.refresh_from_db()
    assert event.actor is None and event.grant is None
    assert event.actor_snapshot['id'] == actor_id
    assert event.grant_snapshot['revision'] == str(grant.revision)


def test_audit_reservation_failure_prevents_read(mcp_identity, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(MCPAccessEvent.objects, 'create', fail)
    calls = []
    monkeypatch.setattr('ai_assistant.tool_executor.execute_tool_call', lambda *a: calls.append(a))
    with pytest.raises(PermissionError, match='audit_unavailable'):
        read()
    assert not calls


def test_audit_completion_failure_withholds_output(mcp_identity, monkeypatch):
    import access_control.authority as authority
    original = authority._finish
    def fail(event, outcome, reason=''):
        if outcome == 'completed':
            raise PermissionError('mcp_access_audit_unavailable')
        return original(event, outcome, reason)
    monkeypatch.setattr(authority, '_finish', fail)
    monkeypatch.setattr('ai_assistant.tool_executor.execute_tool_call', lambda *a: 'must not return')
    with pytest.raises(PermissionError, match='audit_unavailable'):
        read()
    assert MCPAccessEvent.objects.get().outcome == 'started'


@pytest.mark.parametrize('change', ['revoke', 'role', 'expire', 'deactivate_actor', 'scope'])
def test_authority_changes_during_read_withhold_output(mcp_identity, monkeypatch, change):
    actor, _, grant = mcp_identity
    def dispatch(*args):
        assert MCPAccessEvent.objects.get().outcome == 'started'
        if change == 'scope':
            monkeypatch.setenv('DECLARAI_MCP_SCOPES', 'declarai.action.prepare')
        elif change == 'deactivate_actor':
            actor.is_active = False
            actor.save()
        else:
            if change == 'revoke':
                grant.active = False
            elif change == 'role':
                grant.role = 'read'
            else:
                grant.expires_at = timezone.now() - timedelta(seconds=1)
            grant.save()
        return 'withhold this data'
    monkeypatch.setattr('ai_assistant.tool_executor.execute_tool_call', dispatch)
    with pytest.raises(PermissionError, match='changed_during_access'):
        read()
    assert MCPAccessEvent.objects.get().outcome == 'withheld'


@pytest.mark.parametrize('approval_id', ['', 'fabricated-id', 'changed-code-id'])
def test_unverified_approvals_and_legacy_flags_cannot_execute(mcp_identity, monkeypatch, approval_id):
    monkeypatch.setenv('DECLARAI_MCP_ENABLE_DIRECT_ACTIONS', 'true')
    monkeypatch.setenv('DECLARAI_MCP_REQUIRE_APPROVAL', 'false')
    monkeypatch.setenv('DECLARAI_MCP_SCOPES', 'declarai.notes.write')
    with pytest.raises(PermissionError, match='exact_approval_unavailable'):
        actions.execute_direct_action(42, 'update_notes', {}, approval_id=approval_id)
    assert auth.direct_actions_enabled() is False
    assert MCPAccessEvent.objects.get().outcome == 'failed'


def test_trusted_cli_grant_revoke_and_audit_are_atomic(mcp_identity, monkeypatch):
    actor, dataset, grant = mcp_identity
    original_revision = grant.revision
    out = StringIO()
    call_command('mcp_dataset_grant', '--actor', actor.username, '--file-id', str(dataset.pk), '--role', 'read', stdout=out)
    grant.refresh_from_db()
    assert grant.role == 'read' and grant.revision != original_revision
    assert MCPAccessEvent.objects.get().authority_source == 'trusted_local_cli'
    call_command('mcp_dataset_grant', '--actor', actor.username, '--file-id', str(dataset.pk), '--revoke', stdout=out)
    grant.refresh_from_db()
    assert not grant.active
    def fail(**kwargs): raise RuntimeError('audit unavailable')
    monkeypatch.setattr(MCPAccessEvent.objects, 'create', fail)
    with pytest.raises(RuntimeError):
        call_command('mcp_dataset_grant', '--actor', actor.username, '--file-id', str(dataset.pk), '--role', 'prepare', stdout=out)
    grant.refresh_from_db()
    assert not grant.active  # grant mutation rolled back with failed audit


@pytest.mark.parametrize('expiry', ['not-a-date', '2020-01-01T00:00:00Z', '2099-01-01T00:00:00'])
def test_cli_rejects_invalid_expiries_without_grant_changes(mcp_identity, expiry):
    actor, dataset, grant = mcp_identity
    with pytest.raises(CommandError):
        call_command('mcp_dataset_grant', '--actor', actor.username, '--file-id', str(dataset.pk), '--role', 'read', '--expires-at', expiry)
    grant.refresh_from_db()
    assert grant.role == 'prepare'
    assert not MCPAccessEvent.objects.exists()


@pytest.mark.parametrize('transport', ['streamable-http', 'sse'])
def test_network_transports_are_blocked_before_binding(mcp_identity, transport):
    mcp = server.create_mcp_server()
    with pytest.raises(PermissionError, match='http_identity_unavailable'):
        mcp.run(transport=transport)
    with pytest.raises(PermissionError, match='http_identity_unavailable'):
        (mcp.streamable_http_app if transport == 'streamable-http' else mcp.sse_app)()
    with pytest.raises(PermissionError, match='http_identity_unavailable'):
        asyncio.run((mcp.run_streamable_http_async if transport == 'streamable-http' else mcp.run_sse_async)())


def test_management_network_transport_is_closed_even_with_actor(mcp_identity):
    with pytest.raises(CommandError, match='http_identity_unavailable'):
        call_command('run_mcp_server', '--transport', 'streamable-http')


@pytest.mark.parametrize('superuser', [False, True])
def test_admin_grant_and_audit_http_permissions(mcp_identity, client, superuser):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    actor, dataset, grant = mcp_identity
    admin_actor = get_user_model().objects.create_user(username='grant-admin', password='test-only-password',
        is_staff=True, is_superuser=superuser)
    # Even staff explicitly granted model permissions cannot administer MCP authority.
    admin_actor.user_permissions.set(Permission.objects.filter(content_type__app_label='access_control'))
    assert client.login(username=admin_actor.username, password='test-only-password')
    path = f'/admin/access_control/mcpdatasetgrant/{grant.pk}/change/'
    response = client.get(path)
    assert response.status_code == (200 if superuser else 403)
    old_revision = grant.revision
    response = client.post(path, {'actor': actor.pk, 'dataset': dataset.pk, 'role': 'read',
        'active': 'on', 'expires_at_0': '', 'expires_at_1': '', '_save': 'Save'})
    assert response.status_code == (302 if superuser else 403)
    grant.refresh_from_db()
    assert (grant.revision != old_revision) is superuser
    assert grant.role == ('read' if superuser else 'prepare')
    if superuser:
        event = MCPAccessEvent.objects.get()
        assert event.authority_source == 'authenticated_admin'
        assert event.actor_id == admin_actor.pk
        assert event.grant_snapshot['revision'] == str(grant.revision)
        assert client.get(f'/admin/access_control/mcpaccessevent/{event.pk}/change/').status_code == 200
        assert client.post(f'/admin/access_control/mcpaccessevent/{event.pk}/change/', {'outcome': 'erased'}).status_code == 403
        event.refresh_from_db()
        assert event.outcome == 'completed'
    else:
        assert not MCPAccessEvent.objects.exists()
    assert client.post(f'/admin/access_control/mcpdatasetgrant/{grant.pk}/delete/', {'post': 'yes'}).status_code == 403
    assert MCPDatasetGrant.objects.filter(pk=grant.pk).exists()


def test_admin_mutation_rolls_back_when_audit_write_fails(mcp_identity, monkeypatch):
    from django.contrib import admin
    from django.test import RequestFactory
    actor, _, grant = mcp_identity
    request = RequestFactory().post('/admin/')
    request.user = actor
    grant.active = False
    def fail(**kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(MCPAccessEvent.objects, 'create', fail)
    with pytest.raises(RuntimeError):
        admin.site._registry[MCPDatasetGrant].save_model(request, grant, None, True)
    grant.refresh_from_db()
    assert grant.active
