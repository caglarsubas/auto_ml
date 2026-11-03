#!/usr/bin/env python3
"""Reviewed staged, data-preserving image/schema upgrade and compatible rollback."""

import argparse
import copy
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import private_installation_recovery as recovery
from private_upgrade_runtime import DESCRIBE_CODE, MIGRATE_CODE

resources, checker, startup, adopter = (
    recovery.resources,
    recovery.checker,
    recovery.startup,
    recovery.adopter,
)
LIMITS = {
    "cpus": 1,
    "memory_bytes": 1024**3,
    "pids": 64,
    "seconds": 120,
    "data_bytes": recovery.MAX_DATA,
}
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")


def require(value, code):
    if not value:
        raise checker.planner.PlanError("upgrade_" + code)


def controller_sha():
    return recovery.digest(
        Path(__file__).read_bytes()
        + DESCRIBE_CODE.encode()
        + MIGRATE_CODE.encode()
        + recovery.CODE.encode()
        + recovery.schema_init.SCHEMA_CODE.encode()
    )


def execute(value, receipt, image, code, payload, offline=False):
    """No caller Python, writable host mounts, network egress or host modules."""
    identifier = None
    role = "upgrade-inspection" if offline else "upgrade-migration"
    labels = (
        {"org.declarai.upgrade.inspection": uuid.uuid4().hex}
        if offline
        else {**startup.labels(value, receipt), resources.LABEL + "role": role}
    )
    env = (
        {
            "PROMETA_DISABLE": "1",
            "DECLARAI_RUNTIME_PROFILE": "development",
            "DECLARAI_DB_ENGINE": "sqlite",
            "DJANGO_DEBUG": "false",
        }
        if offline
        else {
            **checker.planner.composition(value["request"], value["images"])[
                "services"
            ]["api"]["environment"],
            "DECLARAI_MEDIA_ROOT": "/tmp/recovery-media",
        }
    )
    network = "none" if offline else value["prerequisites"]["networks"][0]["name"]
    args = [
        "container",
        "create",
        "--name",
        "declarai-upgrade-" + uuid.uuid4().hex,
        "--pull",
        "never",
        "-i",
        "--network",
        network,
        "--read-only",
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--cpus",
        "1",
        "--memory",
        "1g",
        "--pids-limit",
        "64",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=134217728,uid=10001,gid=10001,mode=700",
        "--entrypoint",
        "python",
    ]
    for k, v in labels.items():
        args += ["--label", k + "=" + v]
    for k, v in env.items():
        args += ["--env", k + "=" + v]
    if not offline:
        args += [
            "--mount",
            "type=bind,src="
            + value["request"]["root"]
            + "/secrets/app,dst=/installation,readonly",
        ]
    try:
        identifier = (
            resources.command([*args, image["Id"], "-I", "-c", code]).decode().strip()
        )
        require(re.fullmatch(r"[0-9a-f]{64}", identifier), "helper_identity")
        info = resources.inspect("container", identifier)
        if offline:
            config, host = info["Config"], info["HostConfig"]
            require(
                info["Image"] == image["Id"]
                and config["Labels"] == labels
                and config["User"] == "10001:10001"
                and config["WorkingDir"] == image["Config"].get("WorkingDir")
                and config.get("Healthcheck") == image["Config"].get("Healthcheck")
                and adopter.parsed_environment(config.get("Env"))
                == {
                    **adopter.parsed_environment(image["Config"].get("Env") or []),
                    **env,
                }
                and config["Entrypoint"] == ["python"]
                and config["Cmd"] == ["-I", "-c", code]
                and host["NetworkMode"] == "none"
                and host["ReadonlyRootfs"] is True
                and host["Privileged"] is False
                and host["CapDrop"] == ["ALL"]
                and not host.get("CapAdd")
                and host["SecurityOpt"] == ["no-new-privileges:true"]
                and host["PidsLimit"] == 64
                and host["NanoCpus"] == 1_000_000_000
                and host["Memory"] == 1024**3
                and not host.get("Binds")
                and not host.get("Mounts")
                and not host.get("VolumesFrom")
                and not host.get("PortBindings")
                and host.get("Runtime") == "runc"
                and host.get("IpcMode") == "private"
                and all(
                    host.get(k) in (None, "")
                    for k in ("PidMode", "UTSMode", "UsernsMode")
                )
                and all(
                    host.get(k) in (None, [])
                    for k in (
                        "GroupAdd",
                        "ExtraHosts",
                        "Links",
                        "Dns",
                        "DnsOptions",
                        "DnsSearch",
                    )
                )
                and host.get("Sysctls") in (None, {})
                and host.get("Tmpfs")
                == {
                    "/tmp": "rw,noexec,nosuid,size=134217728,uid=10001,gid=10001,mode=700"
                }
                and set(info.get("NetworkSettings", {}).get("Networks", {})) == {"none"}
                and not host.get("Devices")
                and not host.get("DeviceRequests")
                and all(
                    m["Type"] == "tmpfs" and m["Destination"] == "/tmp"
                    for m in info.get("Mounts", [])
                ),
                "inspection_profile",
            )
        else:
            adopter.validate_preflight(
                info,
                value,
                env,
                {k: v for k, v in labels.items() if k != resources.LABEL + "role"},
                image,
                role=role,
                entrypoint=["python"],
                command=["-I", "-c", code],
                mount_sources={
                    "/installation": value["request"]["root"] + "/secrets/app"
                },
            )
        require(info["Config"].get("OpenStdin") is True, "helper_stdin")
        result = subprocess.run(
            [
                *resources.PREFIX,
                "container",
                "start",
                "--attach",
                "--interactive",
                identifier,
            ],
            input=recovery.encoded(payload),
            capture_output=True,
            timeout=LIMITS["seconds"],
            check=False,
        )
        state = resources.inspect("container", identifier)["State"]
        require(
            result.returncode == 0
            and not state["Running"]
            and state["ExitCode"] == 0
            and len(result.stdout) <= 2_000_000,
            "helper_failed",
        )
        return checker.planner.decode(result.stdout)
    finally:
        if identifier:
            require(
                resources.inspect("container", identifier)["Config"].get("Labels")
                == labels,
                "helper_cleanup_owner",
            )
            resources.command(["container", "rm", "--force", identifier])


def inspect_image(image_id):
    import private_api_package as package

    image = package.inspect_image(image_id)
    require(image["Id"] == image_id and image["Os"] == "linux", "image_identity")
    package.native_manifest(image_id)
    result = execute(None, None, image, DESCRIBE_CODE, {}, offline=True)
    require(
        result.get("schema") == "private_upgrade_image_v1"
        and result.get("database_access") is False,
        "inspection_result",
    )
    return result


def nodes(description):
    return {(row["app"], row["name"]): row for row in description["graph"]["vertices"]}


def compatibility(source, target):
    require(
        source["runtime"] == target["runtime"]
        and source["requirements_sha256"] == target["requirements_sha256"],
        "runtime_incompatible",
    )
    # A physical-index release cannot change scientific/API/authority code or
    # earlier migrations, and cannot add arbitrary runtime files.
    old, new = nodes(source), nodes(target)
    require(set(old) < set(new) or set(new) < set(old), "graph_incompatible")
    large, small = (target, source) if set(old) < set(new) else (source, target)
    common = set(old) & set(new)
    require(
        all(
            old[k] == new[k]
            and source["migrations"]["/".join(k)]["file_sha256"]
            == target["migrations"]["/".join(k)]["file_sha256"]
            for k in common
        ),
        "migration_history_changed",
    )
    delta = set(nodes(large)) - set(nodes(small))
    paths = {"backend/" + app + "/migrations/" + name + ".py" for app, name in delta}
    require(
        {k: v for k, v in source["files"].items() if k not in paths}
        == {k: v for k, v in target["files"].items() if k not in paths},
        "application_code_incompatible",
    )
    indexes = []
    for key in sorted(delta):
        op = large["migrations"]["/".join(key)]
        require(
            op["index_only"] is True and op["indexes"],
            "migration_operation_incompatible",
        )
        for item in op["indexes"]:
            require(
                set(item) == {"table", "name", "fields"}
                and IDENTIFIER.fullmatch(item["table"])
                and IDENTIFIER.fullmatch(item["name"])
                and item["fields"]
                and all(
                    isinstance(f, str) and IDENTIFIER.fullmatch(f.lstrip("-"))
                    for f in item["fields"]
                ),
                "index_specification",
            )
            indexes.append(item)
    require(len({i["name"] for i in indexes}) == len(indexes), "index_duplicate")
    return {
        "direction": "upgrade" if set(old) < set(new) else "rollback",
        "indexes": indexes,
        "source_nodes": [list(k) for k in sorted(old)],
        "target_nodes": [list(k) for k in sorted(new)],
    }


def data_identity(database):
    return {
        k: {f: row[f] for f in ("sha256", "bytes", "rows")}
        for k, row in database["tables"].items()
        if k != "django_migrations"
    }


def sequence_identity(database):
    return {
        k: v
        for k, v in database["sequences"].items()
        if k != "django_migrations_id_seq"
    }


def verify_catalog(before, after, transition):
    left, right = copy.deepcopy(before), copy.deepcopy(after)
    larger = right if transition["direction"] == "upgrade" else left
    smaller = left if transition["direction"] == "upgrade" else right
    for index in transition["indexes"]:
        table, name = index["table"], index["name"]
        require(
            table in larger["tables"] and table in smaller["tables"], "catalog_table"
        )
        found = [row for row in larger["tables"][table]["indexes"] if row[0] == name]
        columns = ", ".join(
            f.lstrip("-") + (" DESC" if f.startswith("-") else "")
            for f in index["fields"]
        )
        expected = [
            name,
            False,
            True,
            True,
            False,
            True,
            f"CREATE INDEX {name} ON public.{table} USING btree ({columns})",
        ]
        require(
            found == [expected]
            and not any(row[0] == name for row in smaller["tables"][table]["indexes"]),
            "catalog_index",
        )
        larger["tables"][table]["indexes"].remove(found[0])
    require(left == right, "catalog_incompatible")


def render(
    archive,
    archive_sha,
    keyfile,
    source_plan,
    source_sha,
    target_plan,
    target_sha,
    destination,
):
    source_value, target = (
        checker.verify(source_plan, source_sha),
        checker.verify(target_plan, target_sha),
    )
    payload = recovery.unseal(
        recovery.private_read(archive, recovery.MAX_WIRE),
        recovery.private_read(keyfile, 32, 0o400),
        archive_sha,
    )
    require(
        payload["source_plan_sha256"] == source_sha
        and payload["images"] == source_value["images"]
        and payload["helper_sha256"] == recovery.digest(recovery.CODE.encode()),
        "source_backup_binding",
    )
    require(
        source_value["request"]["root"] != target["request"]["root"]
        and source_value["request"]["installation_id"]
        != target["request"]["installation_id"],
        "separate_target_required",
    )
    require(
        all(
            source_value["images"][k] == target["images"][k]
            for k in ("postgres", "redis", "ingress")
        )
        and source_value["images"]["api"] != target["images"]["api"]
        and source_value["manifest"]["architecture"]
        == target["manifest"]["architecture"],
        "dependency_images_incompatible",
    )
    old, new = (
        inspect_image(source_value["images"]["api"]),
        inspect_image(target["images"]["api"]),
    )
    require(old["schema_sha256"] == payload["schema_sha256"], "source_schema_binding")
    change = compatibility(old, new)
    runner = (
        target["images"]["api"]
        if change["direction"] == "upgrade"
        else source_value["images"]["api"]
    )
    spec = {
        "schema": "private_upgrade_plan_v1",
        "backup_sha256": archive_sha,
        "source_plan_sha256": source_sha,
        "target_plan_sha256": target_sha,
        "source_images": source_value["images"],
        "target_images": target["images"],
        "source_root": source_value["request"]["root"],
        "target_root": target["request"]["root"],
        "source_schema_sha256": old["schema_sha256"],
        "target_schema_sha256": new["schema_sha256"],
        "source_description": old,
        "target_description": new,
        "transition": change,
        "runner_image": runner,
        "controller_sha256": controller_sha(),
        "limits": LIMITS,
        "chosen_authority_point": "current_quiescent_backup",
        "model_use_approved": False,
        "release_qualified": False,
    }
    raw = recovery.encoded(spec)
    recovery.publish(destination, raw)
    return {
        "plan_sha256": recovery.digest(raw),
        "direction": change["direction"],
        "execution_authorized": False,
    }


def context(plan, expected):
    require(sys.platform == "linux" and os.geteuid() == 0, "linux_root_required")
    value, spec, receipt, _, _, root = startup.prepared(plan, expected)
    os.close(root)
    resources.docker_host(value["manifest"]["architecture"])
    require(
        resources.record(["info", "--format", "{{json .}}"]).get("DefaultRuntime")
        == "runc",
        "runtime_required",
    )
    images = {k: resources.inspect("image", v) for k, v in value["images"].items()}
    deps = startup.snapshot(value, spec, receipt, images, True)
    startup.network(value, receipt, deps)
    require(
        not adopter.project_containers(
            checker.planner.composition(value["request"], value["images"])["name"]
        ),
        "applications_present",
    )
    return value, receipt, images


def image_value(value, image):
    result = copy.deepcopy(value)
    result["images"]["api"] = image
    return result


def complete(intent):
    return {
        "schema": "private_upgrade_complete_v1",
        "intent_sha256": recovery.digest(recovery.encoded(intent)),
        "target_plan_sha256": intent["target_plan_sha256"],
        "controller_sha256": intent["controller_sha256"],
        "data_artifacts_and_schema_verified": True,
        "model_use_approved": False,
        "release_qualified": False,
    }


def read_intent(value, expected):
    root = Path(value["request"]["root"]) / "transition"
    info = root.lstat()
    require(
        stat.S_ISDIR(info.st_mode)
        and (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o700),
        "journal_invalid",
    )
    intent = checker.planner.decode(
        recovery.private_read(root / "intent.json", recovery.MAX_JOURNAL, 0o600)
    )
    require(
        set(intent)
        == {
            "schema",
            "plan_sha256",
            "target_plan_sha256",
            "initialization_id",
            "controller_sha256",
        }
        and intent["schema"] == "private_upgrade_intent_v1"
        and recovery.sha(intent["plan_sha256"])
        and intent["target_plan_sha256"] == expected
        and intent["controller_sha256"] == controller_sha()
        and intent["initialization_id"]
        == resources.initialization(value)["initialization_id"],
        "journal_binding",
    )
    return intent


def adoption_guard(value, expected):
    root = Path(value["request"]["root"]) / "transition"
    if not root.exists() and not root.is_symlink():
        return
    intent = read_intent(value, expected)
    try:
        result = checker.planner.decode(
            recovery.private_read(root / "complete.json", 16384, 0o600)
        )
    except FileNotFoundError:
        require(False, "pending")
    require(result == complete(intent), "completion_changed")


def apply(archive, keyfile, target_plan, target_sha, request, request_sha):
    raw = recovery.private_read(request, recovery.MAX_JOURNAL, 0o600)
    require(
        recovery.sha(request_sha) and recovery.digest(raw) == request_sha, "plan_digest"
    )
    approved = checker.planner.decode(raw)
    value = checker.verify(target_plan, target_sha)
    fields = {
        "schema",
        "backup_sha256",
        "source_plan_sha256",
        "target_plan_sha256",
        "source_images",
        "target_images",
        "source_root",
        "target_root",
        "source_schema_sha256",
        "target_schema_sha256",
        "source_description",
        "target_description",
        "transition",
        "runner_image",
        "controller_sha256",
        "limits",
        "chosen_authority_point",
        "model_use_approved",
        "release_qualified",
    }
    require(isinstance(approved, dict) and set(approved) == fields, "plan_shape")
    require(
        approved["schema"] == "private_upgrade_plan_v1"
        and approved["target_plan_sha256"] == target_sha
        and approved["target_images"] == value["images"]
        and approved["target_root"] == value["request"]["root"]
        and approved["controller_sha256"] == controller_sha()
        and approved["limits"] == LIMITS
        and approved["model_use_approved"] is approved["release_qualified"] is False
        and approved["chosen_authority_point"] == "current_quiescent_backup"
        and approved["source_root"] != approved["target_root"]
        and all(
            approved["source_images"][k] == value["images"][k]
            for k in ("postgres", "redis", "ingress")
        )
        and approved["source_images"]["api"] != value["images"]["api"],
        "plan_changed",
    )
    payload = recovery.unseal(
        recovery.private_read(archive, recovery.MAX_WIRE),
        recovery.private_read(keyfile, 32, 0o400),
        approved["backup_sha256"],
    )
    require(
        payload["images"] == approved["source_images"]
        and payload["source_plan_sha256"] == approved["source_plan_sha256"]
        and payload["schema_sha256"] == approved["source_schema_sha256"]
        and payload["helper_sha256"] == recovery.digest(recovery.CODE.encode()),
        "backup_binding",
    )
    require(
        inspect_image(approved["source_images"]["api"])
        == approved["source_description"]
        and inspect_image(value["images"]["api"]) == approved["target_description"],
        "images_changed",
    )
    require(
        approved["source_schema_sha256"]
        == approved["source_description"]["schema_sha256"]
        and approved["target_schema_sha256"]
        == approved["target_description"]["schema_sha256"],
        "schema_changed",
    )
    change = compatibility(
        approved["source_description"], approved["target_description"]
    )
    require(
        change == approved["transition"]
        and approved["runner_image"]
        == (
            value["images"]["api"]
            if change["direction"] == "upgrade"
            else approved["source_images"]["api"]
        ),
        "transition_changed",
    )
    with adopter.managed_operation(value):
        root = Path(value["request"]["root"]) / "transition"
        if root.exists() or root.is_symlink():
            intent = read_intent(value, target_sha)
            require(intent["plan_sha256"] == request_sha, "journal_binding")
            if (root / "complete.json").exists():
                adoption_guard(value, target_sha)
                return {
                    **complete(intent),
                    "direction": change["direction"],
                    "reused": True,
                }
        value, receipt, images = context(target_plan, target_sha)
        source = image_value(value, approved["source_images"]["api"])
        source_image = resources.inspect("image", source["images"]["api"])
        if not root.exists():
            description = recovery.schema_init.helper(
                source, receipt, source_image, "describe"
            )
            require(
                description["state"] == "fresh"
                and not os.listdir(Path(value["request"]["root"]) / "artifacts"),
                "target_occupied",
            )
            require(
                root.parent.stat().st_dev == (root.parent / "artifacts").stat().st_dev,
                "atomic_artifact_volume_required",
            )
            intent = {
                "schema": "private_upgrade_intent_v1",
                "plan_sha256": request_sha,
                "target_plan_sha256": target_sha,
                "initialization_id": resources.initialization(value)[
                    "initialization_id"
                ],
                "controller_sha256": controller_sha(),
            }
            stage = root.parent / (".transition-" + uuid.uuid4().hex)
            stage.mkdir(mode=0o700)
            recovery.publish(stage / "intent.json", recovery.encoded(intent))
            fd = resources.initializer.trusted_directory(root.parent)
            try:
                resources.initializer.rename_noreplace(fd, stage.name, root.name)
                os.fsync(fd)
            finally:
                os.close(fd)
        description = recovery.schema_init.helper(
            source, receipt, source_image, "describe"
        )
        if description["state"] == "fresh":
            recovery.schema_init.helper(
                source,
                receipt,
                source_image,
                "apply_fresh",
                approved["source_schema_sha256"],
            )
            description = recovery.schema_init.helper(
                source, receipt, source_image, "describe"
            )
        baseline_file = root / "baseline.json"
        if not baseline_file.exists():
            require(description["state"] == "current", "source_schema_incompatible")
            baseline = recovery.helper(source, receipt, source_image, "inspect")
            require(
                baseline["empty_application"]
                and baseline["catalog"] == payload["database"]["catalog"],
                "target_occupied",
            )
            recovery.publish(baseline_file, recovery.encoded(baseline))
        baseline = checker.planner.decode(
            recovery.private_read(baseline_file, recovery.MAX_JOURNAL, 0o600)
        )
        current_files = recovery.artifacts(root.parent / "artifacts")
        require(
            not current_files or current_files == payload["artifacts"],
            "artifacts_diverged",
        )
        staged = (
            None
            if current_files == payload["artifacts"]
            else recovery.stage_artifacts(root, payload["artifacts"])
        )
        if description["state"] == "current":
            recovery.helper(
                source,
                receipt,
                source_image,
                "restore",
                {"source": payload["database"], "baseline": baseline},
            )
        runner = image_value(value, approved["runner_image"])
        result = execute(
            runner,
            receipt,
            resources.inspect("image", approved["runner_image"]),
            MIGRATE_CODE,
            {
                "action": "inspect",
                "payload": {
                    "source_nodes": change["source_nodes"],
                    "target_nodes": change["target_nodes"],
                    "targets": approved["target_description"]["graph"]["targets"],
                    "data": data_identity(payload["database"]),
                    "sequences": sequence_identity(payload["database"]),
                },
            },
        )
        require(
            result.get("schema") == "private_upgrade_migration_v1"
            and result.get("application_role_elevated") is False
            and result.get("data_and_sequences_preserved") is True,
            "migration_result",
        )
        after = recovery.helper(value, receipt, images["api"], "inspect")
        require(
            data_identity(after) == data_identity(payload["database"])
            and sequence_identity(after) == sequence_identity(payload["database"]),
            "data_changed",
        )
        verify_catalog(payload["database"]["catalog"], after["catalog"], change)
        if staged is not None:
            require(not os.listdir(root.parent / "artifacts"), "artifacts_diverged")
            os.rename(staged, root.parent / "artifacts")
            fd = resources.initializer.trusted_directory(root.parent)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        require(
            recovery.artifacts(root.parent / "artifacts") == payload["artifacts"],
            "artifacts_changed",
        )
        recovery.schema_init.helper(
            value,
            receipt,
            images["api"],
            "verify_current",
            approved["target_schema_sha256"],
        )
        recovery.publish(root / "complete.json", recovery.encoded(complete(intent)))
        adoption_guard(value, target_sha)
        return {**complete(intent), "direction": change["direction"], "reused": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "apply"])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--target-plan", type=Path, required=True)
    parser.add_argument("--expected-target-sha256", required=True)
    parser.add_argument("--transition-plan", type=Path, required=True)
    parser.add_argument("--source-plan", type=Path)
    parser.add_argument("--expected-source-sha256")
    parser.add_argument("--expected-backup-sha256")
    parser.add_argument("--expected-transition-sha256")
    v = parser.parse_args()
    if v.action == "plan":
        require(
            v.source_plan is not None
            and recovery.sha(v.expected_source_sha256)
            and recovery.sha(v.expected_backup_sha256),
            "arguments",
        )
        result = render(
            v.archive,
            v.expected_backup_sha256,
            v.key_file,
            v.source_plan,
            v.expected_source_sha256,
            v.target_plan,
            v.expected_target_sha256,
            v.transition_plan,
        )
    else:
        result = apply(
            v.archive,
            v.key_file,
            v.target_plan,
            v.expected_target_sha256,
            v.transition_plan,
            v.expected_transition_sha256,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (
        checker.planner.PlanError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ):
        print("private_installation_upgrade_refused", file=sys.stderr)
        raise SystemExit(1)
