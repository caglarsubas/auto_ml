"""Bounded read-only Linux qualification facts; no environment or host identity.

Observations are diagnostics, never capacity or installation qualification.
Missing counters remain unavailable. No process, service or limit is changed.
"""

import datetime
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess

LIMIT = 1024 * 1024
COUNTERS = {
    "cpu.stat": {
        "usage_usec",
        "user_usec",
        "system_usec",
        "nr_periods",
        "nr_throttled",
        "throttled_usec",
    },
    "memory.events": {"low", "high", "max", "oom", "oom_kill", "oom_group_kill"},
}


def _read(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            return None
        return raw.decode("ascii")
    except (OSError, UnicodeError, ValueError):
        return None


def _integer(value):
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,19}", value):
        return None
    number = int(value)
    return number if number <= 2**64 - 1 else None


def _pairs(text, allowed):
    result = {}
    for line in (text or "").splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] in allowed and fields[0] not in result:
            value = _integer(fields[1])
            if value is not None:
                result[fields[0]] = value
    return result


def _pressure(text):
    result = {}
    for line in (text or "").splitlines():
        fields = line.split()
        if not fields or fields[0] not in {"some", "full"} or fields[0] in result:
            continue
        values = dict(
            field.split("=", 1) for field in fields[1:] if field.count("=") == 1
        )
        try:
            avg = float(values["avg10"])
            total = _integer(values.get("total"))
            if math.isfinite(avg) and 0 <= avg <= 100 and total is not None:
                result[fields[0]] = {"avg10": avg, "total_usec": total}
        except (KeyError, TypeError, ValueError, OverflowError):
            pass
    return result


def _cgroup():
    entries = [
        line[3:]
        for line in (_read("/proc/self/cgroup") or "").splitlines()
        if line.startswith("0::")
    ]
    if (
        len(entries) != 1
        or not entries[0].startswith("/")
        or ".." in Path(entries[0]).parts
    ):
        return {"status": "unavailable", "reason": "unified_cgroup_unavailable"}
    # Use the current process's unified hierarchy only. Never emit its path,
    # which may contain an ephemeral host/container identifier.
    root = Path("/sys/fs/cgroup") / entries[0].lstrip("/")
    result = {"status": "observed", "version": 2}
    for name, keys in COUNTERS.items():
        values = _pairs(_read(root / name), keys)
        result[name] = values or None
    maximum = (_read(root / "cpu.max") or "").split()
    result["cpu.max"] = None
    if len(maximum) == 2:
        quota = "max" if maximum[0] == "max" else _integer(maximum[0])
        period = _integer(maximum[1])
        if quota is not None and period and quota != 0:
            result["cpu.max"] = {"quota_usec": quota, "period_usec": period}
    cpuset = (_read(root / "cpuset.cpus.effective") or "").strip()
    result["cpuset.cpus.effective"] = (
        cpuset
        if len(cpuset) <= 256
        and re.fullmatch(r"[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*", cpuset)
        else None
    )
    for name in ["memory.current", "memory.peak", "memory.max"]:
        value = (_read(root / name) or "").strip()
        result[name] = (
            "max" if name == "memory.max" and value == "max" else _integer(value)
        )
    if all(
        result[key] is None
        for key in [
            *COUNTERS,
            "cpu.max",
            "cpuset.cpus.effective",
            "memory.current",
            "memory.peak",
            "memory.max",
        ]
    ):
        return {"status": "unavailable", "reason": "unified_counters_unavailable"}
    return result


def _containers(owned):
    result = {}
    template = (
        '{"cpu_quota":{{.HostConfig.CpuQuota}},"cpu_period":{{.HostConfig.CpuPeriod}},'
        '"nano_cpus":{{.HostConfig.NanoCpus}},"cpuset":{{json .HostConfig.CpusetCpus}},'
        '"memory":{{.HostConfig.Memory}},"memory_swap":{{.HostConfig.MemorySwap}}}'
    )
    for role, name in owned.items():
        if role not in {"postgres", "cache", "broker", "runner"}:
            continue
        try:
            value = subprocess.run(
                ["docker", "inspect", "--format", template, name],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if value.returncode or len(value.stdout) > 2048:
                raise ValueError
            data = json.loads(value.stdout)
            if (
                set(data)
                != {
                    "cpu_quota",
                    "cpu_period",
                    "nano_cpus",
                    "cpuset",
                    "memory",
                    "memory_swap",
                }
                or any(
                    type(data[k]) is not int or not -1 <= data[k] <= 2**64 - 1
                    for k in data
                    if k != "cpuset"
                )
                or not isinstance(data["cpuset"], str)
                or len(data["cpuset"]) > 256
                or data["cpuset"]
                and not re.fullmatch(
                    r"[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*", data["cpuset"]
                )
            ):
                raise ValueError
            result[role] = {"status": "observed", **data}
        except (OSError, ValueError, subprocess.TimeoutExpired):
            result[role] = {"status": "unavailable"}
    return result


def observe(owned=None):
    result = {
        "schema": "native_qualification_resource_observation_v1",
        "read_only": True,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "system": platform.system(),
        "architecture": platform.machine(),
        "capacity_qualified": False,
        "host_identity_or_environment_retained": False,
    }
    if result["system"] != "Linux":
        return {
            **result,
            "status": "unavailable",
            "reason": "linux_observation_required",
        }
    result.update(status="observed", logical_cpus=os.cpu_count())
    try:
        result["affinity_cpus"] = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        result["affinity_cpus"] = None
    result["cpu_model"] = None
    frequencies = []
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        name, sep, value = line.partition(":")
        if (
            sep
            and name.strip() in {"model name", "Hardware"}
            and result["cpu_model"] is None
        ):
            value = value.strip()
            if 1 <= len(value) <= 160 and value.isprintable():
                result["cpu_model"] = value
        if sep and name.strip() == "cpu MHz":
            try:
                value = float(value.strip())
                if math.isfinite(value) and 0 < value <= 100000:
                    frequencies.append(value)
            except ValueError:
                pass
    result["observed_cpu_mhz"] = (
        {"minimum": min(frequencies), "maximum": max(frequencies)}
        if frequencies
        else None
    )
    result["cpu_jiffies"] = None
    for line in (_read("/proc/stat") or "").splitlines():
        fields = line.split()
        names = [
            "user",
            "nice",
            "system",
            "idle",
            "iowait",
            "irq",
            "softirq",
            "steal",
            "guest",
            "guest_nice",
        ]
        if fields and fields[0] == "cpu" and len(fields) == 11:
            values = [_integer(v) for v in fields[1:]]
            if all(v is not None for v in values):
                result["cpu_jiffies"] = dict(zip(names, values))
            break
    result["memory_kib"] = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        fields = line.split()
        if (
            len(fields) == 3
            and fields[0] in {"MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"}
            and fields[2] == "kB"
        ):
            value = _integer(fields[1])
            if value is not None:
                result["memory_kib"][fields[0][:-1]] = value
    result["cgroup"] = _cgroup()
    result["pressure"] = {
        name: _pressure(_read("/proc/pressure/" + name)) or None
        for name in ["cpu", "memory", "io"]
    }
    result["owned_container_limits"] = _containers(owned or {})
    return result


def write_observation(path, owned=None, *, execution=None):
    """Diagnostic failure remains explicit without replacing test exit status."""
    try:
        value = observe(owned)
    except Exception:
        value = {
            "schema": "native_qualification_resource_observation_v1",
            "read_only": True,
            "status": "unavailable",
            "reason": "observation_failed",
            "capacity_qualified": False,
            "host_identity_or_environment_retained": False,
        }
    if isinstance(execution, str) and execution in {"host", "core_image"}:
        value["suite_execution"] = {
            "location": execution,
            "workers": 2,
            "process_cap_seconds": 900,
            "observation_scope": "controller_host_and_owned_container_limits",
        }
    try:
        Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    except OSError:
        return False
    return True
