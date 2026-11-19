"""Cgroup teardown is distinct from complete resource-isolation evidence."""

import errno
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def qualifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    module = importlib.import_module("qualify_private_expert_isolation")
    monkeypatch.setattr(module.time, "sleep", Mock())
    monkeypatch.setattr(module.time, "monotonic", lambda: 0)
    return module


def cgroup_reads(monkeypatch, observations):
    remaining = iter(observations)

    def read(path, *args, **kwargs):
        name, value = next(remaining)
        assert path.name == name
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(Path, "read_text", read)


@pytest.mark.parametrize("error_number", [errno.ENOENT, errno.ENODEV])
def test_teardown_partial_sample_cannot_increase_observed_peak(qualifier, monkeypatch, error_number):
    cgroup_reads(monkeypatch, [
        ("memory.current", "100"), ("memory.swap.max", "0\n"),
        ("memory.current", "999999999"), ("memory.swap.max", OSError(error_number, "removed")),
    ])
    process = SimpleNamespace(poll=Mock(side_effect=[None, None, 1]))
    assert qualifier.observe_memory_pressure(Path("/synthetic-cgroup"), process) == 100
    assert process.poll.call_count == 3
    assert qualifier.time.sleep.call_count == 2


@pytest.mark.parametrize("error_number", [errno.ENOENT, errno.ENODEV])
def test_missing_complete_swap_evidence_fails_qualification(qualifier, monkeypatch, error_number):
    cgroup_reads(monkeypatch, [
        ("memory.current", "999999999"), ("memory.swap.max", OSError(error_number, "removed")),
    ])
    process = SimpleNamespace(poll=Mock(side_effect=[None, 1]))
    with pytest.raises(AssertionError, match="no complete memory and zero-swap observation"):
        qualifier.observe_memory_pressure(Path("/synthetic-cgroup"), process)


@pytest.mark.parametrize("error_number", [errno.EIO, errno.EACCES])
def test_unexpected_observation_errors_propagate(qualifier, monkeypatch, error_number):
    failure = OSError(error_number, "observation failed")
    cgroup_reads(monkeypatch, [("memory.current", "100"), ("memory.swap.max", failure)])
    process = SimpleNamespace(poll=Mock(return_value=None))
    with pytest.raises(OSError) as raised:
        qualifier.observe_memory_pressure(Path("/synthetic-cgroup"), process)
    assert raised.value is failure
    qualifier.time.sleep.assert_not_called()


@pytest.mark.parametrize("swap_max", ["1", "max"])
def test_nonzero_swap_limit_fails_immediately(qualifier, monkeypatch, swap_max):
    cgroup_reads(monkeypatch, [("memory.current", "100"), ("memory.swap.max", swap_max)])
    process = SimpleNamespace(poll=Mock(return_value=None))
    with pytest.raises(AssertionError, match=swap_max):
        qualifier.observe_memory_pressure(Path("/synthetic-cgroup"), process)
    qualifier.time.sleep.assert_not_called()


@pytest.mark.parametrize("current", ["invalid", "-1"])
def test_invalid_memory_observations_fail_immediately(qualifier, monkeypatch, current):
    cgroup_reads(monkeypatch, [
        ("memory.current", current), ("memory.swap.max", OSError(errno.ENODEV, "removed")),
    ])
    process = SimpleNamespace(poll=Mock(side_effect=[None, 1]))
    with pytest.raises(ValueError if current == "invalid" else AssertionError, match=current):
        qualifier.observe_memory_pressure(Path("/synthetic-cgroup"), process)
    qualifier.time.sleep.assert_not_called()


def test_observation_preserves_original_fifteen_second_deadline(qualifier, monkeypatch):
    cgroup_reads(monkeypatch, [("memory.current", "100"), ("memory.swap.max", "0")])
    monkeypatch.setattr(qualifier.time, "monotonic", Mock(side_effect=[0, 14.99, 15]))
    process = SimpleNamespace(poll=Mock(return_value=None))
    assert qualifier.observe_memory_pressure(Path("/synthetic-cgroup"), process) == 100
    assert process.poll.call_count == 2
    qualifier.time.sleep.assert_called_once_with(0.01)
