#!/usr/bin/env python3
"""Qualify offline planning and real Compose normalization, without adoption."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import private_installation_plan as planner

ROOT = Path(__file__).resolve().parents[1]


def qualify(directory, expected, reports):
    reports = reports.resolve()
    if not reports.is_relative_to(ROOT / "test-reports"):
        raise planner.PlanError("installation_reports_path_invalid")
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
            if normalized["volumes"] != service["volumes"]:
                raise planner.PlanError("installation_compose_normalization_mismatch")
            if role != "ingress" and normalized["environment"] != service["environment"]:
                raise planner.PlanError("installation_compose_normalization_mismatch")
            if role == "ingress" and any(normalized["ports"][0][key] != value for key, value in service["ports"][0].items()):
                raise planner.PlanError("installation_compose_normalization_mismatch")
        reports.mkdir(parents=True, exist_ok=True)
        result.update(schema="private_installation_plan_qualification_v1", actual_compose_configuration="passed", services=list(wanted["services"]), service_adoption=False, secret_reads=False)
        (reports / "installation-plan.json").write_bytes(planner.encoded(result))
        # Retain nonsecret rendered evidence, not the multi-GiB image archives.
        for name in planner.FILES | {"manifest.json"}:
            (reports / ("installation-plan-" + name)).write_bytes((plan / name).read_bytes())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_set", type=Path)
    parser.add_argument("--expected-image-set-sha256", required=True)
    parser.add_argument("--reports", type=Path, default=ROOT / "test-reports/postgresql")
    args = parser.parse_args()
    print(json.dumps(qualify(args.image_set, args.expected_image_set_sha256, args.reports)))


if __name__ == "__main__":
    main()
