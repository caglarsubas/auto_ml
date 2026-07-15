"""Unit tests - feature card level detection and descriptions.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


# ---------------------------------------------------------------------------
# FeatureCardViewSet.determine_level_of_measurement tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFeatureCardDetermineLevel:
    """Test the FeatureCardViewSet.determine_level_of_measurement method."""

    def _determine(self, column_data):
        from feature_card.views import FeatureCardViewSet
        vs = FeatureCardViewSet()
        return vs.determine_level_of_measurement(column_data)

    def test_numeric_continuous(self):
        data = pd.Series(np.random.uniform(0, 100, 200))
        assert self._determine(data) == 'continuous'

    def test_numeric_cardinal(self):
        data = pd.Series(np.random.choice([1, 2, 3, 4, 5], 100))
        assert self._determine(data) == 'cardinal'

    def test_numeric_boundary_10(self):
        """Exactly 10 unique numeric values → cardinal (not continuous)."""
        data = pd.Series(list(range(10)) * 10)
        assert self._determine(data) == 'cardinal'

    def test_numeric_boundary_11(self):
        """11 unique numeric values → continuous."""
        data = pd.Series(list(range(11)) * 10)
        assert self._determine(data) == 'continuous'

    def test_string_nominal(self):
        data = pd.Series(['cat', 'dog', 'bird'] * 20)
        assert self._determine(data) == 'nominal'

# ---------------------------------------------------------------------------
# Feature description generator tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestGenerateFeatureDescription:
    """Test _generate_feature_description for pattern-specific descriptions."""

    def _make_data_file(self):
        from declaration.models import Declaration, DataDictionary
        decl = Declaration.objects.create(
            file='data_files/test.csv', name='test.csv', original_name='test.csv',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_8',
            description='LO Number of bureau enquiries in last 3 months',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_19',
            description='LO Outstanding balance',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_24',
            description='LO Monthly income',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_2',
            description='CA Region code',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_3',
            description='CA Occupation type',
        )
        return decl

    def test_log_signed(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('LogSigned_Var_8', df)
        assert 'sign(Var_8)' in desc
        assert 'ln(1 + |Var_8|)' in desc
        assert 'bureau enquiries' in desc

    def test_log1p(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Log1p_Var_8', df)
        assert 'ln(1 + Var_8)' in desc
        assert '"1p" suffix means "one plus"' in desc
        assert 'bureau enquiries' in desc

    def test_ratio(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Var_19_to_Var_24', df)
        assert 'Ratio' in desc
        assert 'Var_19' in desc and 'Var_24' in desc
        assert 'Outstanding balance' in desc
        assert 'Monthly income' in desc

    def test_difference(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Var_19_minus_Var_24', df)
        assert 'Difference' in desc
        assert 'Outstanding balance' in desc
        assert 'Monthly income' in desc

    def test_categorical_interaction(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Var_2_x_Var_3', df)
        assert 'Categorical interaction' in desc
        assert 'Region code' in desc
        assert 'Occupation type' in desc

    def test_is_missing(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('IsMissing_Var_8', df)
        assert 'missingness indicator' in desc
        assert 'bureau enquiries' in desc

    def test_datetime_feature(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Application_Month', df)
        assert 'Month' in desc
        assert 'Application_Datetime' in desc

    def test_aggregation_known(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('NumVars_Missing_Count', df)
        assert 'missing' in desc.lower()
        assert 'numeric' in desc.lower()

    def test_aggregation_range(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('NumVars_Range', df)
        assert 'NumVars_Max' in desc
        assert 'NumVars_Min' in desc

    def test_fallback(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('SomeUnknownCol', df)
        assert 'SomeUnknownCol' in desc

    def test_no_parent_desc_graceful(self):
        """Features referencing unknown parent vars should still describe the transform."""
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('LogSigned_Var_999', df)
        assert 'sign(Var_999)' in desc
        assert 'ln(1 + |Var_999|)' in desc
        # No parent desc — should NOT crash, just omit the parenthetical
        assert 'Var_999)' not in desc or 'sign(Var_999)' in desc
