"""Additive private TLS worker and coordinated restore proof for native assessment."""

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
        raise RuntimeError("Disposable private installation required.")
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django

    django.setup()
    from access_control.projects import bind_dataset, operator_change
    from declaration.models import Declaration
    from deployment.native_candidate import sha
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db import connection
    from django.test import Client
    from execution_jobs import native_assessment as assessment
    from execution_jobs import service
    from execution_jobs.models import NativeAdoption, NativeJob, NativeProtectedInput
    from execution_jobs.preflight import check_runtime
    from modeling.holdout_evidence import HoldoutAccess

    if (
        settings.DECLARAI_RUNTIME_PROFILE != "private"
        or connection.vendor != "postgresql"
        or not connection.settings_dict["NAME"].startswith("declarai_fixture")
    ):
        raise RuntimeError("Owned private PostgreSQL fixture required.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
        assert cursor.fetchone()[0] is True
        cursor.execute(
            "SELECT format_type(atttypid,atttypmod) FROM pg_attribute "
            "WHERE attrelid='execution_jobs_nativeprotectedinput'::regclass AND attname='payload'"
        )
        assert cursor.fetchone()[0] == "bytea"
    check_runtime()
    state_root = Path(os.environ["DECLARAI_JOB_FIXTURE_STATE"])
    assert state_root.is_absolute() and not state_root.is_relative_to(ROOT)
    state = state_root.with_name("native-assessment-state.json")

    def receipt(proof):
        trained = NativeJob.objects.get(pk=proof["training_job_id"])
        job = NativeJob.objects.get(pk=proof["assessment_job_id"])
        adoption = NativeAdoption.objects.get(pk=proof["adoption_id"])
        protected = NativeProtectedInput.objects.get(pk=proof["protected_input_id"])
        access = HoldoutAccess.objects.get(pk=job.result["outcome_access_id"])
        assert trained.result_sha256 == proof["training_result_sha256"]
        assert all(
            trained.result[k] is False
            for k in ["final_holdout_accessed", "model_adopted"]
        )
        assert adoption.proposal_sha256 == proof["proposal_sha256"]
        assert adoption.events.count() == 1 and adoption.events.get().kind == "approve"
        assert protected.specification_sha256 == proof["specification_sha256"]
        assert (
            sha(bytes(protected.payload))
            == protected.specification["input_sha256"]
            == proof["input_sha256"]
        )
        assert (
            service.digest(job.result)
            == job.result_sha256
            == proof["assessment_result_sha256"]
        )
        assert job.state == "succeeded" and job.result["n_assessed"] == 60
        assert (
            job.result["evidence_status"] == "exploratory"
            and job.result["prior_related_accesses"] == 0
        )
        assert (
            job.result["candidate_adopted_for_assessment"]
            and job.result["final_holdout_accessed"]
        )
        assert all(
            job.result[k] is False
            for k in [
                "confirmatory",
                "review_approved",
                "production_use_approved",
                "legacy_projection_updated",
            ]
        )
        assert not {"scores", "labels", "payload", "model"}.intersection(job.result)
        assert (
            access.attempt_state == "completed"
            and job.events.filter(event_type="succeeded").count() == 1
        )

    if sys.argv[1:] == ["verify-restored"]:
        assert connection.settings_dict["NAME"] == "declarai_fixture_jobs_restored"
        proofs = json.loads(state.read_text())
        assert {p["task"] for p in proofs} == {"classification", "regression"}
        for proof in proofs:
            receipt(proof)
        print(
            json.dumps(
                {
                    "schema": "private_native_assessment_restore_v1",
                    "coordinated_restore": "passed",
                    "sealed_bytes_decisions_access_and_result_digests": "passed",
                    "tasks": [p["task"] for p in proofs],
                    "confirmatory": False,
                    "production_use_approved": False,
                    "customer_installation_modified": False,
                }
            )
        )
        return
    assert not sys.argv[1:]
    assert connection.settings_dict["NAME"] == "declarai_fixture"
    password = secrets.token_urlsafe(32)
    developer = get_user_model().objects.create_user(
        username="assessment-dev-" + uuid.uuid4().hex, password=password
    )
    reviewer = get_user_model().objects.create_user(
        username="assessment-reviewer-" + uuid.uuid4().hex, password=password
    )
    event, _ = operator_change(
        {
            "operation": "create",
            "name": "Private protected fixture",
            "user": developer.username,
        },
        uuid.uuid4(),
        "disposable-private-assessment",
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
            "disposable-private-assessment",
        )
    clients = {
        role: Client(enforce_csrf_checks=True) for role in ["developer", "reviewer"]
    }
    request = {"secure": True, "HTTP_HOST": settings.ALLOWED_HOSTS[0]}

    def post(role, path, body, status=200, multipart=False):
        client = clients[role]
        csrf = client.get("/api/auth/session/", **request).json()["csrf_token"]
        params = {
            "HTTP_X_CSRFTOKEN": csrf,
            "HTTP_ORIGIN": settings.CSRF_TRUSTED_ORIGINS[0],
            **request,
        }
        response = (
            client.post(path, body, **params)
            if multipart
            else client.post(
                path, json.dumps(body), content_type="application/json", **params
            )
        )
        assert response.status_code == status, (
            path,
            response.status_code,
            response.content,
        )
        return response.json()

    for role, actor in [("developer", developer), ("reviewer", reviewer)]:
        post(
            role, "/api/auth/login/", {"username": actor.username, "password": password}
        )
    processes, proofs = [], []

    def wait(identifier):
        until = time.monotonic() + 45
        while True:
            job = NativeJob.objects.get(pk=identifier)
            if job.state in service.TERMINAL:
                assert job.state == "succeeded", job.reason_code
                return job
            assert time.monotonic() < until and all(p.poll() is None for p in processes)
            time.sleep(0.05)

    try:
        with state_root.with_name("assessment-worker.log").open("wb") as log:
            for role in ["worker", "dispatcher"]:
                processes.append(
                    subprocess.Popen(
                        ["sh", str(ROOT / "docker/private-job-entrypoint.sh"), role],
                        cwd=ROOT / "backend",
                        env=os.environ.copy(),
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                    )
                )
            for task in ["classification", "regression"]:

                def outcome(i):
                    return i % 4 if task == "regression" else "bad" if i % 2 else "good"

                raw = (
                    "x,z,outcome\n"
                    + "".join(f"{i / 80},{i % 7},{outcome(i)}\n" for i in range(80))
                ).encode()
                dataset = Declaration.objects.create(
                    name="Private assessment " + task, original_name="development.csv"
                )
                dataset.file.save(
                    "private-assessment-" + uuid.uuid4().hex + ".csv", ContentFile(raw)
                )
                bind_dataset(
                    dataset, event.project_id, source="disposable-private-assessment"
                )
                base = f"/api/jobs/datasets/{dataset.pk}/"
                selected = f"?project_id={event.project_id}"
                options = {
                    "data_role": "development_only",
                    "business_understanding": {
                        "problem_type": task,
                        "objective": "Synthetic assessment",
                        "population": "Development applicants",
                        "prediction_horizon": "12 months",
                        "feature_availability": {"default": "available_at_prediction"},
                        "target_contract": {
                            "target_column": "outcome",
                            "positive_class": "bad"
                            if task == "classification"
                            else None,
                            "event_definition": "Synthetic outcome",
                            "label_maturity": "Complete follow-up",
                        },
                        "success_criteria": {
                            "primary_metric": "roc_auc"
                            if task == "classification"
                            else "rmse"
                        },
                    },
                    "features": ["x", "z"],
                    "validation": {"strategy": "random", "n_splits": 2},
                }
                p = post("developer", base + "training-input/" + selected, options)
                queued = post(
                    "developer",
                    base + selected,
                    {
                        **options,
                        "kind": p["kind"],
                        "input_sha256": p["input_sha256"],
                        "training_sha256": p["training_sha256"],
                        "request_id": str(uuid.uuid4()),
                    },
                    202,
                )
                trained = wait(queued["id"])
                proposal_body = {
                    "request_id": str(uuid.uuid4()),
                    "training_result_sha256": trained.result_sha256,
                    "rationale": "Freeze exact candidate for independent assessment.",
                }
                proposal_url = f"/api/jobs/{trained.pk}/adoptions/" + selected
                p = post("developer", proposal_url, proposal_body, 201)
                assert post("developer", proposal_url, proposal_body)["id"] == p["id"]
                adoption_url = f"/api/native-adoptions/{p['id']}/" + selected
                accepted = post(
                    "reviewer",
                    adoption_url,
                    {
                        "request_id": str(uuid.uuid4()),
                        "expected_revision": 0,
                        "proposal_sha256": p["proposal_sha256"],
                        "action": "approve",
                        "rationale": "Independent acceptance for protected exploratory assessment only.",
                    },
                )
                assert accepted["usable"] and accepted["scope"] == assessment.SCOPE
                protected_raw = (
                    "z,x,outcome\n"
                    + "".join(
                        f"{i % 7},{10 + i / 60},{outcome(i)}\n" for i in range(60)
                    )
                ).encode()
                sealed = post(
                    "reviewer",
                    f"/api/native-adoptions/{p['id']}/protected-inputs/" + selected,
                    {
                        "request_id": str(uuid.uuid4()),
                        "proposal_sha256": p["proposal_sha256"],
                        "rationale": "Synthetic disjoint population with complete follow-up; external history remains unverified.",
                        "assessment_as_of": "2026-10-21T00:00:00Z",
                        "population_and_maturity_attested": "true",
                        "file": SimpleUploadedFile(
                            "private.csv", protected_raw, content_type="text/csv"
                        ),
                    },
                    multipart=True,
                )
                protected = sealed["protected_inputs"][0]
                assert protected_raw.decode() not in json.dumps(sealed)
                preview = post(
                    "reviewer",
                    f"/api/native-protected-inputs/{protected['id']}/preview/"
                    + selected,
                    {},
                )
                body = {
                    "kind": assessment.KIND,
                    "request_id": str(uuid.uuid4()),
                    "protected_input_id": protected["id"],
                    "assessment_sha256": preview["assessment_sha256"],
                }
                queued = post("reviewer", base + selected, body, 202)
                assert post("reviewer", base + selected, body)["id"] == queued["id"]
                result = wait(queued["id"])
                assert post("reviewer", base + selected, body)["id"] == str(result.pk)
                proofs.append(
                    {
                        "task": task,
                        "training_job_id": str(trained.pk),
                        "training_result_sha256": trained.result_sha256,
                        "adoption_id": p["id"],
                        "proposal_sha256": p["proposal_sha256"],
                        "protected_input_id": protected["id"],
                        "specification_sha256": protected["specification_sha256"],
                        "input_sha256": sha(protected_raw),
                        "assessment_job_id": str(result.pk),
                        "assessment_result_sha256": result.result_sha256,
                    }
                )
                receipt(proofs[-1])
        state.write_text(json.dumps(proofs, indent=2) + "\n")
        state.chmod(0o600)
        print(
            json.dumps(
                {
                    "schema": "private_native_assessment_v1",
                    "private_tls_prefork_and_dispatcher": "passed",
                    "real_csrf_independent_review_seal_preview_submit": "passed",
                    "duplicate_single_publication": "passed",
                    "private_bytea_and_accounted_access": "passed",
                    "tasks": [p["task"] for p in proofs],
                    "rows_per_task": 60,
                    "confirmatory": False,
                    "production_use_approved": False,
                    "release_qualified": False,
                    "customer_installation_modified": False,
                }
            )
        )
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
