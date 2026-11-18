"""Reproduce a bounded native refit and final assessment in an isolated runtime."""

import argparse
import json
import os
import platform
import stat
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

from deployment import native_candidate
from deployment.runtime_metadata import package_version
from modeling import native_assessment_replay, native_training_replay

SCOPE = "native_refit_assessment_reproduction_v1"
ASSESSMENT_KIND = "native_protected_assessment_v1"
MAX_MANIFEST_BYTES = 2 * 1024**2
PACKAGES = ("Django", "numpy", "pandas", "scipy", "scikit-learn", "xgboost")
SOURCES = (
    "deployment/native_candidate.py",
    "deployment/offline_reproduce.py",
    "deployment/runtime_metadata.py",
    "evaluation/eval_utils.py",
    "modeling/booster_adapters.py",
    "modeling/declared_metric.py",
    "modeling/development_assessment.py",
    "modeling/development_validation.py",
    "modeling/fit_receipts.py",
    "modeling/native_assessment_replay.py",
    "modeling/native_training_replay.py",
    "modeling/paired_diagnostic_uncertainty.py",
    "modeling/prediction_contract.py",
    "modeling/rank_metrics.py",
    "modeling/sfs_objective.py",
    "modeling/split_contract.py",
    "preprocessing/purifier_contract.py",
)
ASSESSMENT_FIELDS = ("n_assessed", "population_checks", "primary_value", "metrics", "scores_sha256")


class ReplayBlocked(ValueError):
    """An actionable verification failure safe to record without source data."""


class ReplayMismatch(ReplayBlocked):
    """The computation completed but disagreed with recorded evidence."""


def digest(value):
    return native_candidate.sha(native_candidate.canonical(value))


def native_platform():
    return {"system": platform.system(), "machine": platform.machine(), "implementation": platform.python_implementation()}


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _uuid(value):
    return isinstance(value, str) and str(UUID(value)) == value


def _verify_runtime(recorded):
    root = Path(__file__).resolve().parents[1]
    if (recorded["python"] != sys.version.split()[0]
            or recorded["reproduction_platform"] != native_platform()
            or recorded["reproduction_platform"]["system"] != "Linux"
            or recorded["reproduction_platform"]["implementation"] != "CPython"
            or any(recorded["packages"].get(name) != package_version(name) for name in PACKAGES)
            or any(recorded["sources"].get(name) != native_candidate.sha((root / name).read_bytes())
                   for name in SOURCES)):
        raise ReplayBlocked("The installed replay runtime differs from the recorded Linux runtime.")


def reference_fit(result):
    """Record development evidence without including the executable model artifact."""
    evidence = {
        "model_sha256": native_candidate.sha(result["model_json"].encode()),
        "refit_receipt": result["refit_receipt"],
        "refit_preprocessing": result["refit_preprocessing"],
        "candidates": result["candidates"],
        "selected_max_depth": result["selected_max_depth"],
        "selection_rule": result["selection_rule"],
    }
    if "paired_diagnostics" in result:
        evidence["paired_diagnostics"] = result["paired_diagnostics"]
    return evidence


def _checked_members(manifest):
    training, assessment = manifest["training"], manifest["assessment"]
    train_spec, spec, result = training["specification"], assessment["specification"], assessment["result"]
    plan, seal = train_spec["training"], manifest["protected_input"]
    adoption = manifest["adoption"]
    proposal, approval = adoption["proposal"], adoption["approval"]
    train_sha, plan_sha = training["result_sha256"], digest(plan)
    protected_spec = seal["specification"]
    outcome = manifest["outcome_access"]
    project_id, dataset_id = manifest["project_id"], manifest["dataset_id"]
    ids = (project_id, training["job_id"], assessment["job_id"], adoption["id"], approval["id"], seal["id"],
           result["outcome_access_id"])
    if (manifest["schema_version"] != 1 or manifest["scope"] != SCOPE
            or not all(_uuid(value) for value in ids)
            or type(dataset_id) is not int or dataset_id < 1
            or plan["source"]["file_id"] != dataset_id or spec["project_id"] != project_id):
        raise ReplayBlocked("Reproduction manifest identity is inconsistent.")

    if (train_spec["kind"] != native_training_replay.KIND or train_spec["schema_version"] != 1
            or type(plan["schema_version"]) is not int
            or plan["schema_version"] not in (1, native_training_replay.PLAN_SCHEMA)
            or ("paired_diagnostics" in training["fit"]) != (
                plan["schema_version"] == native_training_replay.PLAN_SCHEMA
            )
            or plan["profile"] != {"kind": train_spec["kind"], "runtime": train_spec["runtime"], "limits": train_spec["limits"]}
            or any(train_spec["limits"].get(key) != value for key, value in native_training_replay.BUDGET.items())
            or plan_sha != train_spec["training_sha256"]
            or digest(train_spec) != spec["training_specification_sha256"]
            or train_sha != spec["training_result_sha256"] or training["job_id"] != spec["training_job_id"]):
        raise ReplayBlocked("Reproduction manifest contains inconsistent development evidence.")

    reviewer_id = approval["payload"]["actor"]["id"]
    protocol = spec.get("confirmation_protocol")
    if (adoption["id"] != spec["adoption_id"] or digest(proposal) != spec["proposal_sha256"]
            or proposal["training_job_id"] != training["job_id"] or proposal["training_result_sha256"] != train_sha
            or proposal["export_sha256"] != spec["candidate_export_sha256"]
            or approval["kind"] != "approve" or approval["revision"] != 1 or approval["id"] != spec["approval_event_id"]
            or (protocol is not None and protocol["approved_at"] != approval["created_at"])
            or digest(approval["payload"]) != spec["approval_sha256"]
            or reviewer_id in (proposal["actor"]["id"], training["actor"]["id"])
            or approval["payload"]["proposal_sha256"] != spec["proposal_sha256"]
            or protected_spec["actor"]["id"] != reviewer_id
            or protected_spec["authority"] != approval["payload"]["authority"]
            or seal["id"] != spec["protected_input_id"] or digest(protected_spec) != spec["protected_input_sha256"]
            or protected_spec["adoption_id"] != adoption["id"] or protected_spec["approval_event_id"] != approval["id"]
            or protected_spec["proposal_sha256"] != spec["proposal_sha256"]
            or protected_spec["scope"] != "sealed_native_outcomes_v1"
            or protected_spec["input_sha256"] != spec["input_sha256"]
            or protected_spec.get("confirmation_protocol") != spec.get("confirmation_protocol")
            or plan["source"]["sha256"] == protected_spec["input_sha256"]):
        raise ReplayBlocked("Reproduction manifest contains inconsistent approval or sealed outcome evidence.")

    if (spec["kind"] != ASSESSMENT_KIND or spec["schema_version"] != 2
            or spec["limits"]["chunk_size"] != native_assessment_replay.CHUNK_SIZE
            or digest({key: value for key, value in spec.items() if key != "assessment_sha256"}) != spec["assessment_sha256"]
            or digest({key: result[key] for key in spec}) != digest(spec)
            or result["job_id"] != assessment["job_id"] or result["scope"] != ASSESSMENT_KIND
            or digest(result) != assessment["result_sha256"]
            or result["prediction_contract"] != plan["prediction_contract"]
            or result["prediction_contract"] != proposal["prediction_contract"]
            or result["metric"] != proposal["metric"]
            or plan["options"]["features"] != proposal["features"]
            or digest(result["prediction_contract"]) != spec["prediction_contract_sha256"]
            or digest(result["metric"]) != spec["metric_sha256"]
            or digest(spec["assessment_policy"]) != spec["assessment_policy_sha256"]
            or result["final_holdout_accessed"] is not True
            or result["review_approved"] is not False or result["production_use_approved"] is not False
            or any(not _sha(value) for value in (train_sha, plan["source"]["sha256"], protected_spec["input_sha256"],
                   result["scores_sha256"], training["fit"]["model_sha256"], spec["candidate_export_sha256"]))):
        raise ReplayBlocked("Reproduction manifest contains inconsistent assessment evidence.")

    receipt_fields = {
        "id": result["outcome_access_id"], "actor_id": reviewer_id,
        "evidence_status": result["evidence_status"], "attempt_state": "completed",
        "assessment_sha256": spec["assessment_sha256"], "outcomes_sha256": spec["input_sha256"],
    }
    if digest({key: outcome[key] for key in receipt_fields}) != digest(receipt_fields):
        raise ReplayBlocked("Reproduction manifest contains an inconsistent outcome access receipt.")
    _verify_runtime(train_spec["runtime"])
    _verify_runtime(spec["runtime"])
    return training, assessment, plan, protected_spec


def parse_manifest(raw, expected_sha256):
    if not _sha(expected_sha256) or not 0 < len(raw) <= MAX_MANIFEST_BYTES or native_candidate.sha(raw) != expected_sha256:
        raise ReplayBlocked("Reproduction manifest does not match its independently supplied digest.")
    try:
        manifest = json.loads(raw)
        return manifest, _checked_members(manifest)
    except ReplayBlocked:
        raise
    except (ValueError, KeyError, TypeError, OSError, RecursionError):
        raise ReplayBlocked("Reproduction manifest is malformed or uses an unsupported profile.") from None


def _read_regular(path, limit):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                raise ValueError
            raw = stream.read(limit + 1)
            if not 0 < len(raw) <= limit:
                raise ValueError
            return raw
    except (OSError, ValueError):
        raise ReplayBlocked("Replay input must be a readable, bounded regular file.") from None


def _input(path, record, role):
    raw = _read_regular(path, native_training_replay.BUDGET["max_input_bytes"])
    if len(raw) != record["bytes"] or native_candidate.sha(raw) != record["sha256"]:
        raise ReplayBlocked(f"The supplied {role} CSV differs from the recorded bytes.")
    return raw


def reproduce(manifest_path, manifest_sha256, development_path, outcomes_path):
    raw = _read_regular(manifest_path, MAX_MANIFEST_BYTES)
    manifest, (training, assessment, plan, seal) = parse_manifest(raw, manifest_sha256)
    development = _input(development_path, plan["source"], "development")
    contract, folds, context = native_training_replay.prepare_training(development, plan["options"])
    if contract != plan["prediction_contract"] or folds != plan["folds"]:
        raise ReplayMismatch("The declaration or ordered development folds could not be reproduced.")

    train_spec = training["specification"]
    fitted = native_training_replay.fit_prepared(
        plan, context, job_id=training["job_id"], training_sha256=train_spec["training_sha256"],
        runtime=train_spec["runtime"],
    )
    result_sha256 = digest(fitted)
    if result_sha256 != training["result_sha256"] or digest(reference_fit(fitted)) != digest(training["fit"]):
        raise ReplayMismatch("The refitted model, transformations or development evidence differ from the recorded fit.")
    fresh_export = native_candidate.export_candidate(
        training["job_id"], manifest["dataset_id"], manifest["project_id"], fitted, result_sha256,
    )
    candidate_digest = native_candidate.sha(fresh_export)
    expected = assessment["result"]
    if candidate_digest != expected["candidate_export_sha256"]:
        raise ReplayMismatch("The freshly refitted candidate differs from the one approved for assessment.")

    # Outcomes first become readable after exact reproduction of the development-only candidate.
    outcomes = _input(outcomes_path, {"bytes": seal["bytes"], "sha256": seal["input_sha256"]}, "protected outcomes")
    frame = native_training_replay.parsed_frame(outcomes)
    if list(frame.columns) != seal["header"] or len(frame) != seal["rows"]:
        raise ReplayBlocked("The protected CSV layout differs from its recorded seal.")
    as_of = datetime.fromisoformat(seal["assessment_as_of"])
    if as_of.tzinfo is None:
        raise ReplayBlocked("The original assessment clock must include a timezone.")

    def predict(features):
        return native_candidate.score(fresh_export, candidate_digest, features, chunk_size=native_assessment_replay.CHUNK_SIZE)["scores"]

    replay = native_assessment_replay.calculate_assessment(
        frame, native_training_replay.parsed_frame(development), plan["options"]["validation"], as_of,
        contract, fitted["metric"], fitted["features"], predict,
    )
    if digest(replay) != digest({field: expected[field] for field in ASSESSMENT_FIELDS}):
        raise ReplayMismatch("Reproduced final scores, metrics or population checks differ from recorded assessment.")
    return {
        "schema_version": 1, "scope": SCOPE, "status": "passed", "task": contract["task"],
        "manifest_sha256": manifest_sha256, "training_result_sha256": result_sha256,
        "assessment_result_sha256": assessment["result_sha256"],
        "development_sha256": plan["source"]["sha256"], "outcomes_sha256": seal["input_sha256"],
        "candidate_export_sha256": candidate_digest, "model_sha256": training["fit"]["model_sha256"],
        "scores_sha256": replay["scores_sha256"], "outcome_access_id": expected["outcome_access_id"],
        "n_assessed": replay["n_assessed"], "model_refit_reproduced": True, "assessment_reproduced": True,
        "comparison": "exact_canonical_result_and_scores_sha256",
        "confirmation_granted": False, "review_approved": False, "production_use_approved": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "manifest-sha256", "development", "outcomes", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    # Reserve a unique outcome before any approved data is opened.
    with Path(args.output).open("x", encoding="utf-8") as stream:
        try:
            report = reproduce(args.manifest, args.manifest_sha256, args.development, args.outcomes)
        except Exception as error:
            report = {
                "schema_version": 1, "scope": SCOPE,
                "status": "failed" if isinstance(error, ReplayMismatch) else "blocked",
                "error": str(error) if isinstance(error, ReplayBlocked) else "Native refit or assessment reproduction could not complete.",
                "model_refit_reproduced": False, "assessment_reproduced": False,
                "confirmation_granted": False, "review_approved": False, "production_use_approved": False,
            }
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ("scope", "status")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
