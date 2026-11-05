"""Family-specific admitted requests exercise actual shared queue transactions.

Rejected synthetic output is a publication-fence probe, never model evidence.
Positive/lost-ack cases execute the real kernels. Installed natural-lease and
broker-loss drills remain independently required.
"""

import copy
import hashlib
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pandas as pd
import pytest
from django.conf import settings
from django.db import DatabaseError, connections
from django.utils import timezone

from access_control import projects
from access_control.models import ProjectMembership
from declaration.models import Declaration
from execution_jobs import service, training_scoring
from execution_jobs.models import NativeJob
from tests.unit import test_durable_training_search as native
from tests.unit import test_native_protected_assessment as protected
from tests.unit.test_package_reviews import packaged, world as package_world  # noqa: F401
from tests.unit.test_durable_training_search import world as native_world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
FAULTS = ("queued_cancel", "running_cancel", "duplicate_claim", "expired_request", "stale_token",
          "expired_lease", "missing_lease", "exhausted_attempts", "runtime_changed", "limits_changed", "revoked",
          "expired_during_work", "deadline_elapsed", "scope_changed")


def row(identifier):
    return NativeJob.objects.get(pk=identifier)


def terminal(job):
    job.refresh_from_db()
    assert job.state in service.TERMINAL
    assert job.events.filter(event_type__in=service.TERMINAL).count() == 1
    assert job.result is None and not job.result_sha256
    return {"job_id": str(job.pk), "request_sha256": job.request_sha256,
            "specification_sha256": service.digest(job.specification),
            "state": job.state, "reason": job.reason_code, "events": job.events.count(),
            "terminal_events": 1, "published_results": 0, "attempts": job.attempts}


def fences(factory, actor):
    outcomes = []
    for fault in FAULTS:
        identifier = factory()
        job = row(identifier)
        assert job.state == "queued" and job.attempts == 0
        if fault == "queued_cancel":
            service.cancel(actor, identifier, {"action": "cancel"})
            service.execute(identifier)
        elif fault in {"expired_request", "exhausted_attempts"}:
            NativeJob.objects.filter(pk=identifier).update(**(
                {"expires_at": timezone.now() - timedelta(seconds=1)} if fault == "expired_request"
                else {"attempts": service.LIMITS["attempts"]}))
            assert service.claim(identifier) is None
        else:
            claimed = service.claim(identifier)
            assert claimed is not None
            job, token = claimed
            member = ProjectMembership.objects.get(project=job.project, actor=actor)
            if fault in {"running_cancel", "duplicate_claim"}:
                if fault == "duplicate_claim":
                    assert service.claim(identifier) is None
                service.cancel(actor, identifier, {"action": "cancel"})
                with pytest.raises(service.JobStopped):
                    service.checkpoint(identifier, token, time.monotonic() + 120)
            elif fault == "stale_token":
                service.finish(identifier, uuid.uuid4(), "succeeded", result={"forbidden": True})
                assert row(identifier).state == "running" and row(identifier).result is None
                service.cancel(actor, identifier, {"action": "cancel"})
            elif fault in {"expired_lease", "missing_lease"}:
                NativeJob.objects.filter(pk=identifier).update(lease_until=(
                    timezone.now() - timedelta(seconds=1) if fault == "expired_lease" else None))
                service.finish(identifier, token, "succeeded", result={"forbidden": True})
                assert row(identifier).result is None
                if fault == "expired_lease":
                    service.reconcile()
                    assert row(identifier).state == "queued"
                    service.cancel(actor, identifier, {"action": "cancel"})
                else:
                    # A missing lease needs operator reconciliation; it is not repaired.
                    before = list(job.events.values_list("revision", "event_type"))
                    service.reconcile()
                    assert row(identifier).state == "running" and row(identifier).lease_until is None
                    assert list(job.events.values_list("revision", "event_type")) == before
                    outcomes.append({"fault": fault, "state": "running", "published_results": 0,
                                     "operator_reconciliation_required": True})
                    # Test-only cleanup after recording refusal, not a recovery qualification.
                    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1))
                    service.reconcile()
                    service.cancel(actor, identifier, {"action": "cancel"})
                    continue
            elif fault in {"runtime_changed", "limits_changed"}:
                spec = copy.deepcopy(job.specification)
                if fault == "runtime_changed":
                    spec["runtime"]["python"] = "unapproved-runtime"
                else:
                    spec["limits"]["max_active"] += 1
                NativeJob.objects.filter(pk=identifier).update(specification=spec)
            elif fault == "revoked":
                ProjectMembership.objects.filter(pk=member.pk).update(active=False)
            elif fault == "expired_during_work":
                NativeJob.objects.filter(pk=identifier).update(expires_at=timezone.now() - timedelta(seconds=1))
            elif fault == "scope_changed":
                authority = {**job.authority, "file_id": job.dataset_id + 10000}
                NativeJob.objects.filter(pk=identifier).update(authority=authority)
            try:
                service.finish(identifier, token, "succeeded", result={"forbidden": True},
                               deadline=time.monotonic() + (-1 if fault == "deadline_elapsed" else 120))
            finally:
                if fault == "revoked":
                    ProjectMembership.objects.filter(pk=member.pk).update(active=True)
        result = terminal(job)
        before = list(job.events.values_list("revision", "event_type"))
        service.execute(identifier)
        assert list(job.events.values_list("revision", "event_type")) == before
        outcomes.append({"fault": fault, **result})
    return outcomes


def execute_with_lost_ack(factory, monkeypatch):
    identifier = factory()
    captured = {}
    actual = service.record

    def record(job, kind, **kwargs):
        if kind == "succeeded" and not captured:
            captured.update(token=row(job.pk).lease_token, result=copy.deepcopy(job.result))
            raise DatabaseError("synthetic lost publication acknowledgement")
        return actual(job, kind, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(service, "record", record)
        with pytest.raises(DatabaseError):
            service.execute(identifier)
    job = row(identifier)
    assert job.state == "running" and job.result is None and not job.result_sha256
    assert captured["result"] and job.events.filter(event_type="succeeded").count() == 0
    service.finish(identifier, captured["token"], "succeeded", result=captured["result"],
                   deadline=time.monotonic() + 120)
    job.refresh_from_db()
    assert job.state == "succeeded" and job.result_sha256 == service.digest(captured["result"])
    assert job.attempts == 1 and job.events.filter(event_type="succeeded").count() == 1
    before = list(job.events.values_list("revision", "event_type"))
    service.execute(identifier)
    service.finish(identifier, captured["token"], "succeeded", result={"forbidden": True})
    job.refresh_from_db()
    assert job.result == captured["result"] and list(job.events.values_list("revision", "event_type")) == before
    label_access = None
    if job.specification["kind"] == service.native_assessment.KIND:
        from modeling.models import HoldoutAccess

        access = HoldoutAccess.objects.get(pk=job.result["outcome_access_id"])
        assert access.attempt_state == "completed"
        assert job.result["evidence_status"] == "exploratory" and job.result["confirmatory"] is False
        label_access = {"id": str(access.pk), "attempt_state": access.attempt_state, "confirmatory": False}
    return {"fault": "publication_ack_loss_and_duplicate_delivery", "job_id": str(job.pk), "state": "succeeded",
            "terminal_events": 1, "published_results": 1, "result_sha256": job.result_sha256,
            "retained_label_access": label_access,
            "review_approved": job.result.get("review_approved", False), "production_use_approved": False}


def report(name, families, observations=None):
    assert all(len(values) == len(FAULTS) + 1 for values in families.values())
    # CI already explicitly owns this disposable test installation. Keep local
    # ordinary unit runs within tmp media; only native fixture runs retain receipts.
    if os.environ.get("DECLARAI_TEST_INSTALLATION") == "1":
        root = Path(settings.BASE_DIR).parent
        destination = root / "test-reports/postgresql/failure-matrix"
        destination.mkdir(parents=True, exist_ok=True)
        paths = [Path(__file__), Path(__file__).with_name("test_d07_failure_matrix_legacy.py"), Path(service.__file__)]
        value = {"schema": "private_job_failure_matrix_v1", "group": name, "families": families,
                 "observations": observations or {},
                 "case_count": sum(map(len, families.values())), "synthetic_only": True,
                 "fault_scope": "valid admissions and real queue transactions; rejected synthetic output is not model evidence",
                 "unit_expiry_faults_modify_metadata": True, "installed_natural_lease_drill_required_separately": True,
                 "sources": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                 "native_limit_seconds": 900, "lease_seconds": service.LIMITS["lease_seconds"],
                 "max_active": service.LIMITS["max_active"], "attempt_limit": service.LIMITS["attempts"],
                 "release_qualified": False, "customer_accepted": False}
        (destination / (name + ".json")).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def test_package_and_csv_family_failure_matrix(package_world, monkeypatch, settings):
    from execution_jobs import csv_scoring

    settings.DECLARAI_JOBS_ENABLED = True
    file_id, project, bundle, users, _ = package_world
    path = Path(settings.MEDIA_ROOT) / "data_files/matrix-input.csv"
    pd.DataFrame({"x": [-1., 0., 1.], "other": [0., 1., 2.]}).to_csv(path, index=False)
    dataset = Declaration.objects.create(name="Matrix scoring", file="data_files/matrix-input.csv")
    projects.bind_dataset(dataset, project.pk)
    actor = users["developer"]
    records = {}
    for name, kind in [("package_integrity", service.KIND), ("package_csv_scoring", csv_scoring.KIND)]:
        def factory():
            data = {"request_id": str(uuid.uuid4()), "kind": kind,
                    "bundle_id": bundle["bundle_id"], "manifest_sha256": bundle["manifest_sha256"]}
            if kind == csv_scoring.KIND:
                data.update(input_file_id=dataset.pk, input_sha256=csv_scoring.prepare(actor, dataset.pk)["sha256"])
            queued = service.submit(actor, file_id, data)
            assert service.submit(actor, file_id, data)["id"] == queued["id"]
            return queued["id"]
        records[name] = fences(factory, actor) + [execute_with_lost_ack(factory, monkeypatch)]
    report("packages", records)


def test_native_and_protected_family_failure_matrix(native_world, monkeypatch):
    w = native_world
    trained = native.queue(w, native.admission(w)[0])
    service.execute(trained)
    w.trained = row(trained)
    assert w.trained.state == "succeeded"
    path = w.root / "data_files/matrix-candidate.csv"
    pd.DataFrame({"x": [-1., 0., 1.], "z": [1., 2., 3.]}).to_csv(path, index=False)
    dataset = Declaration.objects.create(name="Matrix candidate", file="data_files/matrix-candidate.csv")
    projects.bind_dataset(dataset, w.project.pk)
    adoption = protected.approve(w, protected.proposal(w))
    sealed = protected.seal(w, adoption)[0]

    def training_factory():
        return native.queue(w, native.admission(w)[0])

    def scoring_factory():
        preview = native.post(w.clients["developer"], f"/api/jobs/{trained}/scoring-input/", {
            "input_file_id": dataset.pk, "training_result_sha256": w.trained.result_sha256})
        assert preview.status_code == 200, preview.content
        data = {k: preview.json()[k] for k in training_scoring.FIELDS}
        return native.queue(w, {**data, "kind": training_scoring.KIND, "request_id": str(uuid.uuid4())})

    factories = [("native_training_search", training_factory, w.users["developer"]),
                 ("native_candidate_scoring", scoring_factory, w.users["developer"]),
                 ("protected_assessment", lambda: protected.queued(w, sealed), w.users["reviewer"])]
    records = {}
    for name, factory, actor in factories:
        records[name] = fences(factory, actor)
    # Distinct valid job families contend for the same two slots, using real DB connections.
    identifiers = [factory() for _, factory, _ in factories]
    barrier = Barrier(3)

    def claim(identifier):
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            return service.claim(identifier) is not None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=3) as pool:
        claims = list(pool.map(claim, identifiers))
        assert sum(claims) == 2
    assert NativeJob.objects.filter(state="running").count() == 2
    for identifier, (_, _, actor) in zip(identifiers, factories):
        job = row(identifier)
        service.cancel(actor, identifier, {"action": "cancel"})
        if job.lease_token:
            service.finish(identifier, job.lease_token, "succeeded", result={"forbidden": True})
        terminal(job)
    for name, factory, _ in factories:
        records[name].append(execute_with_lost_ack(factory, monkeypatch))
    report("native", records, {"mixed_family_contention": {
        "families": [name for name, _, _ in factories], "simultaneous_claims": 3, "claimed": sum(claims),
        "pending": claims.count(False), "terminal_cancellations": 3, "published_results": 0}})
