#!/usr/bin/env python3
"""Qualify opaque expert state across training, evaluation, replay and scoring."""

import ast
import base64
import json
import subprocess
import sys
import uuid
from pathlib import Path

import private_expert_worker as worker
import qualify_private_expert_worker as foundation

RECIPE = b"""
import base64
import json
import os
import pickle

data = json.load(open('/work/input.json'))
stage = json.load(open('/work/context.json'))['stage']
if stage == 'fit':
    assert not os.path.exists('/work/state.bin')
    state = {'mean': sum(row[0] for row in data['rows']) / len(data['rows'])}
else:
    state = pickle.loads(open('/work/state.bin', 'rb').read())
name = 'score' if stage in ('score', 'evaluate') else 'centered'
table = {'columns': [name], 'row_ids': data['row_ids'],
         'rows': [[row[0] - state['mean']] for row in data['rows']]}
if stage == 'fit':
    print(json.dumps({'table': table, 'state_base64': base64.b64encode(pickle.dumps(state, protocol=4)).decode()}))
else:
    print(json.dumps(table))
"""


def invoke(home, operation, request=None, *args, state=None, failure=None):
    command = foundation.command(home, operation, request, *args)
    if state:
        command[command.index("--state") + 1] = str(state)
    completed = subprocess.run(command, capture_output=True, timeout=50)
    value = json.loads(completed.stdout)
    if failure:
        assert completed.returncode == 1 and value.get("reason_code") == failure, value
    else:
        assert completed.returncode == 0 and value.get("state") != "blocked", value
    return value


def request(home, mode, project, partition, rows, artifact=None):
    path = foundation.create(home, mode, RECIPE)
    selection = json.loads((path / "request.json").read_bytes())
    selection.update(project_id=project, partition_id=partition)
    if artifact is not None:
        selection["artifact_sha256"] = worker.digest(artifact)
        (path / "fitted.json").write_bytes(artifact)
    (path / "request.json").write_bytes(worker.canonical(selection))
    (path / "input.json").write_bytes(worker.canonical({
        "columns": ["x"], "row_ids": ["first", "second"], "rows": [[x] for x in rows],
    }))
    return path


def approve(home, path, state=None):
    preview = invoke(home, "preview", path, state=state)
    return invoke(home, "approve", path, "--expected", preview["sha256"],
                  "--reviewer", "fixture-reviewer", state=state)


def controller_boundary():
    tree = ast.parse((foundation.ROOT / "private_expert_worker.py").read_text())
    imports = [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
    assert not set(imports).intersection({"pickle", "joblib", "importlib", "cloudpickle", "dill"})
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in {"exec", "eval", "compile", "__import__"} for node in ast.walk(tree))


def qualify(home):
    record = foundation.qualify(home)  # Every D08-T01 scenario still executes.
    controller_boundary()
    state = home / "state"
    project, partition = str(uuid.uuid4()), str(uuid.uuid4())
    fit = request(home, "fit", project, partition, [2, 4])
    approval = approve(home, fit)
    receipt = invoke(home, "execute", fit)
    assert receipt["approval_sha256"] == worker.digest(worker.canonical(approval))
    assert json.loads((state / fit.name / "candidate.json").read_bytes())["rows"] == [[-1], [1]]
    artifact = (state / fit.name / "fitted.json").read_bytes()
    assert worker.digest(artifact) == receipt["artifact_sha256"]
    output = home / "portable-fitted.json"
    exported = invoke(home, "export", fit, "--output", str(output))
    assert output.read_bytes() == artifact and exported["artifact_sha256"] == receipt["artifact_sha256"]
    assert exported["scope"] == "opaque_expert_state_requires_gvisor"
    assert invoke(home, "execute", fit) == receipt

    for mode, column in (("apply", "centered"), ("evaluate", "score"), ("score", "score")):
        selected = request(home, mode, project, str(uuid.uuid4()), [100, 200], artifact)
        approved = approve(home, selected)
        assert approved["manifest"]["fitted_state_sha256"] == json.loads(artifact)["state_sha256"]
        assert approved["manifest"]["fit_partition_id"] == partition
        result = invoke(home, "execute", selected)
        assert result["applied_artifact_sha256"] == exported["artifact_sha256"]
        candidate = json.loads((state / selected.name / "candidate.json").read_bytes())
        assert candidate == {"columns": [column], "row_ids": ["first", "second"], "rows": [[97], [197]]}
        assert not (state / selected.name / "fitted.json").exists()

    clean = home / "clean-state"
    clean.mkdir(mode=0o700)
    invoke(home, "pin", state=clean)
    replay = request(home, "replay", project, partition, [2, 4], artifact)
    approve(home, replay, clean)
    replay_receipt = invoke(home, "execute", replay, state=clean)
    assert replay_receipt["candidate_sha256"] == receipt["candidate_sha256"]
    assert not (clean / fit.name).exists()
    assert not (clean / replay.name / "fitted.json").exists()
    wrong = request(home, "replay", project, partition, [20, 40], artifact)
    invoke(home, "preview", wrong, failure="expert_replay_requires_exact_fit_partition")

    cross_project = request(home, "score", str(uuid.uuid4()), str(uuid.uuid4()), [100, 200], artifact)
    invoke(home, "preview", cross_project, failure="expert_artifact_scope_changed")
    missing = request(home, "apply", project, str(uuid.uuid4()), [100, 200])
    invoke(home, "preview", missing, failure="expert_fitted_artifact_required")
    altered = request(home, "score", project, str(uuid.uuid4()), [100, 200], artifact)
    with (altered / "code.py").open("ab") as code:
        code.write(b"\n# changed expert recipe\n")
    invoke(home, "preview", altered, failure="expert_artifact_scope_changed")
    changed = request(home, "score", project, str(uuid.uuid4()), [100, 200], artifact)
    approve(home, changed)
    with (changed / "fitted.json").open("ab") as out:
        out.write(b"\n")
    invoke(home, "execute", changed, failure="expert_artifact_changed")
    assert not (state / changed.name / "claimed.json").exists()

    mismatched = json.loads(artifact)
    mismatched["state_sha256"] = "0" * 64
    raw = worker.canonical(mismatched)
    bad_state = request(home, "apply", project, str(uuid.uuid4()), [100, 200], raw)
    invoke(home, "preview", bad_state, failure="expert_artifact_state_changed")
    incompatible = json.loads(artifact)
    incompatible["fit"]["environment"]["runtime_sha256"] = "0" * 64
    raw = worker.canonical(incompatible)
    bad_env = request(home, "score", project, str(uuid.uuid4()), [100, 200], raw)
    invoke(home, "preview", bad_env, failure="expert_artifact_scope_changed")

    # A deliberately non-replayable state verifies that replay compares opaque
    # bytes, in addition to the numeric output. It is created only in gVisor.
    random_fit = request(home, "fit", project, partition, [2, 4])
    code = RECIPE.replace(b"'mean':", b"'nonce': os.urandom(16), 'mean':")
    (random_fit / "code.py").write_bytes(code)
    approve(home, random_fit)
    invoke(home, "execute", random_fit)
    random_artifact = (state / random_fit.name / "fitted.json").read_bytes()
    random_replay = request(home, "replay", project, partition, [2, 4], random_artifact)
    (random_replay / "code.py").write_bytes(code)
    approve(home, random_replay, clean)
    invoke(home, "execute", random_replay, state=clean, failure="expert_replay_state_mismatch")

    assert not (state / "active.json").exists() and not (clean / "active.json").exists()
    assert base64.b64decode(json.loads(artifact)["state_base64"], validate=True)
    record["lifecycle"] = {
        "schema": "expert_fitted_lifecycle_qualification_v1",
        "cases": ["sandbox_fit", "opaque_export", "fit_partition_only", "sandbox_apply",
                  "sandbox_evaluate", "sandbox_score", "clean_state_replay", "replay_exact_inputs",
                  "replay_state_mismatch", "same_project", "exact_code", "exact_artifact",
                  "required_state", "state_integrity", "environment_integrity", "controller_never_imports_expert"],
        "artifact_sha256": exported["artifact_sha256"], "all_passed": True,
    }
    return record


if __name__ == "__main__":
    print(json.dumps(qualify(Path(sys.argv[1])), indent=2))
