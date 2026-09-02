"""Unit tests for CRISP-DM helpers (business floors, PSI recs, export, monitoring)."""

import json
import os
import tempfile
import zipfile

import numpy as np
import pandas as pd
import pytest

from modeling.crisp_dm import (
    build_crisp_export_zip,
    compute_monitoring_report,
    detect_sequential_pattern_candidates,
    empty_business_understanding,
    enrich_datq_with_recommendations,
    evaluate_success_floors,
    expected_cost_table,
    merge_crisp_dm,
    normalize_business_understanding,
    psi_shift_recommendation,
    recommend_threshold_by_cost,
)


def test_normalize_business_understanding_problem_type():
    bu = normalize_business_understanding({
        'objective': 'Estimate loss given default',
        'problem_type': 'Regression',
    })
    assert bu['problem_type'] == 'regression'
    # Unknown / absent values fall back to undeclared rather than guessing.
    assert normalize_business_understanding({'problem_type': 'clustering'})['problem_type'] == ''
    assert 'decision_use_case' not in empty_business_understanding()


def test_normalize_business_understanding_floors():
    bu = normalize_business_understanding({
        'objective': 'Predict default',
        'success_criteria': {
            'primary_metric': 'roc_auc',
            'direction': 'maximize',
            'floor': 0.72,
            'cost_matrix': {'fn_cost': 5, 'fp_cost': 1},
        },
        'forbidden_features': ['ssn', ''],
    })
    assert bu['completed'] is True
    assert bu['success_criteria']['floor'] == 0.72
    assert bu['success_criteria']['cost_matrix']['fn_cost'] == 5.0
    assert bu['forbidden_features'] == ['ssn']


def test_evaluate_success_floors_pass_fail():
    sc = {'primary_metric': 'roc_auc', 'direction': 'maximize', 'floor': 0.7}
    assert evaluate_success_floors({'roc_auc': 0.8}, sc)['passed'] is True
    assert evaluate_success_floors({'roc_auc': 0.6}, sc)['passed'] is False
    rmse_sc = {'primary_metric': 'rmse', 'direction': 'minimize', 'floor': 1.5}
    assert evaluate_success_floors({'rmse': 1.2}, rmse_sc)['passed'] is True


def test_psi_shift_recommendation_bands():
    assert psi_shift_recommendation(0.05) == 'keep'
    assert psi_shift_recommendation(0.15) == 'investigate'
    assert psi_shift_recommendation(0.30) == 'drop'
    assert psi_shift_recommendation(None) == 'investigate'


def test_enrich_datq_with_recommendations():
    rows = [{'Variable': 'a', 'PSI': 0.3}, {'Variable': 'b', 'CSI': 0.05}]
    out = enrich_datq_with_recommendations(rows)
    assert out[0]['Shift_Recommendation'] == 'drop'
    assert out[1]['Shift_Recommendation'] == 'keep'


def test_expected_cost_and_threshold_recommendation():
    rows = [
        {'threshold': 0.3, 'fn': 10, 'fp': 2},
        {'threshold': 0.5, 'fn': 4, 'fp': 8},
    ]
    costed = expected_cost_table(rows, fn_cost=5.0, fp_cost=1.0)
    assert costed[0]['expected_cost'] == 52.0
    assert costed[1]['expected_cost'] == 28.0
    best = recommend_threshold_by_cost(costed)
    assert best['threshold'] == 0.5


def test_merge_crisp_dm_iteration():
    state = merge_crisp_dm(None, {
        'business_understanding': {'objective': 'x'},
        'iteration_id': 2,
    })
    assert state['iteration_id'] == 2
    assert state['phase_status']['business_understanding'] == 'completed'
    assert state['business_understanding']['objective'] == 'x'


def test_build_crisp_export_zip():
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, 'data_quality'))
        with open(os.path.join(td, 'data_quality', '1_datq_summary.json'), 'w') as f:
            json.dump([{'Variable': 'a', 'PSI': 0.1}], f)
        raw, name = build_crisp_export_zip(
            td, 1,
            business_understanding=empty_business_understanding(),
        )
        assert name.startswith('crisp_pack_1_')
        with zipfile.ZipFile(__import__('io').BytesIO(raw)) as zf:
            names = zf.namelist()
            assert 'business_understanding.json' in names
            assert 'crisp_dm.json' in names
            assert 'datq_summary.json' in names


def test_detect_sequential_pattern_candidates():
    df = pd.DataFrame({
        't': [1, 2, 3, 4],
        'a': [1, 1, 9, 9],
        'b': [0, 1, 1, 2],
        'c': [5, 5, 5, 5],
    })
    cands = detect_sequential_pattern_candidates(df, time_col='t')
    assert isinstance(cands, list)
    assert len(cands) >= 1
    assert 'changed_features' in cands[0]


def test_compute_monitoring_report_alert():
    rng = np.random.default_rng(0)
    ref = pd.DataFrame({'x': rng.normal(0, 1, 200), 'y': rng.normal(0, 1, 200)})
    cur = pd.DataFrame({'x': rng.normal(3, 1, 200), 'y': rng.normal(0, 1, 200)})
    report = compute_monitoring_report(ref, cur)
    assert report['n_features_scanned'] >= 1
    assert report['status'] in ('ok', 'alert')
    assert any(r['feature'] == 'x' for r in report['top_feature_psi'])
