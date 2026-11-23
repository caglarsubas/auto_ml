"""Operator adapter for the disposable PTY test. Never opens an installed exercise."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


BACKEND = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestInstallation:
    replay_description = "Synthetic UX test. Refit and assessment run in a fresh local Python process."

    def __init__(self, root):
        self.root = root
        self.enrollment_command = [
            sys.executable,
            "-m",
            "tests.qualification.reviewer_journey_fixture",
            "enroll",
            str(root.parent),
        ]
        config = json.loads((root / "fixture.json").read_bytes())
        self.api_url = config["api"]
        self.cases = {case["task"]: case for case in config["cases"]}
        self.expected = {
            task: (case["development_sha256"], case["outcomes_sha256"], case["model_sha256"], case["scores_sha256"])
            for task, case in self.cases.items()
        }

    def payload(self, task, role):
        field = {"development": "development_file", "outcomes": "outcome_file"}[role]
        raw = Path(self.cases[task][field]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.cases[task][role + "_sha256"]:
            raise ValueError("Synthetic input changed.")
        return raw

    def verify_runtime(self, identifier):
        if identifier != digest(BACKEND / "deployment/offline_reproduce.py"):
            raise ValueError("The reproduction CLI differs from this test run.")

    def replay_binding(self, identifier):
        self.verify_runtime(identifier)
        return {"profile": "test_subprocess", "replay_source_sha256": identifier}

    def replay(self, identifier, approved, digests):
        self.verify_runtime(identifier)
        args = [sys.executable, "-m", "deployment.offline_reproduce", "--manifest-sha256", digests["manifest"]]
        for role, suffix in (("manifest", "json"), ("development", "csv"), ("outcomes", "csv")):
            path = approved / f"reproduction-{role}.{suffix}"
            if digest(path) != digests[role]:
                raise ValueError("A staged replay input changed.")
            args.extend(["--" + role, str(path)])
        with tempfile.TemporaryDirectory() as work:
            report = Path(work) / "report.json"
            env = {
                key: os.environ[key]
                for key in ("PATH", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
                if key in os.environ
            }
            env.update(PYTHONPATH=str(BACKEND), PYTHONDONTWRITEBYTECODE="1", PROMETA_DISABLE="1")
            proc = subprocess.run(args + ["--output", str(report)], cwd=work, env=env, capture_output=True, timeout=60)
            return proc.returncode, report.read_bytes() if report.is_file() else None
