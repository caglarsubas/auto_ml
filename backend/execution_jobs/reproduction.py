"""Export authorized evidence for a completed native assessment without opening outcomes."""

from access_control import projects
from deployment import native_candidate, offline_reproduce
from execution_jobs import native_assessment, service
from execution_jobs.models import NativeJob, NativeProtectedInput


def development_actors(manifest):
    return {manifest["training"]["actor"]["id"], manifest["adoption"]["proposal"]["actor"]["id"]}


def verified_manifest(job, expected_sha256):
    """Verify the current source and return the manifest without reading labels.

    The caller holds the queue lock and resolves read authority before entering.
    """
    spec = service.execution_specification(job)
    if (job.state != "succeeded" or spec["kind"] != native_assessment.KIND
            or job.result_sha256 != expected_sha256 or not isinstance(job.result, dict)
            or service.digest(job.result) != expected_sha256
            or spec.get("schema_version") != native_assessment.PLAN_SCHEMA):
        raise service.JobConflict("job_reproduction_assessment_unavailable")
    service.recheck_execution(job)
    status = "confirmatory" if job.result.get("confirmatory") is True else "exploratory"
    receipt = native_assessment.bound_access(job, job.result).filter(evidence_status=status).values(
        "id", "actor_id", "attempt_state", "evidence_status", "accessed_at",
    ).first()
    if receipt is None:
        raise service.JobConflict("job_reproduction_outcome_receipt_unavailable")

    seal = NativeProtectedInput.objects.defer("payload").select_related("adoption__training_job").get(
        pk=spec["protected_input_id"],
    )
    adoption = seal.adoption
    training = adoption.training_job
    approval = adoption.events.get(pk=spec["approval_event_id"])
    manifest = {
        "schema_version": 1, "scope": offline_reproduce.SCOPE,
        "dataset_id": job.dataset_id, "project_id": str(job.project_id),
        "training": {
            "job_id": str(training.pk), "actor": training.actor_snapshot, "specification": training.specification,
            "result_sha256": training.result_sha256, "fit": offline_reproduce.reference_fit(training.result),
        },
        "assessment": {
            "job_id": str(job.pk), "specification": spec,
            "result_sha256": expected_sha256, "result": job.result,
        },
        "adoption": {
            "id": str(adoption.pk), "proposal": adoption.proposal,
            "approval": {
                "id": str(approval.pk), "kind": approval.kind, "revision": approval.revision,
                "created_at": approval.created_at.isoformat(), "payload": approval.payload,
            },
        },
        "protected_input": {"id": str(seal.pk), "specification": seal.specification},
        "outcome_access": {
            **receipt, "id": str(receipt["id"]), "accessed_at": receipt["accessed_at"].isoformat(),
            "assessment_sha256": spec["assessment_sha256"], "outcomes_sha256": spec["input_sha256"],
        },
    }
    raw = native_candidate.canonical(manifest)
    try:
        offline_reproduce.parse_manifest(raw, native_candidate.sha(raw))
    except offline_reproduce.ReplayBlocked:
        raise service.JobConflict("job_reproduction_manifest_unavailable_or_historical") from None
    return manifest, raw


def export(actor, identifier, expected_sha256):
    expected_sha256 = service.require_digest(expected_sha256)
    with service.locked():
        lookup = NativeJob.objects.only("dataset_id", "project_id").get(pk=identifier)
        reviewer = service.scope(actor, lookup.dataset_id)
        if reviewer["role"] != "reviewer" or reviewer["project_id"] != str(lookup.project_id):
            raise projects.ProjectDenied("job_reproduction_reviewer_required")
        job = NativeJob.objects.get(pk=identifier)
        scopes = service.read_authority(actor, job)
        manifest, raw = verified_manifest(job, expected_sha256)
        if actor.pk in development_actors(manifest):
            raise projects.ProjectDenied("job_reproduction_reviewer_required")
        for scope in (reviewer, *scopes):
            projects.recheck(scope)
        return raw
