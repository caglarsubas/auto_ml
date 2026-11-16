#!/usr/bin/env python3
"""Reproduce the synthetic native assessment exports in a confined clean runtime.

Run after the native-assessment Playwright fixture. Pass the full image ID of
its already-built backend via --runtime-image. Only upload --reports, never
the Playwright --inputs directory or the temporary approved inputs.
"""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path


CONTEXT_NAME = "native-reproduction-context.json"
SCOPE = "native_refit_assessment_reproduction_v1"
TASKS = {"classification", "regression"}
INPUTS = {
    "manifest": "reproduction-manifest.json",
    "development": "reproduction-development.csv",
    "outcomes": "reproduction-outcomes.csv",
}
INPUT_LIMITS = {"manifest": 32 * 1024**2, "development": 5 * 1024**2, "outcomes": 5 * 1024**2}


def stage_inputs(context_path, context, target):
    for role, name in INPUTS.items():
        source = context_path.parent / name
        with source.open("rb") as stream:
            raw = stream.read(INPUT_LIMITS[role] + 1)
        if len(raw) > INPUT_LIMITS[role] or hashlib.sha256(raw).hexdigest() != context.get(f"{role}_sha256"):
            raise ValueError(f"Synthetic reproduction {role} bytes differ from their retained digest or budget.")
        (target / name).write_bytes(raw)
        (target / name).chmod(0o644)


def remove_fixture(container):
    exists = subprocess.run(["docker", "inspect", "--type", "container", container], capture_output=True, timeout=15)
    if exists.returncode == 0:
        subprocess.run(["docker", "stop", "--time", "10", container], capture_output=True, timeout=30, check=True)
        subprocess.run(["docker", "rm", container], capture_output=True, timeout=15, check=False)


def qualify(image, context_path, context):
    with tempfile.TemporaryDirectory(prefix="declarai-reproduction-qualification-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        approved = root / "approved"
        approved.mkdir(mode=0o755)
        output = root / "reports"
        output.mkdir()
        output.chmod(0o777)
        stage_inputs(context_path, context, approved)
        container = "declarai-reproduction-qual-" + uuid.uuid4().hex
        command = [
            "docker", "run", "--rm", "--pull", "never", "--name", container, "--network", "none",
            "--read-only", "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "1g", "--pids-limit", "128", "--cpus", "2",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
            "--tmpfs", "/app/backend/media:ro,nosuid,nodev,size=4m",
            "-e", "PYTHONPATH=/app/backend", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PROMETA_DISABLE=1",
            "-e", "OMP_NUM_THREADS=2", "-e", "OPENBLAS_NUM_THREADS=2", "-e", "MKL_NUM_THREADS=2",
            "-v", f"{approved}:/approved:ro", "-v", f"{output}:/evidence:rw", "-w", "/tmp",
            "--entrypoint", "python", image, "-m", "deployment.offline_reproduce",
            "--manifest", f"/approved/{INPUTS['manifest']}", "--manifest-sha256", context["manifest_sha256"],
            "--development", f"/approved/{INPUTS['development']}", "--outcomes", f"/approved/{INPUTS['outcomes']}",
            "--output", "/evidence/reproduction.json",
        ]
        try:
            process = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        except subprocess.TimeoutExpired:
            return None, {"status": "blocked", "error": "clean_run_timed_out"}
        finally:
            # A timed-out Docker client can leave its daemon-owned process alive.
            remove_fixture(container)
        report_path = output / "reproduction.json"
        try:
            with report_path.open("rb") as stream:
                raw = stream.read(262_145)
            if len(raw) > 262_144:
                raise ValueError
            report = json.loads(raw)
            if not isinstance(report, dict):
                raise ValueError
        except (OSError, ValueError):
            report = {"status": "blocked", "error": "clean_run_report_missing_or_invalid"}
        return process.returncode, report


def agreed(report, context):
    return (
        report.get("schema_version") == 1 and report.get("scope") == SCOPE
        and report.get("status") == "passed"
        and all(key in context and key in report and report[key] == context[key] for key in (
            "task", "manifest_sha256", "development_sha256", "outcomes_sha256",
            "assessment_result_sha256", "scores_sha256", "n_assessed",
        ))
        and report.get("comparison") == "exact_canonical_result_and_scores_sha256"
        and report.get("model_refit_reproduced") is True and report.get("assessment_reproduced") is True
        and report.get("confirmation_granted") is False and report.get("review_approved") is False
        and report.get("production_use_approved") is False
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-image", required=True, help="Full sha256 image ID of the built Playwright backend")
    parser.add_argument("--inputs", type=Path, required=True, help="Playwright test-results directory")
    parser.add_argument("--reports", type=Path, required=True, help="Metadata-only qualification output directory")
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", args.runtime_image):
        parser.error("--runtime-image must be the full local Docker image ID.")
    contexts = {
        path: json.loads(path.read_text()) for path in sorted(args.inputs.rglob(CONTEXT_NAME))
    }
    if (len(contexts) != len(TASKS)
            or any(context.get("synthetic_fixture") is not True for context in contexts.values())
            or {context.get("task") for context in contexts.values()} != TASKS):
        parser.error("One explicit synthetic classification and one regression fixture are required.")
    args.reports.mkdir(parents=True, exist_ok=True)
    checks = []
    for path, context in contexts.items():
        task = context["task"]
        exit_code, report = qualify(args.runtime_image, path, context)
        qualified = exit_code == 0 and agreed(report, context)
        (args.reports / f"{task}.json").write_text(json.dumps(report, indent=2) + "\n")
        checks.append({"task": task, "exit_code": exit_code, "qualified": qualified})
    summary = {
        "schema_version": 1, "scope": SCOPE, "synthetic_fixture": True, "runtime_image": args.runtime_image,
        "network": "none", "read_only_runtime": True, "unprivileged": True,
        "installation_media": "empty read-only tmpfs", "checks": checks,
    }
    (args.reports / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    return 0 if all(check["qualified"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
