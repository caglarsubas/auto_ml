"""Unit tests - shared serialization/number utilities.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


# ---------------------------------------------------------------------------
# NumpyEncoder tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestNumpyEncoder:
    """Test the NumpyEncoder.default() method from feature_card/views.py.

    Note: np.float64 / np.int64 are subclasses of Python float / int, so
    json.dumps handles them natively without calling default(). We test
    default() directly for edge cases that the encoder dispatches to it.
    """

    def _default(self, obj):
        from feature_card.views import NumpyEncoder
        return NumpyEncoder().default(obj)

    def test_numpy_int_via_default(self):
        assert self._default(np.int64(42)) == 42
        assert isinstance(self._default(np.int64(42)), int)

    def test_numpy_float_via_default(self):
        result = self._default(np.float64(3.14))
        assert abs(result - 3.14) < 1e-9
        assert isinstance(result, float)

    def test_numpy_nan_returns_none_via_default(self):
        assert self._default(np.float64('nan')) is None

    def test_numpy_inf_returns_none_via_default(self):
        assert self._default(np.float64('inf')) is None
        assert self._default(np.float64('-inf')) is None

    def test_numpy_int_serializable_via_dumps(self):
        import json
        from feature_card.views import NumpyEncoder
        result = json.loads(json.dumps({'val': np.int64(7)}, cls=NumpyEncoder))
        assert result['val'] == 7

    def test_numpy_float_serializable_via_dumps(self):
        import json
        from feature_card.views import NumpyEncoder
        result = json.loads(json.dumps({'val': np.float64(2.5)}, cls=NumpyEncoder))
        assert result['val'] == 2.5

    def test_dict_with_mixed_numpy_types(self):
        import json
        from feature_card.views import NumpyEncoder
        data = {'a': 1, 'b': 'hello', 'c': [1, 2]}
        result = json.loads(json.dumps(data, cls=NumpyEncoder))
        assert result == data

# ---------------------------------------------------------------------------
# FeatureCardViewSet.safe_float tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSafeFloat:
    """Test the safe_float static method from FeatureCardViewSet."""

    def _safe_float(self, value):
        from feature_card.views import FeatureCardViewSet
        return FeatureCardViewSet.safe_float(value)

    def test_normal_float(self):
        assert self._safe_float(3.14) == 3.14

    def test_normal_int(self):
        assert self._safe_float(42) == 42.0

    def test_nan_returns_none(self):
        assert self._safe_float(float('nan')) is None

    def test_inf_returns_none(self):
        assert self._safe_float(float('inf')) is None

    def test_neg_inf_returns_none(self):
        assert self._safe_float(float('-inf')) is None

    def test_none_returns_none(self):
        assert self._safe_float(None) is None

    def test_numpy_nan_returns_none(self):
        assert self._safe_float(np.nan) is None

    def test_numpy_inf_returns_none(self):
        assert self._safe_float(np.inf) is None

    def test_numpy_float64(self):
        result = self._safe_float(np.float64(2.5))
        assert result == 2.5

    def test_non_numeric_string_returns_none(self):
        assert self._safe_float('abc') is None

    def test_numeric_string(self):
        assert self._safe_float('3.14') == 3.14

    def test_zero(self):
        assert self._safe_float(0) == 0.0
        assert self._safe_float(0.0) == 0.0
