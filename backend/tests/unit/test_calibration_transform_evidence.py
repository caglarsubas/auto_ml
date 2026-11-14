"""Validate the exported primitives against the fitted scoring behavior."""

import json

import numpy as np
import pytest
from scipy.special import expit

from modeling.calibration_utils import apply_calibrator, fit_calibrator

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('method', ['isotonic', 'platt'])
def test_calibration_state_can_be_replayed_without_deserializing_the_model(method):
    scores = np.linspace(0.05, 0.95, 100)
    y = np.where(np.arange(100) % 7 == 0, scores < 0.5, scores >= 0.5)
    fitted, meta = fit_calibrator(y, scores, method=method)
    receipt = json.loads(json.dumps(meta, allow_nan=False))
    state = receipt['fitted_transform']
    probes = np.array([0, 0.06, 0.5, 0.94, 1])
    assert receipt['fit_partition'] == 'development_validation'
    if method == 'isotonic':
        assert state['out_of_bounds'] == 'clip'
        replay = np.interp(probes, state['input_thresholds'], state['output_thresholds'])
    else:
        replay = expit(state['coefficient'] * probes + state['intercept'])
    np.testing.assert_allclose(replay, apply_calibrator(fitted, probes), rtol=1e-12, atol=1e-12)
