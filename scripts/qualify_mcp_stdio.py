#!/usr/bin/env python3
"""Exercise the actual MCP protocol only in an explicitly disposable installation."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import uuid
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get("DECLARAI_TEST_INSTALLATION") != "1":
        raise SystemExit(
            "Set DECLARAI_TEST_INSTALLATION=1 only for a disposable test database."
        )
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django

    django.setup()
    from asgiref.sync import sync_to_async
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from access_control.models import AssistantActionApproval, MCPAccessEvent
    from ai_assistant.cache import cache_put, cache_delete, ARTIFACT_DATA_DICTIONARY
    from declaration.models import Declaration
    from execution_jobs.models import NativeJob
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    token = uuid.uuid4().hex
    actor = get_user_model().objects.create_user(
        username=f"mcp-qualification-{token}", password=None
    )
    actor_id = actor.pk
    datasets = []
    from access_control import projects

    project_id = None
    if projects.governed():
        bootstrap, _ = projects.operator_change(
            {
                "operation": "create",
                "name": "Disposable MCP project",
                "user": actor.username,
            },
            uuid.uuid4(),
            "disposable-mcp-fixture",
        )
        project_id = str(bootstrap.project_id)
        projects.operator_change(
            {
                "operation": "member",
                "project_id": project_id,
                "user": actor.username,
                "role": "developer",
            },
            uuid.uuid4(),
            "disposable-mcp-fixture",
        )
    summary = {}
    try:
        for kind in ["granted", "private"]:
            dataset = Declaration.objects.create(
                name=f"mcp-{kind}-{token}",
                original_name="synthetic.csv",
                file=f"data_files/mcp-qualification-{token}-{kind}.csv",
            )
            datasets.append(dataset)
            if project_id:
                projects.bind_dataset(
                    dataset, project_id, source="disposable_mcp_fixture"
                )
            assert cache_put(
                dataset.pk,
                ARTIFACT_DATA_DICTIONARY,
                [
                    {
                        "Feature_Name": f"{kind}-sentinel-{token}",
                        "Feature_Description": "Synthetic MCP qualification",
                    }
                ],
            )
        allowed, private = datasets
        call_command(
            "mcp_dataset_grant",
            "--actor",
            actor.username,
            "--file-id",
            str(allowed.pk),
            "--role",
            "read",
            stdout=StringIO(),
        )
        env = {
            **os.environ,
            "DECLARAI_MCP_ACTOR_USER_ID": str(actor.pk),
            "DECLARAI_MCP_SCOPES": "declarai.pipeline.read,declarai.action.prepare",
            "DECLARAI_MCP_TRANSPORT": "stdio",
            "DECLARAI_MCP_ENABLE_DIRECT_ACTIONS": "true",
            "DECLARAI_MCP_REQUIRE_APPROVAL": "false",
            "PROMETA_DISABLE": "1",
        }
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "backend/manage.py"), "run_mcp_server"],
            env=env,
        )

        def text(result):
            return "\n".join(
                item.text for item in result.content if hasattr(item, "text")
            )

        expert_marker = f"synthetic-expert-{token}"
        expert_payload = {"mode": "apply", "code": f"raise RuntimeError({expert_marker!r})"}
        guarded_proposals = {
            "declarai.prepare.execute_code": expert_payload,
            "declarai.prepare.start_modeling": {},
        }
        unavailable_tools = {
            "declarai.action.execute_code",
            "declarai.action.start_modeling",
            "declarai.action.approve_model",
            "declarai.get_reproduction_manifest",
            "declarai.export_expert_fitted_state",
        }

        async def qualify_unavailable_controls(session, names):
            assert set(guarded_proposals) <= names
            assert unavailable_tools.isdisjoint(names)
            for name, payload in guarded_proposals.items():
                result = await session.call_tool(name, {"file_id": allowed.pk, "payload": payload})
                assert not result.isError
                proposal = json.loads(text(result))
                assert proposal["status"] == "prepared"
                assert proposal["action_type"] == name.removeprefix("declarai.prepare.")
                assert proposal["requires_approval"] is True
                assert proposal["side_effects"] is False
                assert proposal["execution_available"] is False
                assert proposal["execution_blocker"] == "mcp_exact_approval_unavailable"
                assert proposal["access_receipt"]["actor"]["id"] == actor_id
                assert proposal["access_receipt"]["grant"]["role"] == "prepare"
            for name in sorted(unavailable_tools):
                refused = await session.call_tool(
                    name,
                    {
                        "file_id": allowed.pk,
                        "approval_id": str(uuid.uuid4()),
                        "payload": expert_payload,
                    },
                )
                assert refused.isError and "unknown tool" in text(refused).lower(), name
                assert expert_marker not in text(refused)

        async def exercise():
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    assert "declarai.prepare.update_notes" in names
                    assert not any(
                        name.startswith("declarai.action.") for name in names
                    )
                    catalog = await session.call_tool(
                        "declarai.get_mcp_tool_catalog", {}
                    )
                    assert not catalog.isError
                    catalog_data = json.loads(text(catalog))
                    assert catalog_data["direct_execution_available"] is False
                    assert catalog_data["access_receipt"]["actor"]["id"] == actor_id
                    read = await session.call_tool(
                        "declarai.get_data_dictionary", {"file_id": allowed.pk}
                    )
                    assert not read.isError and f"granted-sentinel-{token}" in text(
                        read
                    )
                    denied = await session.call_tool(
                        "declarai.get_data_dictionary", {"file_id": private.pk}
                    )
                    assert denied.isError and "mcp_dataset_access_denied" in text(
                        denied
                    )
                    assert f"private-sentinel-{token}" not in text(denied)
                    proposal_args = {
                        "file_id": allowed.pk,
                        "payload": {"content": "synthetic candidate"},
                    }
                    denied = await session.call_tool(
                        "declarai.prepare.update_notes", proposal_args
                    )
                    assert denied.isError and "mcp_dataset_role_denied" in text(denied)
                    await sync_to_async(call_command)(
                        "mcp_dataset_grant",
                        "--actor",
                        actor.username,
                        "--file-id",
                        str(allowed.pk),
                        "--role",
                        "prepare",
                        stdout=StringIO(),
                    )
                    proposal = await session.call_tool(
                        "declarai.prepare.update_notes", proposal_args
                    )
                    assert not proposal.isError
                    prepared = json.loads(text(proposal))
                    assert prepared["execution_available"] is False
                    assert prepared["access_receipt"]["grant"]["role"] == "prepare"
                    await qualify_unavailable_controls(session, names)
                    if project_id:
                        def role_change(role):
                            return projects.operator_change({'operation': 'member', 'project_id': project_id,
                                'user': actor.username, 'role': role}, uuid.uuid4(), 'disposable-mcp-fixture')
                        await sync_to_async(role_change)('none')
                        denied = await session.call_tool('declarai.get_data_dictionary', {'file_id': allowed.pk})
                        assert denied.isError and 'project_access_denied' in text(denied)
                        await sync_to_async(role_change)('reviewer')
                        read = await session.call_tool('declarai.get_data_dictionary', {'file_id': allowed.pk})
                        assert not read.isError and f'granted-sentinel-{token}' in text(read)
                        denied = await session.call_tool('declarai.prepare.update_notes', proposal_args)
                        assert denied.isError and 'project_access_denied' in text(denied)
                        await sync_to_async(role_change)('developer')
                        read = await session.call_tool('declarai.get_data_dictionary', {'file_id': allowed.pk})
                        assert not read.isError
                    await sync_to_async(call_command)(
                        "mcp_dataset_grant",
                        "--actor",
                        actor.username,
                        "--file-id",
                        str(allowed.pk),
                        "--revoke",
                        stdout=StringIO(),
                    )
                    denied = await session.call_tool(
                        "declarai.get_data_dictionary", {"file_id": allowed.pk}
                    )
                    assert denied.isError and "mcp_dataset_access_denied" in text(
                        denied
                    )
                    actor.is_active = False
                    await sync_to_async(actor.save)()
                    denied = await session.call_tool(
                        "declarai.get_mcp_tool_catalog", {}
                    )
                    assert denied.isError and "mcp_actor_identity_unavailable" in text(
                        denied
                    )
                    return len(names)

        tool_count = asyncio.run(exercise())
        for arguments, code in [
            (["--transport", "streamable-http"], "mcp_http_identity_unavailable"),
            (["--direct-actions"], "mcp_actor_identity_unavailable"),
        ]:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "backend/manage.py"),
                    "run_mcp_server",
                    *arguments,
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode != 0 and code in result.stderr
        # Test direct-action startup with a valid actor, even with both legacy flags.
        actor.is_active = True
        actor.save()
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "backend/manage.py"),
                "run_mcp_server",
                "--direct-actions",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            result.returncode != 0 and "mcp_exact_approval_unavailable" in result.stderr
        )
        events = list(MCPAccessEvent.objects.filter(actor_snapshot__id=actor_id))
        outcomes = {
            value: sum(event.outcome == value for event in events)
            for value in ["completed", "denied"]
        }
        expected = {"completed": 8, "denied": 6} if project_id else {"completed": 6, "denied": 4}
        expected["completed"] += len(guarded_proposals)
        expected_count = sum(expected.values())
        assert outcomes == expected and len(events) == expected_count
        assert all(event.finished_at for event in events)
        assert all("synthetic candidate" not in str(event.__dict__) and expert_marker not in str(event.__dict__)
                   for event in events)
        for name, payload in guarded_proposals.items():
            event, = [entry for entry in events if entry.tool_name == name]
            arguments = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
            assert event.arguments_sha256 == hashlib.sha256(arguments.encode()).hexdigest()
            assert event.outcome == "completed" and event.operation == "prepare_action"
            assert event.file_id == allowed.pk and event.grant_snapshot["role"] == "prepare"
        assert not AssistantActionApproval.objects.filter(file_id=allowed.pk).exists()
        assert not NativeJob.objects.filter(dataset_id=allowed.pk).exists()
        summary = {
            "status": "passed",
            "transport": "actual_sdk_stdio",
            "tools_registered": tool_count,
            "access_events": len(events),
            "outcomes": outcomes,
            "network_transport": "blocked",
            "direct_execution": "blocked",
            "private_threat_model_mcp_controls": {
                "schema": "declarai_mcp_non_bypass_v1",
                "status": "passed",
                "expert_and_training_proposals": "review_only",
                "unavailable_tools": sorted(unavailable_tools),
                "dispatch_and_job_store": "unchanged",
                "audit": "exact_digest_without_payload",
            },
            "fixture_data": "synthetic",
            "cleanup": "fixtures_removed_audit_retained",
        }
    finally:
        for dataset in datasets:
            cache_delete(dataset.pk, ARTIFACT_DATA_DICTIONARY)
            dataset.delete()
        actor.delete()
    assert (
        MCPAccessEvent.objects.filter(
            actor_snapshot__id=actor_id, actor__isnull=True, grant__isnull=True
        ).count()
        == expected_count
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
