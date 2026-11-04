"""Evidence parsing, deterministic bounds and concurrency accounting for P166."""

import copy
import csv
import importlib
import io
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def envelope(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    return importlib.import_module("qualify_private_workload_envelope")


@pytest.mark.parametrize(
    "text,expected",
    [("1B", 1), ("1.5kB", 1500), ("2MB", 2000000), ("1GiB", 1024**3), ("512MiB", 512 * 1024**2), ("4KiB", 4096)],
)
def test_explicit_docker_memory_units(envelope, text, expected):
    assert envelope.number_bytes(text) == expected


@pytest.mark.parametrize("text", ["NaNMiB", "-1MB", "1TB", "1e9B", "1", "", "unknown", "9" * 400 + "GiB"])
def test_unsupported_nonfinite_or_negative_memory_refuses(envelope, text):
    with pytest.raises(envelope.schema.checker.planner.PlanError):
        envelope.number_bytes(text)


@pytest.fixture
def sample():
    identity = {"worker": {"id": "a" * 64}}
    rows = [{"ID": "a" * 64, "CPUPerc": "12.25%", "MemUsage": "512MiB / 2GiB", "PIDs": "14"}]
    return identity, rows


def test_owned_resource_observation_preserves_cli_semantics(envelope, sample):
    identities, rows = sample
    assert envelope.stats_sample(rows, identities) == {
        "worker": {
            "cpu_cli_percent": 12.25,
            "memory_cli_bytes": 512 * 1024**2,
            "memory_cli_limit_bytes": 2 * 1024**3,
            "pids": 14,
        }
    }


@pytest.mark.parametrize(
    "fault",
    [
        "foreign_id",
        "duplicate",
        "missing",
        "cpu_nan",
        "cpu_negative",
        "cpu_overflow",
        "pids",
        "memory_shape",
        "memory_over_limit",
        "zero_limit",
    ],
)
def test_malformed_or_foreign_stats_are_not_recorded_as_zero(envelope, sample, fault):
    identities, rows = sample
    if fault == "foreign_id":
        rows[0]["ID"] = "b" * 64
    elif fault == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif fault == "missing":
        rows.clear()
    elif fault.startswith("cpu_"):
        rows[0]["CPUPerc"] = {"cpu_nan": "NaN%", "cpu_negative": "-1%", "cpu_overflow": "9" * 400 + "%"}[fault]
    elif fault == "pids":
        rows[0]["PIDs"] = "-1"
    else:
        rows[0]["MemUsage"] = {"memory_shape": "invalid", "memory_over_limit": "3GiB / 2GiB", "zero_limit": "0B / 0B"}[
            fault
        ]
    with pytest.raises(envelope.schema.checker.planner.PlanError):
        envelope.stats_sample(rows, identities)


@pytest.mark.parametrize("task", ["classification", "regression"])
@pytest.mark.parametrize(
    "rows,features,strategy,folds", [(30, 2, "random", 2), (300, 16, "group", 3), (1000, 32, "oot", 2)]
)
def test_seeded_cases_cover_admitted_bounds_without_changing_folds(envelope, task, rows, features, strategy, folds):
    raw, options = envelope.dataset(task, rows, features, strategy)
    assert (raw, options) == envelope.dataset(task, rows, features, strategy)
    table = list(csv.reader(io.StringIO(raw.decode())))
    assert len(table) - 1 == rows and len(options["features"]) == features
    assert all(len(row) == len(table[0]) for row in table)
    assert len(raw) < 1024**2 and options["validation"]["n_splits"] == folds
    assert options["data_role"] == "development_only" and "outcome" not in options["features"]
    assert options["business_understanding"]["problem_type"] == task
    if strategy == "group":
        assert options["validation"]["group_column"] == "entity"
    if strategy == "oot":
        assert (
            options["validation"]["date_column"] == "observed"
            and options["validation"]["label_end_column"] == "matured"
        )
        assert all(row[-2] > row[-3] for row in table[1:])


def job(start="2026-01-01T00:00:01+00:00", end="2026-01-01T00:00:04+00:00"):
    return {
        "created_at": "2026-01-01T00:00:00+00:00",
        "events": [{"event_type": "started", "created_at": start}],
        "finished_at": end,
        "attempts": 1,
        "state": "succeeded",
    }


def test_recorded_queue_and_execution_intervals(envelope):
    assert envelope.job_timing(job())["queue_seconds"] == 1
    assert envelope.job_timing(job())["execution_seconds"] == 3


@pytest.mark.parametrize(
    "fault", ["failed", "retry", "missing_start", "duplicate_start", "reverse_clock", "naive_clock"]
)
def test_unmeasured_or_incoherent_job_history_cannot_claim_latency(envelope, fault):
    value = job()
    if fault == "failed":
        value["state"] = "failed"
    elif fault == "retry":
        value["attempts"] = 2
    elif fault == "missing_start":
        value["events"] = []
    elif fault == "duplicate_start":
        value["events"] *= 2
    elif fault == "reverse_clock":
        value["finished_at"] = "2025-12-31T23:59:59+00:00"
    else:
        value["finished_at"] = "2026-01-01T00:00:04"
    with pytest.raises(envelope.schema.checker.planner.PlanError):
        envelope.job_timing(value)


def test_concurrency_is_observed_not_assumed(envelope):
    assert envelope.max_overlap([job(), job("2026-01-01T00:00:04+00:00", "2026-01-01T00:00:05+00:00")]) == 1
    assert envelope.max_overlap([job(), job("2026-01-01T00:00:02+00:00", "2026-01-01T00:00:05+00:00")]) == 2
    with pytest.raises(envelope.schema.checker.planner.PlanError):
        envelope.max_overlap([job(), job(), job()])


@pytest.fixture
def comparison(envelope):
    cases = []
    for rows, features, strategy, folds in envelope.CASES:
        for task in ("classification", "regression"):
            cases.append(
                {
                    "task": task,
                    "rows": rows,
                    "features": features,
                    "validation": {"strategy": strategy, "n_splits": folds},
                    "input_sha256": "a" * 64,
                    "prediction_values_sha256": "b" * 64,
                    "workflow_seconds": 1.0,
                    "offline_chunk_parity": "passed",
                    "duplicate_submission": "single_job",
                    "observed_pair_active": 1,
                }
            )
    one = {
        "schema": "private_workload_envelope_v1",
        "cases": cases,
        "customer_capacity_qualified": False,
        "release_qualified": False,
        "row_overflow": "refused_before_submission",
        "resources": {"samples": [{}, {}], "observer_overhead_included": True},
    }
    images = {"api": "sha256:" + "a" * 64}
    profiles = [{"installation_id": str(i), "application_images": images} for i in range(2)]
    return [one, copy.deepcopy(one)], profiles, images


def test_two_clean_roots_qualify_observations_with_capacity_unclaimed(envelope, comparison):
    report = envelope.comparison(*comparison)
    assert report["same_seeded_inputs_and_predictions"] is True and report["clean_roots"] == 2
    assert report["customer_capacity_qualified"] is report["legacy_workload_envelope_qualified"] is False
    assert json.loads(json.dumps(report))["release_qualified"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "same_root",
        "images",
        "case_missing",
        "case_duplicate",
        "prediction",
        "input",
        "latency",
        "capacity_claim",
        "parity",
        "no_stats",
    ],
)
def test_partial_inconsistent_or_overclaimed_profiles_refuse(envelope, comparison, fault):
    runs, profiles, images = comparison
    if fault == "same_root":
        profiles[1]["installation_id"] = profiles[0]["installation_id"]
    elif fault == "images":
        profiles[1]["application_images"] = {}
    elif fault == "case_missing":
        runs[1]["cases"].pop()
    elif fault == "case_duplicate":
        runs[1]["cases"][0] = copy.deepcopy(runs[1]["cases"][1])
    elif fault in ("prediction", "input"):
        runs[1]["cases"][0]["prediction_values_sha256" if fault == "prediction" else "input_sha256"] = "changed"
    elif fault == "latency":
        runs[1]["cases"][0]["workflow_seconds"] = float("nan")
    elif fault == "capacity_claim":
        runs[1]["customer_capacity_qualified"] = True
    elif fault == "parity":
        runs[1]["cases"][0]["offline_chunk_parity"] = "failed"
    else:
        runs[1]["resources"]["samples"] = []
    with pytest.raises(envelope.schema.checker.planner.PlanError):
        envelope.comparison(runs, profiles, images)
