"""Unit tests for regression outer-test evaluation helpers."""

import numpy as np
import pytest

from evaluation.eval_utils import build_model_card, evaluate_regression
from evaluation.views import _is_regression_task, _resolve_algorithm


@pytest.mark.unit
def test_evaluate_regression_metrics():
    rng = np.random.default_rng(0)
    y = rng.normal(size=80)
    pred = y + rng.normal(scale=0.2, size=80)
    out = evaluate_regression(y, pred)
    assert out['task'] == 'regression'
    assert out['metrics']['r2'] is not None
    assert out['metrics']['r2'] > 0.5
    assert out['metrics']['rmse'] is not None
    assert out['metrics']['mae'] is not None
    assert out['threshold_table'] == []


@pytest.mark.unit
def test_resolve_algorithm_strips_regressor_suffix():
    assert _resolve_algorithm({'model_type': 'xgboost_regressor'}, {}) == 'xgboost'
    assert _resolve_algorithm({'algorithm': 'lightgbm'}, {}) == 'lightgbm'


@pytest.mark.unit
def test_is_regression_task_from_train_data_and_path():
    assert _is_regression_task({}, {'task': 'regression'}) is True
    assert _is_regression_task({'model_type': 'catboost_regressor'}, {}) is True
    assert _is_regression_task({'model_path': 'models/1_xgb_regressor.json'}, {}) is True
    assert _is_regression_task({'model_type': 'xgboost_classifier'}, {}) is False


@pytest.mark.unit
def test_model_card_regression_checks():
    card = build_model_card(
        7,
        {'task': 'regression', 'metrics': {'r2': 0.8, 'rmse': 0.3}},
        modeling_status={'model': {'task': 'regression', 'test_r2': 0.75, 'model_type': 'xgboost_regressor'}},
    )
    assert card['task'] == 'regression'
    assert any('residual' in c.lower() or 'rmse' in c.lower() for c in card['human_checks_remaining'])
    assert card['sections']['modeling']['test_r2'] == 0.75
