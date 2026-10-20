#!/usr/bin/env python3
"""Owned synthetic native training/search over the real private TLS worker.

Recovery kills the owned process group after an observed running claim, then
explicitly expires its lease in the fixture. It does not claim natural lease
expiry, production recovery, UI migration or adoption of a deployed model.
"""

import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get("DECLARAI_TEST_INSTALLATION") != "1":
        raise RuntimeError("Use only the disposable private TLS installation.")
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django

    django.setup()
    import numpy as np
    import pandas as pd
    from access_control import projects
    from access_control.models import Project, ProjectMembership, ProjectPolicy
    from declaration.models import Declaration
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import connection
    from django.test import Client
    from django.utils import timezone
    from execution_jobs import service, training_search
    from execution_jobs.models import NativeJob
    from execution_jobs.preflight import check_runtime
    from execution_jobs.tasks import run_native_job

    if (
        settings.DECLARAI_RUNTIME_PROFILE != "private"
        or connection.vendor != "postgresql"
        or not connection.settings_dict["NAME"].startswith("declarai_fixture")
    ):
        raise RuntimeError("Use only the owned PostgreSQL fixture.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
        assert cursor.fetchone()[0] is True
    state = Path(os.environ["DECLARAI_JOB_FIXTURE_STATE"])
    if not state.is_absolute() or state.is_relative_to(ROOT):
        raise RuntimeError("Logs stay in the owner's disposable directory.")
    check_runtime()
    token = uuid.uuid4().hex
    ProjectPolicy.objects.get_or_create(pk=1)
    project = Project.objects.create(name="Synthetic durable training " + token)
    password = secrets.token_urlsafe(32)
    actor = get_user_model().objects.create_user(
        username="training-" + token, password=password
    )
    ProjectMembership.objects.create(project=project, actor=actor, role="developer")
    client = Client(enforce_csrf_checks=True)
    request = {"secure": True, "HTTP_HOST": settings.ALLOWED_HOSTS[0]}

    def post(path, body, expected=200):
        csrf = client.get("/api/auth/session/", **request).json()["csrf_token"]
        response = client.post(
            path,
            json.dumps(body),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_ORIGIN=settings.CSRF_TRUSTED_ORIGINS[0],
            **request,
        )
        assert response.status_code == expected, (
            path,
            response.status_code,
            response.content,
        )
        return response.json()

    post("/api/auth/login/", {"username": actor.username, "password": password})
    files = []

    def input_file(label, task="classification"):
        relative = "data_files/training-" + token + "-" + label + ".csv"
        path = Path(settings.MEDIA_ROOT) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(25)
        x = rng.normal(size=1000)
        frame = pd.DataFrame(
            {
                "x": x,
                "z": np.where(np.arange(1000) % 3, x * 0.5, np.nan),
                "entity": np.repeat(np.arange(250), 4),
                "outcome": np.where(x > 0, "bad", "good")
                if task == "classification"
                else x * 2,
            }
        )
        frame.to_csv(path, index=False)
        files.append(path)
        dataset = Declaration.objects.create(
            name=label, original_name=path.name, file=relative
        )
        projects.bind_dataset(dataset, project.pk, source="disposable_training_fixture")
        return dataset, path

    def queue(dataset, task="classification"):
        options = {
            "data_role": "development_only",
            "features": ["x", "z"],
            "validation": {
                "strategy": "group",
                "group_column": "entity",
                "n_splits": 3,
            },
            "business_understanding": {
                "problem_type": task,
                "objective": "Predict synthetic outcomes",
                "population": "Synthetic rows",
                "prediction_horizon": "Synthetic horizon",
                "feature_availability": {"default": "available_at_prediction"},
                "target_contract": {
                    "target_column": "outcome",
                    "positive_class": "bad" if task == "classification" else None,
                    "event_definition": "Synthetic event",
                    "label_maturity": "Synthetic complete labels",
                },
                "success_criteria": {
                    "primary_metric": "roc_auc" if task == "classification" else "rmse"
                },
            },
        }
        preview = post(f"/api/jobs/datasets/{dataset.pk}/training-input/", options)
        body = {
            **options,
            "kind": training_search.KIND,
            "request_id": str(uuid.uuid4()),
            "input_sha256": preview["input_sha256"],
            "training_sha256": preview["training_sha256"],
        }
        value = post(f"/api/jobs/datasets/{dataset.pk}/", body, 202)
        assert post(f"/api/jobs/datasets/{dataset.pk}/", body)["replayed"] is True
        return value["id"]

    processes = []

    def start(role, log):
        process = subprocess.Popen(
            ["sh", str(ROOT / "docker/private-job-entrypoint.sh"), role],
            cwd=ROOT / "backend",
            env=os.environ.copy(),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        processes.append(process)
        return process

    def stop():
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)

    def wait(identifier, states, seconds=45):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            job = NativeJob.objects.get(pk=identifier)
            if job.state in states:
                return job
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("An owned training process exited unexpectedly.")
            time.sleep(0.01)
        raise RuntimeError("Training job did not reach its expected state.")

    classification, _ = input_file("binary")
    orphan = queue(classification)
    log_path = state.with_name("training-worker.log")
    try:
        with log_path.open("wb") as log:
            worker = start("worker", log)
            run_native_job.apply_async(args=[orphan], retry=False)
            running = wait(orphan, {"running", "succeeded", "blocked", "failed"})
            # Freeze only the process group created above before inspecting the
            # interrupted claim. Never pause another installation's worker.
            os.killpg(worker.pid, signal.SIGSTOP)
            running.refresh_from_db()
            assert (
                running.state == "running"
                and running.result is None
                and running.attempts == 1
            )
            stale = running.lease_token
            os.killpg(worker.pid, signal.SIGKILL)
            worker.wait(timeout=10)
            processes.remove(worker)
            NativeJob.objects.filter(pk=orphan).update(
                lease_until=timezone.now() - timedelta(seconds=1)
            )
            service.reconcile()
            recovered = NativeJob.objects.get(pk=orphan)
            assert recovered.state == "queued" and recovered.result is None
            service.finish(orphan, stale, "succeeded", result={"stale": True})
            assert NativeJob.objects.get(pk=orphan).result is None

            regression, _ = input_file("regression", "regression")
            identifiers = {
                "interrupted_binary": orphan,
                "regression": queue(regression, "regression"),
            }
            cancelled = queue(classification)
            post(f"/api/jobs/{cancelled}/", {"action": "cancel"})
            changed, changed_path = input_file("changed")
            changed_job = queue(changed)
            changed_path.write_bytes(changed_path.read_bytes() + b"\n")
            input_hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in files
            }
            start("worker", log)
            start("dispatcher", log)
            for label, identifier in identifiers.items():
                job = wait(identifier, {"succeeded", "blocked", "failed"})
                assert job.state == "succeeded", job.reason_code
                assert job.attempts == (2 if label == "interrupted_binary" else 1)
                assert job.result_sha256 == service.digest(job.result)
                result = job.result
                assert len(result["candidates"]) == 2 and all(
                    len(c["folds"]) == 3 for c in result["candidates"]
                )
                assert result["refit_receipt"]["train"]["n_rows"] == 1000
                assert (
                    result["model_format"] == "xgboost_json"
                    and json.loads(result["model_json"])["learner"]
                )
                assert result["data_role"] == "development_only"
                assert all(
                    result[key] is False
                    for key in [
                        "final_holdout_accessed",
                        "legacy_projection_updated",
                        "model_adopted",
                        "review_approved",
                        "production_use_approved",
                    ]
                )
                assert job.events.filter(event_type="succeeded").count() == 1
            assert (
                wait(changed_job, {"blocked", "failed", "succeeded"}).state == "blocked"
            )
            assert NativeJob.objects.get(pk=changed_job).result is None
            assert NativeJob.objects.get(pk=cancelled).state == "cancelled"
            before = {
                identifier: service.serialize(NativeJob.objects.get(pk=identifier))
                for identifier in [*identifiers.values(), changed_job, cancelled]
            }
            for identifier in before:
                run_native_job.apply_async(args=[identifier], retry=False)
            time.sleep(1)
            assert before == {
                identifier: service.serialize(NativeJob.objects.get(pk=identifier))
                for identifier in before
            }
            assert input_hashes == {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in files
            }
            service.finish(orphan, stale, "succeeded", result={"stale": True})
            assert service.serialize(NativeJob.objects.get(pk=orphan)) == before[orphan]
            print(
                json.dumps(
                    {
                        "schema": "private_native_training_search_v1",
                        "scope": training_search.KIND,
                        "private_tls_prefork_and_dispatcher": "passed",
                        "real_csrf_login_preview_submit": "passed",
                        "binary_and_regression_search_and_refit": "passed",
                        "grouped_fold_evidence": "passed",
                        "actual_owned_worker_killed_after_running_claim": "passed",
                        "fixture_injected_expired_lease_recovery": "passed",
                        "stale_token_fenced_before_and_after_completion": "passed",
                        "duplicate_single_publication": "passed",
                        "queued_cancel_and_changed_input": "passed",
                        "source_files_unchanged_by_execution": "passed",
                        "expert_or_fitted_state_deserialized": False,
                        "natural_lease_expiry_qualified_here": False,
                        "legacy_training_search_migrated": False,
                        "model_adopted": False,
                        "production_recovery_qualified": False,
                        "release_qualified": False,
                        "customer_installation_modified": False,
                    }
                )
            )
    finally:
        stop()


if __name__ == "__main__":
    main()
