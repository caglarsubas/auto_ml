#!/usr/bin/env python3
"""Offline Linux-operator evidence verification and private runbook handoff.

Expected digests and installation pins must come from independent trusted
records. A matching checksum is neither a signature nor execution approval.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

import private_queue_incidents as triage

MAX_FILE_BYTES = triage.MAX_BYTES + 1024
SIGNALS = {"failed", "blocked", "expired_request", "overdue_lease", "missing_lease", "attempt_limit"}
STATES = {"queued", "running", "cancel_requested", "succeeded", "blocked", "failed", "cancelled"}
KINDS = {"package_integrity_v1", "native_csv_scoring_v1", "native_numeric_training_search_v1",
         "native_training_scoring_v1", "native_protected_assessment_v1", "unsupported"}
STEPS = {
    "retain": "Retain the original evidence, separately trusted digest, installation pins and this handoff under the installation retention/egress policy.",
    "service_attention": "Ask the installation owner to inspect the identified service and existing lifecycle readiness evidence. This handoff neither tests connectivity nor repairs services.",
    "queue_unavailable": "Ask the installation owner to investigate API/database observation availability. Unavailable is not an empty or healthy queue.",
    "queue_signals": "Correlate exact project/job IDs and revisions with the project owner's authorized operational handoff. Signals overlap; terminal failures may be historical.",
    "incomplete": "The sample is truncated, unstable or has unknown states. Preserve those limits and collect a separately authorized new observation if needed.",
    "age": "Compare the observation interval with the incident timeline. The chosen age threshold is a handoff aid, not proof of current health.",
    "authority": "Record investigation findings and a named owner. Maintenance, recovery, new requests, model review and production use each require their separate approved workflow. Do not edit job state, raise limits or replay requests from this handoff.",
    "protected": "Interrupted assessments may have accessed protected outcomes. Preserve access history and exploratory status; this handoff cannot restore confirmatory evidence.",
}


def require(condition):
    if not condition:
        raise ValueError("queue_evidence_invalid")


def keys(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected.split()))


def integer(value, minimum=0):
    require(type(value) is int and minimum <= value <= 2**63 - 1)


def digest(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None)
    return value


def timestamp(value):
    require(isinstance(value, str) and len(value) <= 40)
    parsed = dt.datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0))
    return parsed


def text(value, limit=1024):
    require(isinstance(value, str) and len(value) <= limit and not any(ord(c) < 32 for c in value))


def identifier(value, pattern):
    require(isinstance(value, str) and re.fullmatch(pattern, value) is not None)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def services(value, roles):
    require(isinstance(value, dict) and set(value) == roles)
    for service in value.values():
        require(isinstance(service, dict))
        if service.get("status") == "missing":
            require(service == {"status": "missing", "attention_required": True})
            continue
        keys(service, "container_id image_id restart_count state attention_required")
        digest(service["container_id"])
        require(isinstance(service["image_id"], str) and service["image_id"].startswith("sha256:"))
        digest(service["image_id"][7:])
        integer(service["restart_count"])
        state = service["state"]
        require(isinstance(state, dict) and set(state) == set(triage.STATE_KEYS))
        require(all(type(state[k]) is bool for k in triage.STATE_KEYS[:5]))
        integer(state["ExitCode"])
        integer(state["Pid"])
        attention = not state["Running"] or any(state[k] for k in triage.STATE_KEYS[1:5]) or state["ExitCode"] != 0
        require(type(service["attention_required"]) is bool and service["attention_required"] == attention)


def queue(value):
    require(isinstance(value, dict))
    if value.get("status") == "unavailable":
        require(set(value) in ({"status", "reason"}, {"schema", "status", "reason"}))
        require(value.get("schema", "native_queue_operator_snapshot_v1") == "native_queue_operator_snapshot_v1")
        require(value["reason"] in {"api_not_active", "probe_transport_unavailable", "probe_unavailable", "queue_metadata_unavailable"})
        return
    keys(value, "schema status observed_at scope read_only_transaction repeatable_read statement_timeout_ms jobs_enabled states signals incident_total attempt_limit rows row_limit truncated selection guidance live_service_health recovery_authorized")
    require(value["schema"] == "native_queue_operator_snapshot_v1" and value["status"] == "observed")
    timestamp(value["observed_at"])
    require(value["scope"] == "trusted_installation_all_projects" and value["read_only_transaction"] is True and value["repeatable_read"] is True)
    require(type(value["statement_timeout_ms"]) is int and value["statement_timeout_ms"] == 5000)
    require(type(value["jobs_enabled"]) is bool and value["row_limit"] == 50 and type(value["row_limit"]) is int)
    require(value["live_service_health"] == "not_tested" and value["recovery_authorized"] is False)
    require(isinstance(value["states"], dict) and set(value["states"]) == STATES | {"unknown"})
    require(isinstance(value["signals"], dict) and set(value["signals"]) == SIGNALS)
    for count in [*value["states"].values(), *value["signals"].values(), value["incident_total"]]:
        integer(count)
    integer(value["attempt_limit"], 1)
    rows = value["rows"]
    require(isinstance(rows, list) and len(rows) == min(50, value["incident_total"]))
    require(type(value["truncated"]) is bool and value["truncated"] == (value["incident_total"] > len(rows)))
    seen = set()
    for row in rows:
        keys(row, "job_id dataset_id project_id revision state attempts kind created_at expires_at lease_until signals")
        for field in ("job_id", "project_id"):
            identifier(row[field], r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        require(row["job_id"] not in seen)
        seen.add(row["job_id"])
        for field in ("dataset_id", "revision", "attempts"):
            integer(row[field])
        require(row["state"] in STATES and row["kind"] in KINDS)
        require(timestamp(row["created_at"]) <= timestamp(row["expires_at"]))
        if row["lease_until"] is not None:
            timestamp(row["lease_until"])
        flags = row["signals"]
        require(isinstance(flags, list) and 0 < len(flags) <= len(SIGNALS) and all(isinstance(s, str) and s in SIGNALS for s in flags) and len(set(flags)) == len(flags))
    text(value["selection"])
    require(isinstance(value["guidance"], dict) and set(value["guidance"]) == SIGNALS)
    for guidance in value["guidance"].values():
        text(guidance)


def verify(raw, *, expected_sha256, expected_plan_sha256, installation_id, initialization_id, now=None, max_age_seconds=900):
    """Pure verification: no plan, credentials, engine, database or network read."""
    digest(expected_sha256)
    digest(expected_plan_sha256)
    identifier(installation_id, r"[a-z][a-z0-9-]{0,31}")
    identifier(initialization_id, r"[0-9a-f]{32}")
    require(type(max_age_seconds) is int and 1 <= max_age_seconds <= 86400)
    require(isinstance(raw, bytes) and len(raw) <= MAX_FILE_BYTES)
    wrapper = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=lambda _: require(False))
    keys(wrapper, "evidence sha256")
    evidence = wrapper["evidence"]
    canonical = triage.encode(evidence)
    require(len(canonical) <= triage.MAX_BYTES)
    require(wrapper["sha256"] == expected_sha256 == hashlib.sha256(canonical).hexdigest())
    keys(evidence, "schema plan_manifest_sha256 installation_id architecture plan_verified archives_reverified installation_qualified release_qualified expert_isolation_qualified read_only authority initialization_id application_profile_sha256 observation_started_at observation_finished_at managed_operation_serialized services_before services_after dependencies_before dependencies_after stable_service_observations queue dependency_health https_health recovery_authorized review_approved production_use_approved limitations")
    require(evidence["schema"] == "private_queue_incident_evidence_v1" and evidence["plan_manifest_sha256"] == expected_plan_sha256)
    require(evidence["installation_id"] == installation_id and evidence["initialization_id"] == initialization_id)
    require(evidence["architecture"] in {"amd64", "arm64"} and evidence["authority"] == "linux_root_with_trusted_installation_plan")
    digest(evidence["application_profile_sha256"])
    for field in ("plan_verified", "read_only", "managed_operation_serialized"):
        require(evidence[field] is True)
    for field in ("archives_reverified", "installation_qualified", "release_qualified", "expert_isolation_qualified", "recovery_authorized", "review_approved", "production_use_approved"):
        require(evidence[field] is False)
    require(evidence["dependency_health"] == evidence["https_health"] == "not_tested")
    for key in ("services_before", "services_after"):
        services(evidence[key], {"api", "worker", "dispatcher", "ingress"})
    for key in ("dependencies_before", "dependencies_after"):
        services(evidence[key], set(triage.startup.ROLES))
    stable = evidence["services_before"] == evidence["services_after"] and evidence["dependencies_before"] == evidence["dependencies_after"]
    require(type(evidence["stable_service_observations"]) is bool and evidence["stable_service_observations"] == stable)
    queue(evidence["queue"])
    require(isinstance(evidence["limitations"], list) and len(evidence["limitations"]) == 6)
    for limit in evidence["limitations"]:
        text(limit)
    started, finished = timestamp(evidence["observation_started_at"]), timestamp(evidence["observation_finished_at"])
    current = now or dt.datetime.now(dt.timezone.utc)
    require(current.tzinfo is not None and started <= finished <= current + dt.timedelta(seconds=30))
    age = max(0, int((current - finished).total_seconds()))
    return evidence, {"verified_at": current.isoformat(), "age_seconds": age, "max_age_seconds": max_age_seconds,
                      "older_than_selected_age": age > max_age_seconds}


def load(path):
    require(sys.platform == "linux" and os.geteuid() == 0 and path.is_absolute() and ".." not in path.parts)
    parent = triage.resources.initializer.trusted_directory(path.parent)
    try:
        info = os.fstat(parent)
        require(info.st_uid == info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o700)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0 and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= MAX_FILE_BYTES)
            triage.checker.no_directory_acl(stream.fileno())
            raw = stream.read(MAX_FILE_BYTES + 1)
            require(len(raw) <= MAX_FILE_BYTES)
            return raw
    finally:
        os.close(parent)


def handoff(evidence, verification, expected_sha256):
    """Render allowlisted facts and fixed guidance, never source free text/code."""
    attention = [group + "/" + role for group in ("services_before", "services_after", "dependencies_before", "dependencies_after")
                 for role, service in sorted(evidence[group].items()) if service["attention_required"]]
    q = evidence["queue"]
    observed = q["status"] == "observed"
    steps = ["retain"]
    if attention:
        steps.append("service_attention")
    if not observed:
        steps.append("queue_unavailable")
    elif q["incident_total"]:
        steps.append("queue_signals")
    if not evidence["stable_service_observations"] or (observed and (q["truncated"] or q["states"]["unknown"])):
        steps.append("incomplete")
    steps += ["age", "authority", "protected"]
    value = {"schema": "private_queue_operator_handoff_v1", "source_evidence_sha256": expected_sha256,
             "installation_id": evidence["installation_id"], "initialization_id": evidence["initialization_id"],
             "plan_manifest_sha256": evidence["plan_manifest_sha256"], "application_profile_sha256": evidence["application_profile_sha256"],
             "observation_started_at": evidence["observation_started_at"], "observation_finished_at": evidence["observation_finished_at"],
             "verification": verification, "service_attention": attention, "stable_service_observations": evidence["stable_service_observations"],
             "queue_status": q["status"], "incident_total": q["incident_total"] if observed else None,
             "truncated": q["truncated"] if observed else None, "signals": q["signals"] if observed else None,
             "job_references": [{k: row[k] for k in ("job_id", "project_id", "dataset_id", "revision", "signals")} for row in q["rows"]] if observed else [],
             "investigation_steps": [{"id": step, "instruction": STEPS[step]} for step in steps],
             "checksum_is_signature": False, "current_health_qualified": False, "recovery_authorized": False,
             "review_approved": False, "production_use_approved": False, "release_qualified": False,
             "limitation": "Offline checksum/context/schema verification against independently trusted pins; no live checks or authenticity claim. No commands or changes authorized."}
    return {"evidence": value, "sha256": hashlib.sha256(triage.encode(value)).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--installation-id", required=True)
    parser.add_argument("--initialization-id", required=True)
    parser.add_argument("--max-age-seconds", type=int, default=900)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence, verification = verify(load(args.evidence), expected_sha256=args.expected_sha256,
                                    expected_plan_sha256=args.expected_plan_sha256, installation_id=args.installation_id,
                                    initialization_id=args.initialization_id, max_age_seconds=args.max_age_seconds)
    value = handoff(evidence, verification, args.expected_sha256)
    triage.export(value, args.output)
    print(json.dumps({"schema": "private_queue_handoff_export_v1", "verified": True, "sha256": value["sha256"],
                      "older_than_selected_age": verification["older_than_selected_age"], "recovery_authorized": False}))


if __name__ == "__main__":
    try:
        main()
    except (triage.checker.planner.PlanError, OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        print("queue_evidence_verification_or_handoff_failed", file=sys.stderr)
        sys.exit(1)
