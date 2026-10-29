"""Qualification diagnostics observe bounded facts without changing execution."""

import ast
import io
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "native_observation_test_subject", ROOT / "scripts/native_qualification_observation.py"
)
observation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observation)
pytestmark = pytest.mark.unit


@pytest.fixture
def files(monkeypatch):
    values = {
        "/proc/self/cgroup": "0::/fixture\n",
        "/sys/fs/cgroup/fixture/cpu.max": "200000 100000\n",
        "/sys/fs/cgroup/fixture/cpu.stat": "usage_usec 10\nnr_throttled 2\nthrottled_usec 3\nsecret 999\n",
        "/sys/fs/cgroup/fixture/memory.current": "1024\n",
        "/sys/fs/cgroup/fixture/memory.peak": "2048\n",
        "/sys/fs/cgroup/fixture/memory.max": "max\n",
        "/sys/fs/cgroup/fixture/memory.events": "oom 0\noom_kill 0\nunknown 555\n",
        "/sys/fs/cgroup/fixture/cpuset.cpus.effective": "0-3\n",
        "/proc/cpuinfo": "model name : Standard fixture CPU\ncpu MHz : 2400\nSerial : SECRET\n",
        "/proc/stat": "cpu 1 2 3 4 5 6 7 8 9 10\ncpu0 SECRET\n",
        "/proc/meminfo": "MemTotal: 8000 kB\nMemAvailable: 4000 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\nHostSecret: SECRET\n",
        "/proc/pressure/cpu": "some avg10=1.25 avg60=2 total=100\nfull avg10=0 total=0\n",
        "/proc/pressure/memory": "",
        "/proc/pressure/io": "",
    }
    monkeypatch.setattr(observation, "_read", lambda path: values.get(str(path)))
    monkeypatch.setattr(observation, "platform", SimpleNamespace(system=lambda: "Linux", machine=lambda: "x86_64"))
    monkeypatch.setattr(
        observation, "os", SimpleNamespace(cpu_count=lambda: 4, sched_getaffinity=lambda pid: {0, 1, 2, 3})
    )
    return values


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", 0),
        ("1", 1),
        (str(2**64 - 1), 2**64 - 1),
        (str(2**64), None),
        ("-1", None),
        ("+1", None),
        ("01", None),
        ("1.0", None),
        ("nan", None),
        ("", None),
        (None, None),
        ("9" * 500, None),
    ],
)
def test_counter_parser_is_bounded_and_refuses_noncanonical_values(value, expected):
    assert observation._integer(value) == expected


def test_allowlisted_fields_exclude_identity_environment_and_unknown_proc_content(files):
    value = observation.observe()
    assert value["schema"] == "native_qualification_resource_observation_v1" and value["read_only"]
    assert (
        value["system"] == "Linux"
        and value["architecture"] == "x86_64"
        and value["logical_cpus"] == value["affinity_cpus"] == 4
    )
    assert value["cpu_model"] == "Standard fixture CPU" and value["observed_cpu_mhz"] == {
        "minimum": 2400.0,
        "maximum": 2400.0,
    }
    assert value["cpu_jiffies"]["steal"] == 8 and len(value["cpu_jiffies"]) == 10
    assert value["memory_kib"] == {"MemTotal": 8000, "MemAvailable": 4000, "SwapTotal": 0, "SwapFree": 0}
    assert value["cgroup"]["cpu.max"] == {"quota_usec": 200000, "period_usec": 100000}
    assert value["cgroup"]["cpu.stat"] == {"usage_usec": 10, "nr_throttled": 2, "throttled_usec": 3}
    assert value["pressure"]["cpu"]["some"] == {"avg10": 1.25, "total_usec": 100}
    assert value["pressure"]["memory"] is None and not value["capacity_qualified"]
    assert not value["host_identity_or_environment_retained"]
    assert all(word not in json.dumps(value) for word in ["SECRET", "/fixture", "Serial", "HostSecret"])


@pytest.mark.parametrize("text", ["1:cpu:/fixture\n", "0::/../other\n", "0::relative\n", "0::/a\n0::/b\n", "garbage"])
def test_missing_or_unsafe_unified_hierarchy_is_explicitly_unavailable(files, text):
    files["/proc/self/cgroup"] = text
    assert observation.observe()["cgroup"] == {"status": "unavailable", "reason": "unified_cgroup_unavailable"}


@pytest.mark.parametrize(
    "text",
    [
        "some avg10=nan total=1",
        "some avg10=101 total=1",
        "some avg10=1 total=-1",
        "other avg10=1 total=2",
        "some missing=1",
        "some avg10=inf total=0",
    ],
)
def test_malformed_pressure_never_becomes_a_capacity_claim(text):
    assert observation._pressure(text) == {}


@pytest.mark.parametrize("system", ["Darwin", "Windows"])
def test_other_hosts_are_unavailable_without_proc_or_docker_calls(monkeypatch, system):
    monkeypatch.setattr(observation, "platform", SimpleNamespace(system=lambda: system, machine=lambda: "example"))
    monkeypatch.setattr(observation, "_read", lambda path: pytest.fail("unsupported host filesystem was probed"))
    value = observation.observe({"postgres": "owned"})
    assert (
        value["status"] == "unavailable"
        and value["reason"] == "linux_observation_required"
        and not value["capacity_qualified"]
    )


def test_missing_counters_remain_unknown_instead_of_zero(files):
    for key in list(files):
        if key.startswith("/sys/fs/cgroup/"):
            files.pop(key)
    value = observation.observe()
    assert value["cgroup"] == {"status": "unavailable", "reason": "unified_counters_unavailable"}
    assert value["pressure"]["memory"] is None


def test_real_reader_has_a_hard_byte_limit_and_no_decode_error_disclosure(tmp_path):
    path = tmp_path / "counter"
    path.write_bytes(b"a" * (observation.LIMIT + 1))
    assert observation._read(path) is None
    path.write_bytes(b"\xff")
    assert observation._read(path) is None
    assert observation._read(tmp_path / "absent") is None
    path.write_text("123\n")
    assert observation._read(path) == "123\n"


@pytest.mark.parametrize("fault", ["none", "exit", "size", "json", "extra", "negative", "cpuset", "timeout"])
def test_only_selected_owned_container_limits_are_retained(files, monkeypatch, fault):
    data = {
        "cpu_quota": 0,
        "cpu_period": 0,
        "nano_cpus": 1000000000,
        "cpuset": "0-1",
        "memory": 536870912,
        "memory_swap": -1,
    }
    if fault == "extra":
        data["Env"] = "SECRET"
    if fault == "negative":
        data["memory"] = -2
    if fault == "cpuset":
        data["cpuset"] = "SECRET"
    calls = []

    def inspect(args, **kwargs):
        calls.append((args, kwargs))
        if fault == "timeout":
            raise subprocess.TimeoutExpired(args, 5)
        return SimpleNamespace(
            returncode=1 if fault == "exit" else 0,
            stdout=b"x" * 2049 if fault == "size" else b"bad" if fault == "json" else json.dumps(data).encode(),
        )

    monkeypatch.setattr(
        observation, "subprocess", SimpleNamespace(run=inspect, TimeoutExpired=subprocess.TimeoutExpired)
    )
    value = observation.observe({"postgres": "owned-random-name", "ignored": "not-authorized"})
    assert len(calls) == 1 and calls[0][0][:3] == ["docker", "inspect", "--format"] and calls[0][1]["timeout"] == 5
    assert "Env" not in calls[0][0][3] and "Id" not in calls[0][0][3]
    assert "owned-random-name" not in json.dumps(value) and "SECRET" not in json.dumps(value)
    assert value["owned_container_limits"]["postgres"]["status"] == ("observed" if fault == "none" else "unavailable")


def test_observation_failure_and_output_failure_do_not_change_a_test_exit_status(tmp_path, monkeypatch):
    monkeypatch.setattr(observation, "observe", lambda owned: (_ for _ in ()).throw(RuntimeError("SECRET")))
    path = tmp_path / "observation.json"
    assert observation.write_observation(path, execution="host")
    value = json.loads(path.read_text())
    assert value["reason"] == "observation_failed" and "SECRET" not in path.read_text()
    assert value["suite_execution"] == {
        "location": "host",
        "workers": 2,
        "process_cap_seconds": 900,
        "observation_scope": "controller_host_and_owned_container_limits",
    }
    assert observation.write_observation(tmp_path / "absent" / "output.json") is False


@pytest.mark.parametrize("mode", ["host", "core_image"])
@pytest.mark.parametrize("outcome", ["pass", "fail", "timeout"])
@pytest.mark.parametrize("diagnostic_available", [True, False])
def test_actual_controller_keeps_original_arguments_budget_exit_and_after_observation(
    tmp_path, monkeypatch, mode, outcome, diagnostic_available
):
    tree = ast.parse((ROOT / "scripts/qualify_postgres_fixture.py").read_text())
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "run_python")
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    events = []
    calls = []

    def record(path, owned, **kwargs):
        events.append((Path(path).name, owned, kwargs))
        return diagnostic_available

    monkeypatch.setitem(sys.modules, "native_qualification_observation", SimpleNamespace(write_observation=record))

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(args, 900)
        return SimpleNamespace(returncode=0 if outcome == "pass" else 1)

    namespace = {
        "env": {},
        "ROOT": tmp_path,
        "reports": tmp_path,
        "fixture": tmp_path,
        "runner": "owned-runner",
        "network": "owned-network",
        "db": "owned-db",
        "redis": "owned-cache",
        "job_broker": "owned-broker",
        "args": SimpleNamespace(runner_image="fixed-image" if mode == "core_image" else None),
        "sys": SimpleNamespace(executable="fixed-python", stderr=io.StringIO()),
        "subprocess": SimpleNamespace(run=run),
    }
    exec(compile(module, "<actual-controller-test>", "exec"), namespace)
    args = ["-m", "pytest", "-p", "tests.postgresql_parallel", "-n", "2", "--max-worker-restart=0"]
    if outcome == "pass":
        namespace["run_python"](args, report="postgresql.log")
    else:
        with pytest.raises(subprocess.TimeoutExpired if outcome == "timeout" else RuntimeError):
            namespace["run_python"](args, report="postgresql.log")
    assert [e[0] for e in events] == ["native-resources-before.json", "native-resources-after.json"]
    assert all(
        e[1] == {"postgres": "owned-db", "cache": "owned-cache", "broker": "owned-broker"}
        and e[2] == {"execution": mode}
        for e in events
    )
    assert len(calls) == 1 and calls[0][1]["timeout"] == 900 and calls[0][1]["check"] is False
    assert calls[0][0][-len(args) :] == args
    assert ("--cpuset-cpus=2-3" in calls[0][0]) is (mode == "core_image")
    assert bool(namespace["sys"].stderr.getvalue()) is (not diagnostic_available)


def test_other_private_checks_do_not_probe_host_resources(tmp_path, monkeypatch):
    tree = ast.parse((ROOT / "scripts/qualify_postgres_fixture.py").read_text())
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "run_python")
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    monkeypatch.setitem(
        sys.modules,
        "native_qualification_observation",
        SimpleNamespace(write_observation=lambda *a, **k: pytest.fail("unrelated fixture phase was probed")),
    )
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    namespace = {
        "env": {},
        "ROOT": tmp_path,
        "reports": tmp_path,
        "args": SimpleNamespace(runner_image=None),
        "sys": SimpleNamespace(executable="python"),
        "subprocess": SimpleNamespace(run=run),
    }
    exec(compile(module, "<actual-controller-other-phase>", "exec"), namespace)
    namespace["run_python"](["-c", "pass"], report="private-jobs.log")
    assert calls[0][0] == ["python", "-c", "pass"] and calls[0][1]["timeout"] == 900


def test_actual_host_observation_is_explicit_without_capacity_or_identity_claims():
    value = observation.observe()
    assert value["read_only"] and not value["capacity_qualified"] and not value["host_identity_or_environment_retained"]
    assert value["status"] in {"observed", "unavailable"}
    assert not {"hostname", "node", "machine_id", "environment", "pid", "container_id"} & value.keys()
    json.dumps(value, allow_nan=False)
