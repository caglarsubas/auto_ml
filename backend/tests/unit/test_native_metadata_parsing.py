"""Decoder nesting failures are invalid input, not uncertain worker execution."""

import hashlib
import json
from pathlib import Path

import pytest

from deployment.deploy_utils import bundle_dir
from deployment.evidence import verify_bundle
from access_control import projects
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob
from tests.unit.test_native_jobs import submit
from tests.unit.test_native_package_files import package, worker  # noqa: F401
from tests.unit.test_package_reviews import packaged, world  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def configured(settings):
    settings.DECLARAI_JOBS_ENABLED = True
    settings.CELERY_BROKER_URL = "redis://127.0.0.1:9/15"


def nested(shape):
    # Exercise the existing decoder's own ceiling without changing recursion,
    # byte, worker, timeout or test budgets. Both payloads fit publication.json.
    # CPython 3.12's C decoder has a different ceiling from Python calls.
    depth = 10000
    raw = b"[" * depth + b"0" + b"]" * depth if shape == "array" else b'{"c":' * depth + b"0" + b"}" * depth
    assert len(raw) < 65536
    return raw


@pytest.mark.parametrize("shape", ["array", "object"])
def test_reproduction_crosses_the_actual_decoder_ceiling(shape):
    with pytest.raises(RecursionError):
        json.loads(nested(shape))


@pytest.mark.parametrize("name", ["manifest.json", "publication.json"])
@pytest.mark.parametrize("shape", ["array", "object"])
def test_header_classifies_decoder_nesting_as_invalid_metadata(package, name, shape):
    (package.out / name).write_bytes(nested(shape))
    with pytest.raises(ValueError, match="^Package metadata nesting is unsupported\\.$"):
        service.header(7, package.identity["bundle_id"], package.sha)


@pytest.mark.parametrize("name", ["evaluation.json", "model_card.json"])
@pytest.mark.parametrize("shape", ["array", "object"])
def test_worker_blocks_decoder_nesting_without_a_result(package, worker, name, shape):
    (package.out / name).write_bytes(nested(shape))
    service.execute("owned-job")
    assert worker[0] == [{"state": "blocked", "reason": "job_package_or_budget_invalid", "result": None}]


@pytest.mark.parametrize("name", ["manifest.json", "publication.json"])
@pytest.mark.parametrize("shape", ["array", "object"])
def test_native_verifier_uses_the_same_decoder_failure_boundary(package, name, shape):
    (package.out / name).write_bytes(nested(shape))
    with pytest.raises(ValueError, match="^Package metadata nesting is unsupported\\.$"):
        verify_bundle(package.out, 7, package.identity["bundle_id"], metadata_bytes=lambda path: path.read_bytes())


@pytest.mark.parametrize("extra", [None, {"unicode": "é"}, [1, True, None], {"a": [{"b": ["value"]}]}])
def test_supported_metadata_values_and_exact_manifest_digest_remain(package, extra):
    manifest = {**package.manifest, "extra": extra}
    raw = json.dumps(manifest, ensure_ascii=False).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (package.out / "manifest.json").write_bytes(raw)
    (package.out / "publication.json").write_text(json.dumps({**package.identity, "manifest_sha256": sha}))
    assert service.header(7, package.identity["bundle_id"], sha) == (manifest, package.identity)


@pytest.mark.parametrize("name", ["manifest.json", "publication.json"])
def test_existing_syntax_errors_keep_their_decoder_type(package, name):
    (package.out / name).write_bytes(b'{"broken":')
    with pytest.raises(json.JSONDecodeError):
        service.header(7, package.identity["bundle_id"], package.sha)


def test_unexpected_execution_recursion_is_not_classified_as_bad_metadata(worker, monkeypatch):
    def unexpected(*args):
        raise RecursionError("internal-worker-failure")

    monkeypatch.setattr(service.projects, "assert_evidence_scope", unexpected)
    with pytest.raises(RecursionError, match="^internal-worker-failure$"):
        service.execute("owned-job")
    assert worker[0] == []


def test_unexpected_capture_recursion_is_not_classified_as_bad_metadata(package):
    def unexpected(path):
        raise RecursionError("internal-capture-failure")

    with pytest.raises(RecursionError, match="^internal-capture-failure$"):
        verify_bundle(package.out, 7, package.identity["bundle_id"], metadata_bytes=unexpected)


@pytest.mark.django_db(transaction=True)
@pytest.mark.auth_boundary
@pytest.mark.parametrize("name", ["manifest.json", "publication.json"])
@pytest.mark.parametrize("shape", ["array", "object"])
def test_real_admission_rejects_deep_metadata_without_queue_or_event(world, name, shape):
    out = Path(bundle_dir(world[0], world[2]["bundle_id"]))
    path = out / name
    original = path.read_bytes()
    path.write_bytes(nested(shape))
    try:
        response, _ = submit(world)
        assert response.status_code == 400 and response.json() == {"error_code": "job_request_invalid"}
        assert NativeJob.objects.count() == JobEvent.objects.count() == 0
    finally:
        path.write_bytes(original)
    assert submit(world)[0].status_code == 202
    assert NativeJob.objects.count() == JobEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.auth_boundary
@pytest.mark.parametrize("name", ["evaluation.json", "model_card.json"])
@pytest.mark.parametrize("shape", ["array", "object"])
def test_real_worker_records_one_terminal_refusal_and_recovers_on_a_fresh_request(world, name, shape):
    response, _ = submit(world)
    assert response.status_code == 202
    identifier = response.json()["id"]
    path = Path(bundle_dir(world[0], world[2]["bundle_id"])) / name
    original = path.read_bytes()
    path.write_bytes(nested(shape))
    try:
        service.execute(identifier)
        job = NativeJob.objects.get(pk=identifier)
        assert job.state == "blocked" and job.reason_code == "job_package_or_budget_invalid"
        assert job.attempts == 1 and job.result is None and job.result_sha256 == ""
        assert job.lease_token is None and job.lease_until is None
        assert list(job.events.values_list("event_type", flat=True)) == ["submitted", "started", "blocked"]
        assert list(job.events.values_list("detail", flat=True))[-1] == {"reason_code": "job_package_or_budget_invalid"}
        service.execute(identifier)
        assert identifier not in {str(value) for value in service.reconcile()}
        job.refresh_from_db()
        assert job.attempts == 1 and job.events.count() == 3 and job.result is None
    finally:
        path.write_bytes(original)
    fresh, _ = submit(world)
    assert fresh.status_code == 202 and fresh.json()["id"] != identifier
    service.execute(fresh.json()["id"])
    recovered = NativeJob.objects.get(pk=fresh.json()["id"])
    assert recovered.state == "succeeded" and recovered.attempts == 1
    assert recovered.result_sha256 == service.digest(recovered.result)


@pytest.mark.django_db(transaction=True)
@pytest.mark.auth_boundary
@pytest.mark.parametrize("shape", ["array", "object"])
@pytest.mark.parametrize("foreign", [False, True])
def test_decoder_supported_depth_gets_a_complete_scope_check(world, shape, foreign):
    from declaration.models import Declaration
    from access_control.models import Project

    target = world[0]
    if foreign:
        other = Declaration.objects.create(name="other-project-evidence")
        projects.bind_dataset(other, Project.objects.create(name="Other evidence project").pk)
        target = other.pk
    leaf = json.dumps({"relation": "same_final_rows", "file_id": target}).encode()
    depth = 2000
    raw = b"[" * depth + leaf + b"]" * depth if shape == "array" else b'{"c":' * depth + leaf + b"}" * depth
    # This is supported by the actual decoder. The old Python scope walk fails.
    json.loads(raw)
    out = Path(bundle_dir(world[0], world[2]["bundle_id"]))
    (out / "evaluation.json").write_bytes(raw)
    manifest = json.loads((out / "manifest.json").read_bytes())
    manifest["artifact_integrity"]["evaluation.json"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    manifest_raw = json.dumps(manifest).encode()
    sha = hashlib.sha256(manifest_raw).hexdigest()
    (out / "manifest.json").write_bytes(manifest_raw)
    publication = json.loads((out / "publication.json").read_bytes())
    publication["manifest_sha256"] = sha
    (out / "publication.json").write_text(json.dumps(publication))
    world[2]["manifest_sha256"] = sha
    response, _ = submit(world)
    assert response.status_code == 202
    service.execute(response.json()["id"])
    job = NativeJob.objects.get(pk=response.json()["id"])
    assert job.state == ("blocked" if foreign else "succeeded")
    assert job.reason_code == ("job_authority_changed" if foreign else "")
    assert job.attempts == 1 and job.lease_token is None
    assert (job.result is None) == foreign


@pytest.fixture
def scope_without_project(monkeypatch):
    from access_control.models import ProjectDataset
    from types import SimpleNamespace

    empty = SimpleNamespace(values_list=lambda *args, **kwargs: SimpleNamespace(first=lambda: None))
    monkeypatch.setattr(ProjectDataset.objects, "filter", lambda **kwargs: empty)


@pytest.mark.parametrize("shape", ["array", "object"])
def test_internal_cycles_still_raise_an_unexpected_recursion_error(scope_without_project, shape):
    value = [] if shape == "array" else {}
    if shape == "array":
        value.append(value)
    else:
        value["self"] = value
    with pytest.raises(RecursionError):
        projects.assert_evidence_scope(value, 7)


def test_shared_acyclic_values_remain_unchanged(scope_without_project):
    leaf = {"relation": "same_final_rows", "file_id": 7}
    value = {"first": [leaf], "second": [leaf]}
    projects.assert_evidence_scope(value, 7)
    assert value == {"first": [leaf], "second": [leaf]}
    assert value["first"][0] is value["second"][0] is leaf
