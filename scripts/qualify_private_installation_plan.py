#!/usr/bin/env python3
"""Qualify offline planning and optionally complete installation and recovery."""

import argparse
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

import private_installation_plan as planner

ROOT = Path(__file__).resolve().parents[1]


def qualification_profile_matches(profile, image_architecture):
    """A native profile must match the frozen bundle; never relabel evidence."""
    architectures = {"x86_64": "amd64", "aarch64": "arm64"}
    return (image_architecture in architectures.values()
            and architectures.get(profile["architecture"]) == image_architecture
            and profile["os_release"].get("ID") == "ubuntu"
            and profile["os_release"].get("VERSION_ID") == "24.04")


def normalized_mounts(values):
    # Compose 2 serializes its false CreateHostPath bool as an omitted field.
    # Accept only that representation; true and other mount changes still fail.
    result = []
    for value in values:
        value = dict(value)
        if value.get("type") == "bind":
            value["bind"] = {"create_host_path": False, **value.get("bind", {})}
        result.append(value)
    return result


def missing_bind_check(image, temp):
    name = "declarai-plan-bind-" + uuid.uuid4().hex
    source = temp / (name + "-missing")
    file = temp / "missing-bind.json"
    file.write_bytes(planner.encoded({"name": name, "services": {"fixture": {
        "container_name": name, "image": image, "pull_policy": "never", "network_mode": "none",
        "user": "10001:10001", "read_only": True, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "cpus": 1, "mem_limit": "256m", "pids_limit": 32,
        "volumes": [{"type": "bind", "source": str(source), "target": "/installation", "read_only": True, "bind": {"create_host_path": False}}],
    }}}))
    try:
        command = subprocess.run(["docker", "compose", "--project-directory", str(temp), "-f", str(file), "create", "--no-build", "--pull", "never", "fixture"], capture_output=True, timeout=30, check=False)
        output = (command.stdout + command.stderr).decode(errors="replace").lower()
        if command.returncode == 0 or source.exists() or "bind source path does not exist" not in output or source.name not in output:
            raise planner.PlanError("installation_missing_bind_not_blocked")
    finally:
        # The owned UUID container is never started. No other object is removed.
        subprocess.run(["docker", "container", "rm", "--force", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)


def qualify(directory, expected, reports, path_check_image=None, adoption_check=False):
    reports = reports.resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        raise planner.PlanError("installation_reports_path_invalid")
    if adoption_check and path_check_image is None:
        raise planner.PlanError("installation_adoption_fixture_image_required")
    request = {
        "schema": planner.SCHEMA, "installation_id": "qualification", "root": "/srv/declarai/qualification",
        "authority": "api.private.test:8443", "body_mib": 1, "bind_ip": "127.0.0.1",
        "database": {"name": "declarai_qualification", "user": "declarai_app"},
    }
    with tempfile.TemporaryDirectory(prefix="declarai-plan-qualification-") as temp:
        temp = Path(temp)
        request_path = temp / "request.json"
        request_path.write_bytes(planner.encoded(request))
        plan = temp / "plan"
        result = planner.render(request_path, directory, expected, plan)
        if path_check_image is not None and path_check_image != result["images"]["api"]:
            raise planner.PlanError("installation_path_fixture_scope_required")
        command = subprocess.run(
            ["docker", "compose", "--project-directory", str(plan), "-f", str(plan / "compose.json"), "config", "--format", "json"],
            capture_output=True, timeout=30, check=False,
        )
        if command.returncode:
            raise planner.PlanError("installation_compose_normalization_failed")
        actual = planner.decode(command.stdout)
        wanted = planner.composition(request, result["images"])
        if set(actual["services"]) != set(wanted["services"]) or actual["name"] != wanted["name"]:
            raise planner.PlanError("installation_compose_normalization_mismatch")
        for role, service in wanted["services"].items():
            normalized = actual["services"][role]
            for field in ("image", "pull_policy", "user", "read_only", "cap_drop", "security_opt", "pids_limit", "restart", "tmpfs"):
                if normalized[field] != service[field]:
                    raise planner.PlanError("installation_compose_normalization_mismatch")
            if normalized_mounts(normalized["volumes"]) != normalized_mounts(service["volumes"]):
                raise planner.PlanError("installation_compose_normalization_mismatch")
            if role != "ingress" and normalized["environment"] != service["environment"]:
                raise planner.PlanError("installation_compose_normalization_mismatch")
            if role == "ingress" and any(normalized["ports"][0][key] != value for key, value in service["ports"][0].items()):
                raise planner.PlanError("installation_compose_normalization_mismatch")
        missing_bind_check(result["images"]["api"], temp)
        if path_check_image is not None:
            from qualify_private_installation_check import qualify as qualify_paths

            qualify_paths(plan, result["plan_manifest_sha256"], path_check_image, reports)
            from qualify_private_installation_init import qualify as qualify_init

            qualify_init(plan, result["plan_manifest_sha256"], path_check_image, reports)
            from qualify_private_dependency_init import qualify as qualify_dependencies

            qualify_dependencies(plan, result["plan_manifest_sha256"], path_check_image, reports)
            from qualify_private_installation_resources import qualify as qualify_resources

            qualify_resources(plan, result["plan_manifest_sha256"], path_check_image, reports)
            if adoption_check:
                from qualify_private_installation_adopt import qualify as qualify_adoption

                qualify_adoption(plan, result["plan_manifest_sha256"], path_check_image, reports)
                from qualify_private_dependency_start import qualify as qualify_dependency_start

                first = qualify_dependency_start(plan, result["plan_manifest_sha256"], path_check_image, reports, profile_workloads=True)
                repeated = qualify_dependency_start(plan, result["plan_manifest_sha256"], path_check_image, reports / "clean-repeat", profile_workloads=True)
                legacy = qualify_dependency_start(plan, result["plan_manifest_sha256"], path_check_image, reports / "legacy-execution", profile_legacy=True)
                legacy_profile = legacy["qualification"]["fresh_application_adoption"]["legacy_execution"]
                if (legacy_profile.get("case_count") != 21 or not legacy["owned_root_and_resources_removed"]
                    or legacy_profile.get("application_images") != result["images"]):
                    raise planner.PlanError("installation_legacy_execution_incomplete")
                runs = [first, repeated]
                profiles = [run["qualification"]["installation_profile"] for run in runs]
                if (profiles[0]["installation_id"] == profiles[1]["installation_id"]
                    or any(profile["application_images"] != result["images"] for profile in profiles)
                    or any(not qualification_profile_matches(profile, result["architecture"]) for profile in profiles)
                    or any(run["source_plan_sha256"] != result["plan_manifest_sha256"] for run in runs)
                    or any(not run["owned_root_and_resources_removed"] for run in runs)):
                    raise planner.PlanError("installation_clean_reproduction_mismatch")
                acceptance = {
                    "schema": "private_clean_installation_acceptance_v1",
                    "image_set_manifest_sha256": expected,
                    "plan_manifest_sha256": result["plan_manifest_sha256"],
                    "images": result["images"],
                    "clean_roots": 2,
                    "same_exact_image_inputs": True,
                    "installation_profiles": profiles,
                    "workflows": [run["qualification"]["fresh_application_adoption"]["installed_developer_workflow"] for run in runs],
                    "backups": [run["qualification"]["baseline_backup"] for run in runs],
                    "all_original_dependency_start_assertions": "passed_twice",
                    "owned_roots_and_resources_removed": True,
                    "synthetic_clean_installation_qualified": True,
                    "upgrade_or_machine_loss_restore_qualified": False,
                    "operator_key_custody_qualified": False,
                    "customer_accepted": False,
                    "release_qualified": False,
                }
                reports.mkdir(parents=True, exist_ok=True)
                envelopes = [run["qualification"]["fresh_application_adoption"]["workload_envelope"] for run in runs]
                from qualify_private_workload_envelope import comparison
                observed = comparison(envelopes, profiles, result["images"])
                (reports / "workload-envelope.json").write_bytes(planner.encoded(observed))
                (reports / "clean-installation-acceptance.json").write_bytes(planner.encoded(acceptance))
        reports.mkdir(parents=True, exist_ok=True)
        result.update(schema="private_installation_plan_qualification_v1", actual_compose_configuration="passed", missing_bind_auto_creation="blocked", services=list(wanted["services"]), service_adoption=False, secret_reads=False)
        (reports / "installation-plan.json").write_bytes(planner.encoded(result))
        # Retain nonsecret rendered evidence, not the multi-GiB image archives.
        for name in planner.FILES | {"manifest.json"}:
            (reports / ("installation-plan-" + name)).write_bytes((plan / name).read_bytes())
    if adoption_check:
        from qualify_private_installation_recovery import qualify as qualify_recovery

        qualify_recovery(reports)
        from qualify_private_installation_upgrade import qualify as qualify_upgrade

        qualify_upgrade(directory, expected, reports)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_set", type=Path)
    parser.add_argument("--expected-image-set-sha256", required=True)
    parser.add_argument("--path-check-image", help="Exact API image from the verified set; adds owned Linux filesystem qualification")
    parser.add_argument("--adoption-check", action="store_true", help="Additionally qualify owned Linux installation and coordinated recovery fixtures")
    parser.add_argument("--reports", type=Path, default=ROOT / "test-reports/postgresql")
    args = parser.parse_args()
    print(json.dumps(qualify(args.image_set, args.expected_image_set_sha256, args.reports, args.path_check_image, args.adoption_check)))


if __name__ == "__main__":
    main()
