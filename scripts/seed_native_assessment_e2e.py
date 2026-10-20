"""Independent disposable fixtures; never reuse earlier browser populations."""

import os
import uuid


def seed_native_assessment_e2e(username, password):
    if os.environ.get("DECLARAI_TEST_INSTALLATION") != "1":
        raise RuntimeError(
            "Only disposable installations may seed assessment fixtures."
        )
    from access_control.projects import bind_dataset, operator_change
    from declaration.models import Declaration
    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile
    from django.db import transaction

    with transaction.atomic():
        users = get_user_model().objects
        developer = users.create_user(
            username=username + "-adoption-dev", password=password
        )
        reviewer = users.create_user(
            username=username + "-adoption-reviewer", password=password
        )
        operator = users.create_user(
            username="assessment-admin-" + uuid.uuid4().hex, password=None
        )
        event, _ = operator_change(
            {
                "operation": "create",
                "name": "Protected native fixture",
                "user": operator.username,
            },
            uuid.uuid4(),
            "disposable-assessment-e2e",
        )
        for actor, role in [(developer, "developer"), (reviewer, "reviewer")]:
            operator_change(
                {
                    "operation": "member",
                    "project_id": str(event.project_id),
                    "user": actor.username,
                    "role": role,
                },
                uuid.uuid4(),
                "disposable-assessment-e2e",
            )
        for task in ["binary", "regression"]:
            name = "Adoption " + task + ".csv"
            rows = ["x,z,outcome"] + [
                f"{i / 80},{i % 7},{i % 4 if task == 'regression' else 'bad' if i % 2 else 'good'}"
                for i in range(80)
            ]
            dataset = Declaration.objects.create(name=name, original_name=name)
            dataset.file.save(
                "adoption-ui-" + uuid.uuid4().hex + ".csv",
                ContentFile(("\n".join(rows) + "\n").encode()),
            )
            bind_dataset(dataset, event.project_id, source="disposable-assessment-e2e")
