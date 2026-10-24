"""Unambiguous operator JSON at the real pipe and offline evidence boundaries."""

import copy
import importlib
import json
import subprocess
import sys

import pytest

from tests.unit.test_private_queue_evidence import NOW, sample, verify, wrapped

pytestmark = pytest.mark.unit
RUN = subprocess.run
API = {"container_id": "a" * 64, "attention_required": False}
V1 = "native_queue_operator_snapshot_v1"
V2 = "native_queue_operator_snapshot_v2"
HEADER = b'{"schema":"native_queue_operator_snapshot_v2","status":"observed"'
BAD = [
    HEADER + b',"schema":"native_queue_operator_snapshot_v2"}',
    HEADER + b',"status":"unavailable"}',
    HEADER + b',"\\u0073tatus":"observed"}',
    HEADER + b',"states":{"queued":0,"queued":1}}',
    HEADER + b',"rows":[{"id":"first","id":"second"}]}',
    HEADER + b',"extension":{"nested":{"x":1,"x":1}}}',
    *[HEADER + b',"extension":' + n + b'}' for n in
      (b'NaN', b'Infinity', b'-Infinity', b'1e10000', b'-1e10000')],
    HEADER + b',"extension":[{"nested":1e10000}]}',
    (HEADER + b'}').decode().encode('utf-16'),
    (HEADER + b'}').decode().encode('utf-32'),
    b'\xef\xbb\xbf' + HEADER + b'}',
    HEADER + b',"extension":"\xff"}',
    *[b'{"schema":"native_queue_operator_snapshot_v2","status":' + s + b'}'
      for s in (b'[]', b'{}', b'true', b'null', b'0')],
    HEADER + b'} {}',
]


def module():
    return importlib.import_module("private_queue_incidents")


def transport(monkeypatch, raw, returncode=0):
    m = module()
    def run(args, **kwargs):
        assert args == [*m.resources.PREFIX, "exec", "--user", "10001:10001", API["container_id"],
                        "python", "-m", "execution_jobs.operator_triage"]
        assert kwargs["timeout"] == 20 and kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["check"] is False
        program = (f"import sys; sys.stdout.buffer.write(b\"x\" * {len(raw)}); sys.exit({returncode})"
                   if len(raw) > 131072 else f"import sys; sys.stdout.buffer.write({raw!r}); sys.exit({returncode})")
        return RUN([sys.executable, "-c", program], **kwargs)
    monkeypatch.setattr(m.subprocess, "run", run)
    return m


@pytest.mark.parametrize("raw", BAD, ids=[f"ambiguous-{i}" for i in range(len(BAD))])
def test_real_probe_rejects_ambiguous_json_with_a_sanitized_error(monkeypatch, raw):
    m = transport(monkeypatch, raw)
    with pytest.raises(m.checker.planner.PlanError) as exc:
        m.probe(API)
    assert str(exc.value) == "queue_incident_probe_output_invalid"
    assert exc.value.__suppress_context__ is True


@pytest.mark.parametrize("schema", [V1, V2])
@pytest.mark.parametrize("status", ["observed", "unavailable"])
def test_valid_versions_statuses_and_finite_extensions_survive_the_real_pipe(monkeypatch, schema, status):
    value = dict(schema=schema, status=status, extension={"unicode": "审查", "values": [1.25, -0.0, 1e-300], "empty": {}})
    raw = json.dumps(value, ensure_ascii=False).encode()
    m = transport(monkeypatch, raw)
    assert m.probe(API) == value
    assert m.encode(m.probe(API)) == m.encode(value)


@pytest.mark.parametrize("schema,timeout", [(V1, 5000), (V2, 5000), (V2, 1), (V2, 2000)])
def test_real_probe_complete_snapshot_still_passes_offline_verification(monkeypatch, schema, timeout):
    value = sample()
    value["queue"].update(schema=schema, statement_timeout_ms=timeout)
    m = transport(monkeypatch, m_encode(value["queue"]))
    observed = m.probe(API)
    assert observed == value["queue"]
    value["queue"] = observed
    evidence, receipt = verify(value)
    assert evidence == value and receipt["queue_consistency"] == "cross_checked_metadata"
    assert receipt["verified_at"] == NOW.isoformat()


def m_encode(value):
    return module().encode(value)


@pytest.mark.parametrize("raw", [BAD[0], BAD[8], BAD[17], BAD[18]])
def test_collection_main_never_reaches_export_for_rejected_probe_json(monkeypatch, tmp_path, raw):
    m = transport(monkeypatch, raw)
    target = tmp_path / "incident.json"
    monkeypatch.setattr(m.sys, "argv", ["private_queue_incidents.py", str(tmp_path / "plan"),
                                      "--expected-plan-sha256", "c" * 64, "--output", str(target)])
    def observe(*args):
        assert args == (tmp_path / "plan", "c" * 64)
        return m.probe(API)
    monkeypatch.setattr(m, "observe", observe)
    monkeypatch.setattr(m, "export", lambda *a: pytest.fail("rejected observation reached export"))
    with pytest.raises(m.checker.planner.PlanError, match="^queue_incident_probe_output_invalid$"):
        m.main()
    assert not target.exists() and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("raw", [BAD[0], BAD[8], BAD[17]])
def test_nonzero_child_keeps_existing_unavailable_precedence(monkeypatch, raw):
    m = transport(monkeypatch, raw, returncode=1)
    assert m.probe(API) == dict(status="unavailable", reason="probe_unavailable")


def test_oversize_response_is_rejected_before_decoding(monkeypatch):
    m = transport(monkeypatch, b"x" * 131073)
    monkeypatch.setattr(m, "decode", lambda *a: pytest.fail("oversize response reached JSON decoder"))
    with pytest.raises(m.checker.planner.PlanError, match="^queue_incident_probe_output_invalid$"):
        m.probe(API)


def test_offline_verifier_uses_the_same_strict_decoder(monkeypatch):
    m = module()
    calls = []
    original = m.decode
    def decode(raw):
        calls.append(raw)
        return original(raw)
    monkeypatch.setattr(m, "decode", decode)
    value = sample()
    assert verify(value)[0] == value
    assert calls == [wrapped(value)[0]]


@pytest.mark.parametrize("field", ["schema", "status", "queued", "sha256"])
def test_offline_self_consistent_digest_does_not_allow_duplicate_members(field):
    evidence = importlib.import_module("private_queue_evidence")
    value = copy.deepcopy(sample())
    raw, sha = wrapped(value)
    parsed = json.loads(raw)
    if field == "sha256":
        fragment = json.dumps(sha).encode()
    else:
        fragment = json.dumps(value["schema"] if field == "schema" else "observed" if field == "status" else 0).encode()
    key = json.dumps(field).encode() + b":"
    assert key + fragment in raw
    raw = raw.replace(key + fragment, key + fragment + b"," + key + fragment, 1)
    assert json.loads(raw) == parsed
    with pytest.raises(ValueError):
        evidence.verify(raw, expected_sha256=sha, expected_plan_sha256="c" * 64,
                        installation_id="test-installation", initialization_id="d" * 32, now=NOW)
