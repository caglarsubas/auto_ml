"""Opt-in snapshot evaluation: independent writers, live authority and exact bytes."""

import json
import threading
import uuid
from datetime import timedelta

import pytest
from django.db import DatabaseError, connection, connections, transaction
from django.http import QueryDict
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from access_control import projects
from access_control.models import Project, ProjectDataset, ProjectMembership
from declaration.models import Declaration
from execution_jobs import read_snapshots as snapshots, service
from execution_jobs.models import JobEvent, NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import world as training_world  # noqa: F401
from tests.unit.test_native_handoff_history_counter import world  # noqa: F401
from tests.unit.test_native_training_scoring import candidate as trained_fixture, preview, submit

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def request(world, query="", method="get", actor=None):
    client = APIClient()
    if actor is not False:
        client.force_authenticate(user=actor or world.actor)
    return getattr(client, method)(f"/api/jobs/{world.job.pk}/snapshot/?{query}")


def supported(world):
    if connection.vendor != "postgresql":
        response = request(world)
        assert response.status_code == 409 and response.json() == {"error_code": "job_snapshot_backend_unsupported"}
        assert response["Cache-Control"] == "no-store"
        return False
    return True


def event(world, count=1):
    JobEvent.objects.bulk_create([JobEvent(job=world.job, revision=n, event_type="observed") for n in range(1, count + 1)])
    NativeJob.objects.filter(pk=world.job.pk).update(revision=count)


@pytest.mark.parametrize("query", ["unknown=x", "revision=1&revision=1", "revision=-1", "revision=01", "revision=",
                                  "revision=2147483648", "revision=1.0", "representation=other", "sha256=" + "a" * 64,
                                  "representation=scores", "representation=candidate&sha256=bad"])
def test_parameters_fail_before_native_materialization(query):
    with pytest.raises(ValueError):
        snapshots.parameters(QueryDict(query))


@pytest.mark.parametrize("revision", ["0", "1", "2147483647"])
def test_canonical_revision_and_digest_are_exact(revision):
    assert snapshots.parameters(QueryDict("revision=" + revision)) == ("receipt", int(revision), None)
    assert snapshots.parameters(QueryDict("representation=scores&revision=" + revision + "&sha256=" + "a" * 64)) == ("scores", int(revision), "a" * 64)


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("actor", ["anonymous", "outsider", "revoked"])
def test_early_denials_are_uncached_without_full_job_read(world, method, actor):
    if actor == "revoked":
        ProjectMembership.objects.filter(actor=world.actor).update(active=False)
    with CaptureQueriesContext(connection) as captured:
        response = request(world, method=method, actor=False if actor == "anonymous" else world.outsider if actor == "outsider" else world.actor)
    assert response.status_code == 403 and response["Cache-Control"] == "no-store"
    assert not any('"execution_jobs_nativejob"."result"' in q["sql"] for q in captured)
    if method == "head":
        assert response.content == b""


@pytest.mark.parametrize("count", [0, 1, 32])
def test_receipt_matches_legacy_without_queue_lock_or_any_write(world, count):
    if not supported(world):
        return
    event(world, count)
    with CaptureQueriesContext(connection) as captured:
        raw = snapshots.read(world.actor, world.job.pk, QueryDict(f"revision={count}")).raw
    captured = list(captured)
    response = request(world, f"revision={count}")
    assert response.status_code == 200, response.content
    value = response.json()
    assert value["receipt"] == json.loads(raw)["receipt"] == service.read(world.actor, world.job.pk)
    assert value["schema"] == "native_job_snapshot_v1" and value["read_only"] and value["revision"] == count
    assert "lease_token" not in response.content.decode() and "authority" not in response.content.decode()
    assert response["X-DeclarAI-Snapshot-Revision"] == str(count) and response["Cache-Control"] == "no-store"
    assert not any("execution_jobs_queuelock" in q["sql"] or "FOR UPDATE" in q["sql"]
                   or q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in captured), [q["sql"] for q in captured]
    event_reads = [q for q in captured if 'FROM "execution_jobs_jobevent"' in q["sql"]]
    assert len(event_reads) == 2 and all(f"LIMIT {snapshots.MAX_EVENTS + 1}" in q["sql"] for q in event_reads)
    assert HoldoutAccess.objects.count() == 0


@pytest.mark.parametrize("fault", ["revision", "state", "reason", "lease", "event", "result"])
def test_changes_during_encoding_never_return_mixed_or_partial_bytes(world, monkeypatch, fault):
    if not supported(world):
        return
    event(world)
    original = snapshots._materialize

    def changing(*args):
        raw = original(*args)
        if fault == "event":
            JobEvent.objects.filter(job=world.job).update(detail={"changed": True})
        else:
            changes = {"revision": {"revision": 2}, "state": {"state": "cancelled"},
                       "reason": {"reason_code": "changed"}, "lease": {"lease_token": uuid.uuid4()},
                       "result": {"result": {"changed": True}, "result_sha256": "a" * 64}}[fault]
            NativeJob.objects.filter(pk=world.job.pk).update(**changes)
        return raw
    monkeypatch.setattr(snapshots, "_materialize", changing)
    response = request(world, "revision=1")
    assert response.status_code == 409 and response.json() == {"error_code": "job_snapshot_stale"}
    assert "X-DeclarAI-Snapshot-Revision" not in response and response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("fault", ["membership", "binding", "source_binding", "source_membership", "actor"])
def test_late_live_authority_changes_deny_prepared_payload(world, monkeypatch, fault):
    if not supported(world):
        return
    source = Declaration.objects.create(name="Snapshot source")
    projects.bind_dataset(source, world.job.project_id)
    NativeJob.objects.filter(pk=world.job.pk).update(source_dataset=source)
    original = snapshots._materialize

    def changing(*args):
        raw = original(*args)
        if fault == "actor":
            type(world.actor).objects.filter(pk=world.actor.pk).update(is_active=False)
        elif fault in {"membership", "source_membership"}:
            ProjectMembership.objects.filter(actor=world.actor).update(revision=uuid.uuid4())
        else:
            dataset_id = source.pk if fault == "source_binding" else world.job.dataset_id
            ProjectDataset.objects.filter(dataset_id=dataset_id).update(revision=uuid.uuid4())
        return raw
    monkeypatch.setattr(snapshots, "_materialize", changing)
    response = request(world)
    assert response.status_code == 403 and response["Cache-Control"] == "no-store"
    assert set(response.json()) == {"error_code"} and "X-DeclarAI-Snapshot-Revision" not in response


@pytest.mark.parametrize("fault", ["missing", "gap", "large", "too_many", "detail"])
def test_history_failures_have_structured_bounded_diagnostics(world, fault):
    if not supported(world):
        return
    if fault == "too_many":
        event(world, snapshots.MAX_EVENTS + 1)
    elif fault == "gap":
        JobEvent.objects.create(job=world.job, revision=2, event_type="fixture")
        NativeJob.objects.filter(pk=world.job.pk).update(revision=1)
    elif fault == "detail":
        event(world)
        JobEvent.objects.filter(job=world.job).update(detail=[])
    else:
        NativeJob.objects.filter(pk=world.job.pk).update(revision=2**31 - 1 if fault == "large" else 1)
    response = request(world)
    assert response.status_code == 409 and response.json() == {"error_code": "job_snapshot_budget_exceeded" if fault == "too_many" else "job_snapshot_history_invalid"}


@pytest.mark.parametrize("fault", ["stale_pin", "tampered_result", "wrong_project", "storage", "budget"])
def test_failure_boundaries_return_no_public_receipt(world, monkeypatch, fault):
    if not supported(world):
        return
    query = ""
    if fault == "stale_pin":
        query = "revision=1"
    elif fault == "tampered_result":
        NativeJob.objects.filter(pk=world.job.pk).update(result={"x": 1}, result_sha256="a" * 64)
    elif fault == "wrong_project":
        NativeJob.objects.filter(pk=world.job.pk).update(project=Project.objects.create(name="Other"))
    elif fault == "storage":
        monkeypatch.setattr(snapshots, "_events", lambda job: (_ for _ in ()).throw(DatabaseError("private diagnostics")))
    else:
        monkeypatch.setattr(snapshots, "MAX_SECONDS", -1)
    response = request(world, query)
    assert response.status_code == (503 if fault == "storage" else 403 if fault == "wrong_project" else 409)
    assert "receipt" not in response.json() and "private diagnostics" not in response.content.decode()
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("level", ["REPEATABLE READ", "SERIALIZABLE"])
def test_stronger_caller_isolation_is_explicitly_unsupported_and_preserved(world, level):
    if not supported(world):
        return
    # The setup committed before opening the caller transaction.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL " + level)
        with pytest.raises(service.JobConflict, match="job_snapshot_isolation_unsupported"):
            snapshots.read(world.actor, world.job.pk, QueryDict())
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_isolation")
            assert cursor.fetchone()[0] == level.lower()


@pytest.mark.parametrize("timeout", ["1250ms", "12s"])
def test_nested_statement_budget_is_not_relaxed_and_restores_caller(world, monkeypatch, timeout):
    if not supported(world):
        return
    original = snapshots._materialize
    observed = []

    def inspect(*args):
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            observed.append(cursor.fetchone()[0])
        return original(*args)
    monkeypatch.setattr(snapshots, "_materialize", inspect)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('statement_timeout', %s, true)", [timeout])
        assert snapshots.read(world.actor, world.job.pk, QueryDict()).revision == 0
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            assert cursor.fetchone()[0] == timeout
    assert observed == ["1250ms" if timeout == "1250ms" else "5s"]


def test_independent_writer_can_commit_while_snapshot_materializes(world, monkeypatch):
    if not supported(world):
        return
    finished, failures = threading.Event(), []
    original = snapshots._materialize

    def write():
        try:
            with service.locked():
                job = NativeJob.objects.select_for_update().get(pk=world.job.pk)
                job.state = "cancelled"
                service.record(job, "cancelled", update_fields=["state", "revision"])
        except BaseException as exc:
            failures.append(exc)
        finally:
            connections.close_all()
            finished.set()

    def paused(*args):
        raw = original(*args)
        worker = threading.Thread(target=write, daemon=True)
        worker.start()
        assert finished.wait(3), "snapshot blocked the independent execution writer"
        worker.join(timeout=1)
        assert not failures
        return raw
    monkeypatch.setattr(snapshots, "_materialize", paused)
    response = request(world)
    assert response.status_code == 409 and response.json() == {"error_code": "job_snapshot_stale"}
    world.job.refresh_from_db()
    assert world.job.state == "cancelled" and world.job.revision == 1


def test_private_fence_preserves_timestamp_precision_and_json_types(world):
    job = world.job
    before = snapshots._fence(job, [])
    job.lease_token = uuid.uuid4()
    assert snapshots._fence(job, []) != before
    job.lease_token = None
    job.created_at += timedelta(microseconds=1)
    assert snapshots._fence(job, []) != before
    job.result = {"x": True}
    boolean = snapshots._fence(job, [])
    job.result = {"x": 1}
    assert snapshots._fence(job, []) != boolean


def test_direct_service_project_selector_cannot_broaden_or_ignore_scope(world):
    if not supported(world):
        return
    other = Project.objects.create(name="Other authorized project")
    ProjectMembership.objects.create(project=other, actor=world.actor, role="reviewer")
    with pytest.raises(projects.ProjectDenied) as denied:
        snapshots.read(world.actor, world.job.pk, QueryDict(f"project_id={other.pk}"))
    assert denied.value.code == "job_project_mismatch"
    assert snapshots.read(world.actor, world.job.pk, QueryDict(f"project_id={world.job.project_id}")).revision == 0


def test_database_cancellation_restores_stricter_caller_timeout(world, monkeypatch):
    if not supported(world):
        return

    def slow(job):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(0.1)")
        pytest.fail("stricter caller statement timeout was relaxed")
    monkeypatch.setattr(snapshots, "_events", slow)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('statement_timeout', '50ms', true)")
        with pytest.raises(DatabaseError):
            snapshots.read(world.actor, world.job.pk, QueryDict())
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            assert cursor.fetchone()[0] == "50ms"


def test_successful_head_has_revision_but_no_body(world):
    if not supported(world):
        return
    response = request(world, method="head")
    assert response.status_code == 200 and response.content == b"" and response["Cache-Control"] == "no-store"
    assert response["X-DeclarAI-Snapshot-Revision"] == "0"


@pytest.fixture
def candidate(training_world):
    return trained_fixture.__wrapped__(training_world)


@pytest.mark.parametrize("representation", ["candidate", "scores"])
def test_real_native_download_matches_legacy_bytes_and_digest(candidate, representation):
    w = candidate
    if representation == "scores":
        identifier = submit(w, preview(w))
        service.execute(identifier)
        job = NativeJob.objects.get(pk=identifier)
    else:
        job = w.trained
    client = w.clients["reviewer"]
    response = client.get(f"/api/jobs/{job.pk}/snapshot/?representation={representation}&revision={job.revision}&sha256={job.result_sha256}")
    if connection.vendor != "postgresql":
        assert response.status_code == 409 and response.json()["error_code"] == "job_snapshot_backend_unsupported"
        return
    legacy = client.get(f"/api/jobs/{job.pk}/{representation}/?sha256={job.result_sha256}")
    assert response.status_code == legacy.status_code == 200
    assert response.content == legacy.content
    header = "X-DeclarAI-Receipt-SHA256" if representation == "scores" else "X-DeclarAI-Export-SHA256"
    assert response[header] == legacy[header] and response["Content-Disposition"] == legacy["Content-Disposition"]
    assert response["X-DeclarAI-Snapshot-Revision"] == str(job.revision)
    assert response["Cache-Control"] == "no-store" and json.loads(response.content)
