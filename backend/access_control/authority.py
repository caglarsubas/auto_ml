"""Fail-closed authorization around local MCP reads and proposals."""
import hashlib
import json
import os
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.utils import timezone

from access_control.models import MCPAccessEvent, MCPDatasetGrant


class AccessDenied(PermissionError):
    def __init__(self, code, grant=None, actor=None):
        self.code = code
        self.grant = grant
        self.actor = actor
        super().__init__(code)


def configured_actor():
    value = os.environ.get('DECLARAI_MCP_ACTOR_USER_ID', '')
    if not value.isdecimal() or not 0 < int(value) <= 2**63 - 1:
        raise AccessDenied('mcp_actor_identity_required')
    try:
        actor = get_user_model().objects.get(pk=int(value))
    except get_user_model().DoesNotExist:
        raise AccessDenied('mcp_actor_identity_unavailable') from None
    if not actor.is_active:
        raise AccessDenied('mcp_actor_identity_unavailable', actor=actor)
    return actor


def actor_snapshot(actor):
    return {'id': actor.pk, 'username': actor.get_username()} if actor else {}


def grant_snapshot(grant):
    return {'id': str(grant.pk), 'actor_id': grant.actor_id, 'dataset_id': grant.dataset_id,
        'revision': str(grant.revision), 'role': grant.role,
        'active': grant.active, 'expires_at': grant.expires_at.isoformat() if grant.expires_at else None} if grant else {}


def _grant(actor, file_id, operation):
    grant = MCPDatasetGrant.objects.filter(actor=actor, dataset_id=file_id).first()
    if not grant or not grant.active or (grant.expires_at and grant.expires_at <= timezone.now()):
        raise AccessDenied('mcp_dataset_access_denied', grant)
    if grant.role not in ('read', 'prepare') or (operation in ('prepare_action', 'direct_action') and grant.role != 'prepare'):
        raise AccessDenied('mcp_dataset_role_denied', grant)
    return grant


def _finish(event, outcome, reason=''):
    try:
        updated = MCPAccessEvent.objects.filter(pk=event.pk, outcome='started').update(
            outcome=outcome, reason_code=reason, finished_at=timezone.now())
        if updated != 1:
            raise AccessDenied('mcp_access_audit_unavailable')
    except AccessDenied:
        raise
    except Exception as exc:
        raise AccessDenied('mcp_access_audit_unavailable') from exc


@contextmanager
def authorized_access(file_id, operation, tool_name, scope, arguments=None):
    """No data access before reservation; recheck authority before returning output."""
    from ai_assistant.mcp_server.auth import require_scope
    actor, grant, failure, arguments_digest = None, None, None, ''
    valid_id = type(file_id) is int and 0 < file_id <= 2**63 - 1
    try:
        actor = configured_actor()
        require_scope(scope)
        if operation != 'catalog':
            if not valid_id:
                raise AccessDenied('mcp_dataset_identifier_invalid')
            grant = _grant(actor, file_id, operation)
        arguments_digest = hashlib.sha256(json.dumps(arguments or {}, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    except AccessDenied as exc:
        failure = exc
        grant = exc.grant
        actor = exc.actor or actor
    except PermissionError:
        failure = AccessDenied('mcp_process_scope_denied')
    except (TypeError, ValueError):
        failure = AccessDenied('mcp_arguments_invalid')
    except Exception as exc:
        raise AccessDenied('mcp_authority_unavailable') from exc
    try:
        event = MCPAccessEvent.objects.create(actor=actor, grant=grant,
            actor_snapshot=actor_snapshot(actor), grant_snapshot=grant_snapshot(grant),
            file_id=file_id if valid_id else None, operation=operation, tool_name=tool_name,
            required_scope=scope, arguments_sha256=arguments_digest,
            outcome='denied' if failure else 'started',
            reason_code=failure.code if failure else '', finished_at=timezone.now() if failure else None)
    except Exception as exc:
        raise AccessDenied('mcp_access_audit_unavailable') from exc
    if failure:
        raise failure
    receipt = {'access_event_id': str(event.pk), 'actor': actor_snapshot(actor),
        'file_id': file_id, 'grant': grant_snapshot(grant),
        'authority_source': 'stdio_installation_actor'}
    try:
        yield receipt
    except Exception as exc:
        _finish(event, 'failed', exc.code if isinstance(exc, AccessDenied) else 'mcp_tool_failed')
        raise
    try:
        current_actor = configured_actor()
        require_scope(scope)
        if current_actor.pk != actor.pk:
            raise AccessDenied('mcp_authority_changed_during_access')
        if grant:
            current = _grant(current_actor, file_id, operation)
            if current.revision != grant.revision:
                raise AccessDenied('mcp_authority_changed_during_access')
    except Exception as exc:
        _finish(event, 'withheld', 'mcp_authority_changed_during_access')
        raise AccessDenied('mcp_authority_changed_during_access') from exc
    _finish(event, 'completed')
