"""Read-only lifecycle observation checks on the exclusively owned Linux fixture."""

import fcntl
from pathlib import Path

import private_lifecycle_readiness as readiness


def qualify(value, plan, expected, parent, adopted):
    resources = readiness.resources
    dependencies = Path(value["request"]["root"]) / "dependencies"
    history = {name: (dependencies / name).read_bytes() for name in ("started.json", "schema.json", "schema-intent.json")}
    observed = readiness.observe(plan, expected, parent / "server.crt")
    assert observed["schema"] == "private_lifecycle_readiness_v1" and observed["read_only"] is True
    assert observed["anonymous_selected_ca_https"] == "passed" and observed["managed_operation_serialized"] is True
    for key in ("maintenance_execution_authorized", "production_recovery_qualified", "upgrade_rollback_qualified",
                "fresh_runtime_preflight_executed", "installation_qualified", "release_qualified", "customer_accepted"):
        assert observed[key] is False
    assert len(observed["services"]["applications"]) == 4 and len(observed["services"]["dependencies"]) == 3
    assert all(observed["services"]["applications"][role]["container_id"] == row["container_id"]
               for role, row in adopted["services"].items())
    # Read-only observation must refuse a busy operation guard, not wait or repair.
    with (dependencies / "start.lock").open("rb") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            readiness.observe(plan, expected, parent / "server.crt")
        except readiness.checker.planner.PlanError as error:
            assert str(error) == "dependency_operation_in_progress"
        else:
            raise readiness.checker.planner.PlanError("lifecycle_fixture_held_lock_bypassed")
    # Only this synthetic qualifier pauses/unpauses its owned worker. The
    # reporter itself must reject the fault, leaving it for the owner to undo.
    worker = adopted["services"]["worker"]["container_id"]
    resources.command(["container", "pause", worker])
    try:
        try:
            readiness.observe(plan, expected, parent / "server.crt")
        except readiness.checker.planner.PlanError as error:
            assert str(error) == "installation_adopt_service_not_active"
        else:
            raise readiness.checker.planner.PlanError("lifecycle_fixture_paused_worker_accepted")
        assert resources.inspect("container", worker)["State"]["Paused"] is True
    finally:
        resources.command(["container", "unpause", worker])
    for services in observed["services"].values():
        for row in services.values():
            assert readiness.service_observation(resources.inspect("container", row["container_id"])) == row
    assert {name: (dependencies / name).read_bytes() for name in history} == history
    with (dependencies / "start.lock").open("rb") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return {"managed_read_only_observation": "passed", "held_lock_refused": "passed",
            "paused_worker_rejected_without_repair": "passed", "same_seven_services_and_history": "passed",
            "operator_installation_modified": False, "synthetic_example": observed}
