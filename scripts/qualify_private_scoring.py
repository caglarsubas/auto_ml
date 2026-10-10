#!/usr/bin/env python3
"""Synthetic native scoring through private TLS restore and an empty broker.

Owned by qualify_postgres_fixture.py. Its private state (sessions and an old
lease token) stays outside the checkout and is destroyed with that fixture.
Only fixed native models generated here are trusted; this is not expert isolation.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get("DECLARAI_TEST_INSTALLATION") != "1":
        raise RuntimeError("Use only a disposable synthetic installation.")
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django

    django.setup()
    import numpy as np
    import pandas as pd
    from access_control import projects
    from access_control.models import (
        Project,
        ProjectDataset,
        ProjectMembership,
        ProjectPolicy,
    )
    from declaration.models import Declaration
    from deployment.deploy_utils import build_deployment_pack_zip, score_frame
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import connection
    from django.test import Client
    from execution_jobs import csv_scoring, service
    from execution_jobs.models import NativeJob
    from execution_jobs.preflight import check_runtime
    from execution_jobs.tasks import run_native_job

    if (
        settings.DECLARAI_RUNTIME_PROFILE != "private"
        or connection.vendor != "postgresql"
        or not connection.settings_dict["NAME"].startswith("declarai_fixture")
    ):
        raise RuntimeError("Use the disposable private TLS PostgreSQL fixture.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
        assert cursor.fetchone()[0] is True
    owner_state = Path(os.environ["DECLARAI_JOB_FIXTURE_STATE"])
    if not owner_state.is_absolute() or owner_state.is_relative_to(ROOT):
        raise RuntimeError("Fixture state must stay outside the checkout.")
    state_file = owner_state.with_name("scoring-" + owner_state.name)
    phase = sys.argv[1:]
    if phase not in [
        ["seed"],
        ["broker-down"],
        ["verify"],
        ["prepare-recovery"],
        ["recover"],
    ]:
        raise RuntimeError(
            "Use seed, broker-down, verify, prepare-recovery or recover."
        )
    request = {"secure": True, "HTTP_HOST": settings.ALLOWED_HOSTS[0]}
    processes = []

    def start_worker(log):
        # Preflight the real private connections, then run an owned prefork worker.
        check_runtime()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "backend.celery:app",
                "worker",
                "--pool=prefork",
                "--concurrency=2",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
                "--loglevel=INFO",
                "--hostname=scoring-fixture@%h",
            ],
            cwd=ROOT / "backend",
            env=os.environ.copy(),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        processes.append(process)

    def start_dispatcher(log):
        process = subprocess.Popen(
            ["sh", str(ROOT / "docker/private-job-entrypoint.sh"), "dispatcher"],
            cwd=ROOT / "backend",
            env=os.environ.copy(),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        processes.append(process)

    def stop():
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)

    def wait(identifier, states, seconds=45):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            job = NativeJob.objects.get(pk=identifier)
            if job.state in states:
                return job
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("An owned scoring worker exited unexpectedly.")
            time.sleep(0.1)
        raise RuntimeError("Scoring did not reach its expected state.")

    def snapshot(ids):
        values = {}
        for label, identifier in ids.items():
            job = NativeJob.objects.get(pk=identifier)
            values[label] = {
                "receipt": service.serialize(job),
                "full_result": job.result,
                "authority": job.authority,
                "request_sha256": job.request_sha256,
                "source_dataset_id": job.source_dataset_id,
                "lease_token": str(job.lease_token) if job.lease_token else None,
                "lease_until": job.lease_until.isoformat() if job.lease_until else None,
                "next_dispatch": job.next_dispatch.isoformat(),
            }
        return values

    def post(client, path, data, expected=200):
        csrf = client.get("/api/auth/session/", **request).json()["csrf_token"]
        response = client.post(
            path,
            json.dumps(data),
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

    def authorize_client(session):
        client = Client(enforce_csrf_checks=True)
        client.cookies[settings.SESSION_COOKIE_NAME] = session
        assert client.get("/api/auth/session/", **request).json()["authenticated"]
        return client

    def input_file(token, label, project, frame):
        relative = "data_files/scoring-" + token + "-" + label + ".csv"
        path = Path(settings.MEDIA_ROOT) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        dataset = Declaration.objects.create(
            name=label, original_name=path.name, file=relative
        )
        projects.bind_dataset(dataset, project.pk, source="disposable_scoring_fixture")
        return dataset

    if phase == ["seed"]:
        assert not state_file.exists()
        check_runtime()
        token = uuid.uuid4().hex
        ProjectPolicy.objects.get_or_create(pk=1)
        project = Project.objects.create(name="Synthetic scoring restore " + token)
        users, clients = {}, {}
        for role in ["developer", "reviewer", "revoked", "outsider"]:
            password = secrets.token_urlsafe(32)
            actor = get_user_model().objects.create_user(
                username="restore-" + role + "-" + token, password=password
            )
            if role != "outsider":
                ProjectMembership.objects.create(
                    project=project,
                    actor=actor,
                    role="developer" if role == "revoked" else role,
                )
            client = Client(enforce_csrf_checks=True)
            post(
                client,
                "/api/auth/login/",
                {"username": actor.username, "password": password},
            )
            users[role], clients[role] = actor, client
        fixtures, ids = {}, {}
        rng = np.random.default_rng(25)
        x, other = rng.normal(size=160), rng.normal(size=160)
        for task in ["classification", "regression"]:
            outcomes = (
                np.where(x + 0.4 * other > 0, "bad", "good")
                if task == "classification"
                else 2 * x - other
            )
            model = input_file(
                token,
                task + "-model",
                project,
                pd.DataFrame({"x": x, "other": other, "outcome": outcomes}),
            )
            declared = {
                "problem_type": task,
                "objective": "Predict the synthetic outcome",
                "population": "Synthetic applicants",
                "prediction_horizon": "12 months",
                "feature_availability": {"default": "available_at_prediction"},
                "target_contract": {
                    "target_column": "outcome",
                    "positive_class": "bad",
                    "event_definition": "Synthetic outcome",
                    "label_maturity": "Complete follow-up",
                },
                "success_criteria": {
                    "primary_metric": "roc_auc" if task == "classification" else "rmse",
                    "cost_matrix": {"fn_cost": 4, "fp_cost": 1},
                },
            }
            trained = post(
                clients["developer"],
                "/api/modeling/start/",
                {
                    "file_id": model.pk,
                    "processed_file": model.file.name,
                    "algorithm": "logistic_regression"
                    if task == "classification"
                    else "xgboost",
                    "business_understanding": declared,
                },
            )
            assessed = post(
                clients["developer"],
                "/api/evaluation/run/",
                {
                    "file_id": model.pk,
                    "execution_id": trained["execution_id"],
                },
            )
            bundle = post(
                clients["developer"],
                "/api/deployment/bundle/",
                {
                    "file_id": model.pk,
                    "execution_id": trained["execution_id"],
                    "assessment_id": assessed["evaluation"]["holdout_access_id"],
                },
            )
            frame = pd.DataFrame(
                {"other": np.linspace(2, -2, 650), "x": np.linspace(-3, 3, 650)}
            )
            source = input_file(token, task + "-input", project, frame)
            expected = score_frame(
                model.pk, pd.read_csv(source.get_file_path()), bundle["bundle_id"]
            )
            if task == "classification":
                assert expected["scores_calibrated"] is True
            fixtures[task] = {
                "file_id": model.pk,
                "source_id": source.pk,
                "bundle_id": bundle["bundle_id"],
                "manifest_sha256": bundle["manifest_sha256"],
                "expected": expected,
            }
            labels = ["queued", "completed", "cancelled"]
            if task == "classification":
                labels += ["orphan", "changed", "missing", "revoked"]
            for label in labels:
                selected = (
                    input_file(token, label, project, frame)
                    if label in {"changed", "missing"}
                    else source
                )
                role = "revoked" if label == "revoked" else "developer"
                metadata = clients[role].get(
                    f"/api/jobs/datasets/{selected.pk}/input/", **request
                )
                assert metadata.status_code == 200
                payload = {
                    "request_id": str(uuid.uuid4()),
                    "kind": csv_scoring.KIND,
                    "bundle_id": bundle["bundle_id"],
                    "manifest_sha256": bundle["manifest_sha256"],
                    "input_file_id": selected.pk,
                    "input_sha256": metadata.json()["sha256"],
                }
                receipt = post(
                    clients[role],
                    f"/api/jobs/datasets/{model.pk}/",
                    payload,
                    expected=202,
                )
                ids[task + "-" + label] = receipt["id"]
                if label == "cancelled":
                    post(
                        clients[role],
                        f"/api/jobs/{receipt['id']}/",
                        {"action": "cancel"},
                    )
        with state_file.with_suffix(".seed.log").open("wb") as log:
            try:
                start_worker(log)
                for task in fixtures:
                    run_native_job.apply_async(
                        args=[ids[task + "-completed"]], retry=False
                    )
                    job = wait(
                        ids[task + "-completed"], {"succeeded", "blocked", "failed"}
                    )
                    assert job.state == "succeeded" and job.attempts == 1
                    np.testing.assert_allclose(
                        job.result["scores"],
                        fixtures[task]["expected"]["scores"],
                        atol=1e-12,
                        rtol=1e-12,
                    )
            finally:
                stop()
        orphan, old_token = service.claim(ids["classification-orphan"])
        assert orphan.attempts == 1 and orphan.lease_until is not None
        # No worker exists for this natural orphan; both shared active slots are
        # retained with the existing integrity orphan until their real leases expire.
        assert (
            NativeJob.objects.filter(state__in=service.ACTIVE).count()
            == service.LIMITS["max_active"]
        )
        artifact_hashes = {
            p.relative_to(settings.MEDIA_ROOT).as_posix(): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in Path(settings.MEDIA_ROOT).rglob("*")
            if p.is_file()
        }
        state = {
            "ids": ids,
            "fixtures": fixtures,
            "old_token": str(old_token),
            "project_id": str(project.pk),
            "revoked_user": users["revoked"].username,
            "sessions": {
                role: client.cookies[settings.SESSION_COOKIE_NAME].value
                for role, client in clients.items()
            },
            "artifact_hashes": artifact_hashes,
            "jobs": snapshot(ids),
        }
        with open(
            state_file, "x", opener=lambda path, flags: os.open(path, flags, 0o600)
        ) as stream:
            json.dump(state, stream)
        print(
            json.dumps(
                {
                    "private_scoring": "seed",
                    "real_login_csrf_and_native_fit": "passed",
                    "tasks": list(fixtures),
                    "rows_per_task": 650,
                    "jobs": len(ids),
                    "calibrated_classification": True,
                    "quiescent_states": ["queued", "running", "succeeded", "cancelled"],
                }
            )
        )
        return

    state = json.loads(state_file.read_text())
    ids, fixtures = state["ids"], state["fixtures"]
    if phase in [["broker-down"], ["verify"], ["prepare-recovery"]]:
        assert snapshot(ids) == state["jobs"]
        for relative, sha in state["artifact_hashes"].items():
            assert (
                hashlib.sha256(
                    (Path(settings.MEDIA_ROOT) / relative).read_bytes()
                ).hexdigest()
                == sha
            )
    if phase == ["broker-down"]:
        assert service.dispatch_once() == {"delivered": 0, "broker_unavailable": 1}
        assert snapshot(ids) == state["jobs"]
        print(
            json.dumps(
                {
                    "private_scoring": "broker-down",
                    "retained_exact_inputs_requests_results": "passed",
                }
            )
        )
        return
    check_runtime()
    clients = {
        role: authorize_client(session) for role, session in state["sessions"].items()
    }
    if phase == ["verify"]:
        for task in fixtures:
            job = NativeJob.objects.get(pk=ids[task + "-completed"])
            url = f"/api/jobs/{job.pk}/scores/?sha256={job.result_sha256}&project_id={state['project_id']}"
            response = clients["reviewer"].get(url, **request)
            assert (
                response.status_code == 200
                and response.content == csv_scoring.canonical_bytes(job.result)
            )
            assert hashlib.sha256(response.content).hexdigest() == job.result_sha256
            assert clients["outsider"].get(url, **request).status_code == 403
        print(
            json.dumps(
                {
                    "private_scoring": "verify",
                    "exact_full_results_inputs_history_restore": "passed",
                    "restored_sessions_and_authorized_http_receipts": "passed",
                }
            )
        )
        return
    if phase == ["prepare-recovery"]:
        for label in ["changed", "missing"]:
            job = NativeJob.objects.get(pk=ids["classification-" + label])
            source = Declaration.objects.get(pk=job.source_dataset_id)
            if label == "changed":
                Path(source.get_file_path()).write_text("other,x\n999,999\n")
            else:
                Path(source.get_file_path()).unlink()
        projects.operator_change(
            {
                "operation": "member",
                "project_id": state["project_id"],
                "user": state["revoked_user"],
                "role": "none",
            },
            uuid.uuid4(),
            "disposable-scoring-recovery",
        )
        print(
            json.dumps(
                {
                    "private_scoring": "prepare-recovery",
                    "restored_negative_inputs_and_revocation": "injected",
                }
            )
        )
        return

    def recover(log_path, log):
        # The integrity recovery may finish before the later scoring orphan's
        # lease expires. Keep our own dispatcher alive for its natural recovery.
        start_dispatcher(log)
        orphan = wait(
            ids["classification-orphan"], {"queued"} | service.TERMINAL, seconds=200
        )
        if orphan.state == "queued":
            assert orphan.attempts == 1 and orphan.result is None
            service.finish(
                orphan.pk,
                uuid.UUID(state["old_token"]),
                "succeeded",
                result={"scores": [999]},
            )
            orphan.refresh_from_db()
            assert orphan.state == "queued" and orphan.result is None
        start_worker(log)
        for label, identifier in ids.items():
            job = wait(identifier, service.TERMINAL)
            original = state["jobs"][label]
            task, scenario = label.split("-", 1)
            if scenario in {"completed", "cancelled"}:
                assert snapshot({label: identifier})[label] == original
            elif scenario in {"changed", "missing", "revoked"}:
                assert (
                    job.state == "blocked"
                    and job.result is None
                    and not job.result_sha256
                )
                reasons = {
                    "changed": "job_input_changed",
                    "missing": "job_package_or_budget_invalid",
                    "revoked": "job_authority_changed",
                }
                assert job.reason_code == reasons[scenario]
            else:
                assert job.state == "succeeded" and job.attempts == (
                    2 if scenario == "orphan" else 1
                )
                assert job.events.filter(event_type="succeeded").count() == 1
                assert (
                    job.authority == original["authority"]
                    and job.request_sha256 == original["request_sha256"]
                )
                assert job.specification == original["receipt"]["specification"]
                assert (
                    service.serialize(job)["events"][
                        : len(original["receipt"]["events"])
                    ]
                    == original["receipt"]["events"]
                )
                if scenario == "orphan":
                    assert (
                        job.events.filter(
                            event_type="requeued",
                            detail__reason_code="worker_lease_expired",
                        ).count()
                        == 1
                    )
                np.testing.assert_allclose(
                    job.result["scores"],
                    fixtures[task]["expected"]["scores"],
                    atol=1e-12,
                    rtol=1e-12,
                )
            if scenario not in {"changed", "missing", "revoked", "cancelled"}:
                detail = clients["reviewer"].get(
                    f"/api/jobs/{job.pk}/?project_id={state['project_id']}", **request
                )
                assert detail.status_code == 200
                assert len(detail.json()["result"]["scores_preview"]) == 500
                url = f"/api/jobs/{job.pk}/scores/?sha256={job.result_sha256}&project_id={state['project_id']}"
                response = clients["reviewer"].get(url, **request)
                assert (
                    response.status_code == 200
                    and response["Cache-Control"] == "no-store"
                )
                assert response.content == csv_scoring.canonical_bytes(job.result)
                assert hashlib.sha256(response.content).hexdigest() == job.result_sha256
                assert len(response.json()["scores"]) == 650
                assert clients["outsider"].get(url, **request).status_code == 403
                assert clients["revoked"].get(url, **request).status_code == 403
        current = snapshot(ids)
        service.finish(
            ids["classification-orphan"],
            uuid.UUID(state["old_token"]),
            "succeeded",
            result={"scores": [999]},
        )
        assert snapshot(ids) == current
        # Wait for actual Celery completion, not just broker publish or a sleep.
        deliveries = []
        for identifier in ids.values():
            for _ in range(2):
                # Celery delivery IDs differ from durable job IDs. Observe each
                # broker delivery's own completion before comparing DB history.
                deliveries.append(
                    run_native_job.apply_async(args=[identifier], retry=False).id
                )
        until = time.monotonic() + 45
        while time.monotonic() < until:
            output = log_path.read_text(errors="replace")
            if all(
                f"Task declarai.package_integrity[{identifier}] succeeded" in output
                for identifier in deliveries
            ):
                break
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("Owned duplicate-delivery worker exited.")
            time.sleep(0.1)
        else:
            raise RuntimeError("Actual duplicate task completion was not observed.")
        assert snapshot(ids) == current

    log_path = state_file.with_suffix(".recovery.log")
    with log_path.open("wb") as log:
        try:
            recover(log_path, log)
        finally:
            stop()
    # Export only generated synthetic inputs/packages/full recovered receipts.
    # The owner copies these to ignored reports before deleting fixture state.
    exports = state_file.parent / "recovered-scoring"
    for task, fixture in fixtures.items():
        destination = exports / task
        destination.mkdir(parents=True)
        job = NativeJob.objects.get(
            pk=ids[task + ("-orphan" if task == "classification" else "-queued")]
        )
        package = build_deployment_pack_zip(fixture["file_id"], fixture["bundle_id"])[0]
        raw = Path(
            Declaration.objects.get(pk=fixture["source_id"]).get_file_path()
        ).read_bytes()
        receipt = csv_scoring.canonical_bytes(job.result)
        (destination / "offline-package.zip").write_bytes(package)
        (destination / "offline-input.csv").write_bytes(raw)
        (destination / "offline-receipt.json").write_bytes(receipt)
        (destination / "offline-context.json").write_text(
            json.dumps(
                {
                    "synthetic_fixture": True,
                    "task": task,
                    "package_sha256": hashlib.sha256(package).hexdigest(),
                    "receipt_sha256": hashlib.sha256(receipt).hexdigest(),
                    "manifest_sha256": fixture["manifest_sha256"],
                }
            )
        )
    # Inject an unsupported binding change only in the disposable restored DB.
    # Model authority alone must not expose the source's retained scores. This
    # fault does not imply that product dataset reassignment is supported.
    current = snapshot(ids)
    moved = fixtures["regression"]["source_id"]
    other_project = Project.objects.create(name="Synthetic unavailable source scope")
    ProjectDataset.objects.filter(dataset_id=moved).update(
        project=other_project, revision=uuid.uuid4()
    )
    for task_label in ["regression-queued", "regression-completed"]:
        job = NativeJob.objects.get(pk=ids[task_label])
        assert (
            clients["reviewer"]
            .get(f"/api/declaration/{job.dataset_id}/", **request)
            .status_code
            == 200
        )
        assert (
            clients["reviewer"].get(f"/api/declaration/{moved}/", **request).status_code
            == 403
        )
        assert (
            clients["reviewer"].get(f"/api/jobs/{job.pk}/", **request).status_code
            == 403
        )
        assert (
            clients["reviewer"]
            .get(f"/api/jobs/{job.pk}/scores/?sha256={job.result_sha256}", **request)
            .status_code
            == 403
        )
    assert snapshot(ids) == current
    print(
        json.dumps(
            {
                "private_scoring": "recover",
                "native_state_loaded": True,
                "jobs": len(ids),
                "rows_per_task": 650,
                "tasks": list(fixtures),
                "empty_broker_restored_scoring_parity": "passed",
                "natural_180_second_scoring_lease": "passed",
                "stale_result_fenced": "passed",
                "twenty_actual_duplicate_task_completions": "passed",
                "terminal_history_unchanged": "passed",
                "changed_missing_inputs_and_revoked_actor": "blocked",
                "full_http_receipts_and_preview": "passed",
                "source_scope_fault_withholds_unchanged_history": "passed",
                "production_recovery": "not_qualified",
                "expert_isolation": "not_qualified",
            }
        )
    )


if __name__ == "__main__":
    main()
