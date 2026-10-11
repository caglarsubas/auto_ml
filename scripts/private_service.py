#!/usr/bin/env python3
"""Fixed private API/worker/dispatcher launch. No migrations or fallback."""

import os
import stat
import subprocess
import sys
from pathlib import Path

from private_runtime_manifest import ManifestError, verify

ROOT = Path(__file__).resolve().parents[1]


def launch(args):
    if len(args) != 1 or args[0] not in ("api", "worker", "dispatcher"):
        raise ManifestError("private_service_role_required")
    if os.environ.get("DECLARAI_RUNTIME_PROFILE") != "private":
        raise ManifestError("private_service_profile_required")
    if os.geteuid() != 10001 or os.getegid() != 10001:
        raise ManifestError("private_service_identity_required")
    forbidden = ("GUNICORN_CMD_ARGS", "FORWARDED_ALLOW_IPS", "PYTHONPATH", "PYTHONHOME", "PROMETA_SKILLS_DIR")
    if any(name in os.environ for name in forbidden):
        raise ManifestError("private_service_override_rejected")
    if os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings") != "backend.settings":
        raise ManifestError("private_service_settings_rejected")
    if os.environ.get("DJANGO_TRUST_PROXY_TLS") != "true":
        raise ManifestError("private_service_ingress_required")
    verify(ROOT)
    os.chdir(ROOT / "backend")
    check = subprocess.run(
        [sys.executable, "manage.py", "check_job_runtime"],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if check.returncode:
        raise ManifestError("private_service_preflight_failed")
    if args[0] != "api":
        os.execv("/bin/sh", ["sh", str(ROOT / "docker/private-job-entrypoint.sh"), args[0]])
    directory = Path("/run/declarai")
    try:
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 10001 or info.st_mode & 0o022:
            raise ManifestError("private_service_socket_directory_required")
    except OSError:
        raise ManifestError("private_service_socket_directory_required") from None
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "gunicorn",
            "--config",
            str(ROOT / "docker/private-gunicorn.py"),
            "backend.wsgi:application",
        ],
    )


if __name__ == "__main__":
    try:
        launch(sys.argv[1:])
    except (ManifestError, OSError, subprocess.TimeoutExpired) as error:
        print(str(error) if isinstance(error, ManifestError) else "private_service_start_failed", file=sys.stderr)
        sys.exit(1)
