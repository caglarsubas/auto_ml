#!/usr/bin/env python3
"""Exercise the actual MCP protocol only in an explicitly disposable installation."""
import asyncio
import json
import os
import subprocess
import sys
import uuid
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get('DECLARAI_TEST_INSTALLATION') != '1':
        raise SystemExit('Set DECLARAI_TEST_INSTALLATION=1 only for a disposable test database.')
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    import django
    django.setup()
    from asgiref.sync import sync_to_async
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from access_control.models import MCPAccessEvent
    from ai_assistant.cache import cache_put, cache_delete, ARTIFACT_DATA_DICTIONARY
    from declaration.models import Declaration
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    token = uuid.uuid4().hex
    actor = get_user_model().objects.create_user(username=f'mcp-qualification-{token}', password=None)
    actor_id = actor.pk
    datasets = []
    summary = {}
    try:
        for kind in ['granted', 'private']:
            dataset = Declaration.objects.create(name=f'mcp-{kind}-{token}', original_name='synthetic.csv',
                file=f'data_files/mcp-qualification-{token}-{kind}.csv')
            datasets.append(dataset)
            assert cache_put(dataset.pk, ARTIFACT_DATA_DICTIONARY,
                [{'Feature_Name': f'{kind}-sentinel-{token}', 'Feature_Description': 'Synthetic MCP qualification'}])
        allowed, private = datasets
        call_command('mcp_dataset_grant', '--actor', actor.username, '--file-id', str(allowed.pk),
            '--role', 'read', stdout=StringIO())
        env = {**os.environ, 'DECLARAI_MCP_ACTOR_USER_ID': str(actor.pk),
            'DECLARAI_MCP_SCOPES': 'declarai.pipeline.read,declarai.action.prepare',
            'DECLARAI_MCP_TRANSPORT': 'stdio', 'DECLARAI_MCP_ENABLE_DIRECT_ACTIONS': 'true',
            'DECLARAI_MCP_REQUIRE_APPROVAL': 'false', 'PROMETA_DISABLE': '1'}
        parameters = StdioServerParameters(command=sys.executable,
            args=[str(ROOT / 'backend/manage.py'), 'run_mcp_server'], env=env)

        def text(result):
            return '\n'.join(item.text for item in result.content if hasattr(item, 'text'))

        async def exercise():
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    assert 'declarai.prepare.update_notes' in names
                    assert not any(name.startswith('declarai.action.') for name in names)
                    catalog = await session.call_tool('declarai.get_mcp_tool_catalog', {})
                    assert not catalog.isError
                    catalog_data = json.loads(text(catalog))
                    assert catalog_data['direct_execution_available'] is False
                    assert catalog_data['access_receipt']['actor']['id'] == actor_id
                    read = await session.call_tool('declarai.get_data_dictionary', {'file_id': allowed.pk})
                    assert not read.isError and f'granted-sentinel-{token}' in text(read)
                    denied = await session.call_tool('declarai.get_data_dictionary', {'file_id': private.pk})
                    assert denied.isError and 'mcp_dataset_access_denied' in text(denied)
                    assert f'private-sentinel-{token}' not in text(denied)
                    proposal_args = {'file_id': allowed.pk, 'payload': {'content': 'synthetic candidate'}}
                    denied = await session.call_tool('declarai.prepare.update_notes', proposal_args)
                    assert denied.isError and 'mcp_dataset_role_denied' in text(denied)
                    await sync_to_async(call_command)('mcp_dataset_grant', '--actor', actor.username,
                        '--file-id', str(allowed.pk), '--role', 'prepare', stdout=StringIO())
                    proposal = await session.call_tool('declarai.prepare.update_notes', proposal_args)
                    assert not proposal.isError
                    prepared = json.loads(text(proposal))
                    assert prepared['execution_available'] is False
                    assert prepared['access_receipt']['grant']['role'] == 'prepare'
                    await sync_to_async(call_command)('mcp_dataset_grant', '--actor', actor.username,
                        '--file-id', str(allowed.pk), '--revoke', stdout=StringIO())
                    denied = await session.call_tool('declarai.get_data_dictionary', {'file_id': allowed.pk})
                    assert denied.isError and 'mcp_dataset_access_denied' in text(denied)
                    actor.is_active = False
                    await sync_to_async(actor.save)()
                    denied = await session.call_tool('declarai.get_mcp_tool_catalog', {})
                    assert denied.isError and 'mcp_actor_identity_unavailable' in text(denied)
                    return len(names)

        tool_count = asyncio.run(exercise())
        for arguments, code in [(['--transport', 'streamable-http'], 'mcp_http_identity_unavailable'),
                                (['--direct-actions'], 'mcp_actor_identity_unavailable')]:
            result = subprocess.run([sys.executable, str(ROOT / 'backend/manage.py'), 'run_mcp_server', *arguments],
                env=env, capture_output=True, text=True, timeout=30)
            assert result.returncode != 0 and code in result.stderr
        # Test direct-action startup with a valid actor, even with both legacy flags.
        actor.is_active = True
        actor.save()
        result = subprocess.run([sys.executable, str(ROOT / 'backend/manage.py'), 'run_mcp_server', '--direct-actions'],
            env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode != 0 and 'mcp_exact_approval_unavailable' in result.stderr
        events = list(MCPAccessEvent.objects.filter(actor_snapshot__id=actor_id))
        outcomes = {value: sum(event.outcome == value for event in events) for value in ['completed', 'denied']}
        assert outcomes == {'completed': 6, 'denied': 4} and len(events) == 10
        assert all(event.finished_at for event in events)
        assert all('synthetic candidate' not in str(event.__dict__) for event in events)
        summary = {'status': 'passed', 'transport': 'actual_sdk_stdio', 'tools_registered': tool_count,
            'access_events': len(events), 'outcomes': outcomes, 'network_transport': 'blocked',
            'direct_execution': 'blocked', 'fixture_data': 'synthetic', 'cleanup': 'fixtures_removed_audit_retained'}
    finally:
        for dataset in datasets:
            cache_delete(dataset.pk, ARTIFACT_DATA_DICTIONARY)
            dataset.delete()
        actor.delete()
    assert MCPAccessEvent.objects.filter(actor_snapshot__id=actor_id, actor__isnull=True, grant__isnull=True).count() == 10
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
