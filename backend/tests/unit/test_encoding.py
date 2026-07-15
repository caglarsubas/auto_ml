"""Unit tests - encoding utilities and categorical analysis.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


# ---------------------------------------------------------------------------
# Encoding utility tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDetermineFallbackStrategy:
    """Test _determine_fallback_strategy from encoding_utils."""

    def _determine(self, lom, nunique):
        from encoding.encoding_utils import _determine_fallback_strategy
        return _determine_fallback_strategy(lom, nunique)

    def test_ordinal_low_unique_ohe(self):
        strategy, _ = self._determine('ordinal', 3)
        assert strategy == 'one_hot_encoding'

    def test_ordinal_mid_unique_ordinal(self):
        strategy, _ = self._determine('ordinal', 7)
        assert strategy == 'ordinal_encoding'

    def test_ordinal_high_unique_target(self):
        strategy, _ = self._determine('ordinal', 15)
        assert strategy == 'target_encoding'

    def test_nominal_label(self):
        strategy, _ = self._determine('nominal', 5)
        assert strategy == 'label_encoding'

    def test_unknown_label(self):
        strategy, _ = self._determine('unknown', 10)
        assert strategy == 'label_encoding'

    def test_boundary_ordinal_5(self):
        """Boundary: ordinal with exactly 5 unique → ordinal_encoding."""
        strategy, _ = self._determine('ordinal', 5)
        assert strategy == 'ordinal_encoding'

    def test_boundary_ordinal_10(self):
        """Boundary: ordinal with exactly 10 unique → ordinal_encoding."""
        strategy, _ = self._determine('ordinal', 10)
        assert strategy == 'ordinal_encoding'

    def test_boundary_ordinal_11(self):
        """Boundary: ordinal with 11 unique → target_encoding."""
        strategy, _ = self._determine('ordinal', 11)
        assert strategy == 'target_encoding'

@pytest.mark.unit
class TestLabelEncode:

    def test_basic_label_encoding(self):
        from encoding.encoding_utils import _label_encode
        df = pd.DataFrame({'Color': ['Red', 'Blue', 'Green', 'Red']})
        df_enc, mapping = _label_encode(df, 'Color')
        assert df_enc['Color'].dtype in (np.int64, np.int32, int)
        assert 'mapping' in mapping
        assert len(mapping['mapping']) == 3

    def test_label_encoding_with_nulls(self):
        from encoding.encoding_utils import _label_encode
        df = pd.DataFrame({'Color': ['Red', None, 'Blue', None]})
        df_enc, mapping = _label_encode(df, 'Color')
        assert '__NULL__' in mapping['mapping']
        assert df_enc['Color'].isnull().sum() == 0

@pytest.mark.unit
class TestOheEncode:

    def test_basic_ohe(self):
        from encoding.encoding_utils import _ohe_encode
        df = pd.DataFrame({'Animal': ['cat', 'dog', 'cat', 'bird'], 'X': [1, 2, 3, 4]})
        df_enc, mapping, new_cols = _ohe_encode(df, 'Animal')
        assert 'Animal' not in df_enc.columns
        assert len(new_cols) == 3
        assert 'X' in df_enc.columns

    def test_ohe_with_nulls(self):
        from encoding.encoding_utils import _ohe_encode
        df = pd.DataFrame({'Animal': ['cat', None, 'dog']})
        df_enc, mapping, new_cols = _ohe_encode(df, 'Animal')
        null_cols = [c for c in new_cols if 'NULL' in c]
        assert len(null_cols) == 1

@pytest.mark.unit
class TestTargetEncode:

    def test_basic_target_encoding(self):
        from encoding.encoding_utils import _target_encode
        df = pd.DataFrame({
            'Region': ['A', 'A', 'B', 'B', 'A', 'B'],
            'Target': [1, 1, 0, 0, 1, 0],
        })
        df_enc, mapping = _target_encode(df, 'Region', 'Target')
        assert df_enc['Region'].dtype == float
        assert mapping['type'] == 'target_encoding'
        assert float(mapping['mapping']['A']) == pytest.approx(1.0, abs=0.01)
        assert float(mapping['mapping']['B']) == pytest.approx(0.0, abs=0.01)

    def test_target_encode_missing_target_falls_back(self):
        from encoding.encoding_utils import _target_encode
        df = pd.DataFrame({'Region': ['A', 'B', 'A']})
        df_enc, mapping = _target_encode(df, 'Region', 'Target')
        assert mapping['type'] == 'label_encoding'

@pytest.mark.unit
class TestComputeStats:

    def test_numeric_stats(self):
        from encoding.encoding_utils import _compute_stats
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        stats = _compute_stats(s)
        assert stats['total_count'] == 5
        assert stats['null_count'] == 0
        assert 'mean' in stats
        assert stats['mean'] == pytest.approx(3.0)

    def test_categorical_stats(self):
        from encoding.encoding_utils import _compute_stats
        s = pd.Series(['A', 'B', 'A', 'C'])
        stats = _compute_stats(s)
        assert stats['nunique'] == 3
        assert 'mean' not in stats

    def test_stats_with_nulls(self):
        from encoding.encoding_utils import _compute_stats
        s = pd.Series([1.0, None, 3.0, None, 5.0])
        stats = _compute_stats(s)
        assert stats['null_count'] == 2
        assert stats['null_ratio'] == pytest.approx(40.0)

@pytest.mark.unit
class TestAnalyzeCategoricalFeatures:

    def test_identifies_categorical_features(self):
        from encoding.encoding_utils import analyze_categorical_features
        df = pd.DataFrame({
            'Region': ['North', 'South', 'East'],
            'Score': [0.5, 0.7, 0.3],
            'Target': [0, 1, 0],
        })
        data_dict = [
            {'Feature_Name': 'Region', 'Level_of_Measurement': 'nominal'},
            {'Feature_Name': 'Score', 'Level_of_Measurement': 'continuous'},
        ]
        plan = analyze_categorical_features(df, data_dict)
        features = [p['feature'] for p in plan]
        assert 'Region' in features
        assert 'Score' not in features
        assert 'Target' not in features

    def test_excludes_target_and_excluded_cols(self):
        from encoding.encoding_utils import analyze_categorical_features
        df = pd.DataFrame({
            'A': ['x', 'y'], 'B': ['a', 'b'], 'Target': [0, 1],
        })
        data_dict = [
            {'Feature_Name': 'A', 'Level_of_Measurement': 'nominal'},
            {'Feature_Name': 'B', 'Level_of_Measurement': 'nominal'},
        ]
        plan = analyze_categorical_features(df, data_dict, excluded_cols=['B'])
        features = [p['feature'] for p in plan]
        assert 'A' in features
        assert 'B' not in features

    def test_plan_entry_structure(self):
        from encoding.encoding_utils import analyze_categorical_features
        df = pd.DataFrame({'Cat': ['a', 'b', 'a'], 'Target': [0, 1, 0]})
        data_dict = [{'Feature_Name': 'Cat', 'Level_of_Measurement': 'nominal'}]
        plan = analyze_categorical_features(df, data_dict)
        assert len(plan) == 1
        entry = plan[0]
        assert entry['feature'] == 'Cat'
        assert 'nunique' in entry
        assert 'strategy' in entry
        assert 'fallback_strategy' in entry
        assert entry['strategy'] == 'native_categorical'

# ---------------------------------------------------------------------------
# AI tool_executor: get_encoding_plan reader exposes unique_values + ranking
# ---------------------------------------------------------------------------
# v2.24.0+: the AI needs to see actual category strings (unique_values)
# and any existing ranking on every encoding-plan tool call so it can
# (a) propose a semantically meaningful ranking instead of guessing
# alphabetically, and (b) skip the set_ordinal_ranking chain when a
# ranking is already in place (idempotency).
@pytest.mark.unit
class TestEncodingPlanReader:
    """Exercises ai_assistant.tool_executor._handle_get_encoding_plan."""

    def _render(self, cached_plan):
        from ai_assistant import tool_executor
        # Monkey-patch the read fn — avoids needing a live Redis.
        orig = tool_executor.read_encoding_plan
        tool_executor.read_encoding_plan = lambda fid: cached_plan
        try:
            return tool_executor._handle_get_encoding_plan(1, {})
        finally:
            tool_executor.read_encoding_plan = orig

    def test_renders_unique_values(self):
        plan = [{
            'feature': 'Var_36', 'user_lom': 'ordinal', 'nunique': 7,
            'fallback_strategy': 'ordinal_encoding', 'needs_ranking': True,
            'unique_values': ['0', '1', '2', '3', '8', 'L', 'Others'],
            'ranking': None,
        }]
        out = self._render(plan)
        assert 'Var_36' in out
        # All unique values are visible in the rendered output.
        for v in ['0', '1', '2', '3', '8', 'L', 'Others']:
            assert v in out

    def test_flags_unset_ranking_when_needs_ranking_true(self):
        plan = [{
            'feature': 'Var_36', 'user_lom': 'ordinal', 'nunique': 7,
            'fallback_strategy': 'ordinal_encoding', 'needs_ranking': True,
            'unique_values': ['Low', 'Mid', 'High'],
            'ranking': None,
        }]
        out = self._render(plan)
        # The marker prompts the LLM to chain set_ordinal_ranking next.
        assert 'NOT SET' in out
        assert 'set_ordinal_ranking' in out

    def test_renders_existing_ranking(self):
        plan = [{
            'feature': 'Var_36', 'user_lom': 'ordinal', 'nunique': 3,
            'fallback_strategy': 'ordinal_encoding', 'needs_ranking': True,
            'unique_values': ['Low', 'Mid', 'High'],
            'ranking': ['Low', 'Mid', 'High'],
        }]
        out = self._render(plan)
        # Arrow-separated rendering of the existing ranking.
        assert 'Low → Mid → High' in out
        # No "call set_ordinal_ranking" prompt because ranking is set.
        assert 'NOT SET' not in out

    def test_does_not_prompt_set_ranking_when_not_ordinal(self):
        plan = [{
            'feature': 'Var_3', 'user_lom': 'nominal', 'nunique': 2,
            'fallback_strategy': 'label_encoding', 'needs_ranking': False,
            'unique_values': ['N', 'Y'],
            'ranking': None,
        }]
        out = self._render(plan)
        assert 'NOT SET' not in out
        assert 'set_ordinal_ranking' not in out

    def test_truncates_unique_values_past_12(self):
        plan = [{
            'feature': 'Var_HighCard', 'user_lom': 'nominal', 'nunique': 20,
            'fallback_strategy': 'label_encoding', 'needs_ranking': False,
            'unique_values': [f'cat{i}' for i in range(20)],
            'ranking': None,
        }]
        out = self._render(plan)
        assert 'cat0' in out
        assert 'cat11' in out  # 12th value (index 11) is shown
        assert 'cat12' not in out  # 13th value truncated
        assert '+8 more' in out  # 20 - 12 = 8 truncated
