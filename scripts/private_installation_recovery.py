#!/usr/bin/env python3
"""Encrypted coordinated recovery into an explicitly approved empty installation.

Same sealed images/schema only. No saved SQL, Python, pickle, service stop,
account creation, model approval or in-place replacement of a live installation.
"""

import argparse
import base64
import ctypes
import hashlib
import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import private_schema_init as schema_init
from private_recovery_runtime import CODE

startup, adopter = schema_init.startup, schema_init.adopter
resources, checker = startup.resources, startup.checker
MAX_DATA = 64 * 1024**2
MAX_WIRE = 96 * 1024**2
MAX_JOURNAL = 4 * 1024**2
HEADER = b"DECLARAI-RECOVERY-v1\n"
HEX = resources.re.compile(r"[0-9a-f]{64}")
NAME = resources.re.compile(r"[a-z_][a-z0-9_]{0,126}")


def require(value, reason):
    if not value:
        raise checker.planner.PlanError("recovery_" + reason)


def encoded(value):
    return checker.planner.encoded(value)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def private_read(path, limit, mode=None):
    path = Path(path)
    parent = resources.initializer.trusted_directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == 0
                    and not stat.S_IMODE(before.st_mode) & 0o077 and 0 < before.st_size <= limit
                    and (mode is None or stat.S_IMODE(before.st_mode) == mode), "private_file_invalid")
            checker.no_directory_acl(stream.fileno())
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            require(identity(before) == identity(after) and len(raw) == before.st_size, "private_file_changed")
            return raw
    finally:
        os.close(parent)


def identity(info):
    return tuple(getattr(info, name) for name in ("st_dev", "st_ino", "st_size", "st_mode", "st_nlink", "st_mtime_ns", "st_ctime_ns"))


def publish(path, raw):
    """No replacement, including a racing destination; fsync before publication."""
    path = Path(path)
    parent = resources.initializer.trusted_directory(path.parent)
    stage = ".recovery-" + uuid.uuid4().hex
    try:
        fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        resources.initializer.rename_noreplace(parent, stage, path.name)
        os.fsync(parent)
    finally:
        if stage in os.listdir(parent):
            os.unlink(stage, dir_fd=parent)
        os.close(parent)


def relative_name(name):
    return (isinstance(name, str) and 0 < len(name.encode()) <= 1024 and "\\" not in name
            and not any(ord(c) < 32 or ord(c) == 127 for c in name)
            and all(p not in {"", ".", ".."} for p in name.split("/")))


def artifacts(path):
    """Descriptor traversal never follows a swapped directory or file link."""
    fd = os.open(path, resources.initializer.DIRECTORY_FLAGS)
    out = {}
    total = 0

    entries = 0

    def names_at(parent):
        names = []
        with os.scandir(parent) as listing:
            for item in listing:
                require(len(names) < 2048, "artifact_budget")
                names.append(item.name)
        return sorted(names)

    def walk(parent, prefix):
        nonlocal total
        nonlocal entries
        require(prefix.count("/") < 32, "artifact_depth")
        before = os.fstat(parent)
        checker.no_directory_acl(parent)
        names = names_at(parent)
        for name in names:
            entries += 1
            require(entries <= 2048, "artifact_budget")
            key = prefix + name
            require(relative_name(key), "artifact_path_invalid")
            old = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if stat.S_ISDIR(old.st_mode):
                child = os.open(name, resources.initializer.DIRECTORY_FLAGS, dir_fd=parent)
                try:
                    require(identity(old) == identity(os.fstat(child)), "artifact_changed")
                    walk(child, key + "/")
                finally:
                    os.close(child)
            else:
                require(stat.S_ISREG(old.st_mode) and old.st_nlink == 1 and old.st_size <= MAX_DATA, "artifact_file_invalid")
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                with os.fdopen(child, "rb") as stream:
                    require(identity(old) == identity(os.fstat(stream.fileno())), "artifact_changed")
                    raw = stream.read(MAX_DATA + 1)
                    require(identity(old) == identity(os.fstat(stream.fileno())) and len(raw) == old.st_size, "artifact_changed")
                total += len(raw)
                require(total <= MAX_DATA and len(out) < 1024, "artifact_budget")
                out[key] = base64.b64encode(raw).decode()
            require(identity(old) == identity(os.stat(name, dir_fd=parent, follow_symlinks=False)), "artifact_changed")
        require(names == names_at(parent) and identity(before) == identity(os.fstat(parent)), "artifact_changed")
    try:
        walk(fd, "")
        return out
    finally:
        os.close(fd)


def decoded_data(value):
    require(isinstance(value, str), "base64_invalid")
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError:
        require(False, "base64_invalid")
    require(base64.b64encode(raw).decode() == value, "base64_invalid")
    return raw


def validate_payload(v):
    require(isinstance(v, dict) and set(v) == {"schema", "source_plan_sha256", "images", "schema_sha256", "helper_sha256", "database", "artifacts"}
            and v["schema"] == "private_coordinated_backup_v1", "payload_schema")
    require(all(sha(v[k]) for k in ("source_plan_sha256", "schema_sha256", "helper_sha256")), "payload_binding")
    require(isinstance(v["images"], dict) and set(v["images"]) == {"api", "ingress", "postgres", "redis"}
            and all(isinstance(x, str) and x.startswith("sha256:") and sha(x[7:]) for x in v["images"].values()), "payload_images")
    db = v["database"]
    require(isinstance(db, dict) and set(db) == {"catalog", "tables", "data_sha256", "sequences", "empty_application", "bytes"}, "database_shape")
    require(isinstance(db["catalog"], dict) and set(db["catalog"]) == {"tables", "sequences"}
            and isinstance(db["tables"], dict) and 0 < len(db["tables"]) < 256
            and set(db["tables"]) == set(db["catalog"]["tables"])
            and set(db["sequences"]) == set(db["catalog"]["sequences"]), "database_catalog")
    require(type(db["empty_application"]) is bool and type(db["bytes"]) is int and sha(db["data_sha256"]), "database_shape")
    total = 0
    identities = {}
    for name, row in db["tables"].items():
        require(NAME.fullmatch(name) is not None and isinstance(row, dict)
                and set(row) == {"sha256", "bytes", "rows", "data"}, "table_shape")
        raw = decoded_data(row["data"])
        require(type(row["bytes"]) is int and type(row["rows"]) is int and row["rows"] >= 0
                and len(raw) == row["bytes"] and raw.startswith(b"PGCOPY\n\xff\r\n\x00")
                and raw.endswith(b"\xff\xff") and digest(raw) == row["sha256"], "table_data")
        identities[name] = {k: row[k] for k in ("sha256", "bytes", "rows")}
        total += len(raw)
    require(total == db["bytes"] and digest(canonical(identities)) == db["data_sha256"], "database_digest")
    for name, row in db["sequences"].items():
        require(NAME.fullmatch(name) is not None and isinstance(row, list) and len(row) == 2
                and type(row[0]) is int and type(row[1]) is bool, "sequence_shape")
    require(isinstance(v["artifacts"], dict) and len(v["artifacts"]) <= 1024, "artifact_budget")
    for name, value in v["artifacts"].items():
        require(relative_name(name), "artifact_path_invalid")
        require(all("/".join(name.split("/")[:i]) not in v["artifacts"] for i in range(1, len(name.split("/")))), "artifact_path_collision")
        total += len(decoded_data(value))
    require(total <= MAX_DATA, "data_budget")
    return v


def seal(value, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    validate_payload(value)
    require(isinstance(key, bytes) and len(key) == 32, "key_invalid")
    raw = encoded(value)
    require(len(raw) <= MAX_WIRE - 128, "wire_budget")
    nonce = os.urandom(12)
    return HEADER + nonce + AESGCM(key).encrypt(nonce, raw, HEADER)


def unseal(raw, key, expected):
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    require(sha(expected) and digest(raw) == expected, "backup_digest")
    require(isinstance(key, bytes) and len(key) == 32, "key_invalid")
    require(len(HEADER) + 28 < len(raw) <= MAX_WIRE and raw.startswith(HEADER), "envelope_invalid")
    nonce, ciphertext = raw[len(HEADER):len(HEADER) + 12], raw[len(HEADER) + 12:]
    try:
        plain = AESGCM(key).decrypt(nonce, ciphertext, HEADER)
    except InvalidTag:
        require(False, "authentication_failed")
    return validate_payload(checker.planner.decode(plain))


def helper(value, receipt, image, action, payload=None):
    env = {**checker.planner.composition(value["request"], value["images"])["services"]["api"]["environment"],
           "DECLARAI_MEDIA_ROOT": "/tmp/recovery-media"}
    binding = startup.labels(value, receipt)
    args = ["container", "create", "--name", "declarai-recovery-" + uuid.uuid4().hex, "--pull", "never",
            "--network", value["prerequisites"]["networks"][0]["name"], "--read-only", "--user", "10001:10001",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--cpus", "1", "--memory", "1g",
            "--pids-limit", "64", "--tmpfs", "/tmp:rw,noexec,nosuid,size=134217728,uid=10001,gid=10001,mode=700",
            "--entrypoint", "python", "-i"]
    for k, x in {**binding, resources.LABEL + "role": "recovery-data"}.items():
        args += ["--label", k + "=" + x]
    for k, x in env.items():
        args += ["--env", k + "=" + x]
    args += ["--mount", "type=bind,src=" + value["request"]["root"] + "/secrets/app,dst=/installation,readonly"]
    identifier = resources.command([*args, value["images"]["api"], "-I", "-c", CODE]).decode().strip()
    require(resources.re.fullmatch(r"[0-9a-f]{64}", identifier), "helper_identity")
    try:
        info = resources.inspect("container", identifier)
        adopter.validate_preflight(info, value, env, binding, image, role="recovery-data", entrypoint=["python"],
                                   command=["-I", "-c", CODE], mount_sources={"/installation": value["request"]["root"] + "/secrets/app"})
        require(info["Config"].get("OpenStdin") is True, "helper_stdin")
        request = encoded({"action": action, "payload": payload})
        require(len(request) <= MAX_WIRE, "wire_budget")
        result = subprocess.run([*resources.PREFIX, "container", "start", "--attach", "--interactive", identifier],
                                input=request, capture_output=True, timeout=120, check=False)
        state = resources.inspect("container", identifier)["State"]
        require(result.returncode == 0 and not state["Running"] and state["ExitCode"] == 0
                and len(result.stdout) <= MAX_WIRE, "helper_failed")
        out = checker.planner.decode(result.stdout)
        require(set(out) == {"schema", "action", "application_role_elevated", "result"}
                and out["schema"] == "private_recovery_data_v1" and out["action"] == action
                and out["application_role_elevated"] is False, "helper_result")
        return out["result"]
    finally:
        require(resources.inspect("container", identifier)["Config"].get("Labels") == {**binding, resources.LABEL + "role": "recovery-data"}, "helper_cleanup_owner")
        resources.command(["container", "rm", "--force", identifier])


def context(plan, expected):
    require(sys.platform == "linux" and os.geteuid() == 0, "linux_root_required")
    value, spec, receipt, _, _, root = startup.prepared(plan, expected)
    os.close(root)
    resources.docker_host(value["manifest"]["architecture"])
    require(resources.record(["info", "--format", "{{json .}}"]).get("DefaultRuntime") == "runc", "runtime_required")
    images = {r: resources.inspect("image", x) for r, x in value["images"].items()}
    require(all(i["Id"] == value["images"][r] and i["Architecture"] == value["manifest"]["architecture"] and i["Os"] == "linux" for r, i in images.items()), "image_binding")
    deps = startup.snapshot(value, spec, receipt, images, True)
    startup.network(value, receipt, deps)
    project = checker.planner.composition(value["request"], value["images"])
    require(not adopter.project_containers(project["name"]), "applications_present")
    description = schema_init.helper(value, receipt, images["api"], "describe")
    require(description["state"] == "current", "schema_not_current")
    return value, receipt, images, description["schema_sha256"]


def backup(plan, expected, keyfile, destination):
    value = checker.verify(plan, expected)
    require(not Path(destination).is_relative_to(Path(value["request"]["root"]))
            and not Path(keyfile).is_relative_to(Path(value["request"]["root"])), "external_backup_custody_required")
    with adopter.managed_operation(value):
        value, receipt, images, schema = context(plan, expected)
        before = artifacts(Path(value["request"]["root"]) / "artifacts")
        database = helper(value, receipt, images["api"], "snapshot")
        require(before == artifacts(Path(value["request"]["root"]) / "artifacts"), "artifacts_changed_during_backup")
        payload = {"schema": "private_coordinated_backup_v1", "source_plan_sha256": expected,
                   "images": value["images"], "schema_sha256": schema, "helper_sha256": digest(CODE.encode()),
                   "database": database, "artifacts": before}
        raw = seal(payload, private_read(keyfile, 32, 0o400))
        publish(destination, raw)
    return {"schema": "private_backup_created_v1", "backup_sha256": digest(raw), "source_plan_sha256": expected,
            "schema_sha256": schema, "quiescent_database_and_artifacts": True, "restore_verified": False,
            "secret_or_customer_bytes_emitted": False, "operator_key_custody_qualified": False}


def restore_spec(payload, backup_sha, target, expected):
    require(payload["images"] == target["images"] and payload["helper_sha256"] == digest(CODE.encode()), "same_runtime_required")
    return {"schema": "private_restore_plan_v1", "backup_sha256": backup_sha,
            "source_plan_sha256": payload["source_plan_sha256"], "target_plan_sha256": expected,
            "target_installation_id": target["request"]["installation_id"], "target_root": target["request"]["root"],
            "images": target["images"], "schema_sha256": payload["schema_sha256"], "helper_sha256": payload["helper_sha256"],
            "strategy": "binary_copy_into_same_runtime_empty_target", "application_services_offline": True,
            "chosen_authority_point": "quiescent_backup", "model_use_approved": False, "release_qualified": False}


def render(archive, backup_sha, keyfile, plan, expected, destination):
    payload = unseal(private_read(archive, MAX_WIRE), private_read(keyfile, 32, 0o400), backup_sha)
    spec = restore_spec(payload, backup_sha, checker.verify(plan, expected), expected)
    raw = encoded(spec)
    publish(destination, raw)
    return {"restore_plan_sha256": digest(raw), "execution_authorized": False, "model_use_approved": False}


def adoption_guard(value, expected):
    path = Path(value["request"]["root"]) / "recovery"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    require(stat.S_ISDIR(info.st_mode) and (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o700), "journal_invalid")
    intent = checker.planner.decode(private_read(path / "intent.json", MAX_JOURNAL, 0o600))
    validate_intent(intent)
    require(intent["target_plan_sha256"] == expected and intent["initialization_id"] == resources.initialization(value)["initialization_id"], "journal_binding")
    require(intent["helper_sha256"] == digest(CODE.encode()), "journal_binding")
    try:
        complete = checker.planner.decode(private_read(path / "complete.json", 16384, 0o600))
    except FileNotFoundError:
        require(False, "pending")
    require(complete == completion(intent), "completion_changed")


def validate_intent(intent):
    require(isinstance(intent, dict) and set(intent) == {"schema", "restore_plan_sha256", "target_plan_sha256", "backup_sha256", "initialization_id", "helper_sha256", "baseline"}
            and intent["schema"] == "private_restore_intent_v1", "journal_invalid")
    require(all(sha(intent[k]) for k in ("restore_plan_sha256", "target_plan_sha256", "backup_sha256", "helper_sha256"))
            and isinstance(intent["initialization_id"], str) and resources.re.fullmatch(r"[0-9a-f]{32}", intent["initialization_id"])
            and isinstance(intent["baseline"], dict) and intent["baseline"].get("empty_application") is True
            and sha(intent["baseline"].get("data_sha256")), "journal_invalid")


def create_journal(installation, intent):
    """Publish the complete initial intent directory in one nonreplacing rename."""
    stage = installation / (".recovery-initial-" + uuid.uuid4().hex)
    stage.mkdir(mode=0o700)
    publish(stage / "intent.json", encoded(intent))
    parent = resources.initializer.trusted_directory(installation)
    try:
        resources.initializer.rename_noreplace(parent, stage.name, "recovery")
        os.fsync(parent)
    finally:
        os.close(parent)


def completion(intent):
    return {"schema": "private_restore_complete_v1", "intent_sha256": digest(encoded(intent)),
            "target_plan_sha256": intent["target_plan_sha256"], "backup_sha256": intent["backup_sha256"],
            "database_and_artifacts_verified": True, "model_use_approved": False,
            "release_qualified": False, "operator_key_custody_qualified": False}


def stage_artifacts(root, values):
    stage = root / "staged-artifacts"
    if stage.exists():
        existing = artifacts(stage)
        require(all(k in values and values[k] == v for k, v in existing.items()), "artifact_stage_changed")
    else:
        stage.mkdir(mode=0o700)
        os.chown(stage, 10001, 10001)
        existing = {}
    for name, value in sorted(values.items()):
        if name in existing:
            continue
        path = stage / name
        current = stage
        for part in name.split("/")[:-1]:
            current = current / part
            if not current.exists():
                current.mkdir(mode=0o700)
                os.chown(current, 10001, 10001)
        temp = root / (".file-" + digest(name.encode()))
        # A private deterministic temporary is owned by this exact pending
        # operation. It never appears inside the published artifact tree.
        if temp.exists() or temp.is_symlink():
            info = temp.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and info.st_uid in {0, 10001} and stat.S_IMODE(info.st_mode) == 0o600, "artifact_stage_changed")
            temp.unlink()
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            os.fchown(stream.fileno(), 10001, 10001)
            stream.write(decoded_data(value))
            stream.flush()
            os.fsync(stream.fileno())
        parent_fd = checker.open_directory(path.parent)
        checker.no_directory_acl(parent_fd)
        temp_fd = resources.initializer.trusted_directory(root)
        try:
            # Atomic cross-directory no-replace rename has no hard-link crash
            # window. A killed writer leaves either a private temporary or one
            # complete staged file, both safely recognized on the next attempt.
            library = ctypes.CDLL(None, use_errno=True)
            rename = library.renameat2
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            require(rename(temp_fd, temp.name.encode(), parent_fd, path.name.encode(), 1) == 0, "artifact_publication_failed")
            os.fsync(parent_fd)
            os.fsync(temp_fd)
        finally:
            os.close(parent_fd)
            os.close(temp_fd)
    require(artifacts(stage) == values, "artifact_stage_changed")
    return stage


def restore(archive, keyfile, plan, expected, request, request_sha):
    raw = private_read(request, 16384, 0o600)
    require(sha(request_sha) and digest(raw) == request_sha, "restore_plan_digest")
    approved = checker.planner.decode(raw)
    require(isinstance(approved, dict) and sha(approved.get("backup_sha256")), "restore_plan_invalid")
    payload = unseal(private_read(archive, MAX_WIRE), private_read(keyfile, 32, 0o400), approved["backup_sha256"])
    value = checker.verify(plan, expected)
    require(approved == restore_spec(payload, approved["backup_sha256"], value, expected), "restore_plan_changed")
    with adopter.managed_operation(value):
        installation = Path(value["request"]["root"])
        root = installation / "recovery"
        initialization = resources.initialization(value)["initialization_id"]
        if root.exists() or root.is_symlink():
            info = root.lstat()
            require(stat.S_ISDIR(info.st_mode) and (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o700), "journal_invalid")
            intent = checker.planner.decode(private_read(root / "intent.json", MAX_JOURNAL, 0o600))
            validate_intent(intent)
            require(intent["restore_plan_sha256"] == request_sha and intent["target_plan_sha256"] == expected
                    and intent["initialization_id"] == initialization and intent["backup_sha256"] == approved["backup_sha256"]
                    and intent["helper_sha256"] == digest(CODE.encode()), "journal_binding")
            if (root / "complete.json").exists():
                adoption_guard(value, expected)
                return {**completion(intent), "reused": True}
        value, receipt, images, schema = context(plan, expected)
        require(schema == payload["schema_sha256"], "schema_binding")
        if not root.exists():
            require(not os.listdir(installation / "artifacts"), "target_artifacts_occupied")
            require(installation.stat().st_dev == (installation / "artifacts").stat().st_dev, "atomic_artifact_volume_required")
            baseline = helper(value, receipt, images["api"], "inspect")
            require(baseline["empty_application"] is True, "target_database_occupied")
            require(baseline["catalog"] == payload["database"]["catalog"], "catalog_binding")
            intent = {"schema": "private_restore_intent_v1", "restore_plan_sha256": request_sha,
                      "target_plan_sha256": expected, "backup_sha256": approved["backup_sha256"],
                      "initialization_id": initialization, "helper_sha256": digest(CODE.encode()), "baseline": baseline}
            create_journal(installation, intent)
        target_files = artifacts(installation / "artifacts")
        require(not target_files or target_files == payload["artifacts"], "target_artifacts_diverged")
        stage = None if target_files == payload["artifacts"] else stage_artifacts(root, payload["artifacts"])
        result = helper(value, receipt, images["api"], "restore", {"source": payload["database"], "baseline": intent["baseline"]})
        require(result["data_sha256"] == payload["database"]["data_sha256"] and result["sequences"] == payload["database"]["sequences"], "restored_database_changed")
        if stage is not None:
            require(not os.listdir(installation / "artifacts"), "target_artifacts_diverged")
            # POSIX rename atomically replaces the existing EMPTY directory.
            # There is no interval with a missing artifact root after a crash.
            os.rename(stage, installation / "artifacts")
            fd = resources.initializer.trusted_directory(installation)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        require(artifacts(installation / "artifacts") == payload["artifacts"], "restored_artifacts_changed")
        schema_init.helper(value, receipt, images["api"], "verify_current", schema)
        complete = completion(intent)
        publish(root / "complete.json", encoded(complete))
        adoption_guard(value, expected)
        return {**complete, "reused": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "plan", "restore"])
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--expected-backup-sha256")
    parser.add_argument("--restore-plan", type=Path)
    parser.add_argument("--expected-restore-plan-sha256")
    args = parser.parse_args()
    if args.action == "backup":
        result = backup(args.plan, args.expected_plan_sha256, args.key_file, args.archive)
    elif args.action == "plan":
        require(args.restore_plan is not None and sha(args.expected_backup_sha256), "plan_arguments")
        result = render(args.archive, args.expected_backup_sha256, args.key_file, args.plan, args.expected_plan_sha256, args.restore_plan)
    else:
        require(args.restore_plan is not None and sha(args.expected_restore_plan_sha256), "restore_arguments")
        result = restore(args.archive, args.key_file, args.plan, args.expected_plan_sha256, args.restore_plan, args.expected_restore_plan_sha256)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (checker.planner.PlanError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("private_installation_recovery_refused", file=sys.stderr)
        raise SystemExit(1)
