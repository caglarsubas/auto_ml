"""Exercise consistency rejection using the owned managed Linux incident export."""

import copy
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import private_queue_evidence as evidence


def qualify(parent):
    root = parent / "incident-evidence"
    source, handoff = root / "incident.json", root / "handoff.json"
    before = {p: p.read_bytes() for p in (source, handoff)}
    original = json.loads(evidence.load(source))
    value = original["evidence"]
    pins = dict(expected_sha256=original["sha256"], expected_plan_sha256=value["plan_manifest_sha256"],
                installation_id=value["installation_id"], initialization_id=value["initialization_id"])
    _, verification = evidence.verify(before[source], **pins)
    assert verification["queue_consistency"] == "cross_checked_metadata" and verification["sample_order"] == "newest_first"
    contradictory = copy.deepcopy(value)
    contradictory["queue"]["states"]["failed"] += 1
    outside = copy.deepcopy(value)
    outside["queue"]["observed_at"] = (evidence.timestamp(value["observation_started_at"]) - dt.timedelta(seconds=1)).isoformat()
    for index, altered in enumerate((contradictory, outside)):
        digest = hashlib.sha256(evidence.triage.encode(altered)).hexdigest()
        forged = evidence.triage.encode(dict(evidence=altered, sha256=digest))
        path, output = root / f"consistency-invalid-{index}.json", root / f"consistency-rejected-{index}.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(forged)
        result = subprocess.run([sys.executable, str(Path(evidence.__file__)), str(path), "--expected-sha256", digest,
                                 "--expected-plan-sha256", pins["expected_plan_sha256"], "--installation-id", pins["installation_id"],
                                 "--initialization-id", pins["initialization_id"], "--output", str(output)],
                                capture_output=True, timeout=20, check=False)
        assert result.returncode == 1 and not output.exists()
        assert result.stderr.strip() == b"queue_evidence_verification_or_handoff_failed" and not result.stdout
        assert path.read_bytes() == forged
    assert {p: p.read_bytes() for p in before} == before
    return {"schema": "private_queue_consistency_qualification_v1", "actual_export_consistency_checked": "passed",
            "recomputed_digest_contradiction_refused_by_cli": "passed", "outside_observation_interval_refused_by_cli": "passed",
            "no_invalid_handoff_published": "passed", "original_source_and_handoff_preserved": "passed",
            "verification": verification, "live_checks_or_recovery_authorized": False,
            "operator_installation_modified": False}
