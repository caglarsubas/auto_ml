"""Verify real exported incident evidence on the exclusively owned Linux fixture."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import private_queue_evidence as evidence


def qualify(value, expected, parent, adopted):
    source = parent / "incident-evidence" / "incident.json"
    original = source.read_bytes()
    wrapper = json.loads(original)
    trusted_sha = wrapper["sha256"]
    initialization_id = evidence.triage.resources.initialization(value)["initialization_id"]
    pins = dict(expected_sha256=trusted_sha, expected_plan_sha256=expected,
                installation_id=value["request"]["installation_id"], initialization_id=initialization_id)
    services = {role: evidence.triage.resources.inspect("container", row["container_id"])["State"] for role, row in adopted["services"].items()}
    observed, verification = evidence.verify(evidence.load(source), **pins)
    assert observed == wrapper["evidence"] and verification["older_than_selected_age"] is False
    output = source.parent / "handoff.json"
    args = [sys.executable, str(Path(evidence.__file__)), str(source), "--expected-sha256", trusted_sha,
            "--expected-plan-sha256", expected, "--installation-id", pins["installation_id"],
            "--initialization-id", initialization_id, "--output", str(output)]
    result = subprocess.run(args, capture_output=True, timeout=20, check=True)
    receipt = json.loads(result.stdout)
    handoff = json.loads(output.read_text())
    assert receipt["verified"] is True and receipt["recovery_authorized"] is False
    assert receipt["sha256"] == handoff["sha256"] == hashlib.sha256(evidence.triage.encode(handoff["evidence"])).hexdigest()
    assert handoff["evidence"]["source_evidence_sha256"] == trusted_sha and output.stat().st_mode & 0o777 == 0o600
    saved = output.read_bytes()
    duplicate = subprocess.run(args, capture_output=True, timeout=20, check=False)
    assert duplicate.returncode != 0 and output.read_bytes() == saved
    assert duplicate.stderr.strip() == b"queue_evidence_verification_or_handoff_failed"
    tampered = json.loads(original)
    tampered["evidence"]["queue"]["jobs_enabled"] = not tampered["evidence"]["queue"]["jobs_enabled"]
    for raw, override in [(evidence.triage.encode(tampered), {}), (original, {"expected_plan_sha256": "0" * 64}),
                          (original, {"initialization_id": "0" * 32})]:
        try:
            evidence.verify(raw, **(pins | override))
        except ValueError:
            pass
        else:
            raise AssertionError("queue_evidence_fixture_untrusted_input_accepted")
    assert source.read_bytes() == original
    assert {role: evidence.triage.resources.inspect("container", row["container_id"])["State"] for role, row in adopted["services"].items()} == services
    return {"schema": "private_queue_evidence_qualification_v1", "actual_private_export_offline_verified": "passed",
            "independent_digest_and_installation_pins": "passed", "tamper_and_wrong_context_refused": "passed",
            "private_exclusive_runbook_handoff_cli": "passed", "same_source_and_service_states": "passed",
            "live_checks_or_recovery_authorized": False, "operator_installation_modified": False,
            "synthetic_handoff": handoff}
