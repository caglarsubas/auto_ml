"""Ordering observations cannot drop, rewrite or split a collected file."""
import hashlib
from collections import Counter, OrderedDict

import pytest

from tests.native_file_order import order_files

pytestmark = pytest.mark.unit


def test_duration_priority_retains_every_original_group_node_and_completion_status(tmp_path):
    root = tmp_path / "tests"
    root.mkdir()
    for name in ["slow.py", "fast.py", "changed.py"]:
        (root / name).write_text("original source\n")
    records = {"schema": "native_file_cost_observations_v1", "source_run": 123,
               "source_run_qualified": False, "files": {
                   "tests/slow.py": {"cases": 2, "wall_seconds": 30.,
                                     "source_sha256": hashlib.sha256((root / "slow.py").read_bytes()).hexdigest()},
                   "tests/fast.py": {"cases": 3, "wall_seconds": 1.,
                                     "source_sha256": hashlib.sha256((root / "fast.py").read_bytes()).hexdigest()},
                   "tests/changed.py": {"cases": 1, "wall_seconds": .1, "source_sha256": "0" * 64}}}
    work = OrderedDict([
        ("tests/fast.py", {"fast::one": False, "fast::two": True, "fast::three": False}),
        ("tests/slow.py", {"slow::one": False, "slow::two": False}),
        ("tests/changed.py", {"changed::one": False}),
        ("tests/new.py", {"new::one": False}),
    ])
    before = [(path, id(unit), tuple(unit.items())) for path, unit in work.items()]
    ordered, receipt = order_files(work, source_root=tmp_path, observations=records)
    assert list(ordered) == ["tests/changed.py", "tests/new.py", "tests/slow.py", "tests/fast.py"]
    assert [(path, id(unit), tuple(unit.items())) for path, unit in work.items()] == before
    assert Counter((node, state) for unit in ordered.values() for node, state in unit.items()) == Counter(
        (node, state) for unit in work.values() for node, state in unit.items())
    assert all(ordered[path] is unit for path, unit in work.items())
    assert receipt["file_groups"] == 4 and receipt["collected_cases"] == 7
    assert receipt["matched_files"] == ["tests/fast.py", "tests/slow.py"]
    assert receipt["new_or_changed_files"] == ["tests/changed.py", "tests/new.py"]
    assert receipt["source_run_qualified"] is False and receipt["original_work_units_preserved"]
    assert receipt["workers"] == 2 and receipt["worker_restarts"] == 0 and receipt["native_cap_seconds"] == 900
