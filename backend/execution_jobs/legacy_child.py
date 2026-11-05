"""Fixed native legacy kernels in a disposable process with no database.

No user modules, source text, dependency installation or arbitrary entrypoint
is supported. This process boundary is not the D08 expert-code sandbox.
"""

import ctypes
import json
import os
import resource
import signal
import sys
from pathlib import Path


def main():
    control = Path(sys.argv[1])
    request = json.loads((control / "request.json").read_bytes())
    parent = request["parent_pid"]
    if sys.platform != "linux" or type(parent) is not int or os.getppid() != parent:
        raise RuntimeError("legacy_child_parent_required")
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
        raise RuntimeError("legacy_child_parent_binding")
    # Restrict only this disposable process and its descendants. Keep model
    # threads at one and at most two explicitly requested candidate workers.
    cpus = sorted(os.sched_getaffinity(0))
    count = request["options"].get("n_jobs", 1)
    os.sched_setaffinity(0, cpus[:count])
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    from execution_jobs.legacy_context import activate

    activate(control)
    os.environ["DJANGO_SETTINGS_MODULE"] = "backend.settings"
    from django.conf import settings

    settings.MEDIA_ROOT = Path(request["work_root"])
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}
    settings.DECLARAI_JOBS_ENABLED = False
    import django

    django.setup()
    # Announce kernel readiness only after expensive handler imports. A
    # cancellation following this event can then reach the kernel's existing
    # stop/checkpoint protocol within its unchanged termination grace.
    from modeling import views

    operation, options = request["operation"], request["options"]
    if operation != "sfs":
        from execution_jobs.legacy_context import active

        active().ready()
    # SFS announces readiness at its first recorded, validated search basis.
    # Import completion alone does not make an empty search resumable.
    handlers = {
        "training": views.execute_legacy_training,
        "sfs": views.execute_legacy_sfs,
        "hpo": views.execute_legacy_hpo,
        "champion": views.execute_legacy_champion,
    }
    try:
        response = handlers[operation](options)
        if response.status_code >= 400:
            if (control / "failure.json").is_file():
                raise SystemExit(1)
            raise ValueError("legacy_request_or_pipeline_invalid")
        if operation in {"training", "champion"}:
            payload = response.data
            outcome = "succeeded" if payload.get("job_status") == "completed" or operation == "champion" and payload.get("status") == "ok" else "failed"
        else:
            prefix, suffix = (
                ("sfs_results", "sfs_results") if operation == "sfs" else ("hyperparam_results", "hyperparam")
            )
            payload = json.loads((settings.MEDIA_ROOT / prefix / f"{options['file_id']}_{suffix}.json").read_bytes())
            outcome = (
                "succeeded"
                if payload.get("status") == "completed"
                else "cancelled"
                if payload.get("status") == "stopped"
                else "failed"
            )
        raw = json.dumps({"outcome": outcome, "payload": payload}, allow_nan=False, default=str).encode()
        if len(raw) > 8 * 1024**2:
            raise ValueError("legacy_result_budget")
        (control / "result.json").write_bytes(raw)
    except Exception as error:
        from modeling.async_failures import record_failure

        failure = record_failure(
            error,
            "legacy_native_execution",
            {"operation": operation, "file_id": options["file_id"], "operation_id": request["job_id"]},
        )
        (control / "failure.json").write_text(json.dumps(failure, allow_nan=False))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
