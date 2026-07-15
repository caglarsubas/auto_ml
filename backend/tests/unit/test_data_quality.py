"""Unit tests - preprocessing/data_quality.py.

The Data_Quality class was never imported by the previous suite (DATQ behaviour
was only checked against pre-written fixture files). These tests build small,
realistic collaborator mocks and run the real PSI / decision / summary
computation on an in-memory DataFrame.
"""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


NUMERIC_COLS = ['Income', 'Age']
CATEGORICAL_COLS = ['Category']
TARGET = 'Target'


@pytest.fixture
def sample_df():
    rng = np.random.default_rng(123)
    n = 200
    return pd.DataFrame({
        'Income': rng.uniform(20_000, 150_000, n).round(2),
        'Age': rng.integers(18, 70, n),
        'Category': rng.choice(['A', 'B', 'C'], n),
        'Target': rng.integers(0, 2, n),
    })


@pytest.fixture
def dq(sample_df):
    """A Data_Quality instance wired with lightweight collaborator mocks."""
    from preprocessing.data_quality import Data_Quality

    meta = pd.DataFrame(index=NUMERIC_COLS)
    meta['%_Missing_Value'] = 0.0
    meta['Sparcity_Bound_Quantile'] = 0.0
    meta['%_Sparcity'] = 0.0

    variable_demystifier = SimpleNamespace(
        numerical_model_features_list=list(NUMERIC_COLS),
        categorical_model_features_list=list(CATEGORICAL_COLS),
        data_meta_info_df=meta,
    )
    argument_declarator = SimpleNamespace(
        numerical_col_sparcity_degree_value_upper_treshold=0.95,
        min_bin_share_allowed=0.05,
        min_bin_count_allowed=2,
        data_target_feature=TARGET,
    )
    return Data_Quality(
        argument_declarator=argument_declarator,
        variable_demystifier=variable_demystifier,
        data_splitter=None,
        data_purifier=None,
    )


@pytest.mark.unit
class TestEnsureSplits:
    def test_split_covers_all_rows_disjointly(self, dq, sample_df):
        dq._ensure_splits(sample_df)
        train = set(dq._train_idx)
        test = set(dq._test_idx)
        assert train.isdisjoint(test)
        assert train | test == set(sample_df.index)
        # 70/30 split should leave both sides non-empty.
        assert len(train) > 0 and len(test) > 0

    def test_split_is_deterministic(self, dq, sample_df):
        dq._ensure_splits(sample_df)
        first = (list(dq._train_idx), list(dq._test_idx))
        # A second call must not recompute / change the cached indices.
        dq._ensure_splits(sample_df)
        assert (list(dq._train_idx), list(dq._test_idx)) == first

    def test_empty_dataframe_is_handled(self, dq):
        empty = pd.DataFrame(columns=['Income'])
        dq._ensure_splits(empty)
        assert len(dq._train_idx) == 0
        assert len(dq._test_idx) == 0


@pytest.mark.unit
class TestFeaturePsi:
    def test_populates_detailed_dict(self, dq, sample_df):
        dq.feature_psi(sample_df)
        assert isinstance(dq.feature_psi_detailed_dict, dict)
        # The categorical feature always yields an entry [psi_value, table].
        assert TARGET in dq.feature_psi_detailed_dict or 'Category' in dq.feature_psi_detailed_dict
        for value in dq.feature_psi_detailed_dict.values():
            assert isinstance(value, list) and len(value) == 2

    def test_returns_self(self, dq, sample_df):
        assert dq.feature_psi(sample_df) is dq


@pytest.mark.unit
class TestShiftDecision:
    def test_decision_table_structure(self, dq, sample_df):
        dq.shift_decision(sample_df)
        df = dq.datq_decision_df
        assert isinstance(df, pd.DataFrame)
        for col in ('PSI', 'CSI', 'Datq_Decision', 'Variable_Type'):
            assert col in df.columns
        allowed = {'Shift', 'Investigate', 'Stable', 'Extremely Sparse'}
        decisions = set(df['Datq_Decision'].dropna().unique())
        assert decisions.issubset(allowed)

    def test_numeric_features_stable_on_iid_data(self, dq, sample_df):
        # Train/test are drawn from the same distribution, so numeric PSI should
        # be small (Stable), never a spurious Shift.
        dq.shift_decision(sample_df)
        df = dq.datq_decision_df
        num_rows = df[df['Variable_Type'] == 'numerical']
        assert not num_rows.empty
        assert (num_rows['PSI'].fillna(0.0) < 0.25).all()


@pytest.mark.unit
class TestDatqSummaryTable:
    def test_summary_dataframe_built(self, dq, sample_df):
        dq.datq_summary_table(sample_df)
        assert isinstance(dq.datq_summary_df, pd.DataFrame)
        assert not dq.datq_summary_df.empty
        # The decision columns are merged onto the change-statistics table.
        assert 'PSI' in dq.datq_summary_df.columns


@pytest.mark.unit
class TestKsStat:
    def test_ks_stat_returns_none(self, dq, sample_df):
        assert dq.ks_stat(sample_df) is None
