"""Source-bound duration ordering; file groups, tests and all limits stay intact."""
import hashlib
import json
import math
from collections import OrderedDict
from pathlib import Path


def order_files(workqueue, *, source_root, observations):
    if observations.get("schema") != "native_file_cost_observations_v1":
        raise ValueError("native_file_order_schema")
    files = observations["files"]
    if not isinstance(files, dict) or not 1 <= len(files) <= 1024:
        raise ValueError("native_file_order_bounds")
    for path, item in files.items():
        if (not path.startswith("tests/") or not path.endswith(".py") or ".." in Path(path).parts
                or type(item["cases"]) is not int or item["cases"] < 1
                or type(item["wall_seconds"]) not in {int, float}
                or not math.isfinite(item["wall_seconds"]) or not 0 <= item["wall_seconds"] <= 1800):
            raise ValueError("native_file_order_bounds")
    unknown = max(item["wall_seconds"] for item in files.values()) + 1
    costs, matched, changed, observed_sources = {}, [], [], {}
    for path in workqueue:
        item = files.get(path)
        current = source_root / path
        observed_sources[path] = (hashlib.sha256(current.read_bytes()).hexdigest()
                                  if current.is_file() and not current.is_symlink() else None)
        if item is not None and observed_sources[path] == item["source_sha256"]:
            costs[path] = item["wall_seconds"]
            matched.append(path)
        else:
            costs[path] = unknown
            changed.append(path)
    ordered = OrderedDict(sorted(workqueue.items(), key=lambda row: -costs[row[0]]))
    assert len(ordered) == len(workqueue) and all(ordered[path] is unit for path, unit in workqueue.items())
    receipt = {
        "schema": "native_file_order_v1", "grouping": "loadfile",
        "ordering": "source_bound_observed_duration_descending",
        "source_run": observations["source_run"], "source_run_qualified": observations["source_run_qualified"],
        "file_groups": len(ordered), "collected_cases": sum(len(unit) for unit in ordered.values()),
        "matched_files": matched, "new_or_changed_files": changed,
        "ordered_files": list(ordered), "original_work_units_preserved": True,
        "test_sources_sha256": observed_sources, "cases_per_file": {path: len(unit) for path, unit in ordered.items()},
        "workers": 2, "worker_restarts": 0, "native_cap_seconds": 900,
    }
    return ordered, receipt


def scheduler(config, log):
    from xdist.scheduler.loadfile import LoadFileScheduling

    if config.getoption("dist") != "loadfile":
        raise ValueError("native_file_order_requires_loadfile")
    root = Path(__file__).absolute().parents[1]
    manifest = Path(__file__).with_name("native_file_costs.json")
    raw = manifest.read_bytes()
    observations = json.loads(raw)
    destination = Path(config.getoption("--postgresql-isolation-report")).absolute().parent / "file-ordering.json"

    class DurationOrderedFiles(LoadFileScheduling):
        _file_order_applied = False

        def _assign_work_unit(self, node):
            if not self._file_order_applied:
                self.workqueue, receipt = order_files(self.workqueue, source_root=root, observations=observations)
                receipt["sources"] = {str(path.relative_to(root.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in (Path(__file__), manifest, Path(__file__).with_name("postgresql_parallel.py"))}
                receipt["observations_sha256"] = hashlib.sha256(raw).hexdigest()
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(".tmp")
                temporary.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
                temporary.replace(destination)
                self._file_order_applied = True
            return super()._assign_work_unit(node)

    return DurationOrderedFiles(config, log)
