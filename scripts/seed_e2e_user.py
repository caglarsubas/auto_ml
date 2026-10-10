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
        review_developer = users.create_user(username=username + "-review-developer", password=password)
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
            if role == 'reviewer':
                operator_change({'operation': 'member', 'project_id': str(event.project_id),
                                 'user': review_developer.username, 'role': 'developer'},
                                uuid.uuid4(), 'disposable-e2e-fixture')
                seed_review_package(dataset, review_developer)
    print("Created disposable, non-admin E2E accounts and owned workspace records.")


def seed_review_package(dataset, actor):
    """Real native execution and assessment; no fabricated package evidence."""
    import numpy as np
    import pandas as pd
    from django.conf import settings
    from rest_framework.test import APIRequestFactory, force_authenticate
    from access_control import projects
    from modeling.views import ModelingStartView
    from evaluation.views import EvaluationRunView
    from deployment.deploy_utils import build_score_bundle

    frame = pd.DataFrame({'x': np.linspace(-2, 2, 160), 'other': np.arange(160) % 7,
                          'outcome': ['bad', 'good'] * 80})
    frame.to_csv(Path(settings.MEDIA_ROOT) / dataset.file.name, index=False)
    declaration = {'problem_type': 'classification', 'objective': 'Synthetic reviewer workflow',
                   'population': 'Synthetic applicants', 'prediction_horizon': '12 months',
                   'feature_availability': {'default': 'available_at_prediction'},
                   'target_contract': {'target_column': 'outcome', 'positive_class': 'bad',
                                       'event_definition': 'Synthetic event', 'label_maturity': 'Complete follow-up'},
                   'success_criteria': {'primary_metric': 'roc_auc', 'cost_matrix': {'fn_cost': 4, 'fp_cost': 1}}}
    token = projects.current_actor.set(actor.pk)
    try:
        request = APIRequestFactory().post('/api/modeling/start/', {'file_id': dataset.pk,
            'processed_file': dataset.file.name, 'algorithm': 'logistic_regression',
            'business_understanding': declaration}, format='json')
        force_authenticate(request, actor)
        result = ModelingStartView.as_view()(request)
        if result.status_code != 200:
            raise RuntimeError('Disposable review model failed to train.')
        request = APIRequestFactory().post('/api/evaluation/run/', {'file_id': dataset.pk,
            'execution_id': result.data['execution_id']}, format='json')
        force_authenticate(request, actor)
        result = EvaluationRunView.as_view()(request)
        if result.status_code != 200:
            raise RuntimeError('Disposable review assessment failed.')
        build_score_bundle(dataset.pk)
    finally:
        projects.current_actor.reset(token)


if __name__ == "__main__":
    main()
