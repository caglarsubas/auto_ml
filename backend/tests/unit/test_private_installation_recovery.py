"""Authenticated binary recovery, empty-target admission and persistent fencing."""

import ast
import base64
import copy
import importlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def recovery(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    return importlib.import_module("private_installation_recovery")


@pytest.fixture
def payload(recovery):
    raw = b"PGCOPY\n\xff\r\n\x00" + b"\0" * 8 + b"\xff\xff"
    row = {"sha256": recovery.digest(raw), "bytes": len(raw), "rows": 0}
    return {"schema": "private_coordinated_backup_v1", "source_plan_sha256": "a" * 64,
            "images": {r: "sha256:" + str(i) * 64 for i, r in enumerate(("api", "ingress", "postgres", "redis"), 1)},
            "schema_sha256": "b" * 64, "helper_sha256": recovery.digest(recovery.CODE.encode()),
            "database": {"catalog": {"tables": {"django_migrations": {}}, "sequences": {"fixture_id_seq": []}},
                         "tables": {"django_migrations": {**row, "data": base64.b64encode(raw).decode()}},
                         "data_sha256": recovery.digest(recovery.canonical({"django_migrations": row})),
                         "sequences": {"fixture_id_seq": [1, False]}, "empty_application": True, "bytes": len(raw)},
            "artifacts": {"data_files/rows.csv": base64.b64encode(b"x\n1\n").decode()}}


def test_authentication_roundtrip_and_nonce_separation(recovery, payload):
    key = b"k" * 32
    first, second = recovery.seal(payload, key), recovery.seal(payload, key)
    assert first != second and payload == recovery.unseal(first, key, recovery.digest(first))
    assert recovery.unseal(second, key, recovery.digest(second)) == payload
    assert b"rows.csv" not in first and b"PGCOPY" not in first


@pytest.mark.parametrize("fault", ["wrong_key", "tamper", "wrong_digest", "header", "oversize"])
def test_bad_envelopes_are_refused_before_use(recovery, payload, monkeypatch, fault):
    raw = recovery.seal(payload, b"k" * 32)
    pin = recovery.digest(raw)
    key = b"k" * 32
    if fault == "wrong_key":
        key = b"z" * 32
    elif fault == "tamper":
        raw = raw[:-1] + bytes([raw[-1] ^ 1])
        pin = recovery.digest(raw)
    elif fault == "wrong_digest":
        pin = "0" * 64
    elif fault == "header":
        raw = b"X" + raw[1:]
        pin = recovery.digest(raw)
    else:
        monkeypatch.setattr(recovery, "MAX_WIRE", len(raw) - 1)
    with pytest.raises(recovery.checker.planner.PlanError):
        recovery.unseal(raw, key, pin)


@pytest.mark.parametrize("fault", ["schema", "extra", "missing", "bad_table_digest", "float_rows", "bool_bytes",
                                  "table_set", "db_digest", "sequence_bool", "sequence_name", "collision", "data_budget"])
def test_malformed_data_never_becomes_a_backup(recovery, payload, monkeypatch, fault):
    row = payload["database"]["tables"]["django_migrations"]
    if fault == "schema":
        payload["schema"] = "other"
    elif fault == "extra":
        payload["sql"] = "DROP DATABASE"
    elif fault == "missing":
        del payload["schema_sha256"]
    elif fault == "bad_table_digest":
        row["sha256"] = "0" * 64
    elif fault == "float_rows":
        row["rows"] = 0.0
    elif fault == "bool_bytes":
        row["bytes"] = True
    elif fault == "table_set":
        payload["database"]["catalog"]["tables"] = {}
    elif fault == "db_digest":
        payload["database"]["data_sha256"] = "0" * 64
    elif fault == "sequence_bool":
        payload["database"]["sequences"]["fixture_id_seq"] = [1, 0]
    elif fault == "sequence_name":
        payload["database"]["sequences"] = {"x;DROP TABLE": [1, False]}
        payload["database"]["catalog"]["sequences"] = {"x;DROP TABLE": []}
    elif fault == "collision":
        payload["artifacts"] = {"a": "", "a/b": ""}
    else:
        monkeypatch.setattr(recovery, "MAX_DATA", 2)
    with pytest.raises(recovery.checker.planner.PlanError):
        recovery.seal(payload, b"k" * 32)


@pytest.mark.parametrize("path", ["/absolute", "../escape", "a/../b", "a//b", "a/./b", "a\\b", "a\nb", "", "\x00"])
def test_artifact_namespace_is_closed(recovery, payload, path):
    payload["artifacts"] = {path: ""}
    with pytest.raises(recovery.checker.planner.PlanError, match="artifact_path"):
        recovery.validate_payload(payload)


def test_runtime_and_controller_data_fingerprints_agree(recovery):
    tree = ast.parse(recovery.CODE)
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "encode" for t in n.targets))
    encoder = eval(compile(ast.Expression(node.value), "fixed-runtime-encoder", "eval"), {"json": json})
    value = {"table": {"rows": 12, "bytes": 100, "sha256": "a" * 64}}
    assert encoder(value) == recovery.canonical(value)


@pytest.mark.parametrize("fault", ["pristine", "missing_lock", "changed_lock", "extra_lock", "user", "project", "job", "session"])
def test_empty_target_accepts_only_exact_bootstrap_state(recovery, fault):
    tree = ast.parse(recovery.CODE)
    function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "application_empty")
    context = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "fixed-runtime-empty-target", "exec"), context)
    tables = {k: {"rows": n} for k, n in [("django_migrations", 40), ("django_content_type", 30),
                                          ("auth_permission", 120), ("execution_jobs_queuelock", 1),
                                          ("auth_user", 0), ("access_control_project", 0),
                                          ("execution_jobs_nativejob", 0), ("django_session", 0)]}
    locks = [(1,)]
    if fault == "missing_lock":
        locks = []
    elif fault == "changed_lock":
        locks = [(2,)]
    elif fault == "extra_lock":
        locks = [(1,), (2,)]
    elif fault != "pristine":
        key = {"user": "auth_user", "project": "access_control_project", "job": "execution_jobs_nativejob",
               "session": "django_session"}[fault]
        tables[key]["rows"] = 1
    assert context["application_empty"](tables, locks) is (fault == "pristine")


@pytest.mark.parametrize("role", ["api", "ingress", "postgres", "redis", "controller"])
def test_restore_plan_requires_exact_runtime(recovery, payload, role):
    target = {"images": dict(payload["images"]), "request": {"root": "/srv/target", "installation_id": "target"}}
    if role == "controller":
        payload["helper_sha256"] = "f" * 64
    else:
        target["images"][role] = "sha256:" + "f" * 64
    with pytest.raises(recovery.checker.planner.PlanError, match="same_runtime"):
        recovery.restore_spec(payload, "e" * 64, target, "d" * 64)


@pytest.mark.parametrize("fault", ["approval", "target", "backup", "strategy"])
def test_modified_approved_plan_stops_before_target_access(recovery, payload, monkeypatch, fault):
    target = {"images": payload["images"], "request": {"root": "/srv/target", "installation_id": "target"}}
    archive = recovery.seal(payload, b"k" * 32)
    spec = recovery.restore_spec(payload, recovery.digest(archive), target, "d" * 64)
    if fault == "approval":
        spec["model_use_approved"] = True
    elif fault == "target":
        spec["target_root"] = "/srv/another"
    elif fault == "backup":
        spec["source_plan_sha256"] = "f" * 64
    else:
        spec["strategy"] = "overwrite_live"
    request = recovery.encoded(spec)
    monkeypatch.setattr(recovery, "private_read", lambda p, *a: {"request": request, "key": b"k" * 32, "archive": archive}[str(p)])
    monkeypatch.setattr(recovery.checker, "verify", lambda *a: target)
    monkeypatch.setattr(recovery, "context", lambda *a: pytest.fail("target was accessed"))
    with pytest.raises(recovery.checker.planner.PlanError, match="restore_plan_changed"):
        recovery.restore("archive", "key", "target", "d" * 64, "request", recovery.digest(request))


@pytest.mark.parametrize("fault", ["symlink", "directory_link", "hardlink", "fifo", "oversize"])
def test_descriptor_snapshot_refuses_unsafe_entries(recovery, tmp_path, monkeypatch, fault):
    monkeypatch.setattr(recovery.checker, "no_directory_acl", lambda *a: None)
    if fault == "symlink":
        (tmp_path / "bad").symlink_to("/etc/passwd")
    elif fault == "directory_link":
        (tmp_path / "bad").symlink_to(tmp_path, target_is_directory=True)
    elif fault == "hardlink":
        (tmp_path / "data").write_bytes(b"x")
        os.link(tmp_path / "data", tmp_path / "bad")
    elif fault == "fifo":
        os.mkfifo(tmp_path / "bad")
    else:
        (tmp_path / "bad").write_bytes(b"12345")
        monkeypatch.setattr(recovery, "MAX_DATA", 4)
    with pytest.raises(recovery.checker.planner.PlanError):
        recovery.artifacts(tmp_path)


def test_snapshot_preserves_nested_bytes(recovery, tmp_path, monkeypatch):
    monkeypatch.setattr(recovery.checker, "no_directory_acl", lambda *a: None)
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/data").write_bytes(b"\x00\xff\n")
    expected = {"nested/data": base64.b64encode(b"\x00\xff\n").decode()}
    assert recovery.artifacts(tmp_path) == expected == recovery.artifacts(tmp_path)


@pytest.fixture
def journal(recovery, tmp_path, monkeypatch):
    root = tmp_path / "recovery"
    root.mkdir(mode=0o700)
    intent = {"schema": "private_restore_intent_v1", "target_plan_sha256": "a" * 64, "backup_sha256": "b" * 64,
              "restore_plan_sha256": "c" * 64, "initialization_id": "d" * 32,
              "helper_sha256": recovery.digest(recovery.CODE.encode()),
              "baseline": {"data_sha256": "e" * 64, "empty_application": True}}
    records = {"intent.json": recovery.encoded(intent), "complete.json": recovery.encoded(recovery.completion(intent))}
    original = Path.lstat

    def owned(path):
        if path == root:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0, st_gid=0)
        return original(path)

    monkeypatch.setattr(Path, "lstat", owned)
    def read(path, *args):
        if path.name not in records:
            raise FileNotFoundError
        return records[path.name]
    monkeypatch.setattr(recovery, "private_read", read)
    monkeypatch.setattr(recovery.resources, "initialization", lambda *a: {"initialization_id": "d" * 32})
    return {"request": {"root": str(tmp_path)}}, intent, records


def test_valid_completion_allows_adoption(recovery, journal):
    value, _, _ = journal
    assert recovery.adoption_guard(value, "a" * 64) is None


@pytest.mark.parametrize("fault", ["pending", "plan", "initialization", "helper", "extra_intent", "approved", "modified_completion"])
def test_partial_or_changed_recovery_blocks_adoption(recovery, journal, fault):
    value, intent, records = journal
    if fault == "pending":
        del records["complete.json"]
    elif fault == "approved":
        done = json.loads(records["complete.json"])
        done["model_use_approved"] = True
        records["complete.json"] = recovery.encoded(done)
    elif fault == "modified_completion":
        records["complete.json"] = b"{}"
    else:
        if fault == "plan":
            intent["target_plan_sha256"] = "f" * 64
        elif fault == "initialization":
            intent["initialization_id"] = "f" * 32
        elif fault == "helper":
            intent["helper_sha256"] = "f" * 64
        else:
            intent["unknown"] = True
        records["intent.json"] = recovery.encoded(intent)
        records["complete.json"] = recovery.encoded(recovery.completion(intent))
    with pytest.raises(recovery.checker.planner.PlanError):
        recovery.adoption_guard(value, "a" * 64)


def test_unrelated_installations_keep_original_admission(recovery, tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "private_read", lambda *a: pytest.fail("unrelated metadata read"))
    recovery.adoption_guard({"request": {"root": str(tmp_path)}}, "a" * 64)


@pytest.fixture
def stage_boundary(recovery, tmp_path, monkeypatch):
    # Kernel ownership and rename admission are independently exercised by the
    # installed Linux drill. Here interrupt actual filesystem publication at
    # the controller boundary, without requiring root on ordinary test workers.
    monkeypatch.setattr(recovery.os, "chown", lambda *a: None)
    monkeypatch.setattr(recovery.os, "fchown", lambda *a: None)
    monkeypatch.setattr(recovery.checker, "no_directory_acl", lambda *a: None)
    monkeypatch.setattr(recovery.resources.initializer, "trusted_directory", lambda p: os.open(p, os.O_RDONLY | os.O_DIRECTORY))
    monkeypatch.setattr(recovery.checker, "open_directory", lambda p: os.open(p, os.O_RDONLY | os.O_DIRECTORY))
    state = {"interrupt": False}
    def move(source_fd, source, target_fd, target, flags):
        assert flags == 1
        with pytest.raises(FileNotFoundError):
            os.stat(target, dir_fd=target_fd, follow_symlinks=False)
        os.rename(source, target, src_dir_fd=source_fd, dst_dir_fd=target_fd)
        if state["interrupt"]:
            state["interrupt"] = False
            raise RuntimeError("lost publication acknowledgement")
        return 0
    monkeypatch.setattr(recovery.ctypes, "CDLL", lambda *a, **kw: SimpleNamespace(renameat2=move))
    return tmp_path, state


def test_artifact_staging_reuses_complete_bytes(recovery, stage_boundary):
    root, _ = stage_boundary
    values = {"nested/data": base64.b64encode(b"\x00\xff\n").decode(), "other": ""}
    path = recovery.stage_artifacts(root, values)
    identity = (path / "nested/data").stat().st_ino
    assert recovery.stage_artifacts(root, values) == path
    assert (path / "nested/data").stat().st_ino == identity
    assert recovery.artifacts(path) == values


def test_artifact_staging_resumes_after_lost_rename_ack(recovery, stage_boundary):
    root, state = stage_boundary
    values = {"first": "YQ==", "nested/second": "Yg=="}
    state["interrupt"] = True
    with pytest.raises(RuntimeError, match="acknowledgement"):
        recovery.stage_artifacts(root, values)
    assert (root / "staged-artifacts/first").read_bytes() == b"a"
    assert not list(root.glob(".file-*"))
    assert recovery.artifacts(recovery.stage_artifacts(root, values)) == values


def test_artifact_staging_refuses_divergence_without_repair(recovery, stage_boundary):
    root, _ = stage_boundary
    values = {"first": "YQ=="}
    path = recovery.stage_artifacts(root, values)
    (path / "first").write_bytes(b"changed")
    with pytest.raises(recovery.checker.planner.PlanError, match="stage_changed"):
        recovery.stage_artifacts(root, values)
    assert (path / "first").read_bytes() == b"changed"


@pytest.mark.parametrize("fault", ["stopped", "substring", "duplicate", "malformed"])
def test_installed_drill_cleanup_uses_exact_container_listing(recovery, monkeypatch, fault):
    qualifier = importlib.import_module("qualify_private_installation_recovery")
    name = "declarai-owned-postgres"
    row = {"ID": "a" * 64, "Names": name, "State": "exited"}
    rows = [row]
    if fault == "substring":
        rows = [{**row, "Names": name + "-other"}]
    elif fault == "duplicate":
        rows.append({**row, "ID": "b" * 64})
    elif fault == "malformed":
        rows = [{"ID": "a" * 64, "Name": name}]
    calls = []
    def listing(args):
        calls.append(args)
        return b"\n".join(json.dumps(r).encode() for r in rows)
    monkeypatch.setattr(qualifier, "command", listing)
    if fault in {"duplicate", "malformed"}:
        with pytest.raises(recovery.checker.planner.PlanError, match="cleanup_"):
            qualifier.dependency_ids(name)
    else:
        assert qualifier.dependency_ids(name) == (["a" * 64] if fault == "stopped" else [])
    assert "--all" in calls[0] and "--no-trunc" in calls[0]


@pytest.mark.parametrize("fault", ["stable_code", "unsafe_plan_error", "arbitrary_exception"])
def test_drill_failure_diagnostics_do_not_expose_exception_arguments(recovery, fault):
    qualifier = importlib.import_module("qualify_private_installation_recovery")
    error = (recovery.checker.planner.PlanError("recovery_target_database_occupied") if fault == "stable_code"
             else recovery.checker.planner.PlanError("secret") if fault == "unsafe_plan_error"
             else RuntimeError("password=secret customer bytes"))
    result = qualifier.failure_diagnostic("coordinated_restore_and_replay", error)
    assert result["stage"] == "coordinated_restore_and_replay"
    assert ("code" in result) is (fault == "stable_code")
    assert "secret" not in json.dumps(result) and "customer bytes" not in json.dumps(result)
