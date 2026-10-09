#!/usr/bin/env python3
"""Disposable private PostgreSQL identity/revocation and process-concurrency checks."""

import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path


def main():
    if os.environ.get("DECLARAI_TEST_INSTALLATION") != "1":
        raise SystemExit("Requires an explicitly disposable test installation.")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django

    django.setup()
    from access_control.models import (
        AuthenticationEvent,
        LoginThrottleBucket,
        SessionAuthority,
    )
    from access_control.session_authority import (
        SESSION_REVISION_KEY,
        deny_login,
        reserve_login,
    )
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connection
    from django.db.models import F
    from django.test import Client, RequestFactory

    assert settings.DECLARAI_RUNTIME_PROFILE == "private" and not settings.DEBUG
    assert connection.vendor == "postgresql" and connection.settings_dict[
        "NAME"
    ].startswith("declarai_fixture")
    with connection.cursor() as cursor:
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
        assert cursor.fetchone()[0] is True
    if sys.argv[1:] == ["reserve"]:
        request = RequestFactory().post(
            "/api/auth/login/", REMOTE_ADDR=os.environ["DECLARAI_FIXTURE_LOGIN_SOURCE"]
        )
        admitted, event = reserve_login(
            request, os.environ["DECLARAI_FIXTURE_LOGIN_PRINCIPAL"]
        )
        if admitted:
            deny_login(event)
        print(json.dumps({"admitted": admitted}))
        return

    token = uuid.uuid4().hex
    for scenario in ["source", "principal"]:
        source = "synthetic-process-" + scenario + token
        username = "synthetic-principal-" + token
        env = {
            **os.environ,
            "DECLARAI_FIXTURE_LOGIN_SOURCE": source,
            "DECLARAI_FIXTURE_LOGIN_PRINCIPAL": username,
            "DECLARAI_AUTH_LOGIN_SOURCE_LIMIT": "3" if scenario == "source" else "20",
            "DECLARAI_AUTH_LOGIN_PAIR_LIMIT": "20" if scenario == "source" else "3",
        }

        def reserve(_, env=env):
            result = subprocess.run(
                [sys.executable, __file__, "reserve"],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            assert result.returncode == 0, "Concurrent reservation process failed."
            return json.loads(result.stdout)["admitted"]

        with ThreadPoolExecutor(max_workers=5) as pool:
            admitted = list(pool.map(reserve, range(5)))
        assert sum(admitted) == 3
        reason = (
            "login_source_rate_limited"
            if scenario == "source"
            else "login_principal_rate_limited"
        )
        # This fixture's random source/principal has exactly one first-denial event.
        event = AuthenticationEvent.objects.filter(reason_code=reason).latest(
            "started_at"
        )
        key = event.source_key if scenario == "source" else event.principal_key
        bucket = LoginThrottleBucket.objects.get(pk=key)
        assert bucket.attempts == 3 and bucket.blocked_attempts == 2
        assert (
            AuthenticationEvent.objects.filter(source_key=event.source_key).count() == 4
        )

    actor = get_user_model().objects.create_user(
        username="identity-fixture-" + token, password=None
    )
    other = get_user_model().objects.create_user(
        username="identity-other-" + token, password=None
    )
    host = settings.ALLOWED_HOSTS[0]
    request = {"secure": True, "HTTP_HOST": host}
    clients = [Client() for _ in range(2)]
    for client in clients:
        client.force_login(actor)
        assert client.get("/api/declaration/", **request).status_code == 200
    unaffected = Client()
    unaffected.force_login(other)
    identifier = str(uuid.uuid4())
    arguments = [
        sys.executable,
        str(root / "backend/manage.py"),
        "revoke_web_sessions",
        "--user",
        actor.username,
        "--request-id",
        identifier,
        "--operator-label",
        "private-fixture",
    ]

    def revoke(_):
        result = subprocess.run(
            arguments,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, "Concurrent revocation process failed."
        return json.loads(result.stdout.strip().splitlines()[-1])

    with ThreadPoolExecutor(max_workers=5) as pool:
        receipts = list(pool.map(revoke, range(5)))
    assert sum(not receipt["replayed_receipt"] for receipt in receipts) == 1
    assert {receipt["event_id"] for receipt in receipts} == {identifier}
    assert (
        AuthenticationEvent.objects.filter(pk=identifier, outcome="completed").count()
        == 1
    )
    for client in clients:
        assert client.get("/api/declaration/", **request).status_code == 403
        assert (
            client.get("/api/auth/session/", **request).json()["authenticated"] is False
        )
    assert unaffected.get("/api/declaration/", **request).status_code == 200
    fresh = Client()
    fresh.force_login(actor)
    revision = fresh.session[SESSION_REVISION_KEY]
    output = StringIO()
    call_command(
        "revoke_web_sessions",
        "--user",
        actor.username,
        "--request-id",
        identifier,
        "--operator-label",
        "private-fixture",
        stdout=output,
    )
    assert json.loads(output.getvalue())["replayed_receipt"] is True
    assert str(SessionAuthority.objects.get(user=actor).revision) == revision
    assert fresh.get("/api/declaration/", **request).status_code == 200
    assert not AuthenticationEvent.objects.filter(finished_at__lt=F("started_at")).exists()
    print(
        json.dumps(
            {
                "identity_fixture": "passed",
                "processes_per_scenario": 5,
                "source_admissions": 3,
                "principal_admissions": 3,
                "revocation_operations": 1,
                "revocation_replays": 4,
                "revoked_sessions": 2,
                "unaffected_actor": "passed",
                "private_tls": "verified",
                "production_security_qualified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
