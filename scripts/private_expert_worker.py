#!/usr/bin/env python3
"""One approved, offline expert candidate on a dedicated Linux worker."""

import argparse
import fcntl
import hashlib
import json
import math
import os
import platform
import re
import selectors
import signal
import shutil
import stat
import subprocess
import time
import uuid
from pathlib import Path

PROFILE = "declarai_expert_runsc_v1"
LIMITS = {
    "code_bytes": 64 * 1024, "input_bytes": 512 * 1024, "output_bytes": 256 * 1024,
    "rows": 1000, "columns": 32, "seconds": 15, "memory_bytes": 256 * 1024**2,
    "scratch_bytes": 8 * 1024**2, "pids": 32, "cpu_quota": 50000, "cpu_period": 100000,
}
APPROVAL_SECONDS = 900
LABEL = re.compile(r"[A-Za-z0-9_.-]{1,80}")
HOST_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}


class Refused(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def decode(raw):
    def unique(pairs):
        value = dict(pairs)
        if len(value) != len(pairs):
            raise Refused("expert_json_duplicate_key")
        return value

    return json.loads(raw, object_pairs_hook=unique)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise Refused("expert_invalid_identifier")
    return value


def directory(path, *, private=False):
    if not path.is_absolute() or path.resolve() != path:
        raise Refused("expert_directory_invalid")
    for item in [path, *path.parents]:
        meta = item.lstat()
        if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != 0:
            raise Refused("expert_directory_invalid")
        # A root-owned sticky scratch ancestor protects its root-owned child.
        if meta.st_mode & 0o022 and (item == path or not meta.st_mode & stat.S_ISVTX):
            raise Refused("expert_directory_invalid")
    if private and stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise Refused("expert_private_directory_required")
    return path


def checked_file(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_nlink != 1
                or before.st_mode & 0o022 or not 0 < before.st_size <= limit):
            raise Refused("expert_input_file_invalid")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(data) != before.st_size or before.st_mtime_ns != after.st_mtime_ns or before.st_ctime_ns != after.st_ctime_ns:
            raise Refused("expert_input_changed")
        return data


def exclusive(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def tree(root):
    """Bind executable, sidecars and rootfs contents including links and modes."""
    directory(root)
    entries = []
    total = 0
    for path in sorted(root.rglob("*")):
        meta = path.lstat()
        mode = stat.S_IMODE(meta.st_mode)
        if meta.st_uid != 0 or meta.st_gid != 0:
            raise Refused("expert_environment_ownership_invalid")
        if stat.S_ISLNK(meta.st_mode):
            value = {"link": os.readlink(path)}
        elif mode & 0o7022:
            raise Refused("expert_environment_mode_invalid")
        elif stat.S_ISDIR(meta.st_mode):
            value = {"directory": True}
        elif stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1:
            total += meta.st_size
            if total > 512 * 1024**2:
                raise Refused("expert_environment_too_large")
            with path.open("rb") as stream:
                value = {"sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
        else:
            raise Refused("expert_environment_entry_invalid")
        entries.append([path.relative_to(root).as_posix(), mode, value])
        if len(entries) > 30000:
            raise Refused("expert_environment_too_large")
    return digest(canonical(entries))


def environment(root):
    runsc = root / "runtime/runsc"
    if not runsc.is_file() or runsc.is_symlink() or not os.access(runsc, os.X_OK):
        raise Refused("expert_runtime_unavailable")
    workspace = directory(root / "rootfs/work")
    if not (root / "rootfs/usr/local/bin/python3").is_file() or any(workspace.iterdir()):
        raise Refused("expert_rootfs_invalid")
    return {"profile": PROFILE, "architecture": platform.machine(),
            "worker_sha256": digest(Path(__file__).read_bytes()),
            "runtime_sha256": tree(root / "runtime"), "rootfs_sha256": tree(root / "rootfs")}


def table(value, row_ids=None, *, score=False):
    if not isinstance(value, dict) or set(value) != {"columns", "row_ids", "rows"}:
        raise Refused("expert_table_invalid")
    columns, ids, rows = (value[key] for key in ("columns", "row_ids", "rows"))
    if (not isinstance(columns, list) or not 1 <= len(columns) <= LIMITS["columns"]
            or any(not isinstance(col, str) or not LABEL.fullmatch(col) for col in columns)
            or len(set(columns)) != len(columns) or score and columns != ["score"]):
        raise Refused("expert_table_columns_invalid")
    if (not isinstance(ids, list) or not 1 <= len(ids) <= LIMITS["rows"]
            or any(not isinstance(row, str) or not LABEL.fullmatch(row) for row in ids)
            or len(set(ids)) != len(ids) or row_ids is not None and ids != row_ids
            or not isinstance(rows, list) or len(rows) != len(ids)):
        raise Refused("expert_table_rows_invalid")
    if any(not isinstance(row, list) or len(row) != len(columns)
           or any(type(v) not in (int, float) or not math.isfinite(v) for v in row) for row in rows):
        raise Refused("expert_table_values_invalid")
    return value


def proposal(request, installed):
    directory(request, private=True)
    selection = decode(checked_file(request / "request.json", 4096))
    if not isinstance(selection, dict) or set(selection) != {
        "id", "project_id", "partition_id", "mode", "proposer",
    }:
        raise Refused("expert_request_invalid")
    for key in ("id", "project_id", "partition_id"):
        identity(selection[key])
    if selection["mode"] not in ("transform", "score") or not LABEL.fullmatch(selection["proposer"]):
        raise Refused("expert_request_invalid")
    code = checked_file(request / "code.py", LIMITS["code_bytes"])
    code.decode("utf-8")
    raw = checked_file(request / "input.json", LIMITS["input_bytes"])
    data = table(decode(raw))
    manifest = {**selection, "profile": PROFILE, "scope": "feature_partition_candidate_only",
                "environment": installed, "limits": LIMITS, "code_sha256": digest(code),
                "input_sha256": digest(raw), "rows": len(data["row_ids"]),
                "row_order_sha256": digest(canonical(data["row_ids"]))}
    return manifest, code, raw, data["row_ids"]


def oci(rootfs, stage):
    return {
        "ociVersion": "1.0.2",
        "root": {"path": str(rootfs), "readonly": True},
        "process": {
            "terminal": False, "cwd": "/work", "user": {"uid": 65534, "gid": 65534},
            "args": ["/usr/local/bin/python3", "-I", "-B", "/work/code.py"],
            "env": ["PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8", "HOME=/tmp"],
            "noNewPrivileges": True,
            "capabilities": {key: [] for key in ("bounding", "effective", "inheritable", "permitted", "ambient")},
            "rlimits": [{"type": name, "hard": limit, "soft": limit} for name, limit in (
                ("RLIMIT_CORE", 0), ("RLIMIT_NOFILE", 64), ("RLIMIT_FSIZE", LIMITS["scratch_bytes"]))],
        },
        "mounts": [
            {"destination": "/proc", "type": "proc", "source": "proc", "options": ["nosuid", "nodev", "noexec"]},
            {"destination": "/tmp", "type": "tmpfs", "source": "tmpfs",
             "options": ["nosuid", "nodev", "noexec", "mode=1777", f"size={LIMITS['scratch_bytes']}"]},
            {"destination": "/work", "type": "bind", "source": str(stage),
             "options": ["bind", "ro", "nosuid", "nodev", "noexec"]},
        ],
        "linux": {
            "namespaces": [{"type": name} for name in ("pid", "ipc", "uts", "mount", "network")],
            "resources": {"memory": {"limit": LIMITS["memory_bytes"]}, "pids": {"limit": LIMITS["pids"]},
                          "cpu": {"quota": LIMITS["cpu_quota"], "period": LIMITS["cpu_period"]}},
        },
    }


def read_output(proc, deadline):
    output = bytearray()
    with selectors.DefaultSelector() as poll:
        poll.register(proc.stdout, selectors.EVENT_READ)
        while True:
            left = deadline - time.monotonic()
            if left <= 0 or not poll.select(left):
                raise Refused("expert_wall_limit")
            block = os.read(proc.stdout.fileno(), min(65536, LIMITS["output_bytes"] + 1 - len(output)))
            if not block:
                break
            output.extend(block)
            if len(output) > LIMITS["output_bytes"]:
                raise Refused("expert_output_limit")
    if proc.wait(timeout=max(0, deadline - time.monotonic())):
        raise Refused("expert_runtime_failed")
    return output


def sandbox(env, bundle, identifier):
    command = [str(env / "runtime/runsc"), f"--root={bundle / 'runtime-state'}",
               "--network=none", "--gofer-network-namespace=new", "--platform=systrap",
               "--directfs=false", "--ignore-cgroups=false"]
    proc = None
    try:
        proc = subprocess.Popen([*command, "run", "--bundle", str(bundle), identifier],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env=HOST_ENV, start_new_session=True)
        return read_output(proc, time.monotonic() + LIMITS["seconds"])
    except subprocess.TimeoutExpired:
        raise Refused("expert_wall_limit") from None
    finally:
        if proc is not None:
            stopped = True
            try:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            except ProcessLookupError:
                stopped = proc.poll() is not None
            except (OSError, subprocess.TimeoutExpired):
                stopped = False
            finally:
                proc.stdout.close()
            try:
                subprocess.run([*command, "delete", "--force", identifier], env=HOST_ENV,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, check=True)
            except (subprocess.SubprocessError, OSError):
                stopped = False
            if not stopped:
                raise Refused("expert_cleanup_unverified")


def execute(state, env, manifest, code, raw, row_ids):
    job = directory(state / manifest["id"], private=True)
    approval = decode(checked_file(job / "approval.json", 32768))
    if approval["manifest"] != manifest or approval["sha256"] != digest(canonical(manifest)):
        raise Refused("expert_approval_stale")
    if (job / "receipt.json").exists():
        return decode(checked_file(job / "receipt.json", 32768))
    if time.time_ns() >= approval["expires_ns"]:
        raise Refused("expert_approval_expired")
    if (job / "claimed.json").exists():
        raise Refused("expert_job_reconciliation_required")
    active = state / "active.json"
    # This durable single-worker fence survives controller loss.
    exclusive(active, canonical({"job_id": manifest["id"]}))
    exclusive(job / "claimed.json", canonical({"approval_sha256": digest(canonical(approval))}))
    receipt = {"id": manifest["id"], "profile": PROFILE, "state": "blocked",
               "approval_sha256": digest(canonical(approval)), "reviewer": approval["reviewer"]}
    bundle = job / "bundle"
    result = None
    try:
        bundle.mkdir(mode=0o700)
        stage = bundle / "staged"
        stage.mkdir(mode=0o755)
        for name, content in (("code.py", code), ("input.json", raw)):
            path = stage / name
            exclusive(path, content)
            path.chmod(0o444)
        exclusive(bundle / "config.json", canonical(oci(env / "rootfs", stage)))
        output = sandbox(env, bundle, manifest["id"])
        candidate = table(decode(output), row_ids, score=manifest["mode"] == "score")
        result = canonical(candidate)
        if len(result) > LIMITS["output_bytes"]:
            raise Refused("expert_output_limit")
    except Refused as exc:
        receipt["reason_code"] = str(exc)
    except (ValueError, OSError, RecursionError, OverflowError):
        receipt["reason_code"] = "expert_candidate_or_storage_invalid"
    if receipt.get("reason_code") != "expert_cleanup_unverified" and bundle.exists():
        try:
            shutil.rmtree(bundle)
        except OSError:
            receipt["reason_code"] = "expert_cleanup_unverified"
    clean = receipt.get("reason_code") != "expert_cleanup_unverified"
    if "reason_code" not in receipt:
        exclusive(job / "candidate.json", result)
        receipt.update(state="succeeded", candidate_sha256=digest(result), scope="unadopted_candidate")
    exclusive(job / "receipt.json", canonical(receipt))
    if clean:
        active.unlink()
        sync_directory(state)
    return receipt


def serve(args):
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise Refused("expert_dedicated_linux_worker_required")
    controllers = Path("/sys/fs/cgroup/cgroup.controllers").read_text().split()
    if not {"cpu", "memory", "pids"}.issubset(controllers):
        raise Refused("expert_cgroup_controls_unavailable")
    state, env = directory(args.state, private=True), directory(args.environment)
    if state.is_relative_to(env) or env.is_relative_to(state):
        raise Refused("expert_environment_state_overlap")
    installed = environment(env)
    pin = state / "environment.json"
    if args.operation == "pin":
        exclusive(pin, canonical(installed))
        return installed
    if decode(checked_file(pin, 32768)) != installed:
        raise Refused("expert_environment_changed")
    manifest, code, raw, rows = proposal(args.request, installed)
    sha = digest(canonical(manifest))
    if args.operation == "preview":
        return {"manifest": manifest, "sha256": sha}
    if args.operation == "approve":
        if not LABEL.fullmatch(args.reviewer) or args.reviewer == manifest["proposer"] or args.expected != sha:
            raise Refused("expert_independent_exact_review_required")
        job = state / manifest["id"]
        job.mkdir(mode=0o700)
        now = time.time_ns()
        approval = {"manifest": manifest, "sha256": sha, "reviewer": args.reviewer,
                    "approved_ns": now, "expires_ns": now + APPROVAL_SECONDS * 10**9}
        exclusive(job / "approval.json", canonical(approval))
        sync_directory(state)
        return approval
    lock_fd = os.open(state / "worker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return execute(state, env, manifest, code, raw, rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    modes = parser.add_subparsers(dest="operation", required=True)
    modes.add_parser("pin")
    for op in ("preview", "approve", "execute"):
        mode = modes.add_parser(op)
        mode.add_argument("request", type=Path)
        if op == "approve":
            mode.add_argument("--expected", required=True)
            mode.add_argument("--reviewer", required=True)
    try:
        result = serve(parser.parse_args())
        print(canonical(result).decode())
        return 1 if result.get("state") == "blocked" else 0
    except Refused as exc:
        code = str(exc)
    except FileExistsError:
        code = "expert_request_or_worker_state_exists"
    except BlockingIOError:
        code = "expert_worker_busy"
    except (ValueError, KeyError, TypeError, OSError, OverflowError, RecursionError):
        code = "expert_request_or_environment_unavailable"
    print(canonical({"state": "blocked", "reason_code": code}).decode())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
