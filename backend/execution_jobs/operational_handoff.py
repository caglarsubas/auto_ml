"""Read-only, revision-pinned job handoff; never recovery or review authority."""

from collections import Counter

from execution_jobs import service
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess

NEXT = {
    "queued": "Wait for dispatch of this same request. Do not submit a replacement while its outcome is uncertain.",
    "running": "Wait for completion. After a worker interruption the dispatcher waits for lease expiry before bounded recovery of this same request.",
    "cancel_requested": "Cancellation is recorded; wait for worker acknowledgement or lease expiry. Cancellation never starts a replacement.",
    "cancelled": "No result was published. Retain possible outcome accesses; any new assessment needs a new explicit reviewed request.",
    "blocked": "Inspect the reason with the project owner. Resolve changed authority, inputs or runtime and prepare a new explicit request; do not replay by editing database state.",
    "failed": "Ask the installation operator to inspect worker, dispatcher, broker and database health. Retain this receipt; recovery does not grant new execution authority.",
    "succeeded": "Hand this receipt and its exact result digest to an independent reviewer. Execution success does not approve scientific validity or production use.",
}


def read(actor, identifier, revision, expected=None):
    if not isinstance(revision, str) or not revision.isascii() or not revision.isdecimal() or str(int(revision)) != revision:
        raise ValueError("Supply the observed nonnegative job revision.")
    if expected is not None:
        service.require_digest(expected)
    with service.locked():
        job = NativeJob.objects.get(pk=identifier)
        scopes = service.read_authority(actor, job)
        if job.revision != int(revision):
            raise service.JobConflict("job_handoff_stale")
        events = list(job.events.all())
        # An inconsistent counter must not size an allocation under this lock.
        if len(events) != job.revision or any(e.revision != n for n, e in enumerate(events, 1)):
            raise service.JobConflict("job_event_history_invalid")
        # Only scalar counters are fetched: no sealed bytes, row membership,
        # predictions, native state or arbitrary historical parameters.
        states = Counter(HoldoutAccess.objects.filter(
            file_id=job.dataset_id, parameters__scope="native_protected_assessment_v1",
            parameters__job_id=str(job.pk),
        ).values_list("attempt_state", flat=True))
        if set(states) - {"started", "failed", "completed"}:
            raise service.JobConflict("job_access_history_invalid")
        spec = job.specification
        value = {
            "schema": "native_operational_handoff_v1", "read_only": True,
            "job_id": str(job.pk), "file_id": job.dataset_id, "project_id": str(job.project_id),
            "kind": spec["kind"], "revision": job.revision, "state": job.state,
            "reason_code": job.reason_code, "request_sha256": job.request_sha256,
            "result_sha256": job.result_sha256, "attempts": job.attempts,
            "attempt_limit": spec["limits"]["attempts"],
            "lease_until": job.lease_until.isoformat() if job.lease_until else None,
            "expires_at": job.expires_at.isoformat(),
            "source_job_id": spec.get("training_job_id"),
            "protected_input_id": spec.get("protected_input_id"),
            "submitted_by": job.actor_snapshot,
            "events": [{"revision": e.revision, "event_type": e.event_type,
                        "actor": e.actor_snapshot, "created_at": e.created_at.isoformat(),
                        "reason_code": e.detail.get("reason_code", "")} for e in events],
            "outcome_accesses": {"total": sum(states.values()),
                **{key: states[key] for key in ["started", "failed", "completed"]}},
            "access_limitation": "Started, failed and completed reservations all count as possible outcome access. Completed access does not prove result publication. Interrupted reservations remain started; cancellation does not erase access. External history remains unknown.",
            "next_action": NEXT[job.state],
            "recovery_scope": "The dispatcher may retry the same immutable request within its original attempt, expiry, runtime and authority limits. Partial training work is recomputed; trial checkpoints are unsupported. This observation does not test live service health or qualify installation recovery.",
            "assessment_status": "exploratory", "recovery_authorized": False,
            "review_approved": False, "production_use_approved": False,
        }
        sha = service.digest(value)
        if expected is not None and sha != expected:
            raise service.JobConflict("job_handoff_stale")
        for current in scopes:
            service.projects.recheck(current)
        return {**value, "sha256": sha}
