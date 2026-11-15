"""Protected assessment adjudication from attributable access metadata."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from access_control.models import Project, ProjectDataset
from declaration.models import Declaration
from execution_jobs import assessment_reuse, training_search
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

WINDOW = {
    "start": "2026-04-01T00:00:00.000000000+00:00",
    "end": "2026-05-01T00:00:00.000000000+00:00",
}
OVERLAP = {
    "start": "2026-05-01T00:00:00.000000000+00:00",
    "end": "2026-06-01T00:00:00.000000000+00:00",
}
DISJOINT = {
    "start": "2026-05-01T00:00:00.000000001+00:00",
    "end": "2026-06-01T00:00:00.000000000+00:00",
}
INPUT = "a" * 64
OTHER = "b" * 64
TIME = datetime(2026, 6, 10, tzinfo=timezone.utc)


@pytest.fixture
def workspace():
    project = Project.objects.create(name="Prospective cohort")
    other = Project.objects.create(name="Other project")
    file = Declaration.objects.create(name="Development data", original_name="develop.csv", file="develop.csv")
    binding = ProjectDataset.objects.create(dataset=file, project=project)
    job = SimpleNamespace(project_id=project.pk)
    return SimpleNamespace(job=job, project=project, other=other, file=file, binding=binding)


def access(workspace, *, project=None, window=None, input_hash=OTHER, **fields):
    parameters = {}
    if project is not None:
        parameters["project_id"] = str(project.pk)
    if window is not None:
        parameters["prospective_window"] = window
    values = {
        "file_id": workspace.file.pk,
        "accessed_at": TIME,
        "dataset_sha256": input_hash,
        "parameters": parameters,
        "actor_snapshot": {"id": 45, "username": "reviewer"},
        "attempt_state": "failed",
    }
    return HoldoutAccess.objects.create(**(values | fields))


def test_reuse_survives_reassignment_and_redacts_outside_project_receipts(workspace):
    own = access(workspace, project=workspace.project, window=OVERLAP)
    exact = access(workspace, project=workspace.other, input_hash=INPUT)
    access(workspace, project=workspace.project, window=DISJOINT)
    workspace.binding.project = workspace.other
    workspace.binding.save(update_fields=["project"])

    decision = assessment_reuse.classify_reuse(workspace.job, WINDOW, INPUT)
    assert decision["reason"] == "prior_exact_input_access"
    assert decision["counts"] == {"exact_input": 1, "unclassified_project": 0, "overlapping_project": 1}
    assert decision["records"][0] == {"relation": "exact_input", "visibility": "outside_project"}
    assert str(exact.pk) not in str(decision)
    assert decision["records"][1] == {
        "relation": "overlapping_project", "visibility": "same_project", "project_binding": "access_receipt",
        "access_id": str(own.pk), "accessed_at": TIME.isoformat(),
        "actor": {"id": 45, "username": "reviewer"}, "attempt_state": "failed",
    }
    assert assessment_reuse.classify_reuse(workspace.job, None, INPUT)["records"] == decision["records"][:1]


def test_pre_snapshot_native_history_recovers_original_project(workspace):
    old_job = NativeJob.objects.create(
        id=uuid.uuid4(), project=workspace.project, dataset=workspace.file, expires_at=TIME,
        actor_snapshot={}, authority={}, specification={"kind": training_search.KIND}, request_sha256=OTHER,
    )
    old = access(workspace, window=OVERLAP, execution_id=old_job.pk, attempt_state="started")
    workspace.binding.project = workspace.other
    workspace.binding.save(update_fields=["project"])
    access(workspace, project=workspace.other, window=OVERLAP)

    decision = assessment_reuse.classify_reuse(workspace.job, WINDOW, INPUT)
    assert decision["reason"] == "prior_overlapping_project_access"
    assert decision["total"] == 1
    assert decision["records"][0]["access_id"] == str(old.pk)
    assert decision["records"][0]["project_binding"] == "native_training_job"
    assert decision["records"][0]["attempt_state"] == "started"


def test_unknown_history_blocks_confirmation_with_bounded_stable_evidence(workspace):
    limit = assessment_reuse.RECORD_LIMIT
    for index in reversed(range(1, limit + 3)):
        access(workspace, id=uuid.UUID(int=index), attempt_state="historical_unknown", actor_snapshot={})
    access(workspace, project=workspace.project, window={**OVERLAP, "start": "2026-01-01"})
    access(workspace, project=workspace.project, window={"start": OVERLAP["end"], "end": OVERLAP["start"]})
    another_file = Declaration.objects.create(name="Unrelated", original_name="other.csv", file="other.csv")
    access(workspace, file_id=another_file.pk)

    decision = assessment_reuse.classify_reuse(workspace.job, WINDOW, INPUT)
    assert decision["reason"] == "prior_unclassified_project_access"
    assert decision["counts"] == {"exact_input": 0, "unclassified_project": limit + 4, "overlapping_project": 0}
    assert decision["total"] == limit + 4 and decision["truncated"] is True
    assert [row["access_id"] for row in decision["records"]] == [str(uuid.UUID(int=i)) for i in range(1, limit + 1)]
    assert all(row["project_binding"] == "historical_dataset_assignment" for row in decision["records"])
    assert decision["records"][0]["actor"] == {"identity": "historical_or_unattributed"}
