"""Immutable, native numeric VIF inputs. No fitted Python state is loaded here."""

import json
from zipfile import BadZipFile
from pathlib import Path

import numpy as np

from modeling.diagnostics import DIAGNOSTIC_LIMITATIONS, numeric_diagnostic_inputs

METHOD = "centered_scaled_auxiliary_ols_v1"
META = "diagnostics/collinearity.json"
ARRAY = "diagnostics/collinearity.npz"
MAX_COLUMNS = 100
MAX_ROWS = 250_000
MAX_WORK = 100_000_000  # Explicit compute bound for repeated auxiliary solves.


def centered_inputs(frame):
    values = frame.to_numpy(dtype=float)
    if not values.size:
        return values
    # Subtract a reference first to preserve small variation around large offsets.
    with np.errstate(over="ignore"):
        differences = values - values[0]
    for index in range(values.shape[1]):
        if not np.isfinite(differences[:, index]).all():
            scaled = values[:, index] / np.max(np.abs(values[:, index]))
            differences[:, index] = scaled - scaled[0]
    scaled = differences / np.max(np.abs(differences), axis=0)
    centered = scaled - np.mean(scaled, axis=0)
    return centered / np.linalg.norm(centered, axis=0)


def vif(matrix, index):
    """Centered, unit-norm target makes VIF equal to 1 / residual SS."""
    target = matrix[:, index]
    others = np.delete(matrix, index, axis=1)
    tolerance = float(8 * np.finfo(float).eps * max(matrix.shape))
    record = {"vif": None, "vif_status": "unavailable", "residual_tolerance": tolerance}
    try:
        if others.shape[1]:
            coefficients, _, rank, _ = np.linalg.lstsq(others, target, rcond=None)
            residual = target - others @ coefficients
        else:
            residual, rank = target, 0
        residual_norm = float(np.linalg.norm(residual))
        if not np.isfinite(residual_norm):
            return {**record, "reason": "nonfinite_solver_result"}
        record["auxiliary_rank"] = int(rank)
        record["sample_saturated"] = int(rank) >= matrix.shape[0] - 1
        if residual_norm <= tolerance:
            return {**record, "vif_status": "unbounded", "reason": "perfect_or_numerically_indistinguishable"}
        return {**record, "vif": float(max(1.0, 1 / residual_norm**2)), "vif_status": "finite", "reason": None}
    except np.linalg.LinAlgError:
        return {**record, "reason": "linear_solver_failed"}


def write_snapshot(root, file_id, execution_id, frame, encoding_report=None):
    from modeling.grouped_collinearity import ARRAY as GROUP_ARRAY, snapshot as grouped_snapshot

    numeric, preparation = numeric_diagnostic_inputs(frame, encoding_report)
    columns = list(numeric.columns)
    work = len(frame) * len(columns) ** 3
    available = len(frame) <= MAX_ROWS and len(columns) <= MAX_COLUMNS and work <= MAX_WORK
    matrix = centered_inputs(numeric) if available else np.empty((0, len(columns)))
    records = {
        name: {"vif": None, "vif_status": reason, "reason": reason} for name, reason in preparation["excluded"].items()
    }
    for index, name in enumerate(columns):
        records[name] = (
            vif(matrix, index)
            if available
            else {"vif": None, "vif_status": "budget_exceeded", "reason": "diagnostic_compute_budget"}
        )
    summary = {
        "schema_version": 1,
        "method": METHOD,
        "status": "available" if available else "budget_exceeded",
        "execution_id": str(execution_id),
        "file_id": int(file_id),
        "row_count": len(frame),
        "columns": columns,
        "preparation": preparation,
        "budget": {
            "max_numeric_columns": MAX_COLUMNS,
            "max_training_rows": MAX_ROWS,
            "max_auxiliary_work": MAX_WORK,
            "estimated_auxiliary_work": work,
        },
        "scope": "Exploratory training-input dependence; no validation/final-outcome rows or labels.",
        "limitations": DIAGNOSTIC_LIMITATIONS["vif"],
        "features": records,
    }
    grouped, group_matrix = grouped_snapshot(frame, encoding_report)
    grouped.update(file_id=int(file_id), execution_id=str(execution_id))
    summary["grouped"] = grouped
    root = Path(root)
    (root / "diagnostics").mkdir(exist_ok=False)
    with (root / ARRAY).open("xb") as stream:
        np.savez_compressed(stream, matrix=matrix)
    with (root / GROUP_ARRAY).open("xb") as stream:
        np.savez_compressed(stream, matrix=group_matrix)
    with (root / META).open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    return summary


def load_snapshot(file_id, execution_id):
    from modeling.execution_artifacts import execution_root, load_execution

    _, manifest = load_execution(execution_id, file_id)
    if not all(name in manifest["files"] for name in (META, ARRAY)):
        raise ValueError("This execution has no verified centered diagnostic inputs. Refit a new version.")
    root = execution_root(execution_id)
    summary = json.loads((root / META).read_text())
    if not isinstance(summary, dict):
        raise ValueError("Invalid diagnostic metadata.")
    if (summary.get("schema_version"), summary.get("method"), summary.get("file_id"), summary.get("execution_id")) != (
        1,
        METHOD,
        file_id,
        str(execution_id),
    ):
        raise ValueError("Diagnostic method or execution identity does not match.")
    if summary.get("status") != "available":
        raise ValueError("Numeric diagnostic budget exceeded. Use a bounded feature subset and refit a new version.")
    columns = summary.get("columns")
    if (not isinstance(columns, list) or any(not isinstance(name, str) for name in columns)
        or not isinstance(summary.get("row_count"), int)
        or not isinstance(summary.get("features"), dict)
        or any(not isinstance(record, dict) for record in summary["features"].values())
        or any(name not in summary["features"] for name in columns)
        or any(key not in summary for key in ("scope", "preparation", "limitations"))):
        raise ValueError("Invalid diagnostic metadata.")
    if (
        len(columns) > MAX_COLUMNS
        or not 0 <= summary["row_count"] <= MAX_ROWS
        or summary["row_count"] * len(columns) ** 3 > MAX_WORK
        or len(set(columns)) != len(columns)
    ):
        raise ValueError("Invalid diagnostic dimensions.")
    try:
        with np.load(root / ARRAY, allow_pickle=False) as data:
            matrix = data["matrix"]
    except (BadZipFile, KeyError, EOFError) as exc:
        raise ValueError("Invalid native numeric diagnostic archive.") from exc
    if (
        matrix.dtype != np.float64
        or matrix.shape != (summary["row_count"], len(columns))
        or not np.isfinite(matrix).all()
    ):
        raise ValueError("Invalid native numeric diagnostic inputs.")
    if matrix.size and (
        not np.allclose(matrix.mean(axis=0), 0, atol=1e-10)
        or not np.allclose(np.linalg.norm(matrix, axis=0), 1, atol=1e-10)
    ):
        raise ValueError("Diagnostic inputs do not follow the recorded normalization.")
    return summary, matrix


def detail(summary, matrix, feature):
    if feature not in summary["features"]:
        raise KeyError(feature)
    columns = summary["columns"]
    result = {
        "feature": feature,
        **summary["features"][feature],
        "execution_id": summary["execution_id"],
        "method": METHOD,
        "scope": summary["scope"],
        "row_count": summary["row_count"],
        "preparation": summary["preparation"],
        "limitations": summary["limitations"],
        "contributions": [],
    }
    if feature not in columns:
        return result
    index = columns.index(feature)
    overall = vif(matrix, index)
    result.update(overall)
    for other_index, other in enumerate(columns):
        if other_index == index:
            continue
        reduced = vif(np.delete(matrix, other_index, axis=1), index - int(other_index < index))
        correlation = float(np.clip(matrix[:, index] @ matrix[:, other_index], -1, 1))
        drop = (
            max(0.0, overall["vif"] - reduced["vif"])
            if overall["vif"] is not None and reduced["vif"] is not None
            else None
        )
        result["contributions"].append(
            {
                "feature": other,
                "correlation": abs(correlation),
                "signed_correlation": correlation,
                "vif_without": reduced["vif"],
                "vif_without_status": reduced["vif_status"],
                "vif_drop": drop,
            }
        )
    result["contributions"].sort(key=lambda row: (-row["correlation"], row["feature"]))
    return result
