#!/usr/bin/env python3
"""Read-only installation-operator queue triage and exclusive evidence export.

Requires Linux root and an independently trusted managed plan digest. Never
repairs services, dispatches/reconciles jobs, or grants review/use authority.
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import stat
import subprocess
import sys
import selectors
import threading
from contextlib import contextmanager
import uuid
from pathlib import Path

import private_installation_adopt as adopter
import private_dependency_start as startup

resources = adopter.resources
checker = adopter.checker
MAX_BYTES = 262144
PROBE_BYTES = 131072
OPERATOR_SCHEMAS = ("native_queue_operator_snapshot_v1", "native_queue_operator_snapshot_v2")
STATE_KEYS = ("Running", "Paused", "Restarting", "Dead", "OOMKilled", "ExitCode", "Pid")


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def decode(raw):
    """Decode one UTF-8 JSON value without ambiguous keys or non-finite numbers."""
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("queue_json_invalid")
            value[key] = item
        return value

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("queue_json_invalid")
        return result

    def constant(_):
        raise ValueError("queue_json_invalid")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_float=number, parse_constant=constant)


def service_observation(info):
    state = info.get("State", {})
    if (not resources.re.fullmatch(r"[0-9a-f]{64}", info.get("Id", ""))
            or not resources.re.fullmatch(r"sha256:[0-9a-f]{64}", info.get("Image", ""))
            or type(info.get("RestartCount")) is not int or info["RestartCount"] < 0
            or any(type(state.get(k)) is not bool for k in STATE_KEYS[:5])
            or any(type(state.get(k)) is not int for k in STATE_KEYS[5:])):
        raise checker.planner.PlanError("queue_incident_service_state_invalid")
    return {"container_id": info["Id"], "image_id": info["Image"], "restart_count": info["RestartCount"],
            "state": {k: state[k] for k in STATE_KEYS},
            "attention_required": not state["Running"] or any(state[k] for k in STATE_KEYS[1:5]) or state["ExitCode"] != 0}


def applications(profile, digest, binding, images):
    found = {}
    for info in adopter.project_containers(profile["name"]):
        role = info.get("Config", {}).get("Labels", {}).get("com.docker.compose.service")
        if role not in adopter.ROLES or role in found:
            raise checker.planner.PlanError("queue_incident_application_conflict")
        adopter.validate_application(info, role, profile["services"][role], profile, digest, binding,
                                     images["ingress" if role == "ingress" else "api"])
        found[role] = service_observation(info)
    return {role: found.get(role, {"status": "missing", "attention_required": True}) for role in sorted(adopter.ROLES)}


def dependencies(value, expected, images):
    _, spec, receipt, _, _, root = startup.prepared_value(value, expected)
    try:
        found = startup.snapshot(value, spec, receipt, images, active=False)
        startup.network(value, receipt, found)
        return {role: service_observation(found[role]) if role in found else {"status": "missing", "attention_required": True}
                for role in sorted(startup.ROLES)}
    finally:
        os.close(root)


@contextmanager
def _probe_capture():
    """Drain a bounded prefix without a file or waiting for inherited writers."""
    output, started = None, False
    finished = threading.Event()
    captured, failed = bytearray(), False

    def collect():
        nonlocal failed
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(read_fd, selectors.EVENT_READ)
                while True:
                    if not finished.is_set() and not selector.select(0.05):
                        continue
                    try:
                        chunk = os.read(read_fd, 8192)
                    except BlockingIOError:
                        if finished.is_set():
                            return
                        continue
                    if not chunk:
                        return
                    captured.extend(chunk[:max(0, PROBE_BYTES + 1 - len(captured))])
                    # Once the producer has returned, drain only immediately
                    # available bytes up to the sentinel. A descendant retaining
                    # stdout must not make cleanup wait for EOF indefinitely.
                    if finished.is_set() and len(captured) > PROBE_BYTES:
                        return
        except BaseException:
            # Worker failures cannot propagate to the caller. Invalidate even
            # a valid prefix; no partial observation can become evidence.
            failed = True
        finally:
            try:
                os.close(read_fd)
            except OSError:
                failed = True

    read_fd, write_fd = os.pipe()
    try:
        output = os.fdopen(write_fd, "wb")
        os.set_blocking(read_fd, False)
        worker = threading.Thread(target=collect, name="declarai-operator-probe-reader")
        try:
            worker.start()
        except RuntimeError:
            raise OSError("probe_capture_unavailable") from None
        started = True
        yield output, captured
    finally:
        try:
            if output is None:
                os.close(write_fd)
            else:
                output.close()
        finally:
            finished.set()
            if started:
                worker.join()
            else:
                os.close(read_fd)
    if failed:
        raise OSError("probe_capture_unavailable")


def probe(api):
    if api.get("status") == "missing" or api["attention_required"]:
        return {"status": "unavailable", "reason": "api_not_active"}
    # No caller-controlled command, code, environment, mount, user or input.
    # Keep at most 128 KiB plus one over-budget sentinel in memory. The
    # collector drains excess stdout while the original 20s timeout applies;
    # neither stdout nor discarded stderr is persisted to temporary storage.
    try:
        with _probe_capture() as (output, captured):
            result = subprocess.run([*resources.PREFIX, "exec", "--user", "10001:10001", api["container_id"],
                                     "python", "-m", "execution_jobs.operator_triage"],
                                    stdout=output, stderr=subprocess.DEVNULL, timeout=20, check=False)
        raw = bytes(captured)
    except (subprocess.TimeoutExpired, OSError):
        return {"status": "unavailable", "reason": "probe_transport_unavailable"}
    if result.returncode != 0:
        return {"status": "unavailable", "reason": "probe_unavailable"}
    try:
        if len(raw) > PROBE_BYTES:
            raise ValueError
        value = decode(raw)
        if not isinstance(value, dict) or value.get("schema") not in OPERATOR_SCHEMAS or value.get("status") not in ("observed", "unavailable"):
            raise ValueError
    except (ValueError, UnicodeError, RecursionError):
        raise checker.planner.PlanError("queue_incident_probe_output_invalid") from None
    return value


def observe(plan, expected):
    value = checker.verify(plan, expected)
    if value["manifest"]["schema"] != checker.planner.PLAN_SCHEMA or sys.platform != "linux" or os.geteuid() != 0:
        raise checker.planner.PlanError("queue_incident_managed_linux_root_required")
    initialized = resources.initialization(value)
    if initialized["plan_manifest_sha256"] != expected:
        raise checker.planner.PlanError("queue_incident_initialization_mismatch")
    checker.check_paths(plan, expected)
    with adopter.managed_operation(value, create_lock=False) as serialized:
        if serialized is not True:
            raise checker.planner.PlanError("queue_incident_managed_lock_required")
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        resources.docker_host(value["manifest"]["architecture"])
        if resources.record(["info", "--format", "{{json .}}"]).get("DefaultRuntime") != "runc":
            raise checker.planner.PlanError("queue_incident_default_runtime_required")
        images = {role: resources.inspect("image", identity) for role, identity in value["images"].items()}
        if any(image.get("Id") != value["images"][role] or image.get("Os") != "linux" or image.get("Architecture") != value["manifest"]["architecture"] for role, image in images.items()):
            raise checker.planner.PlanError("queue_incident_native_images_required")
        profile, digest, binding = adopter.application_profile(value, expected, initialized["initialization_id"])
        before = applications(profile, digest, binding, images)
        dependency_before = dependencies(value, expected, images)
        queue = probe(before["api"])
        after = applications(profile, digest, binding, images)
        dependency_after = dependencies(value, expected, images)
        report = {**checker.receipt(value, expected), "schema": "private_queue_incident_evidence_v1", "read_only": True,
                  "authority": "linux_root_with_trusted_installation_plan", "initialization_id": initialized["initialization_id"],
                  "application_profile_sha256": digest, "observation_started_at": started,
                  "observation_finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "managed_operation_serialized": True, "services_before": before, "services_after": after,
                  "dependencies_before": dependency_before, "dependencies_after": dependency_after,
                  "stable_service_observations": before == after and dependency_before == dependency_after, "queue": queue,
                  "dependency_health": "not_tested", "https_health": "not_tested",
                  "recovery_authorized": False, "review_approved": False, "production_use_approved": False,
                  "limitations": ["Point-in-time metadata; service state may change immediately. Changed before/after observations are disclosed, not treated as stable.",
                                  "The cooperative lock does not stop workers or direct host actions. Database counts and rows share one read-only repeatable-read snapshot.",
                                  "At most 50 newest matching incidents; counts overlap and historical failures need not indicate a current outage.",
                                  "No raw logs, credentials, names, model state, event payloads, protected inputs or outcomes are exported. Project/dataset/job identifiers are installation-confidential.",
                                  "Unavailable observation is not an empty or healthy queue. No dependency delivery, backup, restore, upgrade, scientific or production qualification.",
                                  "Retain this file and its externally recorded SHA-256. A checksum detects changes against a trusted digest; it is not a signature or approval."]}
        raw = encode(report)
        if len(raw) > MAX_BYTES:
            raise checker.planner.PlanError("queue_incident_evidence_budget")
        return {"evidence": report, "sha256": hashlib.sha256(raw).hexdigest()}


def export(value, output):
    if not output.is_absolute() or output.name in {"", ".", ".."}:
        raise checker.planner.PlanError("queue_incident_absolute_output_required")
    raw = encode(value["evidence"])
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != value["sha256"]:
        raise checker.planner.PlanError("queue_incident_evidence_digest_mismatch")
    parent = resources.initializer.trusted_directory(output.parent)
    stage = ".queue-evidence-" + uuid.uuid4().hex
    try:
        info = os.fstat(parent)
        if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
            raise checker.planner.PlanError("queue_incident_private_output_directory_required")
        fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encode(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Existing targets (including symlinks) are never replaced. No partial
        # evidence is published if collection, validation or writing fails.
        resources.initializer.rename_noreplace(parent, stage, output.name)
        os.fsync(parent)
    finally:
        try:
            os.unlink(stage, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = observe(args.plan, args.expected_plan_sha256)
    export(value, args.output)
    print(json.dumps({"schema": "private_queue_incident_export_v1", "sha256": value["sha256"],
                      "exported": True, "recovery_authorized": False}))


if __name__ == "__main__":
    try:
        main()
    except (checker.planner.PlanError, OSError, ValueError, TypeError):
        print("queue_incident_collection_or_export_failed", file=sys.stderr)
        sys.exit(1)
