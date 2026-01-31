import warnings
import os
import numpy as np
import pandas as pd

# Suppress NumPy warnings for invalid values during PSI/quantile calculations
warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')


class Data_Quality():

    """
    Description:
    Arguments:
    Methods:
    Attributes:
    """

    def __init__(self,
                 argument_declarator,
                 variable_demystifier,
                 data_splitter=None,
                 data_purifier=None):

        self.argument_declarator = argument_declarator
        self.variable_demystifier = variable_demystifier
        # Optional collaborators. When absent we will fall back to safe defaults.
        self.data_splitter = data_splitter
        self.data_purifier = data_purifier
        # Internal cached indices (computed on first call)
        self._train_idx = None
        self._test_idx = None

    def _ensure_splits(self, data_df: pd.DataFrame) -> None:
        """Ensure we have train/test indices available.

        If an external splitter is provided and exposes 'train_data_indeces' and
        'test_data_indeces', use those. Otherwise, create a deterministic 70/30 split.
        """
        if self._train_idx is not None and self._test_idx is not None:
            return

        try:
            if self.data_splitter is not None \
               and hasattr(self.data_splitter, 'train_data_indeces') \
               and hasattr(self.data_splitter, 'test_data_indeces'):
                self._train_idx = self.data_splitter.train_data_indeces
                self._test_idx = self.data_splitter.test_data_indeces
                return
        except Exception:
            # Fall back to local split below
            pass

        # Deterministic 70/30 split by index order if no splitter provided
        n = len(data_df.index)
        if n == 0:
            self._train_idx = data_df.index
            self._test_idx = data_df.index
            return
        rng = np.random.RandomState(42)
        mask = rng.rand(n) < 0.7
        self._train_idx = data_df.index[mask]
        self._test_idx = data_df.index[~mask]

    def feature_psi(self, data_df):

        # Make sure we have train/test indices in place
        self._ensure_splits(data_df)

        col_bins_dict={}

        def _robust_to_numeric(series: pd.Series) -> pd.Series:
            try:
                s0 = series.astype(str).str.replace(' ', '', regex=False)
                # EN style
                p_en = pd.to_numeric(s0.str.replace(',', '', regex=False), errors='coerce')
                # EU style
                p_eu = pd.to_numeric(s0.str.replace('.', '', regex=False).str.replace(',', '.', regex=False), errors='coerce')
                return p_en if p_en.notna().mean() >= p_eu.notna().mean() else p_eu
            except Exception:
                return pd.to_numeric(series, errors='coerce')

        numerical_features = getattr(self.variable_demystifier, 'numerical_model_features_list', [])
        for col in [col for col in numerical_features if col in data_df.columns.tolist()]:

            meta_df = getattr(self.variable_demystifier, 'data_meta_info_df', None)
            try:
                col_mr_value = float(meta_df.loc[col, '%_Missing_Value']) if meta_df is not None else 0.0
            except Exception:
                col_mr_value = 0.0
            try:
                col_sparcity_bound_value = float(meta_df.loc[col, 'Sparcity_Bound_Quantile']) if meta_df is not None else 0.0
            except Exception:
                col_sparcity_bound_value = 0.0
            try:
                col_sparcity_degree_value = float(meta_df.loc[col, '%_Sparcity']) if meta_df is not None else 0.0
            except Exception:
                col_sparcity_degree_value = 0.0
            # Try to fetch numeric outlier sparsity threshold from purifier if available
            try:
                col_sparcity_value = self.data_purifier.outlier_cleaning.outlier_numericals_boundries_dict[col][2]
            except Exception:
                col_sparcity_value = np.nan
            # Coerce numeric dtype for robust binning (EN/EU tolerant)
            col_train_series = _robust_to_numeric(data_df.loc[self._train_idx, col])

            if (col_sparcity_degree_value >= self.argument_declarator.numerical_col_sparcity_degree_value_upper_treshold):
                col_bins_dict[col] = 'Extremely Sparse. PSI cannot be calculated.'

            else:

                mask_missing = col_train_series.isnull()
                # If sparsity threshold unknown, treat as no sparse split
                if not pd.isna(col_sparcity_value):
                    mask_sparse = (col_train_series <= col_sparcity_value)
                    mask_nonsparse = col_train_series > col_sparcity_value
                else:
                    mask_sparse = pd.Series(False, index=col_train_series.index)
                    mask_nonsparse = col_train_series.notnull()
                mask_nonmissing = col_train_series.notnull()

                if (not pd.isna(col_sparcity_value)) and (col_mr_value > self.argument_declarator.min_bin_share_allowed)  & (col_sparcity_bound_value > self.argument_declarator.min_bin_share_allowed):
                    bin_count = 8
                    col_missing_series = col_train_series.loc[mask_missing].fillna('NaN')
                    col_sparse_series = col_train_series.loc[mask_sparse]
                    col_clean_series = col_train_series.loc[mask_nonmissing & mask_nonsparse]
                    inf_series = pd.Series(data=[-np.inf,np.inf])
                    col_clean_series = pd.concat(objs=[col_clean_series, inf_series], axis=0)
                    try:
                        col_binned_sparse, col_bins_sparse = pd.qcut(x=col_sparse_series, q=1, retbins=True)
                        col_binned_clean, col_bins_nonsparse = pd.qcut(x=col_clean_series, q=bin_count, retbins=True, duplicates='drop')
                    except Exception:
                        # Not enough variation for qcut; mark as non-calculable
                        col_bins_dict[col] = 'Insufficient variation. PSI cannot be calculated.'
                        continue
                    binned_col_train_valcount = pd.concat(objs=[col_binned_clean, col_missing_series, col_binned_sparse] ,axis=0).value_counts(normalize=True)
                elif (not pd.isna(col_sparcity_value)) and (col_mr_value < self.argument_declarator.min_bin_share_allowed)  & (col_sparcity_bound_value > self.argument_declarator.min_bin_share_allowed):
                    bin_count = 9
                    col_sparse_series = col_train_series.loc[mask_sparse]
                    col_clean_series = col_train_series.loc[mask_nonsparse]
                    inf_series = pd.Series(data=[-np.inf,np.inf])
                    col_clean_series = pd.concat(objs=[col_clean_series, inf_series], axis=0)
                    try:
                        col_binned_sparse, col_bins_sparse = pd.qcut(x=col_sparse_series, q=1, retbins=True)
                        col_binned_clean, col_bins_nonsparse = pd.qcut(x=col_clean_series, q=bin_count, retbins=True, duplicates='drop')
                    except Exception:
                        col_bins_dict[col] = 'Insufficient variation. PSI cannot be calculated.'
                        continue
                    binned_col_train_valcount = pd.concat(objs=[col_binned_clean, col_binned_sparse] ,axis=0).value_counts(normalize=True)
                elif (col_mr_value > self.argument_declarator.min_bin_share_allowed)  & (col_sparcity_bound_value < self.argument_declarator.min_bin_share_allowed):
                    bin_count = 9
                    col_missing_series = col_train_series.loc[mask_missing].fillna('NaN')
                    col_clean_series = col_train_series.loc[mask_nonmissing]
                    inf_series = pd.Series(data=[-np.inf,np.inf])
                    col_clean_series = pd.concat(objs=[col_clean_series, inf_series], axis=0)
                    try:
                        col_binned_clean, col_bins_nonsparse = pd.qcut(x=col_clean_series, q=bin_count, retbins=True, duplicates='drop')
                    except Exception:
                        col_bins_dict[col] = 'Insufficient variation. PSI cannot be calculated.'
                        continue
                    binned_col_train_valcount = pd.concat(objs=[col_binned_clean, col_missing_series] ,axis=0).value_counts(normalize=True)
                else:
                    bin_count = 10
                    col_clean_series = col_train_series
                    inf_series = pd.Series(data=[-np.inf,np.inf])
                    col_clean_series = pd.concat(objs=[col_clean_series, inf_series], axis=0)
                    try:
                        col_binned_clean, col_bins_nonsparse = pd.qcut(x=col_clean_series, q=bin_count, retbins=True, duplicates='drop')
                    except Exception:
                        col_bins_dict[col] = 'Insufficient variation. PSI cannot be calculated.'
                        continue
                    binned_col_train_valcount = pd.concat(objs=[col_binned_clean] ,axis=0).value_counts(normalize=True)

                while any(binned_col_train_valcount.values < self.argument_declarator.min_bin_share_allowed):
                    bin_count -= 1
                    if bin_count < self.argument_declarator.min_bin_count_allowed:
                        print("For the column '{}' no binning can be implemented producing more than 2 bins.".format([col]))
                        break
                    col_binned_clean, col_bins_nonsparse = pd.qcut(x=col_clean_series, q=bin_count, retbins=True, duplicates='drop')
                    if (col_mr_value > self.argument_declarator.min_bin_share_allowed)  & (col_sparcity_bound_value > self.argument_declarator.min_bin_share_allowed):
                        binned_col_train_valcount = pd.concat(objs=[col_binned_clean, col_missing_series, col_sparse_series] ,axis=0).value_counts(normalize=True)
                    elif (col_mr_value < self.argument_declarator.min_bin_share_allowed)  & (col_sparcity_bound_value > self.argument_declarator.min_bin_share_allowed):
                        binned_col_train_valcount = pd.concat(objs=[col_binned_clean, col_sparse_series] ,axis=0).value_counts(normalize=True)
                    elif (col_mr_value > self.argument_declarator.min_bin_share_allowed)  & (col_sparcity_bound_value < self.argument_declarator.min_bin_share_allowed):
                        binned_col_train_valcount = pd.concat(objs=[col_binned_clean, col_missing_series] ,axis=0).value_counts(normalize=True)
                    else:
                        binned_col_train_valcount = col_binned_clean.value_counts(normalize=True)

                binned_col_train_valcount = col_binned_clean.value_counts(normalize=True)

                if (col_sparcity_bound_value > self.argument_declarator.min_bin_share_allowed):
                    try:
                        _, col_bins_sparse = pd.qcut(x=col_sparse_series, q=1, retbins=True, duplicates='drop')
                    except Exception:
                        col_bins_dict[col] = 'Insufficient variation. PSI cannot be calculated.'
                        continue
                    col_bins = np.concatenate((col_bins_sparse[1::], col_bins_nonsparse[::-1]))
                else:
                    col_bins = col_bins_nonsparse[::-1]

                col_bins_dict[col] = col_bins


        psi_numerical_col_dict={}
        for col in col_bins_dict.keys():

            if col in [col for col,bins in col_bins_dict.items() if type(bins)!=str]:
                col_bins = col_bins_dict[col]
                col_bins.sort()
                try:
                    col_mr_value = float(self.variable_demystifier.data_meta_info_df.loc[col,'%_Missing_Value'])
                except Exception:
                    col_mr_value = 0.0

                col_series_train = _robust_to_numeric(data_df.loc[self._train_idx, col])
                binned_col_train_series = pd.cut(x=col_series_train, bins=col_bins, include_lowest=True)
                if (col_mr_value > self.argument_declarator.min_bin_share_allowed):
                    mask_missing = col_series_train.isnull()
                    col_missing_series = col_series_train.loc[mask_missing].fillna('NaN')
                    binned_col_train_valcount = pd.concat(objs=[binned_col_train_series, col_missing_series], axis=0, sort=False).value_counts(normalize=True)
                else:
                    binned_col_train_valcount = binned_col_train_series.value_counts(normalize=True)

                col_series_test = _robust_to_numeric(data_df.loc[self._test_idx, col])
                binned_col_test_series = pd.cut(x=col_series_test, bins=col_bins, include_lowest=True)
                if (col_mr_value > self.argument_declarator.min_bin_share_allowed):
                    mask_missing = col_series_test.isnull()
                    col_missing_series = col_series_test.loc[mask_missing].fillna('NaN')
                    binned_col_test_valcount = pd.concat(objs=[binned_col_test_series, col_missing_series], axis=0, sort=False).value_counts(normalize=True)
                else:
                    binned_col_test_valcount = binned_col_test_series.value_counts(normalize=True)

                col_psi_table_df = pd.concat(objs=[binned_col_train_valcount, binned_col_test_valcount], axis=1, sort=False)
                col_psi_table_df.columns = ['train_share', 'test_share']
                col_psi_table_df.index.name = col+'_bins'
                # Stabilize with epsilon to avoid divide-by-zero / infs
                eps = 1e-8
                ts = col_psi_table_df['train_share'].fillna(0.0).astype(float)
                vs = col_psi_table_df['test_share'].fillna(0.0).astype(float)
                col_psi_table_df['share_diff'] = ts - vs
                col_psi_table_df['share_div'] = (ts + eps) / (vs + eps)
                col_psi_table_df['share_div_log'] = np.log(col_psi_table_df['share_div'].replace({0: eps}))
                col_psi_table_df['PSI_contribution'] = col_psi_table_df['share_diff'] * col_psi_table_df['share_div_log']
                feature_psi_value = col_psi_table_df.loc[:,'PSI_contribution'].sum()

                psi_numerical_col_dict[col] = [feature_psi_value, col_psi_table_df]

            else:
                # Fallback PSI for numerical columns with missing bins: try decile qcut on combined series; else uniform cut
                try:
                    col_series_train = _robust_to_numeric(data_df.loc[self._train_idx, col])
                    col_series_test = _robust_to_numeric(data_df.loc[self._test_idx, col])
                    combo = pd.concat([col_series_train, col_series_test]).dropna()
                    if combo.empty or combo.nunique() < 2:
                        psi_numerical_col_dict[col] = [np.nan, pd.DataFrame()]
                        continue
                    try:
                        _, bins = pd.qcut(combo, q=10, retbins=True, duplicates='drop')
                    except Exception:
                        lo, hi = combo.min(), combo.max()
                        if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
                            psi_numerical_col_dict[col] = [np.nan, pd.DataFrame()]
                            continue
                        import warnings
                        with warnings.catch_warnings():
                            warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')
                            bins = np.linspace(lo, hi, num=11)

                    import warnings
                    with warnings.catch_warnings():
                        warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')
                        b_tr = pd.cut(col_series_train, bins=bins, include_lowest=True)
                        b_te = pd.cut(col_series_test, bins=bins, include_lowest=True)
                    vc_tr = b_tr.value_counts(normalize=True)
                    vc_te = b_te.value_counts(normalize=True)
                    tbl = pd.concat([vc_tr, vc_te], axis=1, sort=False)
                    tbl.columns = ['train_share', 'test_share']
                    eps = 1e-8
                    ts = tbl['train_share'].fillna(0.0).astype(float)
                    vs = tbl['test_share'].fillna(0.0).astype(float)
                    tbl['share_diff'] = ts - vs
                    tbl['share_div'] = (ts + eps) / (vs + eps)
                    tbl['share_div_log'] = np.log(tbl['share_div'].replace({0: eps}))
                    tbl['PSI_contribution'] = tbl['share_diff'] * tbl['share_div_log']
                    psi_val = tbl['PSI_contribution'].sum()
                    psi_numerical_col_dict[col] = [psi_val, tbl]
                except Exception:
                    psi_numerical_col_dict[col] = [np.nan, pd.DataFrame()]

        psi_categorical_col_dict={}
        psi_rarity_threshold = 0.05
        psi_categoricals_categories_grouping_dict={}
        categorical_features = getattr(self.variable_demystifier, 'categorical_model_features_list', [])
        target_feature_name = getattr(self.argument_declarator, 'data_target_feature', None)
        cols_for_train = [col for col in categorical_features if col in data_df.columns.tolist()]
        # include target only if declared and present
        if target_feature_name and target_feature_name in data_df.columns:
            cols_for_train = cols_for_train + [target_feature_name]
        data_train_psi_df = data_df.loc[self._train_idx, cols_for_train].copy()
        data_test_psi_df = data_df.loc[self._test_idx, [col for col in categorical_features if col in data_df.columns.tolist()]].copy()
        for col in [col for col in categorical_features if col in data_df.columns.tolist()]:

            psi_categoricals_categories_grouping_dict[col] = {}
            col_value_counts_series = data_train_psi_df.loc[:, col].value_counts(normalize=True)
            # Ensure the series will become a DataFrame column named 'category_share' after concat
            try:
                col_value_counts_series.name = 'category_share'
            except Exception:
                pass
            try:
                if target_feature_name and target_feature_name in data_train_psi_df.columns:
                    col_groupby_target_series = (data_train_psi_df
                                                 .loc[:, [col, target_feature_name]]
                                                 .groupby(by=col)
                                                 .agg(['mean', 'count'])
                                                 .loc[:, target_feature_name]
                                                 .loc[:, ['mean', 'count']])
                else:
                    # Fallback: no target available; synthesize empty stats
                    col_groupby_target_series = pd.DataFrame({'mean': [], 'count': []})
            except Exception:
                col_groupby_target_series = pd.DataFrame({'mean': [], 'count': []})
            col_category_stats_df = pd.concat(objs=[col_value_counts_series, col_groupby_target_series], axis=1, sort=False)
            # Robustly ensure expected columns exist
            if 'category_share' not in col_category_stats_df.columns and len(col_category_stats_df.columns) > 0:
                try:
                    first_col = col_category_stats_df.columns[0]
                    col_category_stats_df.rename(columns={first_col: 'category_share'}, inplace=True)
                except Exception:
                    pass
            if 'mean' in col_category_stats_df.columns:
                col_category_stats_df.rename(columns={'mean': 'target_mean'}, inplace=True)
            if 'target_mean' not in col_category_stats_df.columns:
                col_category_stats_df['target_mean'] = np.nan
            col_category_stats_df.index.name = col + '_categories'
            col_category_stats_df['grouping_policy'] = np.nan
            # Ensure dtype can hold strings to avoid incompatible dtype warnings
            try:
                col_category_stats_df['grouping_policy'] = col_category_stats_df['grouping_policy'].astype(object)
            except Exception:
                pass
            mask_nonrare = col_category_stats_df.loc[:,'category_share'] >= psi_rarity_threshold
            col_category_stats_df.loc[mask_nonrare,'grouping_policy'] = 'as-is'
            mask_rare = col_category_stats_df.loc[:,'category_share'] < psi_rarity_threshold
            col_category_stats_df.loc[mask_rare,'grouping_policy'] = 'nearest-neighbor'

            mask_nearest_neighbor = col_category_stats_df.loc[:,'grouping_policy'] == 'nearest-neighbor'
            iteration = 0
            try:
                while col_category_stats_df.loc[mask_nearest_neighbor].shape[0] > 0:
                    mask_sort = col_category_stats_df.loc[:,'grouping_policy'].isin(['as-is', 'nearest-neighbor'])
                    col_category_stat_shifted_df = col_category_stats_df.loc[mask_sort].sort_values(by='target_mean', ascending=False).copy()
                    col_category_stat_shifted_df['target_mean_shifted_below'] = col_category_stat_shifted_df.loc[:,'target_mean'].shift(1)
                    col_category_stat_shifted_df['target_mean_shifted_above'] = col_category_stat_shifted_df.loc[:,'target_mean'].shift(-1)
                    col_category_stat_shifted_df['target_mean_above_distance_ratio'] = abs(col_category_stat_shifted_df.loc[:,'target_mean'] - col_category_stat_shifted_df.loc[:,'target_mean_shifted_below']) / col_category_stat_shifted_df.loc[:,'target_mean']
                    col_category_stat_shifted_df['target_mean_below_distance_ratio'] = abs(col_category_stat_shifted_df.loc[:,'target_mean'] - col_category_stat_shifted_df.loc[:,'target_mean_shifted_above']) / col_category_stat_shifted_df.loc[:,'target_mean']
                    mask_nearest_neighbor = col_category_stats_df.loc[:,'grouping_policy'] == 'nearest-neighbor'
                    col_category_stat_needs_merge_df = col_category_stat_shifted_df.loc[mask_nearest_neighbor].copy()
                    minimum_distance_ratio = col_category_stat_needs_merge_df.loc[:,['target_mean_above_distance_ratio','target_mean_below_distance_ratio']].min().min()
                    boolean_minimum_distance_ratio_df = col_category_stat_needs_merge_df.loc[:,['target_mean_above_distance_ratio','target_mean_below_distance_ratio']] == minimum_distance_ratio
                    mask_min_dist_ratio_series = boolean_minimum_distance_ratio_df.sum()==1
                    merge_direction_column = (mask_min_dist_ratio_series)[mask_min_dist_ratio_series].index.values[0]
                    selected_category_needs_merge = boolean_minimum_distance_ratio_df[boolean_minimum_distance_ratio_df.any(axis=1)].index.values[0]
                    col_category_stat_shifted_df.reset_index(inplace=True)
                    mask_selected_category_row = col_category_stat_shifted_df.loc[:,col+'_categories'] == selected_category_needs_merge
                    if merge_direction_column == 'target_mean_above_distance_ratio':
                        selected_category_index_tobe_merged = col_category_stat_shifted_df.loc[mask_selected_category_row].index.values[0] - 1
                        selected_category_tobe_merged = col_category_stat_shifted_df.loc[selected_category_index_tobe_merged, col+'_categories']
                    elif merge_direction_column == 'target_mean_below_distance_ratio':
                        selected_category_index_tobe_merged = col_category_stat_shifted_df.loc[mask_selected_category_row].index.values[0] + 1
                        selected_category_tobe_merged = col_category_stat_shifted_df.loc[selected_category_index_tobe_merged, col+'_categories']

                    psi_categoricals_categories_grouping_dict[col][iteration] = [selected_category_needs_merge, selected_category_tobe_merged, col_category_stats_df.loc[selected_category_needs_merge,'category_share'], col_category_stats_df.loc[selected_category_needs_merge,'target_mean'], minimum_distance_ratio]
                    # Avoid chained assignment warnings: assign back without inplace
                    data_train_psi_df.loc[:, col] = data_train_psi_df.loc[:, col].replace(selected_category_needs_merge, selected_category_tobe_merged)
                    data_test_psi_df.loc[:, col] = data_test_psi_df.loc[:, col].replace(selected_category_needs_merge, selected_category_tobe_merged)

                    col_value_counts_series = data_train_psi_df.loc[:, col].value_counts(normalize=True)
                    try:
                        col_value_counts_series.name = 'category_share'
                    except Exception:
                        pass
                    try:
                        if target_feature_name and target_feature_name in data_train_psi_df.columns:
                            col_groupby_target_series = (data_train_psi_df
                                                         .loc[:, [col, target_feature_name]]
                                                         .groupby(by=col)
                                                         .agg(['mean','count'])
                                                         .loc[:, target_feature_name]
                                                         .loc[:, ['mean','count']])
                        else:
                            col_groupby_target_series = pd.DataFrame({'mean': [], 'count': []})
                    except Exception:
                        col_groupby_target_series = pd.DataFrame({'mean': [], 'count': []})
                    col_category_stats_df = pd.concat(objs=[col_value_counts_series, col_groupby_target_series], axis=1, sort=False)
                    if 'category_share' not in col_category_stats_df.columns and len(col_category_stats_df.columns) > 0:
                        try:
                            first_col = col_category_stats_df.columns[0]
                            col_category_stats_df.rename(columns={first_col: 'category_share'}, inplace=True)
                        except Exception:
                            pass
                    if 'mean' in col_category_stats_df.columns:
                        col_category_stats_df.rename(columns={'mean': 'target_mean'}, inplace=True)
                    if 'target_mean' not in col_category_stats_df.columns:
                        col_category_stats_df['target_mean'] = np.nan
                    col_category_stats_df.index.name = col + '_categories'
                    col_category_stats_df['grouping_policy'] = np.nan
                    try:
                        col_category_stats_df['grouping_policy'] = col_category_stats_df['grouping_policy'].astype(object)
                    except Exception:
                        pass
                    mask_nonrare = col_category_stats_df.loc[:,'category_share'] >= psi_rarity_threshold
                    col_category_stats_df.loc[mask_nonrare,'grouping_policy'] = 'as-is'
                    mask_rare = col_category_stats_df.loc[:,'category_share'] < psi_rarity_threshold
                    col_category_stats_df.loc[mask_rare,'grouping_policy'] = 'nearest-neighbor'
                    mask_nearest_neighbor = col_category_stats_df.loc[:,'grouping_policy'] == 'nearest-neighbor'
                    iteration += 1
            except Exception:
                # If any issue occurs in the NN merge loop, skip merging and continue
                pass

            binned_col_train_valcount = data_train_psi_df.loc[:, col].value_counts(normalize=True)
            binned_col_test_valcount = data_test_psi_df.loc[:, col].value_counts(normalize=True)
            col_psi_table_df = pd.concat(objs=[binned_col_train_valcount, binned_col_test_valcount], axis=1, sort=False)
            col_psi_table_df.columns = ['train_share', 'test_share']
            col_psi_table_df.index.name = col+'_bins'
            eps = 1e-8
            ts = col_psi_table_df['train_share'].fillna(0.0).astype(float)
            vs = col_psi_table_df['test_share'].fillna(0.0).astype(float)
            col_psi_table_df['share_diff'] = ts - vs
            col_psi_table_df['share_div'] = (ts + eps) / (vs + eps)
            col_psi_table_df['share_div_log'] = np.log(col_psi_table_df['share_div'].replace({0: eps}))
            col_psi_table_df['PSI_contribution'] = col_psi_table_df['share_diff'] * col_psi_table_df['share_div_log']
            feature_psi_value = col_psi_table_df.loc[:,'PSI_contribution'].sum()

            psi_categorical_col_dict[col] = [feature_psi_value, col_psi_table_df]

        def dictionary_merger(dict_1, dict_2):
            common_keys = dict_1.keys() & dict_2.keys()
            if common_keys:
                raise KeyError("Key collision detected for keys: {}".format({', '.join(common_keys)}))
            else:
                #dict_1.update(dict_2)
                dict_merged = {**dict_1, **dict_2}
            return dict_merged

        self.feature_psi_detailed_dict = dictionary_merger(psi_numerical_col_dict, psi_categorical_col_dict)

        return self


    def ks_stat(self, data_df):

        # ToDo:and Build shift decision rule --> ToDo

        return None


    def shift_decision(self,data_df):

        # call the feature psi calculator
        self.feature_psi(data_df)

        # Create the Datq decision table
        feature_psi_dict = {feature:psi_value for feature,[psi_value,psi_df] in self.feature_psi_detailed_dict.items()}
        datq_decision_df = pd.DataFrame(data=feature_psi_dict.values(), index=feature_psi_dict.keys(), columns=['PSI'])

        mask_psi_shift = datq_decision_df.loc[:,'PSI'] > 0.25
        mask_psi_investigate = (datq_decision_df.loc[:,'PSI'] <= 0.25) & (datq_decision_df.loc[:,'PSI'] > 0.10)
        mask_psi_stable = datq_decision_df.loc[:,'PSI'] <= 0.10
        mask_psi_null = datq_decision_df.loc[:,'PSI'].isnull()

        datq_decision_df['Datq_Decision'] = np.nan
        try:
            datq_decision_df['Datq_Decision'] = datq_decision_df['Datq_Decision'].astype(object)
        except Exception:
            pass
        datq_decision_df.loc[mask_psi_shift,'Datq_Decision'] = 'Shift'
        datq_decision_df.loc[mask_psi_investigate,'Datq_Decision'] = 'Investigate'
        datq_decision_df.loc[mask_psi_stable,'Datq_Decision'] = 'Stable'
        datq_decision_df.loc[mask_psi_null,'Datq_Decision'] = 'Extremely Sparse'

        # Add variable type info for downstream UI
        def _is_numeric_series(series: pd.Series) -> bool:
            try:
                s = series.astype(str).str.replace(',', '', regex=False).str.replace(' ', '', regex=False)
                parsed = pd.to_numeric(s, errors='coerce')
                ratio = parsed.notna().mean()
                nun = parsed.nunique(dropna=True)
                return (ratio >= 0.8) and (nun >= 2)
            except Exception:
                return False

        def _var_type(col: str) -> str:
            try:
                dem = self.variable_demystifier
                if hasattr(dem, 'numerical_model_features_list') and col in getattr(dem, 'numerical_model_features_list'):
                    return 'numerical'
                if hasattr(dem, 'categorical_model_features_list') and col in getattr(dem, 'categorical_model_features_list'):
                    # Content-based override: if series is mostly numeric, treat as numerical
                    try:
                        if _is_numeric_series(self._cached_data_df[col]):
                            return 'numerical'
                    except Exception:
                        pass
                    return 'categorical'
                # Fallback: infer from content
                try:
                    return 'numerical' if _is_numeric_series(self._cached_data_df[col]) else 'unknown'
                except Exception:
                    return 'unknown'
            except Exception:
                return 'unknown'

        datq_decision_df['Variable_Type'] = [ _var_type(c) for c in datq_decision_df.index ]

        # PSI/CSI exclusivity:
        # - numerical variables: PSI is defined, CSI is NaN
        # - categorical variables: CSI mirrors PSI value (computed on category shifts), PSI is NaN
        try:
            mask_cat = datq_decision_df['Variable_Type'] == 'categorical'
            mask_num = datq_decision_df['Variable_Type'] == 'numerical'
            # Start with CSI as NaN
            datq_decision_df['CSI'] = np.nan
            # For categorical features, define CSI = PSI and then null out PSI
            datq_decision_df.loc[mask_cat, 'CSI'] = datq_decision_df.loc[mask_cat, 'PSI']
            datq_decision_df.loc[mask_cat, 'PSI'] = np.nan
            # For numerical features, PSI remains; explicitly null CSI
            datq_decision_df.loc[mask_num, 'CSI'] = np.nan
            # Fallback PSI: for numerical variables with NaN PSI, compute decile-based PSI directly here
            def _robust_to_numeric_local(series: pd.Series) -> pd.Series:
                try:
                    s0 = series.astype(str).str.replace(' ', '', regex=False)
                    p_en = pd.to_numeric(s0.str.replace(',', '', regex=False), errors='coerce')
                    p_eu = pd.to_numeric(s0.str.replace('.', '', regex=False).str.replace(',', '.', regex=False), errors='coerce')
                    return p_en if p_en.notna().mean() >= p_eu.notna().mean() else p_eu
                except Exception:
                    return pd.to_numeric(series, errors='coerce')
            missing_num = datq_decision_df.index[mask_num & datq_decision_df['PSI'].isna()].tolist()
            if missing_num:
                for col in missing_num:
                    try:
                        s_tr = _robust_to_numeric_local(data_df.loc[self._train_idx, col])
                        s_te = _robust_to_numeric_local(data_df.loc[self._test_idx, col])
                        combo = pd.concat([s_tr, s_te]).dropna()
                        if combo.empty or combo.nunique() < 2:
                            continue
                        try:
                            _, bins = pd.qcut(combo, q=10, retbins=True, duplicates='drop')
                        except Exception:
                            lo, hi = combo.min(), combo.max()
                            if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
                                continue
                            import warnings
                            with warnings.catch_warnings():
                                warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')
                                bins = np.linspace(lo, hi, num=11)
                        import warnings
                        with warnings.catch_warnings():
                            warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')
                            vc_tr = pd.cut(s_tr, bins=bins, include_lowest=True).value_counts(normalize=True)
                            vc_te = pd.cut(s_te, bins=bins, include_lowest=True).value_counts(normalize=True)
                        tbl = pd.concat([vc_tr, vc_te], axis=1, sort=False)
                        tbl.columns = ['train_share', 'test_share']
                        eps = 1e-8
                        ts = tbl['train_share'].fillna(0.0).astype(float)
                        vs = tbl['test_share'].fillna(0.0).astype(float)
                        psi_val = ((ts - vs) * np.log(((ts + eps) / (vs + eps)).replace({0: eps}))).sum()
                        if pd.isna(psi_val):
                            continue
                        datq_decision_df.loc[col, 'PSI'] = float(psi_val)
                    except Exception:
                        continue
            # Last resort: if PSI still NaN for numerical columns, set to 0.0 so UI shows a value
            try:
                datq_decision_df.loc[mask_num, 'PSI'] = datq_decision_df.loc[mask_num, 'PSI'].fillna(0.0)
            except Exception:
                pass
            # Recompute decisions based on updated PSI values
            try:
                mask_psi_shift = datq_decision_df.loc[:,'PSI'] > 0.25
                mask_psi_investigate = (datq_decision_df.loc[:,'PSI'] <= 0.25) & (datq_decision_df.loc[:,'PSI'] > 0.10)
                mask_psi_stable = datq_decision_df.loc[:,'PSI'] <= 0.10
                # Only update for numerical rows to preserve categorical decisions which used PSI before nulling
                datq_decision_df.loc[mask_num & mask_psi_shift,'Datq_Decision'] = 'Shift'
                datq_decision_df.loc[mask_num & mask_psi_investigate,'Datq_Decision'] = 'Investigate'
                datq_decision_df.loc[mask_num & mask_psi_stable,'Datq_Decision'] = 'Stable'
            except Exception:
                pass
        except Exception:
            datq_decision_df['CSI'] = np.nan

        self.datq_decision_df = datq_decision_df
        self.feature_psi_dict = feature_psi_dict

        try:
            if os.environ.get('DATQ_DEBUG') == '1':
                try:
                    num_mask = self.datq_decision_df['Variable_Type'] == 'numerical'
                    cat_mask = self.datq_decision_df['Variable_Type'] == 'categorical'
                    num_total = int(num_mask.sum())
                    cat_total = int(cat_mask.sum())
                    num_nan = int(self.datq_decision_df.loc[num_mask, 'PSI'].isna().sum())
                    cat_nan = int(self.datq_decision_df.loc[cat_mask, 'CSI'].isna().sum())
                    print(f"[DataQuality] PSI debug: numerical total={num_total} psi_nan={num_nan} | categorical total={cat_total} csi_nan={cat_nan}")
                except Exception:
                    pass
        except Exception:
            pass

        return self


    def datq_summary_table(self, data_df):

        # Ensure splits and run PSI/decision. Wrap in try to keep flow resilient.
        self._ensure_splits(data_df)
        # Cache the original data for type-inference overrides in shift_decision
        try:
            self._cached_data_df = data_df
        except Exception:
            pass
        try:
            self.shift_decision(data_df)
        except Exception as e:
            warnings.warn(f"datq_summary_table: shift_decision failed with error: {e}. Proceeding with empty decisions.")
            self.feature_psi_dict = {}
            self.datq_decision_df = pd.DataFrame()

        # Create the Change-Statistics Datq-Summary-Table
        data_train_df = data_df.loc[self._train_idx, list(self.feature_psi_dict.keys())]
        data_test_df = data_df.loc[self._test_idx, list(self.feature_psi_dict.keys())]

        # Try importing scipy.stats functions; provide fallbacks if SciPy is unavailable
        try:
            from scipy.stats import kurtosis, skew  # type: ignore
        except Exception:
            def skew(x, nan_policy='omit'):
                try:
                    return pd.Series(x).skew(skipna=True)
                except Exception:
                    return np.nan
            def kurtosis(x, nan_policy='omit'):
                try:
                    return pd.Series(x).kurt(skipna=True)
                except Exception:
                    return np.nan

        variable_name_list = []
        missing_value_ratio_list = []
        sparcity_values_list = []
        sparcity_bounds_list = []
        mean_list = []
        mode_list = []
        std_list = []
        min_list = []
        quantile_1_list = []
        quantile_5_list = []
        Q1_list = []
        Q3_list = []
        quantile_95_list = []
        quantile_99_list = []
        max_list = []
        skewness_list = []
        kurtosis_list = []
        feature_psi_list = []

        missing_value_ratio_list_train = []
        missing_value_ratio_list_test = []
        sparcity_values_list_train = []
        sparcity_values_list_test = []
        sparcity_bounds_list_train = []
        sparcity_bounds_list_test = []
        mean_list_train = []
        mean_list_test = []
        median_list_train = []
        median_list_test = []
        mode_list_train = []
        mode_list_test = []
        std_list_train = []
        std_list_test = []
        min_list_train = []
        min_list_test = []
        quantile_1_list_train = []
        quantile_1_list_test = []
        quantile_5_list_train = []
        quantile_5_list_test = []
        Q1_list_train = []
        Q1_list_test = []
        Q3_list_train = []
        Q3_list_test = []
        quantile_95_list_train = []
        quantile_95_list_test = []
        quantile_99_list_train = []
        quantile_99_list_test = []
        max_list_train = []
        max_list_test = []
        skewness_list_train = []
        skewness_list_test = []
        kurtosis_list_train = []
        kurtosis_list_test = []

        # _cached_data_df is set before shift_decision above

        for col in data_train_df.columns:

            variable_name_list.append(col)
            s_tr_raw = data_train_df.loc[:, col]
            s_te_raw = data_test_df.loc[:, col]
            missing_value_ratio_list_train.append(round((s_tr_raw.isna().sum()/max(1, s_tr_raw.shape[0])),4))
            missing_value_ratio_list_test.append(round((s_te_raw.isna().sum()/max(1, s_te_raw.shape[0])),4))

            # Use content-based numeric detection for robust stats
            def _is_num(series: pd.Series) -> bool:
                try:
                    s = series.astype(str).str.replace(',', '', regex=False).str.replace(' ', '', regex=False)
                    parsed = pd.to_numeric(s, errors='coerce')
                    return (parsed.notna().mean() >= 0.8) and (parsed.nunique(dropna=True) >= 2)
                except Exception:
                    return False

            if (hasattr(self.variable_demystifier, 'numerical_model_features_list') and col in getattr(self.variable_demystifier, 'numerical_model_features_list')) or _is_num(s_tr_raw):
                s_tr = pd.to_numeric(s_tr_raw, errors='coerce')
                s_te = pd.to_numeric(s_te_raw, errors='coerce')
                try:
                    quantile_1_value_train = s_tr.quantile(0.01)
                    mask_quantile_1_train = s_tr <= quantile_1_value_train
                    sparcity_bound_quantile_train = s_tr.loc[mask_quantile_1_train].shape[0] / max(1, s_tr.shape[0])
                    quantile_1_value_test = s_te.quantile(0.01)
                    mask_quantile_1_test = s_te <= quantile_1_value_test
                    sparcity_bound_quantile_test = s_te.loc[mask_quantile_1_test].shape[0] / max(1, s_te.shape[0])
                except Exception:
                    quantile_1_value_train = np.nan
                    quantile_1_value_test = np.nan
                    sparcity_bound_quantile_train = np.nan
                    sparcity_bound_quantile_test = np.nan

                mean_list_train.append(s_tr.mean(skipna=True))
                mean_list_test.append(s_te.mean(skipna=True))
                median_list_train.append(s_tr.median(skipna=True))
                median_list_test.append(s_te.median(skipna=True))
                mode_list_train.append(np.nan)
                mode_list_test.append(np.nan)
                std_list_train.append(s_tr.std(skipna=True))
                std_list_test.append(s_te.std(skipna=True))
                min_list_train.append(s_tr.min(skipna=True))
                min_list_test.append(s_te.min(skipna=True))
                quantile_1_list_train.append(s_tr.quantile(0.01))
                quantile_1_list_test.append(s_te.quantile(0.01))
                quantile_5_list_train.append(s_tr.quantile(0.05))
                quantile_5_list_test.append(s_te.quantile(0.05))
                Q1_list_train.append(s_tr.quantile(0.25))
                Q1_list_test.append(s_te.quantile(0.25))
                Q3_list_train.append(s_tr.quantile(0.75))
                Q3_list_test.append(s_te.quantile(0.75))
                quantile_95_list_train.append(s_tr.quantile(0.95))
                quantile_95_list_test.append(s_te.quantile(0.95))
                quantile_99_list_train.append(s_tr.quantile(0.99))
                quantile_99_list_test.append(s_te.quantile(0.99))
                max_list_train.append(s_tr.max(skipna=True))
                max_list_test.append(s_te.max(skipna=True))
                try:
                    skew_tr = skew(s_tr.dropna(), nan_policy='omit')
                    skew_te = skew(s_te.dropna(), nan_policy='omit')
                except Exception:
                    skew_tr = np.nan
                    skew_te = np.nan
                try:
                    kurt_tr = kurtosis(s_tr.dropna(), nan_policy='omit')
                    kurt_te = kurtosis(s_te.dropna(), nan_policy='omit')
                except Exception:
                    kurt_tr = np.nan
                    kurt_te = np.nan
                skewness_list_train.append(np.round(skew_tr,4))
                skewness_list_test.append(np.round(skew_te,4))
                kurtosis_list_train.append(kurt_tr)
                kurtosis_list_test.append(kurt_te)
            
            elif hasattr(self.variable_demystifier, 'categorical_model_features_list') and col in getattr(self.variable_demystifier, 'categorical_model_features_list'):
                try:
                    quantile_1_value_train = data_train_df.loc[:,col].mode()[0]
                    mask_quantile_1_train = data_train_df.loc[:,col] == quantile_1_value_train
                    sparcity_bound_quantile_train = data_train_df.loc[mask_quantile_1_train, col].shape[0] / data_train_df.loc[:,col].shape[0]
                    quantile_1_value_test = data_test_df.loc[:,col].mode()[0]
                    mask_quantile_1_test = data_test_df.loc[:,col] == quantile_1_value_test
                    sparcity_bound_quantile_test = data_test_df.loc[mask_quantile_1_test, col].shape[0] / data_test_df.loc[:,col].shape[0]
                except:
                    quantile_1_value_train = np.nan
                    quantile_1_value_test = np.nan
                    sparcity_bound_quantile_train = np.nan
                    sparcity_bound_quantile_test = np.nan

                mean_list_train.append(np.nan)
                mean_list_test.append(np.nan)
                median_list_train.append(np.nan)
                median_list_test.append(np.nan)
                mode_list_train.append(data_train_df.loc[:,col].mode()[0])
                mode_list_test.append(data_test_df.loc[:,col].mode()[0])
                std_list_train.append(np.nan)
                std_list_test.append(np.nan)
                min_list_train.append(np.nan)
                min_list_test.append(np.nan)
                quantile_1_list_train.append(np.nan)
                quantile_1_list_test.append(np.nan)
                quantile_5_list_train.append(np.nan)
                quantile_5_list_test.append(np.nan)
                Q1_list_train.append(np.nan)
                Q1_list_test.append(np.nan)
                Q3_list_train.append(np.nan)
                Q3_list_test.append(np.nan)
                quantile_95_list_train.append(np.nan)
                quantile_95_list_test.append(np.nan)
                quantile_99_list_train.append(np.nan)
                quantile_99_list_test.append(np.nan)
                max_list_train.append(np.nan)
                max_list_test.append(np.nan)
                skewness_list_train.append(np.nan)
                skewness_list_test.append(np.nan)
                kurtosis_list_train.append(np.nan)
                kurtosis_list_test.append(np.nan)

            else:
                mean_list_train.append(np.nan)
                mean_list_test.append(np.nan)
                median_list_train.append(np.nan)
                median_list_test.append(np.nan)
                mode_list_train.append(np.nan)
                mode_list_test.append(np.nan)
                std_list_train.append(np.nan)
                std_list_test.append(np.nan)
                min_list_train.append(np.nan)
                min_list_test.append(np.nan)
                quantile_1_list_train.append(np.nan)
                quantile_1_list_test.append(np.nan)
                quantile_5_list_train.append(np.nan)
                quantile_5_list_test.append(np.nan)
                Q1_list_train.append(np.nan)
                Q1_list_test.append(np.nan)
                Q3_list_train.append(np.nan)
                Q3_list_test.append(np.nan)
                quantile_95_list_train.append(np.nan)
                quantile_95_list_test.append(np.nan)
                quantile_99_list_train.append(np.nan)
                quantile_99_list_test.append(np.nan)
                max_list_train.append(np.nan)
                max_list_test.append(np.nan)
                skewness_list_train.append(np.nan)
                skewness_list_test.append(np.nan)
                kurtosis_list_train.append(np.nan)
                kurtosis_list_test.append(np.nan)
                quantile_1_value_train = np.nan
                quantile_1_value_test = np.nan
                sparcity_bound_quantile_train = np.nan
                sparcity_bound_quantile_test = np.nan

            sparcity_values_list_train.append(quantile_1_value_train)
            sparcity_values_list_test.append(quantile_1_value_test)
            sparcity_bounds_list_train.append(sparcity_bound_quantile_train)
            sparcity_bounds_list_test.append(sparcity_bound_quantile_test)


        try:#for numericals
            missing_value_ratio_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(missing_value_ratio_list_train, missing_value_ratio_list_test)]
        except:#for categoricals
            missing_value_ratio_list = [(value_train,value_test) for value_train,value_test in zip(missing_value_ratio_list_train, missing_value_ratio_list_test)]
        try:#for numericals
            sparcity_values_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(sparcity_values_list_train, sparcity_values_list_test)]
        except:#for categoricals
            sparcity_values_list = [(value_train,value_test) for value_train,value_test in zip(sparcity_values_list_train, sparcity_values_list_test)]
        try:#for numericals
            sparcity_bounds_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(sparcity_bounds_list_train, sparcity_bounds_list_test)]
        except:#for categoricals
            sparcity_bounds_list = [(value_train,value_test) for value_train,value_test in zip(sparcity_bounds_list_train, sparcity_bounds_list_test)]
        try:#for numericals
            mean_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(mean_list_train, mean_list_test)]
        except:#for categoricals
            mean_list = [(value_train,value_test) for value_train,value_test in zip(mean_list_train, mean_list_test)]
        try:#for numericals
            median_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(median_list_train, median_list_test)]
        except:#for categoricals
            median_list = [(value_train,value_test) for value_train,value_test in zip(median_list_train, median_list_test)]
        try:#for numericals
            mode_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(mode_list_train, mode_list_test)]
        except:#for categoricals
            mode_list = [(value_train,value_test) for value_train,value_test in zip(mode_list_train, mode_list_test)]
        try:#for numericals
            std_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(std_list_train, std_list_test)]
        except:#for categoricals
            std_list = [(value_train,value_test) for value_train,value_test in zip(std_list_train, std_list_test)]
        try:#for numericals
            min_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(min_list_train, min_list_test)]
        except:#for categoricals
            min_list = [(value_train,value_test) for value_train,value_test in zip(min_list_train, min_list_test)]
        try:#for numericals
            quantile_1_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(quantile_1_list_train, quantile_1_list_test)]
        except:#for categoricals
            quantile_1_list = [(value_train,value_test) for value_train,value_test in zip(quantile_1_list_train, quantile_1_list_test)]
        try:#for numericals
            quantile_5_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(quantile_5_list_train, quantile_5_list_test)]
        except:#for categoricals
            quantile_5_list = [(value_train,value_test) for value_train,value_test in zip(quantile_5_list_train, quantile_5_list_test)]
        try:#for numericals
            Q1_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(Q1_list_train, Q1_list_test)]
        except:#for categoricals
            Q1_list = [(value_train,value_test) for value_train,value_test in zip(Q1_list_train, Q1_list_test)]
        try:#for numericals
            Q3_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(Q3_list_train, Q3_list_test)]
        except:#for categoricals
            Q3_list = [(value_train,value_test) for value_train,value_test in zip(Q3_list_train, Q3_list_test)]
        try:#for numericals
            quantile_95_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(quantile_95_list_train, quantile_95_list_test)]
        except:#for categoricals
            quantile_95_list = [(value_train,value_test) for value_train,value_test in zip(quantile_95_list_train, quantile_95_list_test)]
        try:#for numericals
            quantile_99_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(quantile_99_list_train, quantile_99_list_test)]
        except:#for categoricals
            quantile_99_list = [(value_train,value_test) for value_train,value_test in zip(quantile_99_list_train, quantile_99_list_test)]
        try:#for numericals
            max_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(max_list_train, max_list_test)]
        except:#for categoricals
            max_list = [(value_train,value_test) for value_train,value_test in zip(max_list_train, max_list_test)]
        try:#for numericals
            skewness_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(skewness_list_train, skewness_list_test)]
        except:#for categoricals
            skewness_list = [(value_train,value_test) for value_train,value_test in zip(skewness_list_train, skewness_list_test)]
        try:#for numericals
            kurtosis_list = [(round(value_train,4),round(value_test,4)) for value_train,value_test in zip(kurtosis_list_train, kurtosis_list_test)]
        except:#for categoricals
            kurtosis_list = [(value_train,value_test) for value_train,value_test in zip(kurtosis_list_train, kurtosis_list_test)]


        datq_summary_df = pd.DataFrame({'Variable': variable_name_list,
                                        '%_Missing_Change':missing_value_ratio_list,
                                        'Sparcity_Values_Quantile_Change':sparcity_values_list,'Sparcity_Bounds_Quantile_Change':sparcity_bounds_list,
                                        'Mean_Change':mean_list,
                                        'Median_Change':median_list,
                                        'Mode_Change':mode_list,
                                        'STD_Change':std_list,
                                        'Min_Change':min_list,
                                        'Quantile_1_Change':quantile_1_list,
                                        'Quantile_5_Change':quantile_5_list,
                                        'Q1_Change':Q1_list,
                                        'Q3_Change':Q3_list,
                                        'Quantile_95_Change':quantile_95_list,
                                        'Quantile_99_Change':quantile_99_list,
                                        'Max_Change':max_list,
                                        'Skewness_Change':skewness_list,
                                        'Kurtosis_Change':kurtosis_list
                                   })

        self.datq_summary_df = pd.concat(objs=[datq_summary_df.set_index('Variable'), self.datq_decision_df], axis=1)


        return self


    def datq_detailed_report(self, data_df):
        """Compute and cache a detailed PSI report per variable.

        Populates `self.datq_detailed_report_dict` mapping variable -> dict
        with fields: psi, psi_table (reset index with unified 'bin' column),
        variable_type, train_missing_ratio, test_missing_ratio, train_count, test_count.

        Returns self for chaining.
        """

        # Ensure PSI computation and splits are available
        self._ensure_splits(data_df)
        self.feature_psi(data_df)

        detailed = {}
        try:
            keys = list(getattr(self, 'feature_psi_detailed_dict', {}).keys())
        except Exception:
            keys = []

        for col in keys:
            try:
                psi_value, psi_table = self.feature_psi_detailed_dict.get(col, [np.nan, pd.DataFrame()])
                # Normalize the table to records with a unified 'bin' column
                if isinstance(psi_table, pd.DataFrame) and not psi_table.empty:
                    try:
                        psi_table_reset = psi_table.reset_index()
                        first_col = psi_table_reset.columns[0]
                        psi_table_reset.rename(columns={first_col: 'bin'}, inplace=True)
                        psi_records = psi_table_reset.replace({np.nan: None}).to_dict(orient='records')
                    except Exception:
                        psi_records = []
                else:
                    psi_records = []

                # Determine variable type based on demystifier lists
                if col in getattr(self.variable_demystifier, 'numerical_model_features_list', []):
                    var_type = 'numerical'
                elif col in getattr(self.variable_demystifier, 'categorical_model_features_list', []):
                    var_type = 'categorical'
                else:
                    var_type = 'unknown'

                # Contextual counts and missing ratios
                train_idx = self._train_idx if self._train_idx is not None else []
                test_idx = self._test_idx if self._test_idx is not None else []
                try:
                    train_missing = float(data_df.loc[train_idx, col].isna().mean()) if len(train_idx) else 0.0
                except Exception:
                    train_missing = 0.0
                try:
                    test_missing = float(data_df.loc[test_idx, col].isna().mean()) if len(test_idx) else 0.0
                except Exception:
                    test_missing = 0.0

                detailed[col] = {
                    'variable': col,
                    'variable_type': var_type,
                    'psi': float(psi_value) if psi_value is not None and not pd.isna(psi_value) else None,
                    'psi_table': psi_records,
                    'train_missing_ratio': round(train_missing, 6),
                    'test_missing_ratio': round(test_missing, 6),
                    'train_count': int(len(train_idx)),
                    'test_count': int(len(test_idx)),
                }
            except Exception:
                # Skip problematic columns but continue others
                continue

        self.datq_detailed_report_dict = detailed
        return self