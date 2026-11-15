"""Decide protected assessment reuse from retained access metadata alone."""

from django.db.models import Case, Count, Exists, F, OuterRef, Q, TextField, Value, When
from django.db.models.fields.json import KT
from django.db.models.functions import Cast

from access_control.models import ProjectDataset
from execution_jobs import training_search
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess

POLICY = "protected_assessment_reuse_v1"
RECORD_LIMIT = 20
EXACT = "exact_input"
UNCLASSIFIED = "unclassified_project"
OVERLAPPING = "overlapping_project"
REASONS = {
    EXACT: "prior_exact_input_access",
    UNCLASSIFIED: "prior_unclassified_project_access",
    OVERLAPPING: "prior_overlapping_project_access",
}
PROJECT_ID = r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
UTC_NANOSECONDS = r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{9}\+00:00$"


def classify_reuse(job, window, input_sha256):
    """Snapshot the decision and a bounded set of supporting access receipts.

    Call before reserving access, in the same transaction and under the same
    reservation lock. The caller stores the decision with the new access.
    """
    exact = Q(dataset_sha256=input_sha256)
    # Older native receipts still cite a durable training job. Its original
    # project remains available even when the dataset has been moved or unbound.
    native = NativeJob.objects.filter(
        pk=OuterRef("execution_id"), dataset_id=OuterRef("file_id"), specification__kind=training_search.KIND,
    )
    assignment = ProjectDataset.objects.filter(dataset_id=OuterRef("file_id"), project_id=job.project_id)
    rows = HoldoutAccess.objects.annotate(
        recorded_project=Cast(KT("parameters__project_id"), TextField()),
        has_native_job=Exists(native),
        native_project_matches=Exists(native.filter(project_id=job.project_id)),
        assignment_matches=Exists(assignment),
        window_start=Cast(KT("parameters__prospective_window__start"), TextField()),
        window_end=Cast(KT("parameters__prospective_window__end"), TextField()),
    )
    recorded = Q(recorded_project__regex=PROJECT_ID, recorded_project__isnull=False)
    from_receipt = Q(recorded_project=str(job.project_id))
    from_native = Q(native_project_matches=True)
    from_assignment = Q(has_native_job=False, assignment_matches=True) & ~recorded
    same_project = from_native | (Q(has_native_job=False) & from_receipt) | from_assignment

    if window is None:
        unclassified = overlapping = Q(pk__in=[])
    else:
        usable_window = Q(
            window_start__regex=UTC_NANOSECONDS, window_start__isnull=False,
            window_end__regex=UTC_NANOSECONDS, window_end__isnull=False,
            window_start__lt=F("window_end"),
        )
        unclassified = same_project & ~usable_window
        overlapping = same_project & usable_window & Q(
            window_start__lte=window["end"], window_end__gte=window["start"],
        )

    matches = rows.filter(exact | unclassified | overlapping).annotate(
        priority=Case(When(exact, then=Value(0)), When(unclassified, then=Value(1)), default=Value(2)),
        project_binding=Case(
            When(same_project & from_receipt, then=Value("access_receipt")),
            When(from_native, then=Value("native_training_job")),
            When(from_assignment, then=Value("historical_dataset_assignment")),
            default=Value("outside_project"),
        ),
    )
    relations = tuple(REASONS)
    counts = dict.fromkeys(relations, 0)
    for row in matches.values("priority").annotate(count=Count("pk")).order_by():
        counts[relations[row["priority"]]] = row["count"]
    total = sum(counts.values())

    records = []
    if total:
        page = matches.order_by("priority", "accessed_at", "pk").values(
            "pk", "accessed_at", "actor_snapshot", "attempt_state", "priority", "project_binding",
        )[:RECORD_LIMIT]
        for row in page:
            binding = row["project_binding"]
            record = {"relation": relations[row["priority"]], "visibility": "outside_project"}
            if binding != "outside_project":
                record.update(
                    visibility="same_project", project_binding=binding,
                    access_id=str(row["pk"]), accessed_at=row["accessed_at"].isoformat(),
                    actor=row["actor_snapshot"] or {"identity": "historical_or_unattributed"},
                    attempt_state=row["attempt_state"],
                )
            records.append(record)
    return {
        "policy": POLICY,
        "reason": next((REASONS[relation] for relation in relations if counts[relation]), None),
        "counts": counts,
        "total": total,
        "records": records,
        "truncated": total > RECORD_LIMIT,
    }
