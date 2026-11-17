"""Attributable technical decisions on a reproducible native assessment."""

from datetime import UTC, datetime

from django.utils.timezone import now

from access_control import data_policy, projects
from deployment import offline_reproduce
from deployment.reviews import ReviewConflict, digest

SCOPE = "technical_assessment_review_only"
POLICY = {
    "version": 1,
    "scope": SCOPE,
    "requires_exact_refit_and_assessment_report": True,
    "exceptions_apply_only_to_the_named_finding": True,
    "exceptions_require_current_reviewer_and_expiry": True,
    "production_use_authority": False,
}


def policy_sha256():
    return digest({"decision_policy": POLICY, "installation_data_policy_sha256": data_policy.policy_digest()})


def _reviewer_current(event):
    try:
        projects.recheck(event.authority_snapshot)
    except (KeyError, TypeError, projects.ProjectDenied):
        return False
    return event.authority_snapshot.get("role") == "reviewer"


def _exception(event, checked_at, policy):
    value = event.details if isinstance(event.details, dict) else {}
    expires_at = value.get("expires_at")
    status = "invalidated"
    if isinstance(expires_at, str) and value.get("policy_sha256") == policy and _reviewer_current(event):
        try:
            expiry = datetime.fromisoformat(expires_at)
            status = "expired" if expiry <= checked_at else "active"
        except (TypeError, ValueError):
            pass
    return {"event_id": str(event.pk), "actor": event.actor_snapshot,
            "expires_at": expires_at, "status": status}


def findings(events):
    result = {}
    checked_at, policy = now(), policy_sha256()
    for event in events:
        if event.event_type == "finding":
            result[str(event.pk)] = {
                "id": str(event.pk), "severity": event.severity, "text": event.text,
                "state": "open", "responses": 0, "evidence": event.evidence,
            }
        elif event.finding_id:
            item = result[str(event.finding_id)]
            if event.event_type == "response":
                item["responses"] += 1
            elif event.event_type == "exception":
                exception = _exception(event, checked_at, policy)
                item.update(exception=exception, state="excepted" if exception["status"] == "active" else "open")
            elif event.event_type in {"resolve", "reopen"}:
                item.pop("exception", None)
                item["state"] = "resolved" if event.event_type == "resolve" else "open"
    return list(result.values())


def _event_record(event):
    return {
        "id": str(event.pk), "revision": event.revision, "kind": event.event_type,
        "finding_id": str(event.finding_id) if event.finding_id else None,
        "severity": event.severity, "text": event.text, "details": event.details,
        "actor": event.actor_snapshot, "authority": event.authority_snapshot,
        "evidence": event.evidence, "request_sha256": event.request_sha256, "created_at": event.created_at.isoformat(),
    }


def _discussion_sha256(events):
    return digest([_event_record(event) for event in events])


def _expected_report(manifest, manifest_sha256):
    training, assessment = manifest["training"], manifest["assessment"]
    result = assessment["result"]
    return {
        "schema_version": 1, "scope": offline_reproduce.SCOPE, "status": "passed",
        "task": result["prediction_contract"]["task"],
        "manifest_sha256": manifest_sha256,
        "training_result_sha256": training["result_sha256"],
        "assessment_result_sha256": assessment["result_sha256"],
        "development_sha256": training["specification"]["training"]["source"]["sha256"],
        "outcomes_sha256": manifest["protected_input"]["specification"]["input_sha256"],
        "candidate_export_sha256": result["candidate_export_sha256"],
        "model_sha256": training["fit"]["model_sha256"],
        "scores_sha256": result["scores_sha256"], "outcome_access_id": result["outcome_access_id"],
        "n_assessed": result["n_assessed"],
        "model_refit_reproduced": True, "assessment_reproduced": True,
        "comparison": "exact_canonical_result_and_scores_sha256",
        "confirmation_granted": False, "review_approved": False, "production_use_approved": False,
    }


def _approval_details(review, manifest, report, events):
    if not isinstance(report, dict) or digest(report) != digest(_expected_report(manifest, review.manifest_sha256)):
        raise ReviewConflict("review_reproduction_report_mismatch")
    return {
        "schema_version": 1, "scope": SCOPE, "policy_sha256": policy_sha256(),
        "manifest_sha256": review.manifest_sha256, "assessment_result_sha256": review.assessment_result_sha256,
        "discussion_sha256": _discussion_sha256(events),
        "report_sha256": digest(report), "report": report,
    }


def _latest(events):
    return next((event for event in reversed(events) if event.event_type in {"approve", "revoke"}), None)


def prepare(review, kind, data, events, manifest):
    """Build persisted metadata while the exact current subject is fenced."""
    if kind == "exception":
        raw = data["expires_at"]
        try:
            if not isinstance(raw, str) or len(raw) > 40:
                raise ValueError
            expiry = datetime.fromisoformat(raw)
            if expiry.utcoffset() is None or expiry <= now():
                raise ValueError
            expiry = expiry.astimezone(UTC)
        except (OverflowError, ValueError):
            raise ValueError("Supply a future exception expiration with a timezone.") from None
        return {"schema_version": 1, "scope": SCOPE, "policy_sha256": policy_sha256(),
                "expires_at": expiry.isoformat()}
    if kind == "revoke":
        last = _latest(events)
        if last is None or last.event_type != "approve":
            raise ReviewConflict("review_approval_unavailable")
        return {"schema_version": 1, "scope": SCOPE, "approval_event_id": str(last.pk),
                "approval_sha256": digest(_event_record(last))}
    if state(review, events, "current", manifest)["status"] == "approved":
        raise ReviewConflict("review_already_approved")
    if any(item["state"] == "open" for item in findings(events)):
        raise ReviewConflict("review_findings_unaddressed")
    return _approval_details(review, manifest, data["report"], events)


def _invalidated(review, events, event, freshness, manifest):
    if freshness != "current" or manifest is None:
        return "review_upstream_evidence_changed"
    if not isinstance(event.details, dict):
        return "review_approval_evidence_changed"
    if event.details.get("policy_sha256") != policy_sha256():
        return "review_policy_changed"
    if not _reviewer_current(event):
        return "review_approver_authority_changed"
    if event.revision != review.revision or event != events[-1]:
        return "review_discussion_changed"
    if any(item["state"] == "open" for item in findings(events)):
        return "review_exception_unavailable"
    try:
        expected = _approval_details(review, manifest, event.details.get("report"), events[:-1])
    except ReviewConflict:
        return "review_approval_evidence_changed"
    if digest(expected) != digest(event.details):
        return "review_approval_evidence_changed"
    return None


def state(review, events, freshness, manifest=None):
    event = _latest(events)
    if event is None:
        return {"status": "none", "reason_code": None}
    record = {
        "event_id": str(event.pk), "actor": event.actor_snapshot,
        "decision_sha256": digest(_event_record(event)), "scope": SCOPE,
        "created_at": event.created_at.isoformat(),
    }
    if event.event_type == "revoke":
        return record | {"status": "revoked", "reason_code": "review_approval_revoked"}
    reason = _invalidated(review, events, event, freshness, manifest)
    return record | {"status": "invalidated" if reason else "approved", "reason_code": reason}
