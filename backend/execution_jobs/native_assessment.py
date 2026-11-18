"""Independent native adoption and sealed, access-accounted assessment.

Protected custody prevents the native training/search/scoring entrypoints from
reading these labels. Unknown upstream histories never become confirmatory.
"""

import csv
import io
import json
import uuid
from datetime import datetime, timedelta

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.functions import Substr
from django.utils import timezone

from access_control import projects
from access_control.authority import actor_snapshot
from deployment import native_candidate
from deployment.reviews import digest, lock_authority
from deployment.scoring_receipts import require_digest
from execution_jobs import csv_scoring, training_search, training_scoring
from execution_jobs.models import NativeAdoption, NativeAdoptionEvent, NativeJob, NativeProtectedInput
from modeling.declared_metric import metric_spec
from modeling.holdout_evidence import holdout_spec, reserve_holdout_access
from modeling.models import HoldoutAccess
from modeling.native_assessment_replay import CHUNK_SIZE, AssessmentReplayError, calculate_assessment

KIND = "native_protected_assessment_v1"
PLAN_SCHEMA = 2
BUDGET = {**training_search.BUDGET, "chunk_size": CHUNK_SIZE}
SCOPE = "development_candidate_for_protected_assessment_only"
PROSPECTIVE = "prospective_temporal_v1"
ASSESSMENT_POLICY = {
    "version": "native_assessment_policy_v2",
    "confirmation_protocol": PROSPECTIVE,
    "reuse": "possible_access_counts; exact_input_or_intersecting_project_window_withholds_confirmation",
    "exception": "reviewer_attested_exploratory_only",
    "evaluation": "frozen_candidate_and_development_objective",
}
PROSPECTIVE_LIMITATION = (
    "Prospective temporal protocol. The exact independent approval precedes the prediction window. "
    "First use and external custody are reviewer attestations. Reuse, uncertain access and incomplete "
    "provenance withhold confirmation. The worker scores the frozen candidate without refitting."
)
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
    _, source, authority = csv_scoring.unprotected_input_bytes(
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


def sealed_header(raw, job, time_columns=(), *, as_of=None):
    from modeling.prediction_contract import fixed_outcome_window, outcome_window_bounds, PredictionContractError

    required = [*job.result["features"], job.result["prediction_contract"]["target_column"], *controls(job)]
    try:
        rows = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
        header = next(row for row in rows if row)
        count = 0
        if len(set(header)) != len(header) or set(header) != set(required) or len(header) != len(required):
            raise ValueError
        positions = [header.index(name) for name in time_columns]
        times = [[] for _ in positions]
        for row in rows:
            if row:
                count += 1
                if len(row) != len(header) or count > BUDGET["max_rows"]:
                    raise ValueError
                for values, index in zip(times, positions):
                    values.append(row[index])
        if not 30 <= count <= BUDGET["max_rows"]:
            raise ValueError
    except (ValueError, csv.Error, UnicodeError, StopIteration):
        raise ValueError(
            "Protected CSV requires 30–1000 rows and exactly the frozen features, target and validation controls."
        ) from None
    schema = {"header": header, "rows": count}
    if not times:
        return schema, None
    scope = fixed_outcome_window(job.result['prediction_contract'])
    if scope:
        try:
            outcome_window_bounds(pd.DataFrame(dict(zip(time_columns, times, strict=True))),
                                  job.specification['training']['options']['validation'], scope, as_of)
        except PredictionContractError:
            conflict('native_assessment_time_or_maturity_invalid')
    dates, ends = (pd.to_datetime(values, format="ISO8601", errors="coerce", utc=True) for values in times)
    if dates.isna().any() or ends.isna().any() or (ends <= dates).any():
        conflict("native_confirmation_invalid_outcome_window")
    return schema, {
        "start": dates.min().isoformat(timespec="nanoseconds"),
        "end": ends.max().isoformat(timespec="nanoseconds"),
    }


def prospective_window(window, approval, as_of):
    if pd.Timestamp(window["start"]) <= pd.Timestamp(approval.created_at):
        conflict("native_confirmation_candidate_not_frozen_before_prediction")
    if pd.Timestamp(window["end"]) > pd.Timestamp(as_of) or as_of > timezone.now():
        conflict("native_confirmation_outcomes_not_mature")
    return {"version": PROSPECTIVE, "approved_at": approval.created_at.isoformat(), "window": window,
            "external_first_use": "attested_by_independent_reviewer"}


def seal(actor, adoption_id, data, upload):
    from execution_jobs import service
    from modeling.prediction_contract import fixed_outcome_window

    base_fields = {"request_id", "proposal_sha256", "rationale", "assessment_as_of",
                   "population_and_maturity_attested"}
    prospective = "prospective_first_use_attested" in data
    if (set(data) - {"prospective_first_use_attested"} != base_fields
            or data["population_and_maturity_attested"] != "true"
            or prospective and data["prospective_first_use_attested"] != "true"):
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
        validation = job.specification["training"]["options"]["validation"]
        scope = fixed_outcome_window(job.result['prediction_contract'])
        columns = ()
        if prospective or scope:
            if validation["strategy"] != "oot" or not validation.get("label_end_column"):
                conflict("native_confirmation_requires_explicit_temporal_windows")
            columns = (validation["date_column"], validation["label_end_column"])
        if scope and as_of > timezone.now():
            conflict('native_assessment_time_or_maturity_invalid')
        schema, window = sealed_header(raw, job, columns, as_of=as_of)
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
        if prospective:
            spec["confirmation_protocol"] = prospective_window(window, approval, as_of)
            spec["upstream_history"] = "reviewer_attested_first_use"
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
        "schema_version": PLAN_SCHEMA,
        "kind": KIND,
        "project_id": str(job.project_id),
        "adoption_id": str(adoption.pk),
        "proposal_sha256": adoption.proposal_sha256,
        "approval_event_id": str(approval.pk),
        "approval_sha256": approval.payload_sha256,
        "protected_input_id": str(protected.pk),
        "protected_input_sha256": protected.specification_sha256,
        "input_sha256": spec["input_sha256"],
        "training_job_id": str(job.pk),
        "training_result_sha256": job.result_sha256,
        "candidate_export_sha256": native_candidate.sha(raw_export),
        "training_specification_sha256": digest(job.specification),
        "prediction_contract_sha256": digest(job.result["prediction_contract"]),
        "metric_sha256": digest(job.result["metric"]),
        "assessment_policy": ASSESSMENT_POLICY,
        "assessment_policy_sha256": digest(ASSESSMENT_POLICY),
        "runtime": service.runtime(KIND),
        "limits": service.limits(KIND),
    }
    protocol = spec.get("confirmation_protocol")
    if protocol is not None:
        if protocol != prospective_window(protocol["window"], approval, datetime.fromisoformat(spec["assessment_as_of"])):
            conflict("native_confirmation_protocol_changed")
        result["confirmation_protocol"] = protocol
    return result, protected, raw_export, authority


def preview(actor, protected_id):
    prepared, protected, _, authority = plan(actor, protected_id)
    result = {
        **prepared,
        "assessment_sha256": digest(prepared),
        "input_metadata": protected.specification,
        "limitation": PROSPECTIVE_LIMITATION if "confirmation_protocol" in prepared else LIMITATION,
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
        service.record(job, "submitted", actor=actor, update_fields=["revision"])
        return service.authorized_receipt(job, [authority])


def verify_plan(job, prepared):
    saved = job.specification
    if saved.get("assessment_policy_sha256") != prepared["assessment_policy_sha256"]:
        conflict("native_assessment_policy_changed")
    if saved.get("runtime") != prepared["runtime"] or saved.get("limits") != prepared["limits"]:
        conflict("job_runtime_changed")
    if saved != {**prepared, "assessment_sha256": digest(prepared)}:
        conflict("native_assessment_plan_changed")


def recheck(job):
    actor = get_user_model().objects.get(pk=job.authority["actor_id"])
    prepared, _, _, _ = plan(actor, job.specification["protected_input_id"])
    verify_plan(job, prepared)


def assess(job, check):
    from execution_jobs.assessment_intake import prior_development_use
    from execution_jobs.assessment_reuse import classify_reuse
    from execution_jobs import service

    actor = get_user_model().objects.get(pk=job.authority["actor_id"])
    check()
    # The queue lock commits the common outcome-access reservation before any
    # protected payload is fetched/deserialized. Failed/crashed attempts remain.
    with service.locked():
        check()
        prepared, sealed, raw_export, _ = plan(actor, job.specification["protected_input_id"])
        verify_plan(job, prepared)
        spec = sealed.specification
        contract = sealed.adoption.training_job.result["prediction_contract"]
        identity = holdout_spec(
            spec["input_sha256"], contract["target_column"], list(range(spec["rows"])), "raw_snapshot"
        )
        protocol = prepared.get("confirmation_protocol")
        window = protocol["window"] if protocol else None
        reuse = classify_reuse(job, window, spec["input_sha256"])
        prior_development = prior_development_use(spec["input_sha256"], str(job.project_id), sealed_at=sealed.created_at)
        if prior_development:
            reuse["prior_development"] = prior_development
            reuse["reason"] = reuse["reason"] or "prior_development_input_access"
        reason = reuse["reason"] or (None if protocol else "reviewer_selected_exploratory")
        parameters = {
            "scope": KIND,
            "project_id": str(job.project_id),
            "job_id": str(job.pk),
            "adoption_id": prepared["adoption_id"],
            "protected_input_id": str(sealed.pk),
            "assessment_sha256": job.specification["assessment_sha256"],
            "assessment_policy_sha256": prepared["assessment_policy_sha256"],
            "reuse_adjudication": reuse,
            "reuse_adjudication_sha256": digest(reuse),
        }
        if protocol:
            parameters["prospective_window"] = window
            parameters["confirmation_protocol"] = protocol["version"]
        access, history = reserve_holdout_access(
            identity,
            job.dataset_id,
            sealed.adoption.training_job_id,
            actor,
            parameters,
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
        development_raw, _, _ = csv_scoring.unprotected_input_bytes(
            actor.pk, job.dataset_id, check, training.specification["training"]["source"]
        )
        development = training_search.parsed_frame(development_raw)
        metric = training.result["metric"]

        def predict(feature_raw):
            return native_candidate.score(
                raw_export, prepared["candidate_export_sha256"], feature_raw, chunk_size=BUDGET["chunk_size"], check=check
            )["scores"]

        try:
            calculated = calculate_assessment(
                frame, development, training.specification["training"]["options"]["validation"],
                spec["assessment_as_of"], contract, metric, training.result["features"], predict, check=check,
            )
        except AssessmentReplayError as error:
            conflict(error.code)
        access.attempt_state = "completed"
        access.save(update_fields=["attempt_state"])
        confirmed = bool(protocol and not reason)
        result = {
            "schema_version": 1,
            "scope": KIND,
            "job_id": str(job.pk),
            **prepared,
            "assessment_sha256": job.specification["assessment_sha256"],
            "outcome_access_id": str(access.pk),
            "prior_related_accesses": history["total_related_accesses"],
            "reuse_adjudication": reuse,
            "confirmation_reason": reason or "first_prospective_assessment_completed",
            **calculated,
            "metric": metric,
            "prediction_contract": contract,
            "candidate_adopted_for_assessment": True,
            "final_holdout_accessed": True,
            "evidence_status": "confirmatory" if confirmed else "exploratory",
            "confirmatory": confirmed,
            "limitation": PROSPECTIVE_LIMITATION if protocol else LIMITATION,
            "review_approved": False,
            "production_use_approved": False,
            "legacy_projection_updated": False,
        }
        return result
    except BaseException:
        access.attempt_state = "failed"
        access.save(update_fields=["attempt_state"])
        raise


def bound_access(job, result):
    spec = job.specification
    access_id = result.get("outcome_access_id")
    if (
        not isinstance(access_id, str) or str(uuid.UUID(access_id)) != access_id
        or any(result.get(key) != value for key, value in spec.items())
        or result.get("job_id") != str(job.pk)
        or digest(result.get("prediction_contract")) != spec["prediction_contract_sha256"]
        or digest(result.get("metric")) != spec["metric_sha256"]
        or not isinstance(result.get("reuse_adjudication"), dict)
    ):
        conflict("job_assessment_receipt_changed")
    reuse = result["reuse_adjudication"]
    confirmed = bool(spec.get("confirmation_protocol") and not reuse.get("reason"))
    reason = reuse.get("reason") or (
        "first_prospective_assessment_completed" if confirmed else "reviewer_selected_exploratory"
    )
    if (result.get("confirmatory") is not confirmed or result.get("confirmation_reason") != reason
            or result.get("evidence_status") != ("confirmatory" if confirmed else "exploratory")):
        conflict("job_assessment_receipt_changed")
    access = HoldoutAccess.objects.filter(
        pk=access_id, execution_id=spec["training_job_id"],
        file_id=job.dataset_id, actor_id=job.actor_id, attempt_state="completed",
        dataset_sha256=spec["input_sha256"], parameters__job_id=str(job.pk),
        parameters__project_id=spec["project_id"], parameters__adoption_id=spec["adoption_id"],
        parameters__protected_input_id=spec["protected_input_id"],
        parameters__assessment_sha256=spec["assessment_sha256"],
        parameters__assessment_policy_sha256=spec["assessment_policy_sha256"],
        parameters__reuse_adjudication_sha256=digest(reuse),
        parameters__reuse_adjudication=reuse,
    )
    if confirmed:
        access = access.filter(parameters__confirmation_protocol=PROSPECTIVE,
                               parameters__prospective_window=spec["confirmation_protocol"]["window"])
    return access


def publish_assessment(job, result):
    """Bind the outcome-access receipt in the same transaction as the fenced result."""
    try:
        access = bound_access(job, result).filter(evidence_status="exploratory")
        return access.update(evidence_status="confirmatory") == 1 if result["confirmatory"] else access.exists()
    except (ValueError, KeyError, TypeError):
        return False


def applicability(job):
    """Check current use of frozen evidence without reopening the sealed input."""
    from execution_jobs import service

    result = job.result
    status = {
        "status": "exploratory", "confirmation_usable": False,
        "assessment_sha256": job.specification.get("assessment_sha256"),
        "reason_code": result.get("confirmation_reason", "exploratory_assessment"),
    }
    if result.get("confirmatory") is not True:
        return status
    if job.specification.get("schema_version") != PLAN_SCHEMA:
        return {**status, "status": "historical_unverified", "reason_code": "legacy_assessment_binding_unverified"}
    try:
        service.execution_reference(job.specification, "protected_input_id", "assessment_sha256")
        recheck(job)
        if not bound_access(job, result).filter(evidence_status="confirmatory").exists():
            conflict("job_assessment_receipt_changed")
    except (ObjectDoesNotExist, projects.ProjectDenied, OSError, ValueError, KeyError, TypeError) as error:
        return {**status, "status": "invalidated",
                "reason_code": getattr(error, "code", "native_assessment_evidence_unavailable")}
    return {**status, "status": "current", "confirmation_usable": True}
