"""Independent native adoption and sealed, access-accounted exploratory assessment.

Protected custody prevents the native training/search/scoring entrypoints from
reading these labels. Unknown upstream histories never become confirmatory.
"""

import csv
import io
import json
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from django.contrib.auth import get_user_model
from django.db.models.functions import Substr
from django.utils import timezone

from access_control import projects
from access_control.authority import actor_snapshot
from deployment import native_candidate
from deployment.reviews import digest, lock_authority
from deployment.scoring_receipts import require_digest
from execution_jobs import csv_scoring, training_search, training_scoring
from execution_jobs.models import NativeAdoption, NativeAdoptionEvent, NativeJob, NativeProtectedInput
from modeling.declared_metric import metric_spec, metric_value
from modeling.development_assessment import development_metrics
from modeling.holdout_evidence import holdout_spec, reserve_holdout_access

KIND = "native_protected_assessment_v1"
BUDGET = {**training_search.BUDGET, "chunk_size": 500}
SCOPE = "development_candidate_for_protected_assessment_only"
LIMITATION = (
    "Exploratory protected assessment. Upstream history, independent population identity and maturity "
    "are not established by an upload. Reuse or post-inspection changes cannot inherit confirmatory status. "
    "No calibration/threshold fitting, automatic policy gate, legacy champion or production approval."
)


def conflict(code):
    from execution_jobs.service import JobConflict

    raise JobConflict(code)


def text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2000:
        raise ValueError("Supply a rationale of 1–2000 characters.")
    return value.strip()


def candidate(actor, job_id, expected):
    job = NativeJob.objects.get(pk=job_id)
    raw = training_scoring._export(actor, job_id, require_digest(expected))
    _, source, authority = csv_scoring.input_bytes(
        actor.pk, job.dataset_id, expected=job.specification["training"]["source"]
    )
    if (
        source["sha256"] != job.result["input_sha256"]
        or metric_spec(job.result["prediction_contract"]) != job.result["metric"]
    ):
        conflict("native_adoption_training_evidence_changed")
    return job, raw, authority


def integrity(adoption):
    if (
        digest(adoption.proposal) != adoption.proposal_sha256
        or adoption.proposal.get("training_job_id") != str(adoption.training_job_id)
        or adoption.proposal.get("scope") != SCOPE
    ):
        conflict("native_adoption_proposal_changed")
    events = list(adoption.events.all())
    for revision, event in enumerate(events, 1):
        if (
            event.adoption_id != adoption.pk
            or event.revision != revision
            or digest(event.payload) != event.payload_sha256
            or event.kind not in {"approve", "revoke"}
            or event.payload["proposal_sha256"] != adoption.proposal_sha256
        ):
            conflict("native_adoption_decision_changed")
    if events and (events[0].kind != "approve" or len(events) > 2 or len(events) == 2 and events[1].kind != "revoke"):
        conflict("native_adoption_decision_changed")
    return events


def current(adoption):
    events = integrity(adoption)
    if not events or events[-1].kind != "approve":
        conflict("native_adoption_not_approved")
    p, approval = adoption.proposal, events[-1]
    projects.recheck(p["authority"])
    projects.recheck(approval.payload["authority"])
    actor = get_user_model().objects.get(pk=approval.payload["actor"]["id"])
    job, raw, _ = candidate(actor, adoption.training_job_id, p["training_result_sha256"])
    if (
        native_candidate.sha(raw) != p["export_sha256"]
        or job.actor_snapshot["id"] in {actor.pk}
        or p["actor"]["id"] == actor.pk
    ):
        conflict("native_adoption_independence_or_evidence_changed")
    return job, raw, approval


def serialize(actor, adoption, replayed=False):
    job = adoption.training_job
    from execution_jobs import service

    scopes = service.read_authority(actor, job)
    events = integrity(adoption)
    state = "proposed" if not events else ("accepted" if events[-1].kind == "approve" else "revoked")
    usable, reason = False, ""
    if state == "accepted":
        try:
            current(adoption)
            usable = True
        except (ValueError, projects.ProjectDenied, get_user_model().DoesNotExist, OSError) as exc:
            reason = getattr(exc, "code", "native_adoption_evidence_unavailable")
    for authority in scopes:
        projects.recheck(authority)
    protected_inputs = list(adoption.protected_inputs.defer("payload").order_by("created_at", "pk"))
    if any(
        digest(p.specification) != p.specification_sha256 or p.specification.get("adoption_id") != str(adoption.pk)
        for p in protected_inputs
    ):
        conflict("native_protected_specification_changed")
    result = {
        "id": str(adoption.pk),
        "training_job_id": str(job.pk),
        "file_id": job.dataset_id,
        "project_id": str(job.project_id),
        "proposal": adoption.proposal,
        "proposal_sha256": adoption.proposal_sha256,
        "revision": len(events),
        "state": state,
        "usable": usable,
        "reason_code": reason,
        "events": [
            {
                "id": str(e.pk),
                "revision": e.revision,
                "kind": e.kind,
                "payload": e.payload,
                "payload_sha256": e.payload_sha256,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "protected_inputs": [
            {"id": str(p.pk), "specification": p.specification, "specification_sha256": p.specification_sha256}
            for p in protected_inputs
        ],
        "scope": SCOPE,
        "model_adopted_for_scope": usable,
        "production_use_approved": False,
        "confirmatory": False,
        "limitation": LIMITATION,
        "replayed": replayed,
    }
    for authority in scopes:
        projects.recheck(authority)
    return result


def propose(actor, job_id, data):
    from execution_jobs import service

    if not isinstance(data, dict) or set(data) != {"request_id", "training_result_sha256", "rationale"}:
        raise ValueError("Supply exactly the candidate, rationale and request UUID.")
    identifier, rationale = uuid.UUID(str(data["request_id"])), text(data["rationale"])
    request_sha = digest({"actor": actor.pk, "training_job_id": str(job_id), "request": data})
    with service.locked():
        job = NativeJob.objects.get(pk=job_id)
        authority = lock_authority(actor, job.dataset_id, "developer")
        previous = NativeAdoption.objects.filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != request_sha:
                conflict("native_adoption_request_reused")
            return serialize(actor, previous, True)
        job, raw, _ = candidate(actor, job_id, data["training_result_sha256"])
        p = {
            "schema_version": 1,
            "scope": SCOPE,
            "training_job_id": str(job.pk),
            "training_result_sha256": job.result_sha256,
            "export_sha256": native_candidate.sha(raw),
            "prediction_contract": job.result["prediction_contract"],
            "metric": job.result["metric"],
            "features": job.result["features"],
            "actor": actor_snapshot(actor),
            "authority": authority,
            "rationale": rationale,
        }
        adoption = NativeAdoption.objects.create(
            id=identifier, training_job=job, proposal=p, proposal_sha256=digest(p), request_sha256=request_sha
        )
        projects.recheck(authority)
        return serialize(actor, adoption)


def decide(actor, adoption_id, data):
    from execution_jobs import service

    if not isinstance(data, dict) or set(data) != {
        "request_id",
        "expected_revision",
        "proposal_sha256",
        "action",
        "rationale",
    }:
        raise ValueError("Supply the exact reviewed proposal, revision, decision, rationale and request UUID.")
    identifier, rationale = uuid.UUID(str(data["request_id"])), text(data["rationale"])
    if data["action"] not in {"approve", "revoke"} or type(data["expected_revision"]) is not int:
        raise ValueError("Select approve/revoke and the observed revision.")
    request_sha = digest({"actor": actor.pk, "adoption_id": str(adoption_id), "request": data})
    with service.locked():
        adoption = NativeAdoption.objects.select_related("training_job").get(pk=adoption_id)
        authority = lock_authority(actor, adoption.training_job.dataset_id, "reviewer")
        previous = NativeAdoptionEvent.objects.filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != request_sha:
                conflict("native_adoption_request_reused")
            return serialize(actor, adoption, True)
        events = integrity(adoption)
        if data["proposal_sha256"] != adoption.proposal_sha256 or len(events) != data["expected_revision"]:
            conflict("native_adoption_review_changed")
        if data["action"] == "approve":
            if events or actor.pk in {adoption.training_job.actor_snapshot["id"], adoption.proposal["actor"]["id"]}:
                conflict("native_adoption_independent_reviewer_required")
            projects.recheck(adoption.proposal["authority"])
            _, raw, _ = candidate(actor, adoption.training_job_id, adoption.proposal["training_result_sha256"])
            if native_candidate.sha(raw) != adoption.proposal["export_sha256"]:
                conflict("native_adoption_training_evidence_changed")
        elif not events or events[-1].kind != "approve":
            conflict("native_adoption_not_approved")
        payload = {
            "schema_version": 1,
            "scope": SCOPE,
            "proposal_sha256": adoption.proposal_sha256,
            "actor": actor_snapshot(actor),
            "authority": authority,
            "rationale": rationale,
        }
        NativeAdoptionEvent.objects.create(
            id=identifier,
            adoption=adoption,
            revision=len(events) + 1,
            kind=data["action"],
            payload=payload,
            payload_sha256=digest(payload),
            request_sha256=request_sha,
        )
        projects.recheck(authority)
        return serialize(actor, adoption)


def controls(job):
    return list(
        dict.fromkeys(
            v for k, v in job.specification["training"]["options"]["validation"].items() if k.endswith("_column")
        )
    )


def sealed_header(raw, job):
    required = [*job.result["features"], job.result["prediction_contract"]["target_column"], *controls(job)]
    try:
        rows = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
        header = next(row for row in rows if row)
        count = 0
        if len(set(header)) != len(header) or set(header) != set(required) or len(header) != len(required):
            raise ValueError
        for row in rows:
            if row:
                count += 1
                if len(row) != len(header) or count > BUDGET["max_rows"]:
                    raise ValueError
        if not 30 <= count <= BUDGET["max_rows"]:
            raise ValueError
    except (ValueError, csv.Error, UnicodeError, StopIteration):
        raise ValueError(
            "Protected CSV requires 30–1000 rows and exactly the frozen features, target and validation controls."
        ) from None
    return {"header": header, "rows": count}


def seal(actor, adoption_id, data, upload):
    from execution_jobs import service

    if (
        set(data)
        != {"request_id", "proposal_sha256", "rationale", "assessment_as_of", "population_and_maturity_attested"}
        or data["population_and_maturity_attested"] != "true"
    ):
        raise ValueError("Attest the population/maturity and supply the displayed protected input fields.")
    identifier, rationale = uuid.UUID(str(data["request_id"])), text(data["rationale"])
    as_of = datetime.fromisoformat(data["assessment_as_of"].replace("Z", "+00:00"))
    if as_of.tzinfo is None:
        raise ValueError("Assessment as-of must include a timezone.")
    raw = upload.read(BUDGET["max_input_bytes"] + 1)
    if not raw or len(raw) > BUDGET["max_input_bytes"]:
        conflict("native_protected_input_budget_exceeded")
    request_sha = digest(
        {
            "actor": actor.pk,
            "adoption_id": str(adoption_id),
            "request": dict(data),
            "input_sha256": native_candidate.sha(raw),
        }
    )
    with service.locked():
        adoption = NativeAdoption.objects.select_related("training_job").get(pk=adoption_id)
        authority = lock_authority(actor, adoption.training_job.dataset_id, "reviewer")
        previous = NativeProtectedInput.objects.defer("payload").filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != request_sha:
                conflict("native_protected_request_reused")
            return serialize(actor, adoption, True)
        job, _, approval = current(adoption)
        if data["proposal_sha256"] != adoption.proposal_sha256 or authority != approval.payload["authority"]:
            conflict("native_adoption_review_changed")
        schema = sealed_header(raw, job)
        spec = {
            "schema_version": 1,
            "scope": "sealed_native_outcomes_v1",
            "adoption_id": str(adoption.pk),
            "approval_event_id": str(approval.pk),
            "proposal_sha256": adoption.proposal_sha256,
            "input_sha256": native_candidate.sha(raw),
            "bytes": len(raw),
            **schema,
            "actor": actor_snapshot(actor),
            "authority": authority,
            "rationale": rationale,
            "assessment_as_of": as_of.isoformat(),
            "population_and_maturity_attested": True,
            "upstream_history": "unverified",
            "confirmatory": False,
        }
        NativeProtectedInput.objects.create(
            id=identifier,
            adoption=adoption,
            specification=spec,
            specification_sha256=digest(spec),
            payload=raw,
            request_sha256=request_sha,
        )
        projects.recheck(authority)
        return serialize(actor, adoption)


def plan(actor, protected_id):
    from execution_jobs import service

    protected = (
        NativeProtectedInput.objects.defer("payload").select_related("adoption__training_job").get(pk=protected_id)
    )
    adoption = protected.adoption
    authority = service.scope(actor, adoption.training_job.dataset_id)
    if authority["role"] != "reviewer":
        raise projects.ProjectDenied("native_assessment_reviewer_required")
    job, raw_export, approval = current(adoption)
    spec = protected.specification
    if (
        digest(spec) != protected.specification_sha256
        or spec["adoption_id"] != str(adoption.pk)
        or spec["proposal_sha256"] != adoption.proposal_sha256
        or spec["approval_event_id"] != str(approval.pk)
        or spec["authority"] != authority
        or actor.pk != approval.payload["actor"]["id"]
    ):
        conflict("native_protected_scope_changed")
    projects.recheck(spec["authority"])
    result = {
        "schema_version": 1,
        "kind": KIND,
        "adoption_id": str(adoption.pk),
        "proposal_sha256": adoption.proposal_sha256,
        "approval_event_id": str(approval.pk),
        "protected_input_id": str(protected.pk),
        "protected_input_sha256": protected.specification_sha256,
        "training_job_id": str(job.pk),
        "training_result_sha256": job.result_sha256,
        "runtime": service.runtime(KIND),
        "limits": service.limits(KIND),
    }
    return result, protected, raw_export, authority


def preview(actor, protected_id):
    prepared, protected, _, authority = plan(actor, protected_id)
    result = {
        **prepared,
        "assessment_sha256": digest(prepared),
        "input_metadata": protected.specification,
        "limitation": LIMITATION,
    }
    projects.recheck(authority)
    return result


def submit(actor, file_id, data):
    from execution_jobs import service

    if set(data) != {"request_id", "kind", "protected_input_id", "assessment_sha256"}:
        raise ValueError("Supply exactly the reviewed protected assessment fields.")
    identifier, expected = uuid.UUID(str(data["request_id"])), require_digest(data["assessment_sha256"])
    request_sha = digest({"actor": actor.pk, "file_id": file_id, "request": data})
    with service.locked():
        authority = lock_authority(actor, file_id, "reviewer")
        previous = NativeJob.objects.filter(pk=identifier).first()
        if previous:
            if previous.request_sha256 != request_sha:
                conflict("job_request_reused")
            scopes = service.read_authority(actor, previous)
            for scope in scopes:
                projects.recheck(scope)
            return service.authorized_receipt(previous, scopes, replayed=True)
        if NativeJob.objects.filter(state__in=service.ACTIVE | {"queued"}).count() >= service.LIMITS["max_pending"]:
            conflict("job_queue_full")
        prepared, protected, _, _ = plan(actor, data["protected_input_id"])
        if digest(prepared) != expected or protected.adoption.training_job.dataset_id != file_id:
            conflict("native_assessment_plan_changed")
        job = NativeJob.objects.create(
            id=identifier,
            actor=actor,
            actor_snapshot=actor_snapshot(actor),
            project_id=authority["project_id"],
            dataset_id=file_id,
            authority=authority,
            specification={**prepared, "assessment_sha256": expected},
            request_sha256=request_sha,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        service.record(job, "submitted", actor=actor)
        return service.authorized_receipt(job, [authority])


def recheck(job):
    actor = get_user_model().objects.get(pk=job.authority["actor_id"])
    prepared, _, _, _ = plan(actor, job.specification["protected_input_id"])
    if digest(prepared) != job.specification["assessment_sha256"]:
        conflict("native_assessment_plan_changed")


def population(frame, development, validation, as_of):
    strategy = validation["strategy"]
    group = validation.get("group_column")
    if group:
        a, b = development[group], frame[group]
        if (
            a.isna().any()
            or b.isna().any()
            or pd.api.types.is_numeric_dtype(a) != pd.api.types.is_numeric_dtype(b)
            or b.isin(a).any()
        ):
            conflict("native_assessment_entities_overlap_or_unverified")
    if strategy == "oot":
        date, end = validation["date_column"], validation.get("label_end_column", validation["date_column"])
        train_end = pd.to_datetime(development[end], errors="coerce", utc=True)
        held_date = pd.to_datetime(frame[date], errors="coerce", utc=True)
        held_end = pd.to_datetime(frame[end], errors="coerce", utc=True)
        if (
            train_end.isna().any()
            or held_date.isna().any()
            or held_end.isna().any()
            or train_end.max() >= held_date.min()
            or (held_end < held_date).any()
            or held_end.max() > pd.Timestamp(as_of)
        ):
            conflict("native_assessment_time_or_maturity_invalid")
    return {
        "strategy": strategy,
        "entity_separation_checked": bool(group),
        "outcome_window_checked": strategy == "oot",
        "row_identity": "reviewer_declared; unknown upstream or modified imports are not linked automatically",
    }


def assess(job, check):
    from execution_jobs import service

    actor = get_user_model().objects.get(pk=job.authority["actor_id"])
    check()
    # The queue lock commits the common outcome-access reservation before any
    # protected payload is fetched/deserialized. Failed/crashed attempts remain.
    with service.locked():
        check()
        prepared, sealed, raw_export, _ = plan(actor, job.specification["protected_input_id"])
        if digest(prepared) != job.specification["assessment_sha256"]:
            conflict("native_assessment_plan_changed")
        spec = sealed.specification
        contract = sealed.adoption.training_job.result["prediction_contract"]
        identity = holdout_spec(
            spec["input_sha256"], contract["target_column"], list(range(spec["rows"])), "raw_snapshot"
        )
        access, history = reserve_holdout_access(
            identity,
            job.dataset_id,
            sealed.adoption.training_job_id,
            actor,
            {
                "scope": KIND,
                "job_id": str(job.pk),
                "adoption_id": prepared["adoption_id"],
                "protected_input_id": str(sealed.pk),
                "assessment_sha256": digest(prepared),
            },
        )
    try:
        check()
        raw = bytes(
            NativeProtectedInput.objects.filter(pk=sealed.pk)
            .annotate(bounded=Substr("payload", 1, BUDGET["max_input_bytes"] + 1))
            .values_list("bounded", flat=True)
            .get()
        )
        if (
            len(raw) != spec["bytes"]
            or len(raw) > BUDGET["max_input_bytes"]
            or native_candidate.sha(raw) != spec["input_sha256"]
        ):
            conflict("native_protected_payload_changed")
        frame = training_search.parsed_frame(raw)
        training = sealed.adoption.training_job
        development_raw, _, _ = csv_scoring.input_bytes(
            actor.pk, job.dataset_id, check, training.specification["training"]["source"]
        )
        development = training_search.parsed_frame(development_raw)
        separation = population(
            frame, development, training.specification["training"]["options"]["validation"], spec["assessment_as_of"]
        )
        labels = frame[contract["target_column"]]
        if labels.isna().any():
            conflict("native_assessment_labels_missing")
        if contract["task"] == "regression":
            labels = pd.to_numeric(labels, errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(labels).all():
                conflict("native_assessment_labels_invalid")
        else:
            mapping = {str(c["label"]): c["encoded"] for c in contract["class_mapping"]}
            labels = labels.astype(str).map(mapping)
            if labels.isna().any():
                conflict("native_assessment_labels_invalid")
            labels = labels.to_numpy(dtype=int)
        feature_raw = frame[training.result["features"]].to_csv(index=False).encode()
        scored = native_candidate.score(
            raw_export, native_candidate.sha(raw_export), feature_raw, chunk_size=BUDGET["chunk_size"], check=check
        )
        check()
        metric = training.result["metric"]
        try:
            primary = metric_value(metric, labels, scored["scores"])
        except ValueError:
            conflict("native_assessment_primary_metric_unavailable")
        metrics = development_metrics(
            labels, scored["scores"], contract["task"], len(contract["class_mapping"]), metric["cost_matrix"]
        )
        check()
        access.attempt_state = "completed"
        access.save(update_fields=["attempt_state"])
        return {
            "schema_version": 1,
            "scope": KIND,
            "job_id": str(job.pk),
            **prepared,
            "outcome_access_id": str(access.pk),
            "prior_related_accesses": history["total_related_accesses"],
            "input_sha256": spec["input_sha256"],
            "n_assessed": len(frame),
            "metric": metric,
            "primary_value": primary,
            "metrics": metrics,
            "prediction_contract": contract,
            "population_checks": separation,
            "scores_sha256": digest(scored["scores"]),
            "candidate_adopted_for_assessment": True,
            "final_holdout_accessed": True,
            "evidence_status": "exploratory",
            "confirmatory": False,
            "limitation": LIMITATION,
            "review_approved": False,
            "production_use_approved": False,
            "legacy_projection_updated": False,
        }
    except BaseException:
        access.attempt_state = "failed"
        access.save(update_fields=["attempt_state"])
        raise
