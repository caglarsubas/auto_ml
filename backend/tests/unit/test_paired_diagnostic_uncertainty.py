"""Paired development diagnostics preserve the declared comparison population."""

from copy import deepcopy
import json

import pytest

from modeling.paired_diagnostic_uncertainty import compare_paired_folds

pytestmark = pytest.mark.unit

ROCAUC = {"primary_metric": "roc_auc", "direction": "maximize"}
RANDOM = {"strategy": "random", "n_splits": 2}


def _fold(score, train_rows, valid_rows):
    return {
        "score": score,
        "preprocessing": {"train_rows": list(train_rows), "valid_rows": list(valid_rows)},
    }


def _two_folds():
    return [_fold(0.5, [2, 3], [0, 1]), _fold(0.7, [0, 1], [2, 3])]


def _assert_unavailable(record, reason_code):
    assert record["status"] == "unavailable"
    assert record["reason_code"] == reason_code
    assert record["fold_pairs"] == []
    assert record["effect"] is None
    assert record["sensitivity"] is None
    assert record["sampling_uncertainty"]["status"] == "unavailable"
    json.dumps(record, allow_nan=False)


def test_equal_fold_effect_and_sensitivity_preserve_uneven_grouped_folds():
    reference = [
        _fold(0.5, [2, 3, 4, 5, 6, 7, 8], [0, 1]),
        _fold(0.5, [0, 1, 5, 6, 7, 8], [2, 3, 4]),
        _fold(0.5, [0, 1, 2, 3, 4], [5, 6, 7, 8]),
    ]
    candidate = deepcopy(reference)
    for fold, score in zip(candidate, [0.8, 0.7, 0.4]):
        fold["score"] = score
    record = compare_paired_folds(reference, candidate, metric=ROCAUC, validation={
        "strategy": "group", "n_splits": 3, "group_column": "entity",
    })

    assert record["status"] == "completed"
    assert record["validation_strategy"] == "group"
    assert record["effect"]["method"] == "equal_weight_matched_fold_mean"
    assert record["effect"]["n_validation_rows"] == 9
    assert record["effect"]["reference_score"] == pytest.approx(0.5)
    assert record["effect"]["candidate_score"] == pytest.approx(19 / 30)
    assert record["effect"]["difference"] == pytest.approx(0.4 / 3)
    assert record["effect"]["improvement"] == pytest.approx(0.4 / 3)
    assert [row["n_validation_rows"] for row in record["fold_pairs"]] == [2, 3, 4]
    assert [row["improvement"] for row in record["fold_pairs"]] == pytest.approx([0.3, 0.2, -0.1])
    sensitivity = record["sensitivity"]
    assert sensitivity["method"] == "leave_one_validation_fold_out"
    assert sensitivity["lower_improvement"] == pytest.approx(0.05)
    assert sensitivity["upper_improvement"] == pytest.approx(0.25)
    assert [row["omitted_fold"] for row in sensitivity["omissions"]] == [1, 2, 3]
    assert [row["improvement"] for row in sensitivity["omissions"]] == pytest.approx([0.05, 0.10, 0.25])
    assert record["sampling_uncertainty"] == {
        "status": "unavailable", "reason_code": "dependent_development_folds",
    }
    assert all(word not in json.dumps(record, allow_nan=False) for word in ("train_rows", "valid_rows", "p_value"))


def test_minimized_metric_keeps_signed_change_and_orients_improvement_in_temporal_folds():
    # Row 4 from the earlier validation fold is eligible to train the later
    # fold. This does not make the held-out row memberships overlap.
    reference = [_fold(6, [0, 1], [4]), _fold(3, [0, 1, 2, 3, 4], [7, 8])]
    candidate = [_fold(4, [0, 1], [4]), _fold(4, [0, 1, 2, 3, 4], [7, 8])]
    record = compare_paired_folds(
        reference, candidate, metric={"primary_metric": "rmse", "direction": "minimize"},
        validation={"strategy": "oot", "n_splits": 2, "date_column": "origin",
                    "label_end_column": "end", "group_column": "entity"},
    )
    assert record["status"] == "completed"
    assert record["metric"] == "rmse"
    assert record["validation_strategy"] == "oot"
    assert record["effect"]["difference"] == -0.5
    assert record["effect"]["improvement"] == 0.5
    assert record["sensitivity"]["lower_improvement"] == -1
    assert record["sensitivity"]["upper_improvement"] == 2
    assert record["sampling_uncertainty"]["reason_code"] == "dependent_development_folds"


def test_tied_folds_have_zero_effect_and_zero_sensitivity_without_inferential_precision():
    for direction in ("maximize", "minimize"):
        metric = {**ROCAUC, "direction": direction}
        record = compare_paired_folds(_two_folds(), _two_folds(), metric=metric, validation=RANDOM)
        assert record["status"] == "completed"
        assert record["effect"]["difference"] == 0
        assert record["effect"]["improvement"] == 0
        assert record["sensitivity"]["lower_improvement"] == 0
        assert record["sensitivity"]["upper_improvement"] == 0
        assert record["sampling_uncertainty"]["status"] == "unavailable"
        assert all(pair["improvement"].hex() == "0x0.0p+0" for pair in record["fold_pairs"])


@pytest.mark.parametrize(("partition", "rows"), [
    ("train_rows", [3, 2]),
    ("train_rows", [2, 10]),
    ("valid_rows", [1, 0]),
    ("valid_rows", [0, 10]),
])
def test_rejects_swapped_or_different_ordered_membership(partition, rows):
    candidate = _two_folds()
    candidate[0]["preprocessing"][partition] = rows
    _assert_unavailable(
        compare_paired_folds(_two_folds(), candidate, metric=ROCAUC, validation=RANDOM),
        "unmatched_fold_membership",
    )


def test_rejects_reused_singleton_validation_rows_across_folds():
    reused = [_fold(0.5, [1, 2], [0]), _fold(0.6, [1, 3], [0])]
    _assert_unavailable(
        compare_paired_folds(reused, deepcopy(reused), metric=ROCAUC, validation=RANDOM),
        "overlapping_validation_folds",
    )


@pytest.mark.parametrize(("train_rows", "valid_rows"), [
    ([2, 3], [0, 0]), ([2, 2], [0]), ([0, 2], [0]), ([2], [0]), ([2, 3], []), ([2, 3], [False]),
])
def test_rejects_invalid_membership_even_when_both_sides_repeat_it(train_rows, valid_rows):
    invalid = [_fold(0.5, train_rows, valid_rows), _two_folds()[1]]
    _assert_unavailable(
        compare_paired_folds(invalid, deepcopy(invalid), metric=ROCAUC, validation=RANDOM),
        "invalid_fold_membership",
    )


@pytest.mark.parametrize("score", [None, True, float("nan"), float("inf"), 10**400])
def test_does_not_drop_a_pair_with_an_undefined_metric(score):
    candidate = _two_folds()
    candidate[1]["score"] = score
    _assert_unavailable(
        compare_paired_folds(_two_folds(), candidate, metric=ROCAUC, validation=RANDOM),
        "unavailable_fold_metric",
    )


def test_detects_arithmetic_overflow_in_a_pair():
    reference, candidate = _two_folds(), _two_folds()
    reference[0]["score"] = -1e308
    candidate[0]["score"] = 1e308
    _assert_unavailable(
        compare_paired_folds(reference, candidate, metric=ROCAUC, validation=RANDOM),
        "unavailable_fold_metric",
    )


def test_does_not_substitute_for_incomplete_or_unsupported_validation():
    for validation in ({**RANDOM, "n_splits": 1}, {"strategy": "oot", "n_splits": 2}):
        _assert_unavailable(
            compare_paired_folds(_two_folds(), _two_folds(), metric=ROCAUC, validation=validation),
            "unsupported_validation",
        )
    _assert_unavailable(
        compare_paired_folds(_two_folds(), [_two_folds()[0]], metric=ROCAUC, validation=RANDOM),
        "incomplete_fold_pairs",
    )
