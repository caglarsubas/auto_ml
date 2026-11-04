"""Observe complete installed native workflows; never infer customer capacity."""

import csv
import hashlib
import io
import json
import math
import re
import subprocess
import threading
import time
import uuid
from datetime import date, datetime, timedelta

from qualify_private_installation_workflow import FLAGS, offline_score, require
import private_schema_init as schema

CASES = ((30, 2, "random", 2), (300, 16, "group", 3), (1000, 32, "oot", 2))
EXPECTED_BUDGET = {
    "max_rows": 1000,
    "max_features": 32,
    "candidates": 2,
    "boost_rounds": 16,
    "nthread": 1,
    "max_active": 2,
    "seconds": 120,
}
UNITS = {
    "B": 1,
    "kB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
}


def number_bytes(text):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(B|kB|MB|GB|KiB|MiB|GiB)", text.strip())
    require(match is not None, "envelope_memory_format")
    value = float(match[1]) * UNITS[match[2]]
    require(math.isfinite(value), "envelope_memory_range")
    return round(value)


def stats_sample(rows, identities):
    require(
        isinstance(rows, list) and len(rows) == len(identities), "envelope_stats_count"
    )
    result = {}
    by_id = {row["id"]: role for role, row in identities.items()}
    for row in rows:
        identifier = row.get("ID")
        require(
            identifier in by_id and by_id[identifier] not in result,
            "envelope_stats_identity",
        )
        cpu = row.get("CPUPerc", "")
        require(re.fullmatch(r"\d+(?:\.\d+)?%", cpu) is not None, "envelope_cpu_format")
        require(math.isfinite(float(cpu[:-1])), "envelope_cpu_format")
        memory = row.get("MemUsage", "").split(" / ")
        require(
            len(memory) == 2 and re.fullmatch(r"\d+", row.get("PIDs", "")) is not None,
            "envelope_stats_format",
        )
        used, limit = map(number_bytes, memory)
        require(0 <= used <= limit and limit > 0, "envelope_memory_range")
        result[by_id[identifier]] = {
            "cpu_cli_percent": float(cpu[:-1]),
            "memory_cli_bytes": used,
            "memory_cli_limit_bytes": limit,
            "pids": int(row["PIDs"]),
        }
    return result


def dataset(task, rows, columns, strategy):
    require(
        task in ("classification", "regression")
        and 30 <= rows <= 1001
        and 1 <= columns <= 33,
        "envelope_dataset_spec",
    )
    names = ["x" + str(i) for i in range(columns)]
    controls = (
        ["entity"]
        if strategy == "group"
        else ["observed", "matured"]
        if strategy == "oot"
        else []
    )
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow([*names, *controls, "outcome"])
    for i in range(rows):
        values = [
            round(((i * (j + 3) + j * 7) % 101) / 101, 6) if (i + j) % 23 else ""
            for j in range(columns)
        ]
        control = (
            [i // 10]
            if strategy == "group"
            else [
                (date(2020, 1, 1) + timedelta(days=i)).isoformat(),
                (date(2020, 1, 3) + timedelta(days=i)).isoformat(),
            ]
            if strategy == "oot"
            else []
        )
        label = (
            ("bad" if i % 2 else "good")
            if task == "classification"
            else round(i / 7 + i % 3, 6)
        )
        writer.writerow([*values, *control, label])
    validation = {"strategy": strategy, "n_splits": 3 if strategy == "group" else 2}
    if strategy == "group":
        validation["group_column"] = "entity"
    if strategy == "oot":
        validation.update(date_column="observed", label_end_column="matured")
    options = {
        "data_role": "development_only",
        "features": names,
        "validation": validation,
        "business_understanding": {
            "problem_type": task,
            "objective": "Synthetic installed workload envelope",
            "population": "Seeded synthetic numeric rows; not a customer credit population",
            "prediction_horizon": "Two days",
            "feature_availability": {"default": "available_at_prediction"},
            "target_contract": {
                "target_column": "outcome",
                "positive_class": "bad" if task == "classification" else None,
                "event_definition": "Synthetic recorded outcome",
                "label_maturity": "Complete follow-up",
            },
            "success_criteria": {
                "primary_metric": "roc_auc" if task == "classification" else "rmse"
            },
        },
    }
    return stream.getvalue().encode(), options


def job_timing(job):
    starts = [
        event["created_at"]
        for event in job["events"]
        if event["event_type"] == "started"
    ]
    require(
        len(starts) == 1 and job["attempts"] == 1 and job["state"] == "succeeded",
        "envelope_job_outcome",
    )
    created, started, finished = map(
        datetime.fromisoformat, (job["created_at"], starts[0], job["finished_at"])
    )
    require(
        all(t.tzinfo is not None for t in (created, started, finished))
        and created <= started <= finished,
        "envelope_job_clock",
    )
    return {
        "queue_seconds": (started - created).total_seconds(),
        "execution_seconds": (finished - started).total_seconds(),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
    }


def max_overlap(jobs):
    events = []
    for job in jobs:
        timing = job_timing(job)
        events += [
            (datetime.fromisoformat(timing["started_at"]), 1),
            (datetime.fromisoformat(timing["finished_at"]), -1),
        ]
    active = peak = 0
    for _, delta in sorted(events):
        active += delta
        peak = max(peak, active)
    require(peak <= 2, "envelope_admission_exceeded")
    return peak


class Sampler:
    """Read metadata/stats only for the source fixture's exact owned containers."""

    def __init__(self, value, prepared, adopted):
        resources = schema.resources
        binding = resources.labels(
            value, prepared["plan_manifest_sha256"], prepared["initialization_id"]
        )
        self.identities = {}
        self.samples = []
        self.error = None
        self.stop = threading.Event()
        refs = {k: v["container_id"] for k, v in adopted["services"].items()}
        refs.update(schema.startup.names(value))
        for role, reference in refs.items():
            info = resources.inspect("container", reference)
            require(
                all(info["Config"]["Labels"].get(k) == v for k, v in binding.items())
                and info["State"]["Running"],
                "envelope_owner",
            )
            image_role = (
                "redis"
                if role in ("job-broker", "cache")
                else "ingress"
                if role == "ingress"
                else "postgres"
                if role == "postgres"
                else "api"
            )
            require(info["Image"] == value["images"][image_role], "envelope_image")
            self.identities[role] = {
                "id": info["Id"],
                "image": info["Image"],
                "restart_count": info["RestartCount"],
                "cpus": info["HostConfig"]["NanoCpus"] / 1e9,
                "memory_bytes": info["HostConfig"]["Memory"],
                "pids_limit": info["HostConfig"]["PidsLimit"],
            }
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        try:
            while not self.stop.is_set():
                result = subprocess.run(
                    [
                        *schema.resources.PREFIX,
                        "stats",
                        "--no-stream",
                        "--no-trunc",
                        "--format",
                        "{{json .}}",
                        *[v["id"] for v in self.identities.values()],
                    ],
                    capture_output=True,
                    timeout=8,
                    check=False,
                )
                require(
                    result.returncode == 0 and len(result.stdout) <= 65536,
                    "envelope_stats_command",
                )
                rows = [json.loads(line) for line in result.stdout.splitlines() if line]
                self.samples.append(
                    {
                        "elapsed_seconds": time.monotonic() - self.started,
                        "services": stats_sample(rows, self.identities),
                    }
                )
                require(len(self.samples) <= 240, "envelope_samples_budget")
                self.stop.wait(1)
        except BaseException as error:
            self.error = type(error).__name__

    def __enter__(self):
        self.started = time.monotonic()
        self.thread.start()
        return self

    def __exit__(self, kind, value, traceback):
        self.stop.set()
        self.thread.join(10)
        require(not self.thread.is_alive(), "envelope_sampler_shutdown")
        if kind is None:
            require(
                self.error is None and len(self.samples) >= 2,
                "envelope_observations_missing",
            )
            for record in self.identities.values():
                info = schema.resources.inspect("container", record["id"])
                require(
                    info["State"]["Running"]
                    and info["RestartCount"] == record["restart_count"],
                    "envelope_service_restarted",
                )

    def report(self):
        return {
            "method": "docker_cli_stats_no_stream_owned_ids",
            "sample_interval_seconds": 1,
            "memory_convention": "Docker Linux CLI usage minus cache; sampled observations, not exact peaks",
            "observer_overhead_included": True,
            "configured_services": self.identities,
            "samples": self.samples,
        }


def finished_pair(session, submitted):
    deadline = time.monotonic() + 135
    while True:
        jobs = [
            session.data("GET", "/api/jobs/" + item["id"] + "/") for item in submitted
        ]
        require(
            not any(j["state"] in ("failed", "blocked", "cancelled") for j in jobs),
            "envelope_job_failed",
        )
        if all(j["state"] == "succeeded" for j in jobs):
            return jobs
        require(time.monotonic() < deadline, "envelope_terminal_deadline")
        time.sleep(0.2)


def qualify(session, value, accounts, parent, prepared, adopted, command):
    cases = []
    with Sampler(value, prepared, adopted) as sampling:
        for rows, features, strategy, folds in CASES:
            pair = []
            for task in ("classification", "regression"):
                begin = time.monotonic()
                raw, options = dataset(task, rows, features, strategy)
                require(
                    options["validation"]["n_splits"] == folds, "envelope_fold_spec"
                )
                identifier = session.upload(
                    raw, "envelope-" + task + ".csv", accounts["project_id"]
                )
                base = f"/api/jobs/datasets/{identifier}/?project_id={accounts['project_id']}"
                started = time.monotonic()
                preview = session.data(
                    "POST",
                    f"/api/jobs/datasets/{identifier}/training-input/?project_id={accounts['project_id']}",
                    options,
                )
                require(
                    all(preview["budget"][k] == v for k, v in EXPECTED_BUDGET.items()),
                    "envelope_profile_changed",
                )
                request = dict(
                    options,
                    **{
                        k: preview[k]
                        for k in ("kind", "input_sha256", "training_sha256")
                    },
                    request_id=str(uuid.uuid4()),
                )
                queued = session.data("POST", base, request, 202)
                pair.append(
                    {
                        "id": queued["id"],
                        "task": task,
                        "rows": rows,
                        "features": features,
                        "validation": options["validation"],
                        "input_sha256": hashlib.sha256(raw).hexdigest(),
                        "input_bytes": len(raw),
                        "budget": preview["budget"],
                        "preview_and_submission_seconds": time.monotonic() - started,
                        "begin": begin,
                        "base": base,
                        "request": request,
                        "dataset": identifier,
                        "names": options["features"],
                    }
                )
            jobs = finished_pair(session, pair)
            overlap = max_overlap(jobs)
            for item, trained in zip(pair, jobs):
                export, headers = session.request(
                    "GET",
                    f"/api/jobs/{trained['id']}/candidate/?sha256={trained['result_sha256']}",
                )
                export_sha = hashlib.sha256(export).hexdigest()
                require(
                    headers["x-declarai-export-sha256"] == export_sha
                    and all(trained["result"][flag] is False for flag in FLAGS),
                    "envelope_export",
                )
                score_raw = (
                    ",".join(item["names"])
                    + "\n"
                    + "\n".join(
                        ",".join(str((i + j) / 7) for j in range(features))
                        for i in range(3)
                    )
                    + "\n"
                ).encode()
                input_id = session.upload(
                    score_raw, "envelope-score.csv", accounts["project_id"]
                )
                preview = session.data(
                    "POST",
                    f"/api/jobs/{trained['id']}/scoring-input/?project_id={accounts['project_id']}",
                    {
                        "input_file_id": input_id,
                        "training_result_sha256": trained["result_sha256"],
                    },
                )
                request = {
                    k: preview[k]
                    for k in (
                        "kind",
                        "training_job_id",
                        "training_result_sha256",
                        "input_file_id",
                        "input_sha256",
                        "scoring_sha256",
                    )
                }
                request["request_id"] = str(uuid.uuid4())
                queued = session.data("POST", item["base"], request, 202)
                scored = finished_pair(session, [queued])[0]
                raw_score, _ = session.request(
                    "GET",
                    f"/api/jobs/{scored['id']}/scores/?sha256={scored['result_sha256']}",
                )
                expected = offline_score(
                    value, prepared, export, export_sha, score_raw, command
                )
                require(
                    hashlib.sha256(raw_score).hexdigest() == scored["result_sha256"]
                    and scored["result"]["scores"] == expected["scores"]
                    and scored["result"]["n_scored"] == 3
                    and all(scored["result"][flag] is False for flag in FLAGS),
                    "envelope_score_parity",
                )
                require(
                    session.data("POST", item["base"], item["request"])["id"]
                    == trained["id"],
                    "envelope_idempotence",
                )
                public = {
                    k: v
                    for k, v in item.items()
                    if k not in ("begin", "base", "request", "dataset", "names")
                }
                cases.append(
                    {
                        **public,
                        "workflow_seconds": time.monotonic() - item["begin"],
                        "training": job_timing(trained),
                        "scoring": job_timing(scored),
                        "observed_pair_active": overlap,
                        "training_result_sha256": trained["result_sha256"],
                        "export_sha256": export_sha,
                        "scoring_result_sha256": scored["result_sha256"],
                        "prediction_values_sha256": hashlib.sha256(
                            json.dumps(
                                expected["scores"], sort_keys=True, allow_nan=False
                            ).encode()
                        ).hexdigest(),
                        "offline_chunk_parity": "passed",
                        "duplicate_submission": "single_job",
                    }
                )
        raw, options = dataset("classification", 1001, 2, "random")
        identifier = session.upload(
            raw, "envelope-overflow.csv", accounts["project_id"]
        )
        refused = session.data(
            "POST",
            f"/api/jobs/datasets/{identifier}/training-input/?project_id={accounts['project_id']}",
            options,
            409,
        )
        require(
            refused["error_code"] == "job_training_csv_profile_invalid",
            "envelope_overflow_refusal",
        )
    require(len(cases) == 6, "envelope_case_inventory")
    return {
        "schema": "private_workload_envelope_v1",
        "cases": cases,
        "resources": sampling.report(),
        "row_overflow": "refused_before_submission",
        "configured_job_concurrency": 2,
        "cold_root_repetition_required": True,
        "customer_capacity_qualified": False,
        "legacy_workload_envelope_qualified": False,
        "release_qualified": False,
    }


def comparison(envelopes, profiles, images):
    """Require repeatable supported work, preserve each measured run separately."""
    require(
        len(envelopes) == len(profiles) == 2
        and len({p["installation_id"] for p in profiles}) == 2,
        "envelope_independent_roots",
    )
    expected = {
        (task, rows, features, strategy, folds)
        for rows, features, strategy, folds in CASES
        for task in ("classification", "regression")
    }
    fingerprints = []
    for envelope, profile in zip(envelopes, profiles):
        require(
            envelope["schema"] == "private_workload_envelope_v1"
            and profile["application_images"] == images
            and envelope["customer_capacity_qualified"]
            is envelope["release_qualified"]
            is False,
            "envelope_scope",
        )
        cases = envelope["cases"]
        actual = {
            (
                c["task"],
                c["rows"],
                c["features"],
                c["validation"]["strategy"],
                c["validation"]["n_splits"],
            )
            for c in cases
        }
        require(
            len(cases) == 6
            and actual == expected
            and envelope["row_overflow"] == "refused_before_submission",
            "envelope_case_inventory",
        )
        require(
            all(
                math.isfinite(c["workflow_seconds"])
                and c["workflow_seconds"] > 0
                and c["offline_chunk_parity"] == "passed"
                and c["duplicate_submission"] == "single_job"
                and 1 <= c["observed_pair_active"] <= 2
                for c in cases
            ),
            "envelope_observed_outcome",
        )
        samples = envelope["resources"]["samples"]
        require(
            len(samples) >= 2
            and envelope["resources"]["observer_overhead_included"] is True,
            "envelope_resources_missing",
        )
        fingerprints.append(
            {
                (c["task"], c["rows"]): (
                    c["input_sha256"],
                    c["prediction_values_sha256"],
                )
                for c in cases
            }
        )
    require(fingerprints[0] == fingerprints[1], "envelope_repetition_changed")
    return {
        "schema": "private_workload_envelope_comparison_v1",
        "images": images,
        "clean_roots": 2,
        "profiles": profiles,
        "observations": envelopes,
        "same_seeded_inputs_and_predictions": True,
        "end_to_end_installed_workflows": True,
        "customer_capacity_qualified": False,
        "legacy_workload_envelope_qualified": False,
        "release_qualified": False,
        "limitations": [
            "Synthetic numeric development profile only; not a customer population.",
            "Sampled container observations are not exact resource peaks.",
            "Wall times include paired queueing, sequential score/export checks and observer overhead.",
            "No throughput guarantee or extrapolation beyond admitted bounds.",
        ],
    }
