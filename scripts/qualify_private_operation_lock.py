"""Actual managed-controller lock tests inside the exclusively owned Linux root."""

import fcntl
from pathlib import Path

import private_dependency_start as startup
import private_installation_adopt as adopter
import private_schema_init as schema


def qualify(value, plan, expected, parent, adopted):
    root = Path(value["request"]["root"]) / "dependencies"
    paths = [root / name for name in ("started.json", "schema.json", "schema-intent.json")]
    history = {str(p): p.read_bytes() for p in paths}
    identifiers = {r: row["container_id"] for r, row in adopted["services"].items()}

    def states():
        return {r: {"Id": info["Id"], "RestartCount": info["RestartCount"],
                    "State": {k: info["State"][k] for k in ("Running", "Paused", "Restarting", "Dead", "StartedAt", "FinishedAt", "ExitCode", "Pid", "OOMKilled", "Error")}}
                for r, identifier in identifiers.items()
                for info in [startup.resources.inspect("container", identifier)]}

    before = states()
    callbacks = {"dependency_start": lambda: startup.start(plan, expected),
                 "schema_initialization": lambda: schema.initialize(plan, expected),
                 "application_adoption": lambda: adopter.adoption(plan, expected, parent / "server.crt")}
    with (root / "start.lock").open("r+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        for callback in callbacks.values():
            try:
                callback()
            except startup.checker.planner.PlanError as error:
                if str(error) != "dependency_operation_in_progress":
                    raise
            else:
                raise startup.checker.planner.PlanError("operation_fixture_held_lock_bypassed")
    checked = []
    original_https = adopter.https_check

    def locked_https(*args):
        with (root / "start.lock").open("r+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                checked.append("final_https")
            else:
                raise startup.checker.planner.PlanError("operation_fixture_lock_released_early")
        return original_https(*args)

    try:
        adopter.https_check = locked_https
        result = adopter.adoption(plan, expected, parent / "server.crt")
    finally:
        adopter.https_check = original_https
    assert checked and result["managed_operation_serialized"] is True
    with (root / "start.lock").open("r+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert states() == before
    assert {str(p): p.read_bytes() for p in paths} == history
    return {"held_lock_denials": {name: "blocked_before_startup" for name in callbacks},
            "guard_retained_through_verified_https": "passed", "released_after_adoption": "passed",
            "same_service_ids_states_and_history": "passed", "operator_installation_modified": False}
