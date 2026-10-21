"""Offline evidence integrity/context/limits and private operator handoff."""

import copy
import datetime as dt
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
module = importlib.import_module("private_queue_evidence")
NOW = dt.datetime(2026, 10, 21, 9, tzinfo=dt.timezone.utc)
STAMP = NOW.isoformat()


def sample():
    state = dict(Running=True, Paused=False, Restarting=False, Dead=False, OOMKilled=False, ExitCode=0, Pid=1)
    service = dict(container_id="a" * 64, image_id="sha256:" + "b" * 64, restart_count=0, state=state, attention_required=False)
    value = dict(schema="private_queue_incident_evidence_v1", plan_manifest_sha256="c" * 64,
                 installation_id="test-installation", architecture="amd64", plan_verified=True, archives_reverified=False,
                 installation_qualified=False, release_qualified=False, expert_isolation_qualified=False, read_only=True,
                 authority="linux_root_with_trusted_installation_plan", initialization_id="d" * 32,
                 application_profile_sha256="e" * 64, observation_started_at=STAMP, observation_finished_at=STAMP,
                 managed_operation_serialized=True, stable_service_observations=True, dependency_health="not_tested",
                 https_health="not_tested", recovery_authorized=False, review_approved=False, production_use_approved=False,
                 limitations=["fixture limitation"] * 6)
    for group, roles in [("services_before", {"api", "worker", "dispatcher", "ingress"}),
                         ("dependencies_before", {"postgres", "cache", "job-broker"})]:
        value[group] = {role: copy.deepcopy(service) for role in roles}
        value[group.replace("before", "after")] = copy.deepcopy(value[group])
    value["queue"] = dict(schema="native_queue_operator_snapshot_v1", status="observed", observed_at=STAMP,
                          scope="trusted_installation_all_projects", read_only_transaction=True, repeatable_read=True,
                          statement_timeout_ms=5000, jobs_enabled=True, states={s: 0 for s in module.STATES | {"unknown"}},
                          signals={s: 0 for s in module.SIGNALS}, incident_total=0, attempt_limit=2, rows=[], row_limit=50,
                          truncated=False, selection="fixture selection", guidance={s: "fixture guidance" for s in module.SIGNALS},
                          live_service_health="not_tested", recovery_authorized=False)
    return value


def wrapped(value):
    sha = hashlib.sha256(module.triage.encode(value)).hexdigest()
    return module.triage.encode(dict(evidence=value, sha256=sha)), sha


def verify(value, **overrides):
    raw, sha = wrapped(value)
    args = dict(expected_sha256=sha, expected_plan_sha256="c" * 64, installation_id="test-installation",
                initialization_id="d" * 32, now=NOW)
    args.update(overrides)
    return module.verify(raw, **args)


def test_offline_verification_and_fixed_handoff_do_not_touch_runtime(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("live observation forbidden")

    for name in ("observe", "probe", "applications", "dependencies"):
        monkeypatch.setattr(module.triage, name, forbidden)
    for name in ("command", "record", "inspect", "initialization"):
        monkeypatch.setattr(module.triage.resources, name, forbidden)
    value = sample()
    value["queue"]["guidance"]["failed"] = "untrusted instructions never copied"
    evidence, verification = verify(value)
    result = module.handoff(evidence, verification, wrapped(value)[1])
    handoff = result["evidence"]
    assert result["sha256"] == hashlib.sha256(module.triage.encode(handoff)).hexdigest()
    assert handoff["schema"] == "private_queue_operator_handoff_v1" and handoff["job_references"] == []
    assert all(handoff[k] is False for k in ("checksum_is_signature", "current_health_qualified", "recovery_authorized", "review_approved", "production_use_approved", "release_qualified"))
    assert "untrusted instructions" not in json.dumps(handoff)
    assert {s["id"] for s in handoff["investigation_steps"]} == {"retain", "age", "authority", "protected"}


@pytest.mark.parametrize("field,value", [("expected_sha256", "f" * 64), ("expected_plan_sha256", "f" * 64),
                                         ("installation_id", "other"), ("initialization_id", "f" * 32)])
def test_independent_trust_pins_cannot_be_replaced_by_embedded_values(field, value):
    with pytest.raises(ValueError):
        verify(sample(), **{field: value})


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(extra="unknown"),
    lambda v: v.update(recovery_authorized=True),
    lambda v: v.update(installation_qualified=True),
    lambda v: v.update(observation_started_at="2026-10-22T09:00:00+00:00"),
    lambda v: v.update(observation_finished_at="2026-10-21T09:01:00+00:00"),
    lambda v: v.update(observation_finished_at="2026-10-21T09:00:00"),
    lambda v: v["services_after"].update(api=None),
    lambda v: v["services_after"]["api"].update(attention_required=True),
    lambda v: v["dependencies_before"].pop("postgres"),
    lambda v: v["queue"].update(rows=[{}]),
    lambda v: v["queue"]["states"].update(queued=True),
    lambda v: v["queue"].update(incident_total=1),
    lambda v: v["queue"].update(truncated=True),
    lambda v: v["queue"].update(read_only_transaction=False),
    lambda v: v["queue"].update(statement_timeout_ms=5000.0),
    lambda v: v["queue"].update(status="healthy"),
])
def test_even_self_consistent_digest_cannot_bypass_schema_or_authority(mutation):
    value = sample()
    mutation(value)
    with pytest.raises((ValueError, TypeError)):
        verify(value)


@pytest.mark.parametrize("raw", [b'{"evidence":{},"evidence":{},"sha256":"x"}', b'{"evidence":{"x":NaN},"sha256":"x"}',
                                  b'\xff', b'[' * 2000, b' ' * (module.MAX_FILE_BYTES + 1)])
def test_duplicate_nonfinite_invalid_utf8_depth_and_size_fail_closed(raw):
    with pytest.raises((ValueError, RecursionError)):
        module.verify(raw, expected_sha256="a" * 64, expected_plan_sha256="c" * 64,
                      installation_id="test-installation", initialization_id="d" * 32)


def test_modified_evidence_fails_against_original_digest():
    value = sample()
    _, trusted = wrapped(value)
    value["queue"]["jobs_enabled"] = False
    with pytest.raises(ValueError):
        verify(value, expected_sha256=trusted)


def test_stale_unavailable_degraded_unstable_facts_remain_explicit():
    value = sample()
    value["queue"] = dict(status="unavailable", reason="api_not_active")
    value["services_after"]["api"] = dict(status="missing", attention_required=True)
    value["stable_service_observations"] = False
    evidence, verification = verify(value, now=NOW + dt.timedelta(hours=1), max_age_seconds=300)
    handoff = module.handoff(evidence, verification, wrapped(value)[1])["evidence"]
    assert verification["older_than_selected_age"] and verification["age_seconds"] == 3600
    assert handoff["queue_status"] == "unavailable" and handoff["incident_total"] is None and handoff["signals"] is None
    assert handoff["truncated"] is None and handoff["service_attention"] == ["services_after/api"]
    assert {"queue_unavailable", "incomplete", "service_attention"} <= {s["id"] for s in handoff["investigation_steps"]}


def test_truncated_incident_references_remain_bounded_and_revision_pinned():
    value = sample()
    q = value["queue"]
    q.update(incident_total=51, truncated=True)
    q["signals"]["failed"] = q["states"]["failed"] = 51
    q["rows"] = [dict(job_id=f"00000000-0000-0000-0000-{i:012x}", project_id="11111111-1111-1111-1111-111111111111",
                      dataset_id=1, revision=4, state="failed", attempts=1, kind="unsupported", created_at=STAMP,
                      expires_at=STAMP, lease_until=None, signals=["failed"]) for i in range(50)]
    evidence, verification = verify(value)
    result = module.handoff(evidence, verification, wrapped(value)[1])["evidence"]
    assert result["truncated"] and len(result["job_references"]) == 50
    assert all(r["revision"] == 4 and r["signals"] == ["failed"] for r in result["job_references"])
    assert {"incomplete", "queue_signals"} <= {s["id"] for s in result["investigation_steps"]}


@pytest.fixture
def private_file(tmp_path, monkeypatch):
    path = tmp_path / "source.json"
    path.write_bytes(wrapped(sample())[0])
    path.chmod(0o600)
    monkeypatch.setattr(module.triage.resources.initializer, "trusted_directory", lambda p: os.open(p, os.O_RDONLY | os.O_DIRECTORY))
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    # Exercise each descriptor check even on non-root CI hosts. Keep actual
    # file type/mode/link count/size; only supply the supported root ownership.
    original = os.fstat

    def root_owned(fd):
        info = original(fd)
        return SimpleNamespace(st_uid=0, st_gid=0, **{k: getattr(info, k) for k in ("st_mode", "st_nlink", "st_size")})

    monkeypatch.setattr(module.os, "fstat", root_owned)
    return path


def test_private_descriptor_input_reads_pinned_regular_file(private_file):
    assert module.load(private_file) == wrapped(sample())[0]


@pytest.mark.parametrize("case", ["symlink", "hardlink", "public", "directory", "fifo", "oversized", "nonroot", "relative", "parent"])
def test_private_descriptor_input_rejects_unsafe_files(private_file, tmp_path, monkeypatch, case):
    path = private_file
    if case == "symlink":
        target = tmp_path / "link"
        target.symlink_to(path)
        path = target
    elif case == "hardlink":
        os.link(path, tmp_path / "extra")
    elif case == "public":
        path.chmod(0o644)
    elif case == "directory":
        path = tmp_path
    elif case == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif case == "oversized":
        path.write_bytes(b" " * (module.MAX_FILE_BYTES + 1))
    elif case == "nonroot":
        monkeypatch.setattr(module.os, "geteuid", lambda: 10001)
    elif case == "relative":
        path = Path("source.json")
    elif case == "parent":
        path = tmp_path / ".." / tmp_path.name / "source.json"
    with pytest.raises((ValueError, OSError)):
        module.load(path)


def test_cli_failure_does_not_echo_untrusted_input_or_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(module.sys, "argv", ["private_queue_evidence.py", str(tmp_path / "missing"),
                                           "--expected-sha256", "a" * 64, "--expected-plan-sha256", "c" * 64,
                                           "--installation-id", "test-installation", "--initialization-id", "d" * 32,
                                           "--output", str(tmp_path / "handoff")])
    def unavailable(*a):
        raise ValueError("private contents must not escape")

    monkeypatch.setattr(module, "load", unavailable)
    with pytest.raises(ValueError):
        module.main()
    assert not (tmp_path / "handoff").exists()
