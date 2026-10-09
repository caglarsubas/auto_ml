#!/usr/bin/env python3
"""Create a non-admin account only in an explicitly disposable test installation."""

import os
import sys
import uuid
from pathlib import Path


def main():
    if os.environ.get("DECLARAI_TEST_INSTALLATION") != "1":
        raise SystemExit(
            "Set DECLARAI_TEST_INSTALLATION=1 only for a disposable test database."
        )
    username = os.environ.get("E2E_USER", "")
    password = os.environ.get("E2E_PASSWORD", "")
    if not username or not password:
        raise SystemExit(
            "E2E_USER and E2E_PASSWORD are required; no default credentials exist."
        )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.db import transaction

    with transaction.atomic():
        users = get_user_model().objects
        if users.filter(username=username).exists():
            raise SystemExit(
                "The test account already exists; existing users are never modified."
            )
        actor = users.create_user(
            username=username, password=password, is_staff=False, is_superuser=False
        )
        from access_control.projects import operator_change

        admin = users.create_user(
            username="fixture-admin-" + uuid.uuid4().hex, password=None
        )
        event, _ = operator_change(
            {
                "operation": "create",
                "name": "Disposable browser project",
                "user": admin.username,
            },
            uuid.uuid4(),
            "disposable-e2e-fixture",
        )
        operator_change(
            {
                "operation": "member",
                "project_id": str(event.project_id),
                "user": actor.username,
                "role": "developer",
            },
            uuid.uuid4(),
            "disposable-e2e-fixture",
        )
        # Separate account exercises multiple memberships without changing the
        # original single-project scientific and MCP fixtures.
        workspace_actor = users.create_user(username=username + "-workspace", password=password)
        from access_control.projects import bind_dataset, bind_pipeline
        from declaration.models import Declaration
        from django.core.files.base import ContentFile
        from modeling.models import PipelineRun

        for title, role in [("Workspace A", "developer"), ("Workspace B", "developer"),
                            ("Workspace Review", "reviewer"), ("Workspace Admin", "admin")]:
            event, _ = operator_change({"operation": "create", "name": title, "user": admin.username},
                                       uuid.uuid4(), "disposable-e2e-fixture")
            operator_change({"operation": "member", "project_id": str(event.project_id),
                             "user": workspace_actor.username, "role": role},
                            uuid.uuid4(), "disposable-e2e-fixture")
            dataset = Declaration.objects.create(name=title, original_name=title + ".csv")
            dataset.file.save("workspace-" + uuid.uuid4().hex + ".csv", ContentFile(b"x,target\n1,0\n2,1\n"))
            bind_dataset(dataset, event.project_id, source="disposable-e2e-fixture")
            run = PipelineRun.objects.create(name=title + " pipeline", file_id=dataset.pk,
                                             state={"file_id": dataset.pk})
            bind_pipeline(run, event.project_id, source="disposable-e2e-fixture")
    print("Created disposable, non-admin E2E accounts and owned workspace records.")


if __name__ == "__main__":
    main()
