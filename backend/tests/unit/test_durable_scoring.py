"""Exact governed CSV jobs: native parity, limits, authority, fencing and replay."""

import json
import uuid
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta
import numpy as np
import pandas as pd
import pytest
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.test import Client
from access_control import projects
from access_control.models import Project, ProjectDataset, ProjectMembership
from declaration.models import Declaration
from deployment.deploy_utils import score_frame, build_deployment_pack_zip
from deployment.offline_verify import verify_package
from deployment.scoring_receipts import byte_digest
from execution_jobs import service, csv_scoring
from execution_jobs.models import NativeJob
from tests.unit.test_package_reviews import world, packaged, post  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def configured(settings):
    settings.DECLARAI_JOBS_ENABLED = True


@pytest.fixture
def source(world, settings):
    relative = "data_files/batch.csv"
    pd.DataFrame({"x": np.linspace(-2, 2, 650), "other": np.linspace(1, 3, 650)}).to_csv(
        Path(settings.MEDIA_ROOT) / relative, index=False
    )
    dataset = Declaration.objects.create(name="batch", original_name="batch.csv", file=relative)
    projects.bind_dataset(dataset, world[1].pk)
    return dataset


def submit(world, source, role="developer", **overrides):
    metadata = csv_scoring.prepare(world[3]["developer"], source.pk)
    data = {
        "request_id": str(uuid.uuid4()),
        "kind": csv_scoring.KIND,
        "bundle_id": world[2]["bundle_id"],
        "manifest_sha256": world[2]["manifest_sha256"],
        "input_file_id": source.pk,
        "input_sha256": metadata["sha256"],
        **overrides,
    }
    return post(world[4][role], f"/api/jobs/datasets/{world[0]}/", data), data


def test_real_native_job_parity_full_digest_receipt_and_offline_replay(world, source, tmp_path):
    response, body = submit(world, source)
    assert response.status_code == 202, response.content
    identifier = response.json()["id"]
    retry = post(world[4]["developer"], f"/api/jobs/datasets/{world[0]}/", body)
    assert retry.status_code == 200 and retry.json()["replayed"]
    frame = pd.read_csv(source.get_file_path())
    expected = score_frame(world[0], frame, world[2]["bundle_id"])
    service.execute(identifier)
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "succeeded" and job.attempts == 1
    np.testing.assert_allclose(job.result["scores"], expected["scores"], atol=1e-12, rtol=1e-12)
    assert job.source_dataset_id == source.pk and job.result["n_scored"] == 650
    brief = world[4]["reviewer"].get(f"/api/jobs/{identifier}/").json()
    assert "scores" not in brief["result"] and len(brief["result"]["scores_preview"]) == 500
    assert brief["result_sha256"] == service.digest(job.result)
    url = f"/api/jobs/{identifier}/scores/?sha256={brief['result_sha256']}"
    download = world[4]["reviewer"].get(url)
    assert download.status_code == 200 and byte_digest(download.content) == job.result_sha256
    assert json.loads(download.content)["scores"] == job.result["scores"]
    assert not job.result["review_approved"] and not job.result["production_use_approved"]
    assert world[4]["outsider"].get(url).status_code == 403
    assert world[4]["developer"].get(url.replace(job.result_sha256, "0" * 64)).status_code == 409
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(download.content)
    package = tmp_path / "package.zip"
    package.write_bytes(build_deployment_pack_zip(world[0], body["bundle_id"])[0])
    report = verify_package(
        package,
        source.get_file_path(),
        receipt,
        package_sha256=byte_digest(package.read_bytes()),
        receipt_sha256=job.result_sha256,
        manifest_sha256=body["manifest_sha256"],
        atol=1e-12,
        rtol=1e-12,
        chunk_sizes=(1, 17),
        trust_native_state=True,
    )
    assert report["status"] == "passed"
    with pytest.raises(ProtectedError):
        source.delete()


@pytest.mark.parametrize("role", ["reviewer", "admin", "outsider"])
def test_scoring_requires_developer_authority(world, source, role):
    assert submit(world, source, role)[0].status_code == 403
    assert not NativeJob.objects.exists()


@pytest.mark.parametrize("case", ["sha", "id", "extra", "cross_project", "header", "symlink", "bytes"])
def test_bad_or_cross_project_source_never_admitted(world, source, case, settings):
    if case == "sha":
        assert submit(world, source, input_sha256="0" * 64)[0].status_code == 409
    elif case == "id":
        assert submit(world, source, input_file_id=True)[0].status_code == 400
    elif case == "extra":
        assert submit(world, source, code="print(1)")[0].status_code == 400
    else:
        if case == "cross_project":
            project = Project.objects.create(name="Other input")
            ProjectMembership.objects.create(actor=world[3]["developer"], project=project, role="developer")
            ProjectDataset.objects.filter(dataset=source).update(project=project)
            assert submit(world, source)[0].status_code == 403
        else:
            path = Path(source.get_file_path())
            if case == "header":
                source.has_header = False
                source.save()
            elif case == "symlink":
                path.unlink()
                path.symlink_to(Path(settings.MEDIA_ROOT) / "data_files/review.csv")
            else:
                path.write_bytes(b"x" * (csv_scoring.BUDGET["max_input_bytes"] + 1))
            assert world[4]["developer"].get(f"/api/jobs/datasets/{source.pk}/input/").status_code == 409
    assert not NativeJob.objects.exists()


@pytest.mark.parametrize(
    "change", ["input", "path", "binding", "member", "runtime", "cancel", "expiry", "bad_csv", "rows", "columns"]
)
def test_changed_inputs_or_authority_and_invalid_csv_never_publish(world, source, change):
    if change in {"bad_csv", "rows", "columns"}:
        path = Path(source.get_file_path())
        if change == "bad_csv":
            path.write_bytes(b'x,other\n"unterminated')
        elif change == "rows":
            path.write_text("x,other\n" + "1,2\n" * 10001)
        else:
            path.write_text(",".join("c" + str(i) for i in range(257)) + "\n")
    response, _ = submit(world, source)
    assert response.status_code == 202
    job = NativeJob.objects.get(pk=response.json()["id"])
    if change == "input":
        Path(source.get_file_path()).write_text("x,other\n999,999\n")
    elif change == "path":
        source.file = "data_files/review.csv"
        source.save()
    elif change == "binding":
        ProjectDataset.objects.filter(dataset=source).update(revision=uuid.uuid4())
    elif change == "member":
        ProjectMembership.objects.filter(actor=world[3]["developer"]).update(active=False)
    elif change == "runtime":
        job.specification["runtime"]["scoring"]["python_version"] = "invalid"
        job.save()
    elif change == "cancel":
        service.cancel(world[3]["developer"], job.pk, {"action": "cancel"})
    elif change == "expiry":
        job.expires_at = timezone.now() - timedelta(seconds=1)
        job.save()
    service.execute(job.pk)
    job.refresh_from_db()
    assert job.state in {"blocked", "failed", "cancelled"} and job.result is None


def test_revocation_or_cancellation_after_scoring_withholds_atomic_result(world, source):
    response, _ = submit(world, source)
    identifier = response.json()["id"]
    original = service.finish

    def cancel(*args, **kwargs):
        service.cancel(world[3]["developer"], identifier, {"action": "cancel"})
        return original(*args, **kwargs)

    with patch("execution_jobs.service.finish", side_effect=cancel):
        service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "cancelled" and not job.result and not job.result_sha256


def test_input_binding_revocation_withholds_prior_results(world, source):
    response, body = submit(world, source)
    service.execute(response.json()["id"])
    job = NativeJob.objects.get()
    other = Project.objects.create(name="Unrelated")
    ProjectDataset.objects.filter(dataset=source).update(project=other, revision=uuid.uuid4())
    assert world[4]["developer"].get(f"/api/jobs/{job.pk}/").status_code == 403
    assert world[4]["developer"].get(f"/api/jobs/{job.pk}/scores/?sha256={job.result_sha256}").status_code == 403
    assert post(world[4]["developer"], f"/api/jobs/datasets/{world[0]}/", body).status_code == 403


def test_recovered_scoring_attempt_fences_late_result_and_duplicate_delivery(world, source):
    response, _ = submit(world, source)
    identifier = response.json()["id"]
    _, stale_token = service.claim(identifier)
    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1))
    assert identifier in {str(pk) for pk in service.reconcile()}
    service.finish(identifier, stale_token, "succeeded", result={"scores": [999]})
    assert NativeJob.objects.get(pk=identifier).result is None
    service.execute(identifier)
    job = NativeJob.objects.get(pk=identifier)
    assert job.state == "succeeded" and job.attempts == 2 and job.result["n_scored"] == 650
    sha = job.result_sha256
    service.finish(identifier, stale_token, "succeeded", result={"scores": [999]})
    service.execute(identifier)
    job.refresh_from_db()
    assert job.result_sha256 == sha and job.attempts == 2


def test_output_budget_and_tampered_results_block(world, source):
    response, _ = submit(world, source)
    with patch.dict(csv_scoring.BUDGET, max_output_bytes=1):
        # Preserve the submitted budget to reach the actual output boundary.
        job = NativeJob.objects.get()
        job.specification["limits"] = service.limits(csv_scoring.KIND)
        job.save()
        service.execute(response.json()["id"])
    assert NativeJob.objects.get().state == "blocked"
    response, _ = submit(world, source)
    service.execute(response.json()["id"])
    job = NativeJob.objects.get(pk=response.json()["id"])
    job.result["scores"][0] = 999
    job.save()
    assert world[4]["developer"].get(f"/api/jobs/{job.pk}/scores/?sha256={job.result_sha256}").status_code == 409


def test_source_prepare_and_jobs_obey_real_csrf_and_project_selector(world, source):
    assert Client().get(f"/api/jobs/datasets/{source.pk}/input/").status_code == 403
    client = Client(enforce_csrf_checks=True)
    client.force_login(world[3]["developer"])
    _, body = submit(world, source, role="admin")
    assert post(client, f"/api/jobs/datasets/{world[0]}/", body).status_code == 403
    assert (
        world[4]["developer"].get(f"/api/jobs/datasets/{source.pk}/input/?project_id={uuid.uuid4()}").status_code == 403
    )
