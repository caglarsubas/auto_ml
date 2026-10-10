"""Training-input subspace diagnostics, without targets or arbitrary category order."""

import numpy as np
import pandas as pd

from modeling.diagnostics import CATEGORY_ENCODINGS, numeric_diagnostic_inputs

METHOD = "centered_group_subspace_gvif_v1"
ARRAY = "diagnostics/grouped_collinearity.npz"
MAX_COLUMNS = 100
MAX_ROWS = 250_000
MAX_WORK = 100_000_000
LIMITATIONS = (
    "Descriptive, unweighted training-input dependence between selected predictor groups. "
    "Scalar category codes represent nominal partitions; manual groups represent the observed merged partition. "
    "One-hot groups use only selected recorded output columns. Numeric means use training rows only. "
    "GVIF and GVIF^(1/(2 df)) describe subspaces, not fitted booster coefficient uncertainty, model importance, "
    "causation, a statistical test or a feature-removal threshold. Sampling uncertainty and interactions are not assessed. "
    "Unavailable groups block the calculation rather than silently reducing its conditioning set."
)


def _basis(values):
    # Remove zero columns before centering/scaling, including unused one-hot levels.
    from modeling.collinearity import centered_inputs

    frame = pd.DataFrame(values)
    frame = frame.loc[:, (frame != frame.iloc[0]).any()] if len(frame) else frame.iloc[:, :0]
    if frame.shape[1] == 0:
        return np.empty((len(frame), 0))
    matrix = centered_inputs(frame)
    u, singular, _ = np.linalg.svd(matrix, full_matrices=False)
    tolerance = 8 * np.finfo(float).eps * max(matrix.shape) * singular[0]
    return u[:, singular > tolerance]


def group_metric(target, others):
    """Reciprocal residual-volume ratio for an orthonormal centered target basis."""
    df = target.shape[1]
    tolerance = float(8 * np.finfo(float).eps * max(target.shape[0], df + others.shape[1]))
    record = {"df": df, "gvif": None, "adjusted_gvif": None, "log_gvif": None,
              "status": "unavailable", "residual_tolerance": tolerance}
    if not df:
        return {**record, "status": "constant", "reason": "zero_training_subspace"}
    try:
        if others.shape[1]:
            u, singular, _ = np.linalg.svd(others, full_matrices=False)
            rank = int(np.sum(singular > tolerance * singular[0]))
            basis = u[:, :rank]
            residual = target - basis @ (basis.T @ target)
        else:
            rank, residual = 0, target
        singular = np.linalg.svd(residual, compute_uv=False)
        if not np.isfinite(singular).all() or np.any(singular > 1 + tolerance):
            return {**record, "reason": "nonfinite_or_invalid_solver_result"}
        record.update(conditioning_rank=rank, sample_saturated=rank >= target.shape[0] - 1)
        if singular[-1] <= tolerance:
            return {**record, "status": "unbounded", "reason": "intersecting_or_numerically_indistinguishable_subspaces"}
        log_value = float(max(0., -2 * np.log(np.minimum(singular, 1)).sum()))
        value = float(np.exp(log_value)) if log_value <= np.log(np.finfo(float).max) else None
        return {**record, "status": "finite" if value is not None else "overflow",
                "reason": None if value is not None else "gvif_exceeds_float_range",
                "gvif": value, "log_gvif": log_value, "adjusted_gvif": float(np.exp(log_value / (2 * df)))}
    except np.linalg.LinAlgError:
        return {**record, "reason": "linear_solver_failed"}


def calculate(matrix, groups):
    """Replay exactly the recorded group bases; no fitted Python state is required."""
    result = {}
    for name, group in groups.items():
        start, end = group["slice"]
        target = matrix[:, start:end]
        others = np.concatenate([matrix[:, :start], matrix[:, end:]], axis=1)
        result[name] = {**group, **group_metric(target, others)}
    return result


def snapshot(frame, encoding_report=None):
    numeric, preparation = numeric_diagnostic_inputs(frame, encoding_report)
    groups, inputs, claimed, blocked = {}, {}, set(), {}
    width = 0
    for entry in encoding_report or []:
        spec = entry.get("mapping") or {}
        kind = spec.get("type") or entry.get("strategy_applied") or entry.get("strategy")
        if kind not in CATEGORY_ENCODINGS:
            continue
        name = entry.get("feature")
        declared = spec.get("columns") if kind == "one_hot_encoding" else [name]
        if not isinstance(name, str) or not isinstance(declared, list) or any(not isinstance(c, str) for c in declared):
            blocked[str(name)] = "invalid_encoding_provenance"
            continue
        columns = [c for c in declared if c in frame]
        if not columns:
            continue  # A candidate may omit this entire group.
        if name in groups or len(set(columns)) != len(columns) or claimed.intersection(columns):
            blocked[name] = "overlapping_encoding_provenance"
            continue
        claimed.update(columns)
        groups[name] = {"kind": "categorical", "encoding": kind, "columns": columns,
                        "representation": "selected_one_hot_columns" if kind == "one_hot_encoding" else "observed_nominal_partition"}
        if kind in {"frequency_encoding", "target_encoding"}:
            blocked[name] = "original_category_partition_unavailable"
            continue
        if kind == "one_hot_encoding":
            count = len(columns)
            width += count
            groups[name]["input_dimensions"] = count
            if len(frame) > MAX_ROWS or width > MAX_COLUMNS or len(frame) * width ** 3 > MAX_WORK:
                continue  # Do not allocate a dense group after exceeding a bound.
            try:
                values = frame[columns].to_numpy(dtype=float, na_value=np.nan)
            except (TypeError, ValueError):
                blocked[name] = "invalid_one_hot_values"
                continue
            if not np.isin(values, [0., 1.]).all() or np.any(values.sum(axis=1) > 1):
                blocked[name] = "invalid_one_hot_values"
                continue
            counts = values.sum(axis=0).astype(int).tolist()
            inputs[name] = values
        else:
            codes, levels = pd.factorize(frame[columns[0]], sort=False, use_na_sentinel=False)
            count = len(levels)
            counts = np.bincount(codes, minlength=count).tolist()
            inputs[name] = codes  # Delay indicator allocation until all budgets pass.
            width += count
        groups[name].update(input_dimensions=count, support_counts=sorted(counts))
    if not groups and not blocked:
        return {"schema_version": 1, "method": METHOD, "status": "not_applicable",
                "reason": "no_selected_category_groups", "groups": {}, "limitations": LIMITATIONS}, np.empty((0, 0))
    for name in frame:
        if name in claimed:
            continue
        if name in numeric:
            if name in groups:
                blocked[name] = "ambiguous_group_name"
                continue
            groups[name] = {"kind": "numeric", "columns": [name], "representation": "centered_numeric_predictor", "input_dimensions": 1}
            inputs[name] = numeric[[name]].to_numpy(dtype=float)
            width += 1
        elif preparation["excluded"].get(name) not in {"constant", "insufficient_rows"}:
            blocked[name] = "unsupported_training_predictor"
    work = len(frame) * width ** 3
    budget_exceeded = len(frame) > MAX_ROWS or width > MAX_COLUMNS or work > MAX_WORK
    reason = "incomplete_group_provenance" if blocked else "diagnostic_compute_budget" if budget_exceeded else "insufficient_rows" if len(frame) < 2 else None
    result = {"schema_version": 1, "method": METHOD, "status": "unavailable" if blocked or len(frame) < 2 else "budget_exceeded" if budget_exceeded else "available",
              "reason": reason, "groups": groups, "blocked_groups": blocked,
              "row_count": len(frame), "preparation": preparation, "limitations": LIMITATIONS,
              "scope": "Exploratory selected training-input groups; no targets, validation or final-outcome rows.",
              "budget": {"max_expanded_columns": MAX_COLUMNS, "max_training_rows": MAX_ROWS,
                         "max_auxiliary_work": MAX_WORK, "expanded_columns": width, "estimated_auxiliary_work": work}}
    if reason:
        result["groups"] = {name: {**group, "df": None, "gvif": None, "adjusted_gvif": None,
                                   "status": result["status"], "reason": blocked.get(name, reason)} for name, group in groups.items()}
        return result, np.empty((0, 0))

    bases, offset = [], 0
    try:
        for name, group in groups.items():
            values = inputs[name]
            if values.ndim == 1:
                values = (values[:, None] == np.arange(group["input_dimensions"])).astype(float)
            basis = _basis(values)
            group["slice"] = [offset, offset + basis.shape[1]]
            offset += basis.shape[1]
            bases.append(basis)
        matrix = np.concatenate(bases, axis=1)
        result["groups"] = calculate(matrix, groups)
        return result, matrix
    except np.linalg.LinAlgError:
        result.update(status="unavailable", reason="linear_solver_failed")
        result["groups"] = {name: {**group, "df": None, "gvif": None, "adjusted_gvif": None,
                                   "status": "unavailable", "reason": "linear_solver_failed"} for name, group in groups.items()}
        return result, np.empty((0, 0))


def load_snapshot(file_id, execution_id):
    """Verify retained native bases and replay grouped metrics for an exact execution."""
    import json
    from zipfile import BadZipFile, ZipFile

    from modeling.collinearity import META
    from modeling.execution_artifacts import execution_root, load_execution

    _, manifest = load_execution(execution_id, file_id)
    if not all(name in manifest["files"] for name in (META, ARRAY)):
        raise ValueError("This execution has no verified grouped diagnostic inputs. Refit a new version.")
    root = execution_root(execution_id)
    metadata = json.loads((root / META).read_text())
    summary = metadata.get("grouped") if isinstance(metadata, dict) else None
    if not isinstance(summary, dict) or (summary.get("schema_version"), summary.get("method"), summary.get("file_id"), summary.get("execution_id")) != (1, METHOD, file_id, str(execution_id)):
        raise ValueError("Grouped diagnostic method or execution identity does not match.")
    if summary.get("status") != "available":
        raise ValueError("Grouped diagnostic inputs are unavailable. Inspect the recorded reason and refit a supported bounded subset.")
    rows, groups, budget = summary.get("row_count"), summary.get("groups"), summary.get("budget")
    if (type(rows) is not int or not 2 <= rows <= MAX_ROWS or not isinstance(groups, dict)
        or not groups or len(groups) > MAX_COLUMNS or not isinstance(budget, dict)
        or type(budget.get("expanded_columns")) is not int or not 0 < budget["expanded_columns"] <= MAX_COLUMNS
        or rows * budget["expanded_columns"] ** 3 > MAX_WORK or summary.get("blocked_groups") != {}):
        raise ValueError("Invalid grouped diagnostic dimensions or provenance.")
    offset, input_dimensions, claimed = 0, 0, set()
    for name, group in groups.items():
        if (not isinstance(name, str) or not isinstance(group, dict) or not isinstance(group.get("slice"), list)
            or len(group["slice"]) != 2 or any(type(x) is not int for x in group["slice"])
            or group["slice"][0] != offset or group["slice"][1] < offset or group["slice"][1] > MAX_COLUMNS
            or group.get("df") != group["slice"][1] - offset):
            raise ValueError("Invalid grouped diagnostic layout.")
        columns = group.get("columns")
        dimensions = group.get("input_dimensions")
        if (not isinstance(columns, list) or not columns or any(not isinstance(c, str) for c in columns)
            or len(set(columns)) != len(columns) or claimed.intersection(columns)
            or type(dimensions) is not int or not 1 <= dimensions <= MAX_COLUMNS
            or group["slice"][1] - offset > dimensions or group.get("kind") not in {"numeric", "categorical"}):
            raise ValueError("Invalid grouped diagnostic provenance.")
        claimed.update(columns)
        input_dimensions += dimensions
        offset = group["slice"][1]
    if offset > budget["expanded_columns"] or input_dimensions != budget["expanded_columns"]:
        raise ValueError("Invalid grouped diagnostic width.")
    try:
        with ZipFile(root / ARRAY) as archive:
            entries = archive.infolist()
            if len(entries) != 1 or entries[0].filename != "matrix.npy" or entries[0].file_size > rows * offset * 8 + 4096:
                raise ValueError("Grouped diagnostic archive exceeds its recorded allocation.")
            with archive.open(entries[0]) as stream:
                version = np.lib.format.read_magic(stream)
                readers = {(1, 0): np.lib.format.read_array_header_1_0,
                           (2, 0): np.lib.format.read_array_header_2_0}
                if version not in readers:
                    raise ValueError("Unsupported grouped array format.")
                shape, _, dtype = readers[version](stream, max_header_size=4096)
                if shape != (rows, offset) or dtype != np.dtype('float64'):
                    raise ValueError("Grouped array header does not match recorded dimensions or dtype.")
                if entries[0].file_size != stream.tell() + rows * offset * 8:
                    raise ValueError("Grouped array payload does not match its header.")
        with np.load(root / ARRAY, allow_pickle=False) as data:
            matrix = data["matrix"]
    except (BadZipFile, KeyError, EOFError) as exc:
        raise ValueError("Invalid grouped diagnostic archive.") from exc
    if matrix.dtype != np.float64 or matrix.shape != (rows, offset) or not np.isfinite(matrix).all():
        raise ValueError("Invalid grouped diagnostic inputs.")
    for group in groups.values():
        start, end = group["slice"]
        basis = matrix[:, start:end]
        if basis.size and (not np.allclose(basis.mean(axis=0), 0, rtol=0, atol=1e-10)
                           or not np.allclose(basis.T @ basis, np.eye(end - start), rtol=0, atol=1e-10)):
            raise ValueError("Grouped diagnostic inputs do not follow the recorded normalization.")
    replayed = calculate(matrix, groups)
    for name, record in replayed.items():
        if record["status"] != groups[name].get("status"):
            raise ValueError("Grouped diagnostic state does not match retained inputs.")
        for key in ("gvif", "adjusted_gvif", "log_gvif"):
            original = groups[name].get(key)
            if ((record[key] is None) != (original is None)
                or (original is not None and (not isinstance(original, (int, float))
                    or not np.isfinite(original) or not np.isclose(original, record[key], rtol=1e-10, atol=1e-10)))):
                raise ValueError("Grouped diagnostic value does not match retained inputs.")
    return {**summary, "groups": replayed}
