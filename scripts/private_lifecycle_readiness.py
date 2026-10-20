#!/usr/bin/env python3
"""Observe a managed installation without starting services or authorizing maintenance.

The JSON report is a point-in-time operator input, not backup/recovery, upgrade,
fresh database preflight, production-use or release qualification.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import private_dependency_start as startup
import private_installation_adopt as adopter

resources = adopter.resources
checker = adopter.checker
STATE_KEYS = ("Running", "Paused", "Restarting", "Dead", "StartedAt", "FinishedAt", "ExitCode", "Pid", "OOMKilled", "Error")
REQUIRED_REVIEW = [
    "Deployment target, trusted plan digest and selected client CA",
    "Maintenance window and permitted downtime",
    "Recovery point objective (RPO) and recovery time objective (RTO)",
    "Backup destination, encryption, capacity, retention and restore access",
    "Host firewall, ingress/egress policy and restricted-network acceptance",
]


def service_observation(info):
    """Allowlist nonsecret engine metadata; never emit environment or errors."""
    state = info.get("State", {})
    if (
        not all(key in state for key in STATE_KEYS)
        or state["Running"] is not True
        or any(state[key] is not False for key in ("Paused", "Restarting", "Dead", "OOMKilled"))
        or type(state["ExitCode"]) is not int or state["ExitCode"] != 0
        or type(state["Pid"]) is not int or state["Pid"] <= 0
        or state["Error"] != ""
        or any(not isinstance(state[key], str) or not state[key] for key in ("StartedAt", "FinishedAt"))
        or type(info.get("RestartCount")) is not int or info["RestartCount"] < 0
        or not isinstance(info.get("Id"), str) or not resources.re.fullmatch(r"[0-9a-f]{64}", info["Id"])
        or not isinstance(info.get("Image"), str) or not resources.re.fullmatch(r"sha256:[0-9a-f]{64}", info["Image"])
    ):
        raise checker.planner.PlanError("lifecycle_service_observation_invalid")
    return {"container_id": info["Id"], "image_id": info["Image"], "restart_count": info["RestartCount"],
            "state": {key: state[key] for key in STATE_KEYS if key != "Error"}}


def sample(value, expected, profile, digest, binding, images):
    applications = adopter.active_applications(profile, digest, binding, images)
    adopter.prerequisites(value, binding, applications)
    _, spec, receipt, _, _, root = startup.prepared_value(value, expected)
    try:
        dependencies = startup.snapshot(value, spec, receipt, images, True)
        startup.network(value, receipt, dependencies)
        prior = checker.planner.decode(startup.read_file(root, "started.json", 0, 0, 0o600, 16384))
        startup.prior_receipt(prior, expected, receipt, dependencies)
        return {"applications": {role: service_observation(info) for role, info in applications.items()},
                "dependencies": {role: service_observation(info) for role, info in dependencies.items()}}
    finally:
        os.close(root)


def observe(plan, expected, ca):
    value = checker.verify(plan, expected)
    if value["manifest"]["schema"] != checker.planner.PLAN_SCHEMA:
        raise checker.planner.PlanError("lifecycle_v3_plan_required")
    if sys.platform != "linux" or os.geteuid() != 0:
        raise checker.planner.PlanError("lifecycle_linux_root_required")
    initialized = resources.initialization(value)
    if initialized["plan_manifest_sha256"] != expected:
        raise checker.planner.PlanError("lifecycle_initialization_plan_mismatch")
    checker.check_paths(plan, expected)
    context = adopter.client_context(ca)
    with adopter.managed_operation(value, create_lock=False) as serialized:
        if serialized is not True:
            raise checker.planner.PlanError("lifecycle_managed_dependencies_required")
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        resources.docker_host(value["manifest"]["architecture"])
        if resources.record(["info", "--format", "{{json .}}"]).get("DefaultRuntime") != "runc":
            raise checker.planner.PlanError("lifecycle_default_runtime_required")
        images = {role: resources.inspect("image", identity) for role, identity in value["images"].items()}
        for role, image in images.items():
            if (image.get("Id") != value["images"][role]
                    or image.get("Architecture") != value["manifest"]["architecture"] or image.get("Os") != "linux"):
                raise checker.planner.PlanError("lifecycle_native_images_required")
        profile, digest, binding = adopter.application_profile(value, expected, initialized["initialization_id"])
        before = sample(value, expected, profile, digest, binding, images)
        adopter.https_check(value["request"], context)
        after = sample(value, expected, profile, digest, binding, images)
        if before != after:
            raise checker.planner.PlanError("lifecycle_services_changed_during_observation")
        return {**checker.receipt(value, expected), "schema": "private_lifecycle_readiness_v1",
                "read_only": True, "observation_started_at": started,
                "observation_finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "initialization_id": initialized["initialization_id"], "application_profile_sha256": digest,
                "services": after, "managed_operation_serialized": True,
                "anonymous_selected_ca_https": "passed", "stable_service_observations": True,
                "secret_values_or_hashes_emitted": False, "fresh_runtime_preflight_executed": False,
                "maintenance_execution_authorized": False, "production_recovery_qualified": False,
                "upgrade_rollback_qualified": False, "customer_accepted": False,
                "operator_review_required": REQUIRED_REVIEW,
                "limitations": ["Point-in-time observations can become stale immediately.",
                                "The lock coordinates participating DeclarAI controllers; direct host or Docker actions can bypass it.",
                                "Anonymous HTTPS and container profiles do not establish database schema, broker delivery, backup integrity or recovery.",
                                "No services, accounts, schema, artifacts or installation receipts are changed."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--client-ca", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(observe(args.plan, args.expected_plan_sha256, args.client_ca)))


if __name__ == "__main__":
    try:
        main()
    except (checker.planner.PlanError, OSError, ValueError, UnicodeError) as error:
        print(str(error) if isinstance(error, checker.planner.PlanError) else "lifecycle_observation_io_failed", file=sys.stderr)
        sys.exit(1)
