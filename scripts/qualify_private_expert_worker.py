#!/usr/bin/env python3
"""Exercise the real Linux worker against synthetic approved feature partitions."""

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import private_expert_worker as worker

ROOT = Path(__file__).resolve().parent
TRANSFORM = b"""
import json
import os
import socket

assert os.getuid() == 65534
assert not os.path.exists(HOST_SENTINEL)
assert not os.path.exists('/work/approval.json')
try:
    open('/work/input.json', 'a')
except OSError:
    pass
else:
    raise AssertionError('input is writable')
try:
    socket.create_connection(('192.0.2.1', 80), timeout=1)
except OSError:
    pass
else:
    raise AssertionError('external socket connected')
source = json.load(open('/work/input.json'))
print(json.dumps({'columns': ['twice'], 'row_ids': source['row_ids'],
                  'rows': [[2 * row[0]] for row in source['rows']]}))
"""
SCORE = TRANSFORM.replace(b"'twice'", b"'score'")


def command(home, operation, request=None, *args):
    cmd = [sys.executable, "-I", str(ROOT / "private_expert_worker.py"),
           "--state", str(home / "state"), "--environment", str(home / "environment"), operation]
    if request:
        cmd.extend([str(request), *args])
    return cmd


def run(home, operation, request=None, *args, failure=None):
    result = subprocess.run(command(home, operation, request, *args), capture_output=True, timeout=50)
    value = json.loads(result.stdout)
    if failure:
        assert result.returncode == 1 and value.get("reason_code") == failure, (operation, value)
    else:
        assert result.returncode == 0 and value.get("state") != "blocked", (operation, value)
    return value


def create(home, mode, source):
    request = home / str(uuid.uuid4())
    request.mkdir(mode=0o700)
    selection = {"id": request.name, "project_id": str(uuid.uuid4()), "partition_id": str(uuid.uuid4()),
                 "proposer": "fixture-developer", "mode": mode}
    (request / "request.json").write_bytes(worker.canonical(selection))
    if b"HOST_SENTINEL" in source:
        source = source.replace(b"HOST_SENTINEL", repr(str(home / "host-sentinel")).encode())
    (request / "code.py").write_bytes(source)
    (request / "input.json").write_bytes(worker.canonical({
        "columns": ["x"], "row_ids": ["first", "second"], "rows": [[2], [-4]],
    }))
    return request


def approve(home, request):
    preview = run(home, "preview", request)
    run(home, "approve", request, "--expected", preview["sha256"], "--reviewer", "fixture-developer",
        failure="expert_independent_exact_review_required")
    return run(home, "approve", request, "--expected", preview["sha256"], "--reviewer", "fixture-reviewer")


def qualify(home):
    state = home / "state"
    state.mkdir(mode=0o700)
    (home / "host-sentinel").write_text("synthetic sentinel")
    env = run(home, "pin")
    cases = []
    for mode, code, name in (("transform", TRANSFORM, "twice"), ("score", SCORE, "score")):
        request = create(home, mode, code)
        run(home, "execute", request, failure="expert_request_or_environment_unavailable")
        approval = approve(home, request)
        for file, replacement in (
            ("code.py", code + b"\n# changed\n"),
            ("input.json", b'{"columns":["x"],"row_ids":["first","second"],"rows":[[3],[-4]]}'),
            ("request.json", worker.canonical({
                **json.loads((request / "request.json").read_bytes()), "partition_id": str(uuid.uuid4()),
            })),
        ):
            path = request / file
            saved = path.read_bytes()
            path.write_bytes(replacement)
            run(home, "execute", request, failure="expert_approval_stale")
            path.write_bytes(saved)
        receipt = run(home, "execute", request)
        result = state / request.name / "candidate.json"
        assert json.loads(result.read_bytes()) == {
            "columns": [name], "row_ids": ["first", "second"], "rows": [[4], [-8]],
        }
        assert receipt["candidate_sha256"] == worker.digest(result.read_bytes())
        assert receipt["approval_sha256"] == worker.digest(worker.canonical(approval))
        assert run(home, "execute", request) == receipt and not (state / "active.json").exists()
        cases.append(mode)
    cases.extend(["exact_code_input_partition_review", "read_only_input", "no_host_mount_or_network",
                  "approval_consumed_once"])
    request = create(home, "transform", b"print('x' * 300000)")
    approve(home, request)
    run(home, "execute", request, failure="expert_output_limit")
    assert not (state / request.name / "candidate.json").exists() and not (state / "active.json").exists()
    cases.append("bounded_output")
    request = create(home, "score", b"import time\ntime.sleep(4)\n" + SCORE)
    approve(home, request)
    cgroup = Path("/sys/fs/cgroup") / request.name
    with subprocess.Popen(command(home, "execute", request), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE) as proc:
        bound = time.monotonic() + 12
        observed = None
        while proc.poll() is None and time.monotonic() < bound:
            try:
                observed = {name: (cgroup / name).read_text().strip()
                            for name in ("memory.max", "pids.max", "cpu.max")}
                break
            except FileNotFoundError:
                time.sleep(0.05)
        stdout, _ = proc.communicate(timeout=25)
        assert proc.returncode == 0, stdout
    assert observed == {"memory.max": str(worker.LIMITS["memory_bytes"]),
                        "pids.max": str(worker.LIMITS["pids"]),
                        "cpu.max": f"{worker.LIMITS['cpu_quota']} {worker.LIMITS['cpu_period']}"}, observed
    assert not cgroup.exists()
    cases.append("host_cgroup_limits_and_cleanup")
    request = create(home, "transform", b"import time\ntime.sleep(60)\n")
    approve(home, request)
    run(home, "execute", request, failure="expert_wall_limit")
    assert not (state / request.name / "bundle").exists() and not (state / "active.json").exists()
    cases.append("wall_limit_cleanup")
    request = create(home, "transform", b"print('unstructured')\n")
    approve(home, request)
    run(home, "execute", request, failure="expert_candidate_or_storage_invalid")
    assert not (state / request.name / "candidate.json").exists()
    cases.append("typed_candidate")
    request = create(home, "score", SCORE)
    approve(home, request)
    path = home / "environment/runtime/runsc"
    path.rename(path.with_suffix(".absent"))
    run(home, "execute", request, failure="expert_runtime_unavailable")
    assert not (state / request.name / "claimed.json").exists()
    path.with_suffix(".absent").rename(path)
    cases.append("runtime_unavailable_blocks")
    return {"schema": "declarai_expert_worker_qualification_v1", "environment": env,
            "cases": cases, "synthetic": True, "result": "passed", "limits": worker.LIMITS}


if __name__ == "__main__":
    print(json.dumps(qualify(Path(sys.argv[1])), indent=2))
