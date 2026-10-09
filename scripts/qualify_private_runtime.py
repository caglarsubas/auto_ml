#!/usr/bin/env python3
"""Disposable PostgreSQL/TLS smoke check; never a production recovery runner."""

import hashlib
import json
import os
import secrets
import sys
import uuid
from pathlib import Path


def main():
    if os.environ.get("DECLARAI_TEST_INSTALLATION") != "1":
        raise SystemExit("Requires an explicitly disposable test installation.")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django

    django.setup()
    from access_control.models import (
        AssistantActionApproval,
        MCPAccessEvent,
        MCPDatasetGrant,
    )
    from declaration.models import Declaration
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.models import Session
    from django.db import connection
    from django.test import Client
    from django.utils import timezone
    from modeling.models import HoldoutAccess, PipelineRun

    assert settings.DECLARAI_RUNTIME_PROFILE == "private" and not settings.DEBUG
    assert connection.vendor == "postgresql"
    assert connection.settings_dict["NAME"].startswith("declarai_fixture")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
        )
        ssl, protocol = cursor.fetchone()
        assert ssl and protocol.startswith("TLS")
        cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        assert cursor.fetchone()[0] is False
    state_file = Path(os.environ["DECLARAI_FIXTURE_STATE"])
    host = settings.ALLOWED_HOSTS[0]
    request = {
        "secure": True,
        "HTTP_HOST": host,
        "HTTP_ORIGIN": settings.CSRF_TRUSTED_ORIGINS[0],
    }
    client = Client(enforce_csrf_checks=True)
    if sys.argv[1:] == ["seed"]:
        assert not state_file.exists()
        assert client.get("/api/auth/session/", HTTP_HOST=host).status_code == 301
        assert (
            client.get(
                "/api/auth/session/", secure=True, HTTP_HOST="unlisted.private.test"
            ).status_code
            == 400
        )
        assert client.get("/api/declaration/", **request).status_code == 403
        first = client.get("/api/auth/session/", **request)
        assert first.status_code == 200 and first.cookies["csrftoken"]["secure"]
        assert first["Strict-Transport-Security"].startswith("max-age=")
        username, password = (
            "private-fixture-" + uuid.uuid4().hex,
            secrets.token_urlsafe(32),
        )
        user = get_user_model().objects.create_user(
            username=username, password=password
        )
        credentials = json.dumps({"username": username, "password": password})
        assert (
            client.post(
                "/api/auth/login/",
                credentials,
                content_type="application/json",
                **request,
            ).status_code
            == 403
        )
        logged_in = client.post(
            "/api/auth/login/",
            credentials,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=first.json()["csrf_token"],
            **request,
        )
        assert logged_in.status_code == 200 and logged_in.cookies["sessionid"]["secure"]
        csrf = logged_in.json()["csrf_token"]
        state = {
            "modeling": {"substep": "encoding_completed"},
            "fixture": {"nested": [1, False, None, "same"]},
        }
        created = client.post(
            "/api/pipeline/create/",
            json.dumps({"name": "private-runtime-fixture", "state": state}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            **request,
        )
        assert created.status_code == 201
        dataset = Declaration.objects.create(
            name="private-fixture",
            original_name="fixture.csv",
            file="data_files/fixture.csv",
        )
        artifact = Path(settings.MEDIA_ROOT) / dataset.file.name
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("feature,target\n1,0\n2,1\n")
        receipt = HoldoutAccess.objects.create(
            file_id=dataset.pk,
            execution_id=uuid.uuid4(),
            actor=user,
            actor_snapshot={"id": user.pk},
            parameters={"fixture": True},
            attempt_state="failed",
        )
        grant = MCPDatasetGrant.objects.create(actor=user, dataset=dataset, role="read")
        event = MCPAccessEvent.objects.create(
            actor=user,
            grant=grant,
            file_id=dataset.pk,
            actor_snapshot={"id": user.pk},
            grant_snapshot={"revision": str(grant.revision)},
            operation="read",
            tool_name="fixture",
            outcome="completed",
        )
        approval = AssistantActionApproval.objects.create(
            actor=user,
            file_id=dataset.pk,
            actor_snapshot={"id": user.pk},
            action_type="update_notes",
            payload={"content": "fixture"},
            context={"fixture": True},
            environment={"fixture": True},
            budget={"fixture": True},
            proposal_sha256="a" * 64,
            expires_at=timezone.now(),
            state="expired",
        )
        snapshot = {
            "user": user.pk,
            "pipeline": created.json()["id"],
            "state": state,
            "dataset": dataset.pk,
            "receipt": str(receipt.pk),
            "grant": str(grant.pk),
            "revision": str(grant.revision),
            "event": str(event.pk),
            "approval": str(approval.pk),
            "session": client.cookies["sessionid"].value,
            "artifact": dataset.file.name,
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }
        # Contains a session credential: never publish or attach this fixture state.
        with open(
            state_file, "x", opener=lambda path, flags: os.open(path, flags, 0o600)
        ) as output:
            json.dump(snapshot, output)
    elif sys.argv[1:] == ["verify"]:
        snapshot = json.loads(state_file.read_text())
        assert (
            PipelineRun.objects.get(pk=snapshot["pipeline"]).state == snapshot["state"]
        )
        assert (
            HoldoutAccess.objects.get(pk=snapshot["receipt"]).actor_id
            == snapshot["user"]
        )
        assert (
            str(MCPDatasetGrant.objects.get(pk=snapshot["grant"]).revision)
            == snapshot["revision"]
        )
        assert MCPAccessEvent.objects.get(pk=snapshot["event"]).outcome == "completed"
        assert (
            AssistantActionApproval.objects.get(pk=snapshot["approval"]).state
            == "expired"
        )
        assert Session.objects.get(session_key=snapshot["session"]).get_decoded()[
            "_auth_user_id"
        ] == str(snapshot["user"])
        client.cookies["sessionid"] = snapshot["session"]
        assert (
            client.get("/api/auth/session/", **request).json()["authenticated"] is True
        )
        assert (
            client.get(f"/api/pipeline/{snapshot['pipeline']}/", **request).json()[
                "state"
            ]
            == snapshot["state"]
        )
        artifact = Path(settings.MEDIA_ROOT) / snapshot["artifact"]
        assert (
            hashlib.sha256(artifact.read_bytes()).hexdigest()
            == snapshot["artifact_sha256"]
        )
        download = client.get("/media/" + snapshot["artifact"], **request)
        assert (
            download.status_code == 200
            and download["Cache-Control"] == "private, no-store"
        )
        assert (
            hashlib.sha256(b"".join(download.streaming_content)).hexdigest()
            == snapshot["artifact_sha256"]
        )
        download.close()
    else:
        raise SystemExit("Use seed or verify.")
    print(
        json.dumps(
            {
                "private_runtime": sys.argv[1],
                "database": "postgresql",
                "tls": protocol,
                "metadata_fixture": "passed",
                "production_recovery_qualified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
