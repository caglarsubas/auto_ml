"""Exercise operator triage only on the exclusively owned managed Linux fixture."""

import fcntl
import hashlib
import json
from pathlib import Path

import private_queue_incidents as triage


def qualify(value, plan, expected, parent, adopted):
    resources = triage.resources
    dependencies = Path(value["request"]["root"]) / "dependencies"
    history = {name: (dependencies / name).read_bytes() for name in ("started.json", "schema.json", "schema-intent.json")}
    observed = triage.observe(plan, expected)
    report = observed["evidence"]
    assert observed["sha256"] == hashlib.sha256(triage.encode(report)).hexdigest()
    assert report["queue"]["status"] == "observed" and report["queue"]["read_only_transaction"] is True
    assert report["queue"]["repeatable_read"] is True and report["queue"]["statement_timeout_ms"] == 5000
    assert report["queue"]["scope"] == "trusted_installation_all_projects" and report["stable_service_observations"]
    assert all(report["services_after"][role]["container_id"] == row["container_id"] for role, row in adopted["services"].items())
    for key in ("recovery_authorized", "review_approved", "production_use_approved", "installation_qualified", "release_qualified"):
        assert report[key] is False
    output = parent / "incident-evidence"
    output.mkdir(mode=0o700)
    target = output / "incident.json"
    triage.export(observed, target)
    assert json.loads(target.read_text()) == observed and target.stat().st_mode & 0o777 == 0o600
    original = target.read_bytes()
    try:
        triage.export(observed, target)
    except (OSError, triage.checker.planner.PlanError):
        pass
    else:
        raise AssertionError("incident_fixture_export_overwritten")
    assert target.read_bytes() == original
    with (dependencies / "start.lock").open("rb") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            triage.observe(plan, expected)
        except triage.checker.planner.PlanError as error:
            assert str(error) == "dependency_operation_in_progress"
        else:
            raise AssertionError("incident_fixture_held_lock_bypassed")
    worker = adopted["services"]["worker"]["container_id"]
    resources.command(["container", "pause", worker])
    try:
        paused = triage.observe(plan, expected)["evidence"]
        assert paused["services_after"]["worker"]["attention_required"] and paused["services_after"]["worker"]["state"]["Paused"]
        assert paused["queue"]["status"] == "observed" and resources.inspect("container", worker)["State"]["Paused"]
    finally:
        resources.command(["container", "unpause", worker])
    api = adopted["services"]["api"]["container_id"]
    resources.command(["container", "pause", api])
    try:
        unavailable = triage.observe(plan, expected)["evidence"]
        assert unavailable["queue"] == {"status": "unavailable", "reason": "api_not_active"}
        assert resources.inspect("container", api)["State"]["Paused"] is True
    finally:
        resources.command(["container", "unpause", api])
    final = triage.observe(plan, expected)["evidence"]
    assert final["services_after"] == report["services_after"]
    assert {name: (dependencies / name).read_bytes() for name in history} == history
    return {"schema": "private_queue_incident_qualification_v1", "trusted_linux_operator_read_only_postgresql": "passed",
            "bounded_metadata_probe": "passed", "private_exclusive_digest_export": "passed", "held_lock_refused": "passed",
            "paused_worker_observed_without_repair": "passed", "paused_api_unavailable_without_repair": "passed",
            "same_service_ids_states_and_history": "passed", "operator_installation_modified": False,
            "synthetic_example": observed}
