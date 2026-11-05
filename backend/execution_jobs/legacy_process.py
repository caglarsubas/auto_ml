"""Run only the fixed native child; a DB lease owns every observable outcome."""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from access_control import projects
from deployment.reviews import digest
from execution_jobs import legacy_execution as legacy
from execution_jobs.models import NativeJob


def event(identifier, token, kind, detail):
    from execution_jobs import service

    with service.locked(write=True):
        job = NativeJob.objects.select_for_update().get(pk=identifier)
        if not service._owns_live_lease(job, token, timezone.now()):
            return False
        service.recheck_execution(job)
        service.record(job, kind, detail=detail, update_fields=["revision"])
        return True


def checkpoint_files(actor, file_id, options, source):
    from execution_jobs import service

    try:
        job = NativeJob.objects.get(pk=uuid.UUID(str(options["checkpoint_job_id"])))
        checksum = options["checkpoint_sha256"]
    except (KeyError, ValueError, NativeJob.DoesNotExist):
        legacy.conflict("checkpoint_required")
    service.read_authority(actor, job)
    records = [
        e.detail for e in job.events.filter(event_type="legacy_checkpoint") if e.detail.get("sha256") == checksum
    ]
    if (
        job.state not in {"cancelled", "blocked", "failed"}
        or job.dataset_id != file_id
        or job.specification.get("kind") != legacy.KIND
        or not records
        or records[-1]["source"] != source
        or records[-1]["operation"] != "sfs"
    ):
        legacy.conflict("checkpoint_changed")
    record = records[-1]
    token = str(uuid.UUID(record["attempt_token"]))
    path = legacy.job_root(job.pk) / "attempts" / token / "work" / record["path"]
    raw = legacy.read(path, 8 * 1024**2)
    if hashlib.sha256(raw).hexdigest() != checksum:
        legacy.conflict("checkpoint_changed")
    return {record["path"]: raw}


def stop(child, control):
    (control / "stop").touch(exist_ok=True)
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=3)


def retain_checkpoint(job, token, control, work):
    if job.specification["legacy"]["operation"] != "sfs":
        return
    name = f"sfs_results/{job.dataset_id}_sfs_results.json"
    path = work / name
    if not path.exists():
        return
    try:
        from modeling.sfs_state import read_recorded_sfs
        from modeling.sfs_resume import restore_sfs_resume

        raw = legacy.read(path, 8 * 1024**2)
        value = read_recorded_sfs(path)
        source = job.specification["legacy"]["source"]
        if (
            not source
            or value.get("resume_basis", {}).get("execution_id") != source["execution_id"]
        ):
            return
        # An explicit zero-step/intermediate record is a valid checkpoint too;
        # its complete recorded basis is validated by the same replay reader.
        restore_sfs_resume(path, value["resume_basis"])
        path.chmod(0o400)
        event(
            job.pk,
            token,
            "legacy_checkpoint",
            {
                "operation": "sfs",
                "source": source,
                "attempt_token": str(token),
                "path": name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "model_adopted": False,
            },
        )
    except (ValueError, OSError, KeyError):
        return


def execute(job, token, check):
    from execution_jobs import service

    if sys.platform != "linux":
        legacy.conflict("linux_worker_required")
    plan = job.specification["legacy"]
    root = legacy.job_root(job.pk)
    frozen = {name: legacy.read(root / "inputs" / name) for name in plan["inputs"]}
    if legacy.inventory(frozen) != plan["inputs"]:
        legacy.conflict("snapshot_changed")
    attempt = root / "attempts" / str(token)
    attempt.mkdir(parents=True, exist_ok=False)
    work = attempt / "work"
    work.mkdir()
    control = attempt / "control"
    control.mkdir()
    mutable = {f"sfs_results/{job.dataset_id}_sfs_results.json"} if plan["options"].get("resume") else set()
    for name, raw in frozen.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o600 if name in mutable else 0o400)
    request = {
        "job_id": str(job.pk),
        "parent_pid": os.getpid(),
        "work_root": str(work),
        "operation": plan["operation"],
        "options": plan["options"],
    }
    (control / "request.json").write_text(json.dumps(request, allow_nan=False))
    # No credentials, external API configuration, Python paths or caller code
    # enter the fixed child. Its only database is Django's dummy backend.
    environment = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PROMETA_DISABLE": "1",
        "RAG_MODE": "lexical",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "MPLCONFIGDIR": str(control / "matplotlib"),
        "CHROMA_PERSIST_DIR": str(control / "chroma"),
    }
    code = (
        "import sys;sys.path.insert(0,"
        + repr(str(settings.BASE_DIR))
        + ");from execution_jobs.legacy_child import main;main()"
    )
    check()
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", code, str(control)],
        cwd=str(work),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    previous = None
    child_started = False
    next_progress = 0
    began = time.monotonic()
    try:
        while child.poll() is None:
            check()
            if not child_started and (control / "started.json").exists():
                started = json.loads(legacy.read(control / "started.json", 4096))
                if (
                    started.get("job_id") != str(job.pk)
                    or started.get("parent_pid") != os.getpid()
                    or started.get("database") != "dummy"
                    or started.get("entrypoint") != "registered_native"
                ):
                    legacy.conflict("child_binding_changed")
                event(
                    job.pk,
                    token,
                    "legacy_child_started",
                    {"operation": plan["operation"], "database": "dummy", "expert_code": False, "scratch_only": True},
                )
                child_started = True
                check()
                (control / "start-ack").touch(exist_ok=True)
            now = time.monotonic()
            if now >= next_progress and (control / "progress.json").exists():
                raw = legacy.read(control / "progress.json", 16384)
                checksum = hashlib.sha256(raw).hexdigest()
                if checksum != previous:
                    value = json.loads(raw)
                    event(job.pk, token, "legacy_progress", {"operation": plan["operation"], "progress": value})
                    previous = checksum
                next_progress = now + 1
            time.sleep(0.2)
        check()
    except BaseException:
        stop(child, control)
        retain_checkpoint(job, token, control, work)
        raise
    finally:
        if child.poll() is None:
            stop(child, control)
    if child.returncode or not (control / "result.json").exists():
        detail = {"operation": plan["operation"], "stage": "native_child", "exit_code": child.returncode}
        if (control / "failure.json").exists():
            detail["failure"] = json.loads(legacy.read(control / "failure.json", 32768))
        event(job.pk, token, "legacy_failure", detail)
        legacy.conflict("native_execution_failed")
    returned = json.loads(legacy.read(control / "result.json", legacy.BUDGET["max_result_bytes"]))
    if returned["outcome"] == "cancelled":
        retain_checkpoint(job, token, control, work)
        raise service.JobStopped
    if returned["outcome"] != "succeeded":
        failure = returned.get("payload", {}).get("failure")
        event(
            job.pk,
            token,
            "legacy_failure",
            {
                "operation": plan["operation"],
                "stage": "native_kernel",
                "failure": failure,
            },
        )
        legacy.conflict("native_execution_failed")
    files = {}
    total = 0
    for path in sorted(work.rglob("*")):
        if path.is_symlink():
            legacy.conflict("output_invalid")
        if not path.is_file():
            continue
        name = str(path.relative_to(work))
        raw = legacy.read(path, legacy.BUDGET["max_output_bytes"])
        if name in plan["inputs"] and name not in mutable:
            if {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)} != plan["inputs"][name]:
                legacy.conflict("scratch_input_changed")
            continue
        if name.startswith("projection_locks/"):
            continue
        total += len(raw)
        if total > legacy.BUDGET["max_output_bytes"] or len(files) >= legacy.BUDGET["max_files"]:
            legacy.conflict("output_budget")
        files[legacy.relative(name)] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        path.chmod(0o400)
    payload = returned["payload"]
    result = {
        "schema_version": 1,
        "scope": legacy.KIND,
        "operation": plan["operation"],
        "job_id": str(job.pk),
        "attempt_token": str(token),
        "plan_sha256": job.specification["legacy_sha256"],
        "inputs_sha256": digest(plan["inputs"]),
        "source": plan["source"],
        "payload": payload,
        "files": files,
        "files_sha256": digest(files),
        "elapsed_seconds": time.monotonic() - began,
        "legacy_projection_updated": False,
        "model_adopted": False,
        "review_approved": False,
        "production_use_approved": False,
    }
    if len(json.dumps(result, allow_nan=False).encode()) > legacy.BUDGET["max_result_bytes"]:
        legacy.conflict("result_budget")
    check()
    return result
