#!/usr/bin/env python3
"""Qualify hostile synthetic requests and cancellation on the pinned Linux worker."""

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import private_expert_worker as worker
import qualify_private_expert_lifecycle as lifecycle
import qualify_private_expert_worker as foundation

SENTINEL_PROBE = b"""
import os
import socket
assert os.getuid() == 65534 and os.getgid() == 65534
assert not os.path.exists('/work/state.bin')
assert not os.path.exists('/work/fitted.json')
assert not os.path.exists('/work/approval.json')
assert not os.path.exists(OTHER_PARTITION)
assert not os.path.exists('/proc/1/root' + OTHER_PARTITION)
assert not os.path.exists(UNIX_SOCKET)
assert 'DECLARAI_EXPERT_HOST_CANARY' not in os.environ
try:
    os.setuid(0)
except OSError:
    pass
else:
    raise AssertionError('sandbox could become root')
try:
    open('/etc/passwd', 'a')
except OSError:
    pass
else:
    raise AssertionError('root filesystem is writable')
try:
    socket.create_connection(('127.0.0.1', LOOPBACK_PORT), timeout=1)
except OSError:
    pass
else:
    raise AssertionError('host loopback connected')
with socket.socket(socket.AF_UNIX) as peer:
    try:
        peer.connect(UNIX_SOCKET)
    except OSError:
        pass
    else:
        raise AssertionError('host Unix socket connected')
"""

SCRATCH_PROBE = b"""
import errno
block = b'x' * 1048576
count = 0
try:
    for index in range(9):
        with open(f'/tmp/pressure-{index}', 'wb', buffering=0) as output:
            count += output.write(block)
except OSError as exc:
    assert exc.errno == errno.ENOSPC
assert count == 8 * 1048576
"""

MEMORY_PROBE = b"""
import time
allocation = []
for _ in range(40):
    allocation.append(b'x' * (8 * 1024 * 1024))
    time.sleep(0.03)
"""

SPIN_WITH_CHILD = b"""
import os
import time
if os.fork() == 0:
    time.sleep(30)
    os._exit(0)
while True:
    pass
"""


def job_paths(home, request):
    job = home / "state" / request.name
    return job, Path("/sys/fs/cgroup") / request.name


def assert_stopped(home, request):
    job, cgroup = job_paths(home, request)
    assert not cgroup.exists(), "sandbox cgroup retained"
    assert not (job / "bundle").exists(), "sandbox bundle retained"
    assert not (home / "state/active.json").exists(), "worker fence retained"


def assert_blocked(home, request, approval, receipt, *, clean=True):
    job, _ = job_paths(home, request)
    assert receipt == json.loads((job / "receipt.json").read_bytes())
    assert receipt["id"] == request.name and receipt["state"] == "blocked"
    assert receipt["approval_sha256"] == worker.digest(worker.canonical(approval))
    assert receipt["reviewer"] == approval["reviewer"]
    assert not (job / "candidate.json").exists()
    assert not (job / "fitted.json").exists()
    if clean:
        assert_stopped(home, request)


def wait_for_running_children(home, request, process):
    job, cgroup = job_paths(home, request)
    command = [*worker.runtime_command(home / "environment", job / "bundle"),
               "ps", "--format", "json", request.name]
    until = time.monotonic() + 10
    while process.poll() is None and time.monotonic() < until:
        try:
            stats = dict(line.split() for line in (cgroup / "cpu.stat").read_text().splitlines())
            if int(stats["nr_throttled"]) > 0:
                tasks = subprocess.run(command, capture_output=True, timeout=2, env=worker.HOST_ENV)
                if tasks.returncode == 0 and len(json.loads(tasks.stdout)) >= 2:
                    return
        except FileNotFoundError:
            pass
        time.sleep(0.05)
    raise AssertionError("expected two live sandbox processes under host CPU throttling")


def run_cancel(home, request, *, operator="fixture-operator", failure=None):
    return foundation.run(home, "cancel", Path(request.name), "--operator", operator, failure=failure)


def isolation_probes(home):
    other = foundation.create(home, "transform", foundation.TRANSFORM)
    partition = other / "input.json"
    partition_before = partition.read_bytes()
    host_socket = home / "host-listener.sock"
    with socket.socket() as listener, socket.socket(socket.AF_UNIX) as unix:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        unix.bind(str(host_socket))
        unix.listen()
        probe = SENTINEL_PROBE.replace(b"OTHER_PARTITION", repr(str(partition)).encode())
        probe = probe.replace(b"LOOPBACK_PORT", str(listener.getsockname()[1]).encode())
        probe = probe.replace(b"UNIX_SOCKET", repr(str(host_socket)).encode())
        request = foundation.create(home, "transform", probe + foundation.TRANSFORM)
        foundation.approve(home, request)
        with patch.dict("os.environ", {"DECLARAI_EXPERT_HOST_CANARY": "synthetic host only"}):
            result = foundation.run(home, "execute", request)
        assert result["state"] == "succeeded"
    assert partition.read_bytes() == partition_before
    assert_stopped(home, request)
    return ["other_partition_and_control_files_denied", "host_loopback_unix_socket_and_environment_denied",
            "rootfs_and_privilege_escalation_denied"]


def resource_and_output_probes(home):
    request = foundation.create(home, "transform", SCRATCH_PROBE + foundation.TRANSFORM)
    foundation.approve(home, request)
    assert foundation.run(home, "execute", request)["state"] == "succeeded"
    assert_stopped(home, request)

    request = foundation.create(home, "transform", MEMORY_PROBE + foundation.TRANSFORM)
    approval = foundation.approve(home, request)
    _, cgroup = job_paths(home, request)
    peak = 0
    with subprocess.Popen(foundation.command(home, "execute", request), stdout=subprocess.PIPE) as process:
        until = time.monotonic() + 15
        while process.poll() is None and time.monotonic() < until:
            try:
                peak = max(peak, int((cgroup / "memory.current").read_text()))
                assert (cgroup / "memory.swap.max").read_text().strip() == "0"
            except FileNotFoundError:
                pass
            time.sleep(0.01)
        stdout, _ = process.communicate(timeout=15)
        assert process.returncode == 1
    assert peak >= worker.LIMITS["memory_bytes"] * 3 // 4, peak
    receipt = json.loads(stdout)
    assert receipt["reason_code"] == "expert_runtime_failed", receipt
    assert_blocked(home, request, approval, receipt)

    for payload, reason in (
        (b'{"columns":["x"],"columns":["x"],"row_ids":["first","second"],"rows":[[2],[-4]]}',
         "expert_json_duplicate_key"),
        (b'{"columns":["x"],"row_ids":["second","first"],"rows":[[-4],[2]]}',
         "expert_table_rows_invalid"),
    ):
        request = foundation.create(home, "transform", b"print(" + repr(payload.decode()).encode() + b")")
        approval = foundation.approve(home, request)
        receipt = foundation.run(home, "execute", request, failure=reason)
        assert_blocked(home, request, approval, receipt)
    return ["scratch_limit_enforced", "host_memory_pressure_stops_candidate", "duplicate_json_and_row_substitution_refused"]


def poison_artifact(home):
    marker = home / "host-pickle-side-effect"
    script = (
        "open('/tmp/pickle-probe', 'w').close()\n"
        f"try:\n    open({str(marker)!r}, 'w').close()\nexcept OSError:\n    pass\n"
    )
    code = lifecycle.RECIPE.replace(
        b"data = json.load",
        b"class Payload:\n    def __reduce__(self):\n        return (exec, (" + repr(script).encode()
        + b",))\ndata = json.load",
    ).replace(
        b"state = pickle.loads(open('/work/state.bin', 'rb').read())",
        b"assert pickle.loads(open('/work/state.bin', 'rb').read()) is None\n"
        b"    assert os.path.isfile('/tmp/pickle-probe')\n    state = {'mean': 3}",
    ).replace(b"pickle.dumps(state, protocol=4)", b"pickle.dumps(Payload(), protocol=4)")
    seed = foundation.create(home, "fit", code)
    (seed / "input.json").write_bytes(worker.canonical({
        "columns": ["x"], "row_ids": ["first", "second"], "rows": [[2], [4]],
    }))
    approval = foundation.approve(home, seed)
    assert foundation.run(home, "execute", seed)["state"] == "succeeded"
    assert not marker.exists()
    artifact = home / "pickle-probe.fitted.json"
    foundation.run(home, "export", seed, "--output", str(artifact))
    fit = approval["manifest"]
    score = lifecycle.request(home, "score", fit["project_id"], fit["partition_id"],
                              [100, 200], artifact.read_bytes())
    (score / "code.py").write_bytes(code)
    lifecycle.approve(home, score)
    receipt = foundation.run(home, "execute", score)
    job, _ = job_paths(home, score)
    assert receipt["applied_artifact_sha256"] == worker.digest(artifact.read_bytes())
    assert json.loads((job / "candidate.json").read_bytes())["rows"] == [[97], [197]]
    assert not marker.exists()
    assert_stopped(home, score)
    return ["pickle_side_effect_confined_to_sandbox"]


def cancel_active_job(home):
    close_output = b"\nimport sys\nsys.stdout.flush()\nos.close(1)\n"
    request = foundation.create(home, "fit", lifecycle.RECIPE + close_output + SPIN_WITH_CHILD)
    unrelated = foundation.create(home, "transform", foundation.TRANSFORM)
    approval = foundation.approve(home, request)
    foundation.approve(home, unrelated)
    run_cancel(home, request, failure="expert_job_not_active")
    job, _ = job_paths(home, request)
    with subprocess.Popen(foundation.command(home, "execute", request), stdout=subprocess.PIPE) as process:
        wait_for_running_children(home, request, process)
        run_cancel(home, unrelated, failure="expert_job_not_active")
        requested = run_cancel(home, request)
        stdout, _ = process.communicate(timeout=20)
        assert process.returncode == 1
    receipt = json.loads(stdout)
    assert receipt["reason_code"] == "expert_cancelled"
    assert receipt["cancellation"] == requested == json.loads((job / "cancellation.json").read_bytes())
    assert requested["operator"] == "fixture-operator"
    assert requested["approval_sha256"] == receipt["approval_sha256"]
    assert_blocked(home, request, approval, receipt)
    assert foundation.run(home, "execute", request, failure="expert_cancelled") == receipt
    run_cancel(home, request, failure="expert_job_already_finished")
    assert foundation.run(home, "execute", unrelated)["state"] == "succeeded"
    run_cancel(home, unrelated, failure="expert_job_already_finished")
    return ["cpu_quota_throttles_host_work", "exact_active_cancellation_and_descendant_cleanup",
            "terminal_receipt_replay_and_late_cancel_refused", "next_approved_job_succeeds_after_cancel"]


def controller_loss(home):
    request = foundation.create(home, "transform", SPIN_WITH_CHILD)
    later = foundation.create(home, "transform", foundation.TRANSFORM)
    foundation.approve(home, request)
    foundation.approve(home, later)
    state = home / "state"
    job, cgroup = job_paths(home, request)
    bundle = job / "bundle"
    with subprocess.Popen(foundation.command(home, "execute", request), stdout=subprocess.PIPE) as process:
        wait_for_running_children(home, request, process)
        process.kill()
        process.communicate(timeout=5)
    try:
        assert json.loads((state / "active.json").read_bytes()) == {"job_id": request.name}
        assert (job / "claimed.json").exists()
        assert not (job / "candidate.json").exists()
        foundation.run(home, "execute", request, failure="expert_job_reconciliation_required")
        foundation.run(home, "execute", later, failure="expert_worker_reconciliation_required")
        assert not (state / later.name / "claimed.json").exists()
    finally:
        subprocess.run([*worker.runtime_command(home / "environment", bundle), "delete", "--force", request.name],
                       check=True, timeout=5, capture_output=True, env=worker.HOST_ENV)
    assert not cgroup.exists()
    # This disposable fixture is its own installation operator.
    (state / "active.json").unlink()
    worker.sync_directory(state)
    foundation.run(home, "execute", request, failure="expert_job_reconciliation_required")
    assert foundation.run(home, "execute", later)["state"] == "succeeded"
    return ["controller_loss_fences_claim_and_other_jobs", "operator_cleanup_preserves_consumed_claim"]


def cleanup_failure(home):
    request = foundation.create(home, "transform", foundation.TRANSFORM)
    later = foundation.create(home, "transform", foundation.TRANSFORM)
    approval = foundation.approve(home, request)
    foundation.approve(home, later)
    original = subprocess.run
    job, _ = job_paths(home, request)
    command = [*worker.runtime_command(home / "environment", job / "bundle"), "delete", "--force", request.name]

    def fail_delete(args, **kwargs):
        if args == command:
            raise subprocess.CalledProcessError(1, args)
        return original(args, **kwargs)

    args = argparse.Namespace(state=home / "state", environment=home / "environment",
                              request=request, operation="execute")
    try:
        with patch.object(worker.subprocess, "run", side_effect=fail_delete):
            receipt = worker.serve(args)
        assert receipt["reason_code"] == "expert_cleanup_unverified"
        assert_blocked(home, request, approval, receipt, clean=False)
        assert (job / "bundle").is_dir() and (args.state / "active.json").exists()
        foundation.run(home, "execute", later, failure="expert_worker_reconciliation_required")
    finally:
        original(command, check=True, timeout=5, capture_output=True, env=worker.HOST_ENV)
    return ["failed_runtime_delete_quarantines_without_candidate"]


def qualify(home):
    record = lifecycle.qualify(home)
    cases = [
        *isolation_probes(home),
        *resource_and_output_probes(home),
        *poison_artifact(home),
        *cancel_active_job(home),
        *controller_loss(home),
        *cleanup_failure(home),
    ]
    record["isolation"] = {"schema": "expert_hostile_execution_qualification_v1",
                           "cases": cases, "all_passed": True,
                           "cleanup_failure_injected": True}
    return record


if __name__ == "__main__":
    print(json.dumps(qualify(Path(sys.argv[1])), indent=2))
