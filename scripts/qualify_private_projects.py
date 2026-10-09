#!/usr/bin/env python3
"""Real private TLS project roles and cross-process retry receipts on synthetic data."""

import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main():
    if os.environ.get("DECLARAI_TEST_INSTALLATION") != "1":
        raise SystemExit("Requires an explicitly disposable installation.")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import connection
    from django.test import Client
    from access_control import projects
    from access_control.models import (
        ProjectMembership,
        ProjectAuthorityEvent,
        MCPDatasetGrant,
    )
    from access_control.authority import authorized_access, AccessDenied
    from ai_assistant.mcp_server.auth import SCOPE_PIPELINE_READ
    from declaration.models import Declaration

    assert (
        settings.DECLARAI_RUNTIME_PROFILE == "private"
        and connection.vendor == "postgresql"
    )
    if sys.argv[1:] == ["apply"]:
        event, replayed = projects.operator_change(
            {
                "operation": "member",
                "project_id": os.environ["DECLARAI_PROJECT_FIXTURE_ID"],
                "user": os.environ["DECLARAI_PROJECT_FIXTURE_USER"],
                "role": "none",
            },
            os.environ["DECLARAI_PROJECT_FIXTURE_REQUEST"],
            "disposable-project-fixture",
        )
        print(json.dumps({"id": str(event.pk), "replayed": replayed}))
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
        assert cursor.fetchone()[0]
    token = uuid.uuid4().hex
    users = {
        role: get_user_model().objects.create_user(
            username="project-" + role + "-" + token
        )
        for role in ["admin", "developer", "reviewer", "outsider"]
    }
    event, _ = projects.operator_change(
        {
            "operation": "create",
            "name": "Private project A",
            "user": users["admin"].username,
        },
        uuid.uuid4(),
        "disposable-project-fixture",
    )
    a = str(event.project_id)
    event, _ = projects.operator_change(
        {
            "operation": "create",
            "name": "Private project B",
            "user": users["outsider"].username,
        },
        uuid.uuid4(),
        "disposable-project-fixture",
    )
    b = str(event.project_id)
    for role in ["developer", "reviewer"]:
        projects.operator_change(
            {
                "operation": "member",
                "project_id": a,
                "user": users[role].username,
                "role": role,
            },
            uuid.uuid4(),
            "disposable-project-fixture",
        )
    files = []
    for name, project_id in [("A", a), ("B", b)]:
        relative = f"data_files/project-fixture-{token}-{name}.csv"
        path = Path(settings.MEDIA_ROOT) / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text("x,target\n1,0\n2,1\n")
        dataset = Declaration.objects.create(
            name=name, original_name=path.name, file=relative
        )
        projects.bind_dataset(dataset, project_id, source="disposable_project_fixture")
        files.append(dataset)
    request = {"secure": True, "HTTP_HOST": settings.ALLOWED_HOSTS[0]}
    clients = {}
    for role, user in users.items():
        client = Client()
        client.force_login(user)
        clients[role] = client
        rows = client.get("/api/declaration/", **request).json()
        assert (
            files[0].pk in [r["id"] for r in rows]
            if role != "outsider"
            else files[0].pk not in [r["id"] for r in rows]
        )
        assert client.get(
            f"/api/declaration/{files[1].pk}/", **request
        ).status_code == (200 if role == "outsider" else 403)
        result = client.post(
            "/api/pipeline/create/",
            json.dumps({"name": "role-" + role, "project_id": a}),
            content_type="application/json",
            **request,
        )
        assert result.status_code == (201 if role == "developer" else 403)
        assert (
            client.get("/api/auth/session/", **request).json()["authenticated"] is True
        )
    grant = MCPDatasetGrant.objects.create(
        actor=users["developer"], dataset=files[0], role="read"
    )
    os.environ["DECLARAI_MCP_ACTOR_USER_ID"] = str(users["developer"].pk)
    os.environ["DECLARAI_MCP_SCOPES"] = SCOPE_PIPELINE_READ
    with authorized_access(
        files[0].pk, "read", "private-project-fixture", SCOPE_PIPELINE_READ
    ):
        pass
    env = {
        **os.environ,
        "DECLARAI_PROJECT_FIXTURE_ID": a,
        "DECLARAI_PROJECT_FIXTURE_USER": users["developer"].username,
        "DECLARAI_PROJECT_FIXTURE_REQUEST": str(uuid.uuid4()),
    }

    def apply(_):
        result = subprocess.run(
            [sys.executable, __file__, "apply"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, "Private project change process failed."
        return json.loads(result.stdout)

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(apply, range(5)))
    assert sum(not r["replayed"] for r in results) == 1
    assert len({r["id"] for r in results}) == 1
    assert (
        ProjectAuthorityEvent.objects.get(pk=results[0]["id"]).authority_source
        == "installation_operator"
    )
    assert not ProjectMembership.objects.get(
        actor=users["developer"], project_id=a
    ).active
    assert (
        clients["developer"]
        .get(f"/api/declaration/{files[0].pk}/", **request)
        .status_code
        == 403
    )
    assert (
        clients["developer"]
        .get("/api/auth/session/", **request)
        .json()["authenticated"]
        is True
    )
    assert (
        clients["reviewer"]
        .get(f"/api/declaration/{files[0].pk}/", **request)
        .status_code
        == 200
    )
    try:
        with authorized_access(
            files[0].pk, "read", "private-project-fixture", SCOPE_PIPELINE_READ
        ):
            raise AssertionError("Revoked project membership reached data.")
    except AccessDenied as exc:
        assert exc.code == "project_access_denied"
    assert grant.active
    print(
        json.dumps(
            {
                "status": "passed",
                "profile": "private",
                "database": "postgresql",
                "tls": "verified",
                "roles": ["developer", "reviewer", "admin"],
                "isolated_projects": 2,
                "concurrent_processes": 5,
                "committed_changes": 1,
                "replays": 4,
                "revoked_native_and_mcp": "denied",
                "unaffected_reviewer": "authorized",
                "browser_session_preserved": True,
                "production_release_qualified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
