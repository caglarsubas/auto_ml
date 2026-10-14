"""Restore only explicit, internally consistent selection checkpoints."""

from modeling.sfs_objective import validate_resume
from modeling.sfs_state import read_recorded_sfs


def restore_sfs_resume(path, basis):
    record = read_recorded_sfs(path)
    if record["status"] not in ("running", "interrupted", "stopped"):
        raise ValueError("Recorded selection is not resumable. Start a fresh search; history remains inspectable.")
    validate_resume({"resume_basis": record.get("resume_basis")}, basis)
    explicit = record.get("resume_state")
    if explicit is not None:
        if not isinstance(explicit, dict):
            raise ValueError("Recorded resume state must be an object. Inspect the evidence before continuing.")
        validate_resume({"resume_basis": explicit.get("resume_basis")}, basis)
    source = explicit if explicit is not None else record
    baselines = source.get("baselines", {})
    if not isinstance(baselines, dict):
        raise ValueError("Recorded selection baselines are malformed. Inspect the evidence before continuing.")
    pool = basis["train"]["features"]
    methods = basis["methods"]
    keys = record.get("resume_direction_keys")
    if keys is not None and (not isinstance(keys, dict) or set(keys) != set(methods) or
                             any(keys[mode] not in (("forward", "forward_from_backward") if mode == "forward"
                                                  else ("backward",)) for mode in methods)):
        raise ValueError("Recorded active selection directions are malformed. Start a fresh search.")
    restored = {"resume_basis": basis, "baselines": baselines, "completed_steps": []}
    for mode in methods:
        if explicit is not None:
            steps = source.get(mode + "_results", [])
        elif keys is not None:
            steps = source.get(keys[mode], [])
        else:
            # Older simple checkpoints can be read; ambiguous merged directions
            # cannot be assigned to an operation as historical certainty.
            if mode == "forward" and source.get("forward_from_backward"):
                if source.get("forward"):
                    raise ValueError("Recorded forward checkpoint is ambiguous. Start a fresh search.")
                steps = source["forward_from_backward"]
            else:
                steps = source.get(mode, [])
        if not isinstance(steps, list):
            raise ValueError("Recorded selection steps must be a list. Inspect the evidence before continuing.")
        expected_features = [] if mode == "forward" else pool
        for index, step in enumerate(steps, 1):
            if not isinstance(step, dict) or type(step.get("step")) is not int or step["step"] != index:
                raise ValueError("Recorded selection steps are not a contiguous sequence. Start a fresh search.")
            if step.get("direction") != mode or step.get("search_basis_sha256") != basis["sha256"]:
                raise ValueError("Recorded selection steps have a different or unverified search basis. Start a fresh search.")
            features = step.get("selected_features")
            if (not isinstance(features, list) or not features or
                    any(not isinstance(feature, str) or feature not in pool for feature in features) or
                    len(set(features)) != len(features)):
                raise ValueError("Recorded selected features are outside the accepted pool or malformed. Start a fresh search.")
            if mode == "forward":
                valid_change = len(features) == len(expected_features) + 1 and features[:-1] == expected_features
            else:
                removed = [feature for feature in expected_features if feature not in features]
                valid_change = len(removed) == 1 and features == [feature for feature in expected_features if feature not in removed]
            if not valid_change:
                raise ValueError("Recorded feature changes contradict the selection sequence. Start a fresh search.")
            expected_features = features
        feature_key = "forward_selected_features" if mode == "forward" else "backward_current_features"
        if explicit is not None and feature_key in source and source[feature_key] != expected_features:
            raise ValueError("Recorded resume features contradict the saved steps. Start a fresh search.")
        previous = source.get(mode + "_previous_metrics") if explicit is not None else None
        if previous is not None and (not isinstance(previous, dict) or not steps):
            raise ValueError("Recorded previous metrics lack matching selection steps. Start a fresh search.")
        restored[mode + "_results"] = steps
        restored[feature_key] = expected_features
        restored["completed_steps"].extend(steps)
    if explicit is not None and source.get("completed_steps", []) != restored["completed_steps"]:
        raise ValueError("Recorded completed steps contradict the saved directions. Start a fresh search.")
    return restored
