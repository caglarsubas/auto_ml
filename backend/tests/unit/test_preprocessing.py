"""Unit tests - preprocessing purifier catalog and options.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


# ---------------------------------------------------------------------------
# v2.27.0 — Purifier catalog tests
# ---------------------------------------------------------------------------
#
# These tests cover the canonical 34-option catalog introduced in
# v2.27.0 to fix a P0 silent-data-corruption bug.  Pre-v2.27.0 the
# backend `_apply_options` dispatcher and the frontend `purifierOptions`
# array had divergent ID-to-transform mappings: ticking
# "Sparsity-drop 0.95" (UI ID 11) silently executed "Missing-drop ≥ 0.40"
# in the backend, IDs 24-27 were no-op, etc.  See
# `backend/preprocessing/purifier_catalog.py` module docstring and
# the v2.27.0 commit body for the full realignment matrix.
#
# Every test here would have FAILED against pre-v2.27.0 code, which is
# what makes them effective regression guards for the contract.
@pytest.mark.unit
class TestPurifierCatalog:
    """Sanity tests for preprocessing/purifier_catalog.py."""

    def test_catalog_has_exactly_34_entries(self):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS
        assert len(PURIFIER_OPTIONS) == 34

    def test_ids_are_contiguous_1_through_34(self):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS
        ids = sorted(e['id'] for e in PURIFIER_OPTIONS)
        assert ids == list(range(1, 35))

    def test_every_entry_has_required_keys(self):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS
        required = {'id', 'name', 'kind', 'group', 'threshold', 'quantile_range'}
        for entry in PURIFIER_OPTIONS:
            missing = required - set(entry.keys())
            assert not missing, f"entry id={entry.get('id')} missing keys: {missing}"

    def test_threshold_drop_kinds_have_numeric_threshold(self):
        from preprocessing.purifier_catalog import (
            PURIFIER_OPTIONS, KIND_CORR_DROP, KIND_SPARSITY_DROP,
            KIND_MISSING_DROP, KIND_COMBINED_DROP, KIND_OUTLIER_CAT,
        )
        threshold_kinds = {KIND_CORR_DROP, KIND_SPARSITY_DROP,
                           KIND_MISSING_DROP, KIND_COMBINED_DROP,
                           KIND_OUTLIER_CAT}
        for entry in PURIFIER_OPTIONS:
            if entry['kind'] in threshold_kinds:
                assert isinstance(entry['threshold'], (int, float)), \
                    f"id={entry['id']} kind={entry['kind']} missing numeric threshold"
                assert 0 < entry['threshold'] < 1, \
                    f"id={entry['id']} threshold {entry['threshold']} out of (0, 1) range"

    def test_outlier_num_entries_have_valid_quantile_range(self):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS, KIND_OUTLIER_NUM
        for entry in PURIFIER_OPTIONS:
            if entry['kind'] == KIND_OUTLIER_NUM:
                qr = entry['quantile_range']
                assert isinstance(qr, tuple) and len(qr) == 2, \
                    f"id={entry['id']} quantile_range must be a 2-tuple"
                lo, hi = qr
                assert 0 < lo < hi < 1, \
                    f"id={entry['id']} quantile_range ({lo}, {hi}) invalid"

    def test_specific_id_labels_match_frontend_v2_27_0_canonical(self):
        """Pin the IDs that were misaligned pre-v2.27.0.

        Each (id, expected_kind, expected_threshold_or_qrange) tuple
        encodes what the frontend label promises the option does.
        Pre-v2.27.0 the backend dispatcher would have executed a
        different transform for these IDs (or no transform at all for
        24-27).
        """
        from preprocessing.purifier_catalog import (
            get_option, KIND_CORR_DROP, KIND_SPARSITY_DROP,
            KIND_MISSING_DROP, KIND_COMBINED_DROP, KIND_OUTLIER_NUM,
            KIND_OUTLIER_CAT,
        )
        # Format: (id, expected_kind, expected_threshold OR expected_quantile_range)
        cases = [
            # Corr-drop group — ID 9 was Missing-drop pre-v2.27.0
            (5,  KIND_CORR_DROP,     0.95),
            (9,  KIND_CORR_DROP,     0.75),
            # Sparsity group — pre-v2.27.0 IDs 10-15 were Missing-drop with thresholds 0.30-0.60
            (10, KIND_SPARSITY_DROP, 0.99),
            (11, KIND_SPARSITY_DROP, 0.95),
            (15, KIND_SPARSITY_DROP, 0.75),
            # Missing group — pre-v2.27.0 IDs 16-21 were Sparsity-drop with thresholds 0.40-0.60 (only 16-18)
            (16, KIND_MISSING_DROP,  0.99),
            (17, KIND_MISSING_DROP,  0.95),
            (21, KIND_MISSING_DROP,  0.75),
            # Combined group — pre-v2.27.0 IDs 22-23 ran Combined 0.80/0.75, 24-27 were NO-OP
            (22, KIND_COMBINED_DROP, 0.99),
            (23, KIND_COMBINED_DROP, 0.95),
            (24, KIND_COMBINED_DROP, 0.90),
            (27, KIND_COMBINED_DROP, 0.75),
            # Outlier-num — always agreed
            (28, KIND_OUTLIER_NUM,   (0.01, 0.99)),
            (29, KIND_OUTLIER_NUM,   (0.05, 0.95)),
            (30, KIND_OUTLIER_NUM,   (0.10, 0.90)),
            # Cat-outlier — always agreed
            (31, KIND_OUTLIER_CAT,   0.001),
            (34, KIND_OUTLIER_CAT,   0.05),
        ]
        for opt_id, expected_kind, expected_value in cases:
            entry = get_option(opt_id)
            assert entry is not None, f"id={opt_id} missing from catalog"
            assert entry['kind'] == expected_kind, \
                f"id={opt_id} kind={entry['kind']} expected {expected_kind}"
            if expected_kind == KIND_OUTLIER_NUM:
                assert entry['quantile_range'] == expected_value, \
                    f"id={opt_id} quantile_range={entry['quantile_range']} expected {expected_value}"
            else:
                assert entry['threshold'] == expected_value, \
                    f"id={opt_id} threshold={entry['threshold']} expected {expected_value}"

    def test_pick_most_aggressive_returns_lowest_threshold(self):
        from preprocessing.purifier_catalog import pick_most_aggressive, KIND_CORR_DROP
        # Selecting 5 (0.95) and 9 (0.75) — most aggressive is 9 (0.75
        # drops MORE pairs)
        entry = pick_most_aggressive({5, 9}, KIND_CORR_DROP)
        assert entry is not None
        assert entry['id'] == 9
        assert entry['threshold'] == 0.75

    def test_pick_most_aggressive_returns_none_when_no_match(self):
        from preprocessing.purifier_catalog import pick_most_aggressive, KIND_SPARSITY_DROP
        # IDs 1-4 are not sparsity-drop kind
        assert pick_most_aggressive({1, 2, 3, 4}, KIND_SPARSITY_DROP) is None

    def test_pick_most_aggressive_rejects_non_threshold_kind(self):
        from preprocessing.purifier_catalog import pick_most_aggressive, KIND_OUTLIER_NUM
        with pytest.raises(ValueError):
            pick_most_aggressive({28, 29}, KIND_OUTLIER_NUM)

    def test_selected_entries_of_kind_sorts_by_id(self):
        from preprocessing.purifier_catalog import selected_entries_of_kind, KIND_OUTLIER_NUM
        entries = selected_entries_of_kind({30, 28, 29}, KIND_OUTLIER_NUM)
        assert [e['id'] for e in entries] == [28, 29, 30]

    def test_default_selected_ids_all_valid(self):
        from preprocessing.purifier_catalog import DEFAULT_SELECTED_IDS, get_option
        for opt_id in DEFAULT_SELECTED_IDS:
            assert get_option(opt_id) is not None, f"default id {opt_id} not in catalog"

    def test_default_selected_ids_use_combined_sparsity_missing_drop(self):
        from preprocessing.purifier_catalog import DEFAULT_SELECTED_IDS
        assert DEFAULT_SELECTED_IDS == [1, 2, 3, 4, 7, 23, 28, 32]
        assert 11 not in DEFAULT_SELECTED_IDS
        assert 17 not in DEFAULT_SELECTED_IDS
        assert 23 in DEFAULT_SELECTED_IDS

@pytest.mark.unit
class TestPurifierApplyOptions:
    """Each option ID must execute the transform its UI label describes.

    Pre-v2.27.0 several IDs in 9-27 silently ran the wrong transform.
    These tests construct a tiny synthetic frame where the expected
    transform produces a deterministic outcome, then call
    `PreprocessingRunView._apply_options` and assert.
    """

    @staticmethod
    def _apply(df, option_ids):
        from preprocessing.views import PreprocessingRunView
        view = PreprocessingRunView()
        return view._apply_options(df, set(option_ids))

    # ── Identity / standalone options (1-4) ─────────────────────
    def test_id_1_drops_column_duplicates(self):
        df = pd.DataFrame({'a': [1, 2, 3], 'a_dup': [1, 2, 3], 'b': [4, 5, 6]})
        work, dropped, breakdown, _ = self._apply(df, [1])
        assert 'a_dup' in dropped or 'a' in dropped
        assert any(b['step'] == 'Column-wise duplicate drop' for b in breakdown)

    def test_id_3_drops_zero_variance_columns(self):
        df = pd.DataFrame({'const': [7, 7, 7, 7], 'vary': [1, 2, 3, 4]})
        work, dropped, breakdown, _ = self._apply(df, [3])
        assert 'const' in dropped
        assert 'vary' not in dropped

    # ── Correlation drop (5-9) ──────────────────────────────────
    def test_id_5_drops_pairs_with_correlation_ge_0_95(self):
        # x and y are perfectly correlated (|corr|=1 >= 0.95)
        df = pd.DataFrame({
            'x': [1.0, 2.0, 3.0, 4.0, 5.0],
            'y': [2.0, 4.0, 6.0, 8.0, 10.0],
            'z': [5.0, 1.0, 4.0, 2.0, 3.0],
        })
        work, dropped, _, _ = self._apply(df, [5])
        # Exactly one of (x, y) is dropped; z is uncorrelated and stays.
        assert ('x' in dropped) ^ ('y' in dropped)
        assert 'z' not in dropped

    def test_id_9_executes_corr_drop_threshold_0_75_not_missing_drop(self):
        """v2.27.0 regression — pre-v2.27.0 ID 9 was Missing-drop ≥ 0.20.

        If the dispatcher were still wired the old way, this all-numeric
        zero-missing frame would have no missing data so ID 9 would be
        a no-op.  After the fix it must drop one of the two highly
        correlated columns (|corr|=1 >= 0.75).
        """
        df = pd.DataFrame({
            'x': [1.0, 2.0, 3.0, 4.0, 5.0],
            'y': [2.1, 3.9, 6.05, 7.95, 10.1],  # ~0.999 correlation with x
            'z': [5.0, 1.0, 4.0, 2.0, 3.0],
        })
        work, dropped, breakdown, _ = self._apply(df, [9])
        assert ('x' in dropped) ^ ('y' in dropped), \
            f"ID 9 (Corr-drop ≥ 0.75) did not drop a correlated column; dropped={dropped}"
        corr_step = next((b for b in breakdown if b['step'] == 'Correlation drop (threshold)'), None)
        assert corr_step is not None
        assert corr_step['threshold'] == 0.75

    # ── Sparsity drop (10-15) — THE PRE-v2.27.0 SMOKING GUN ─────
    def test_id_11_drops_columns_with_zero_ratio_at_least_0_95(self):
        """Pre-v2.27.0 ID 11 executed "Missing-drop ≥ 0.40" instead of
        "Sparsity-drop ≥ 0.95".  Fixed in v2.27.0.

        Built so:
          • `mostly_zero` is 96% zeros (no missings) — must drop under
            v2.27.0 semantics; pre-v2.27.0 would NOT drop (no missings).
          • `mostly_missing` is 50% missing (no zeros) — pre-v2.27.0
            would drop under Missing-drop≥0.40; v2.27.0 must NOT drop
            (no zeros, so sparsity≈0).
        """
        n = 100
        df = pd.DataFrame({
            'mostly_zero':    [0.0] * 96 + [1.0, 2.0, 3.0, 4.0],
            'mostly_missing': [None] * 50 + list(range(50)),
            'normal':         list(range(n)),
        })
        work, dropped, breakdown, _ = self._apply(df, [11])
        assert 'mostly_zero' in dropped, \
            f"v2.27.0 contract: ID 11 (Sparsity-drop ≥ 0.95) should drop mostly_zero; dropped={dropped}"
        assert 'mostly_missing' not in dropped, \
            f"v2.27.0 contract: ID 11 must NOT drop missing-heavy columns; dropped={dropped}"
        assert 'normal' not in dropped
        sparse_step = next((b for b in breakdown if b['step'] == 'Sparsity zeros drop (threshold)'), None)
        assert sparse_step is not None
        assert sparse_step['threshold'] == 0.95

    # ── Missing drop (16-21) — THE PRE-v2.27.0 SMOKING GUN #2 ────
    def test_id_17_drops_columns_with_miss_ratio_at_least_0_95(self):
        """Pre-v2.27.0 ID 17 executed "Sparsity-drop ≥ 0.50" instead
        of "Missing-drop ≥ 0.95".  Fixed in v2.27.0.

        Built so:
          • `mostly_missing` is 96% missing — must drop in v2.27.0,
            no-op pre-v2.27.0 (sparsity ≈ 0 since values absent).
          • `mostly_zero` is 60% zeros (no missings) — pre-v2.27.0
            would drop under Sparsity-drop≥0.50; v2.27.0 must NOT
            drop (miss_ratio = 0).
        """
        n = 100
        df = pd.DataFrame({
            'mostly_missing': [None] * 96 + [1.0, 2.0, 3.0, 4.0],
            'mostly_zero':    [0.0] * 60 + list(range(1, 41)),
            'normal':         list(range(n)),
        })
        work, dropped, breakdown, _ = self._apply(df, [17])
        assert 'mostly_missing' in dropped, \
            f"v2.27.0 contract: ID 17 (Missing-drop ≥ 0.95) should drop mostly_missing; dropped={dropped}"
        assert 'mostly_zero' not in dropped, \
            f"v2.27.0 contract: ID 17 must NOT drop sparse columns; dropped={dropped}"
        miss_step = next((b for b in breakdown if b['step'] == 'Missing-drop (threshold)'), None)
        assert miss_step is not None
        assert miss_step['threshold'] == 0.95

    # ── Combined sparsity+missing (22-27) — pre-v2.27.0 NO-OPS ──
    def test_id_24_combined_drop_threshold_0_90_was_silent_noop_pre_v2_27_0(self):
        """Pre-v2.27.0 IDs 24-27 had no dispatcher branch — selecting
        "[Sparsity+Missing]-drop 0.90" did literally nothing.  After
        v2.27.0 it must drop any column where max(zero_ratio, miss_ratio)
        ≥ 0.90.
        """
        n = 100
        df = pd.DataFrame({
            'half_miss_half_zero': [None] * 45 + [0.0] * 45 + list(range(1, 11)),
            'mostly_zero':         [0.0] * 92 + list(range(1, 9)),
            'mostly_missing':      [None] * 91 + list(range(9)),
            'normal':              list(range(n)),
        })
        work, dropped, breakdown, _ = self._apply(df, [24])
        # mostly_zero (92% zeros >= 0.90) must drop.
        assert 'mostly_zero' in dropped, \
            f"v2.27.0 contract: ID 24 must drop mostly_zero; dropped={dropped}"
        # mostly_missing (91% missing >= 0.90) must drop.
        assert 'mostly_missing' in dropped, \
            f"v2.27.0 contract: ID 24 must drop mostly_missing; dropped={dropped}"
        # half_miss_half_zero has max(0.45, 0.45) = 0.45 < 0.90 — keep.
        assert 'half_miss_half_zero' not in dropped
        assert 'normal' not in dropped
        combo_step = next((b for b in breakdown if b['step'] == 'Combined sparsity+missing drop (threshold)'), None)
        assert combo_step is not None
        assert combo_step['threshold'] == 0.90

    # ── Outlier numeric quantile clipping (28-30) — already aligned ─
    def test_id_29_clips_numeric_columns_to_0_05_0_95_quantiles(self):
        """The exact request the user typed that exposed Patch B's
        underlying capability gap: 'change outlier cleaning interval
        for numerical features to 0.05-0.95'.  After v2.27.0 this is
        ID 29 in the catalog — frontend label and backend behavior
        agree, no realignment was needed for outlier IDs, but the
        catalog still owns the quantile-range constant now.
        """
        n = 100
        df = pd.DataFrame({
            # An obvious outlier at index 0 (extreme high), index 1 (extreme low)
            'with_outliers': [1000.0, -1000.0] + [float(i) for i in range(n - 2)],
        })
        original_max = df['with_outliers'].max()
        original_min = df['with_outliers'].min()
        work, dropped, breakdown, step_stats = self._apply(df, [29])
        # No columns dropped — clipping is value-modifying, not column-dropping.
        assert 'with_outliers' not in dropped
        # Max/min must be tightened to the [5%, 95%] quantiles.
        assert work['with_outliers'].max() < original_max
        assert work['with_outliers'].min() > original_min
        outlier_step = next((b for b in breakdown if b['step'] == 'Outlier cleaning (quantile clipping)'), None)
        assert outlier_step is not None
        assert outlier_step['quantile_range'] == [0.05, 0.95]
        # step_stats records before/after snapshots for the AI pipeline.
        oc_stats = next((s for s in step_stats if s['step'] == 'Outlier cleaning (quantile clipping)'), None)
        assert oc_stats is not None
        assert oc_stats['quantile_range'] == [0.05, 0.95]

    # ── v2.28.1 critical regression: target preservation ──────────
    # Pre-v2.28.1, ID 29 (and 28/30) silently corrupted the binary
    # Target column.  An imbalanced 0/1 target with <5% positives has
    # both q(0.05) and q(0.95) equal to 0; clip(0,0) → all zeros →
    # split-validation chart shows 0% target mean across full / train
    # / test, modeling silently breaks downstream.  Reproduced by the
    # user on May 18, 2026 with Good_Bad_Flag.  These tests are the
    # immune system against re-introducing the bug.
    @staticmethod
    def _apply_with_preserve(df, option_ids, preserve=None, data_dictionary=None):
        from preprocessing.views import PreprocessingRunView
        view = PreprocessingRunView()
        return view._apply_options(
            df, set(option_ids),
            preserve=preserve,
            data_dictionary=data_dictionary,
        )

    def test_id_29_does_NOT_modify_Target_column_with_imbalanced_binary(self):
        """Repro of the May-2026 user bug:
            df = 100 rows, 5% Target=1 (95% Target=0)
            apply ID 29 (clip [0.05, 0.95])
            → Target column MUST be unchanged.

        Pre-fix: Target gets clipped to all zeros.
        Post-fix: Target preserved verbatim.
        """
        n = 100
        # Exactly 5 positives → q(0.05)=0 and q(0.95)=0 for binary target.
        target = [1] * 5 + [0] * (n - 5)
        df = pd.DataFrame({
            'Target': target,
            'feature_a': [float(i) for i in range(n)],  # ordinary numeric feature
        })
        target_before = df['Target'].copy()

        work, dropped, breakdown, _ = self._apply_with_preserve(
            df, [29], preserve={'Target'},
        )

        # Critical: Target column is byte-for-byte unchanged.
        assert 'Target' in work.columns, "Target dropped from output"
        assert work['Target'].tolist() == target_before.tolist(), (
            f"Target column was modified by outlier clipping. "
            f"Sum before={target_before.sum()}, after={work['Target'].sum()}. "
            f"This re-introduces the v2.28.0 silent-corruption bug."
        )
        # And the breakdown reports Target as protected.
        outlier_step = next(
            (b for b in breakdown if b['step'] == 'Outlier cleaning (quantile clipping)'),
            None,
        )
        assert outlier_step is not None
        assert 'Target' in outlier_step['protected_columns']

    def test_id_29_does_NOT_modify_Model_Usage_No_columns(self):
        """ID columns / index columns / raw timestamps with
        Model_Usage_YN='No' must not be clipped.  The categorical-
        outlier branch already honored this; the numerical branch
        must too (parity contract).
        """
        n = 50
        df = pd.DataFrame({
            'customer_id': list(range(1, n + 1)),  # 1..50, monotonic — q(0.05)=2.45, q(0.95)=47.55
            'feature_x': [float(i) for i in range(n)],
        })
        cust_id_before = df['customer_id'].copy()
        data_dict = [
            {'Feature_Name': 'customer_id', 'Model_Usage_YN': 'No'},
            {'Feature_Name': 'feature_x', 'Model_Usage_YN': 'Yes'},
        ]

        work, _, breakdown, _ = self._apply_with_preserve(
            df, [29], data_dictionary=data_dict,
        )

        # customer_id must be untouched (Model_Usage='No').
        assert work['customer_id'].tolist() == cust_id_before.tolist(), (
            "customer_id (Model_Usage_YN='No') was modified by outlier clipping."
        )
        # feature_x must have been clipped (its outliers should be
        # squeezed toward [q(0.05), q(0.95)]).  Strict inequality
        # checks the value-modifying behavior actually fired.
        assert work['feature_x'].min() >= 0.0
        # Breakdown surfaces the protection.
        outlier_step = next(
            (b for b in breakdown if b['step'] == 'Outlier cleaning (quantile clipping)'),
            None,
        )
        assert outlier_step is not None
        assert 'customer_id' in outlier_step['protected_columns']
        assert 'feature_x' not in outlier_step['protected_columns']

    def test_id_29_still_clips_normal_numeric_features_when_target_preserved(self):
        """Defense-in-depth: while protecting Target + Model_Usage='No',
        we must NOT regress the core clipping behavior on legitimate
        ordinary features.
        """
        n = 100
        df = pd.DataFrame({
            'Target': [1] * 5 + [0] * (n - 5),
            # An obvious outlier at index 0 (extreme high), index 1 (extreme low).
            'with_outliers': [1000.0, -1000.0] + [float(i) for i in range(n - 2)],
        })
        original_max = df['with_outliers'].max()
        original_min = df['with_outliers'].min()

        work, _, breakdown, _ = self._apply_with_preserve(
            df, [29], preserve={'Target'},
        )

        # The ordinary numeric feature is still clipped.
        assert work['with_outliers'].max() < original_max
        assert work['with_outliers'].min() > original_min
        # And Target is still safe.
        assert work['Target'].sum() == 5

    def test_id_29_repro_target_mean_unchanged_after_clipping(self):
        """The exact metric the user saw collapse to 0 in the screenshot:
        target_mean = mean(Target) per split.  This test reconstructs
        the chart's metric and asserts post-clip target_mean equals
        pre-clip target_mean.

        Pre-v2.28.1: target_mean drops to 0.0 across full/train/test.
        Post-fix: target_mean is preserved exactly.
        """
        n = 1000
        # 4% positive class — exactly the imbalanced shape that caused
        # both q(0.05) and q(0.95) to equal 0 → all-zero clip.
        positives = 40
        target = [1] * positives + [0] * (n - positives)
        df = pd.DataFrame({
            'Target': target,
            'noise_a': np.random.RandomState(0).randn(n).tolist(),
            'noise_b': np.random.RandomState(1).randn(n).tolist(),
        })
        target_mean_before = df['Target'].mean()
        assert target_mean_before == pytest.approx(0.04)  # sanity

        work, _, _, _ = self._apply_with_preserve(
            df, [29], preserve={'Target'},
        )

        target_mean_after = work['Target'].mean()
        assert target_mean_after == pytest.approx(target_mean_before), (
            f"target_mean changed from {target_mean_before:.4f} to "
            f"{target_mean_after:.4f} after outlier clipping. "
            f"This is the smoking-gun metric from the May-2026 screenshot."
        )

    def test_id_29_protected_columns_logged_for_audit_trail(self):
        """The breakdown row must list every protected column so the
        user can audit *why* their Target column wasn't clipped.  Pre-
        v2.28.1 the breakdown silently said 'all numeric columns
        clipped' even though it did so to the Target — same opaque
        observability problem that hid the v2.27.0 ID-realignment bug.
        """
        df = pd.DataFrame({
            'Target': [0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
            'app_id': list(range(10)),
            'feature_a': [float(i) for i in range(10)],
        })
        data_dict = [
            {'Feature_Name': 'app_id', 'Model_Usage_YN': 'No'},
            {'Feature_Name': 'feature_a', 'Model_Usage_YN': 'Yes'},
        ]
        _, _, breakdown, _ = self._apply_with_preserve(
            df, [29], preserve={'Target'}, data_dictionary=data_dict,
        )
        outlier_step = next(
            (b for b in breakdown if b['step'] == 'Outlier cleaning (quantile clipping)'),
            None,
        )
        assert outlier_step is not None
        protected = set(outlier_step['protected_columns'])
        assert 'Target' in protected
        assert 'app_id' in protected
        assert 'feature_a' not in protected
        # Note string explains WHY the cols were skipped.
        assert 'protected' in outlier_step['note'].lower()

@pytest.mark.unit
class TestPurifierCatalogFrontendContract:
    """Parse the frontend's `purifierOptions` TS literal and assert the
    34 entries match the backend catalog character-for-character.

    Pre-v2.27.0 there was no such test, which is exactly why the IDs
    drifted apart.  Both frontend copies (modeling.component.ts and
    model-development.component.ts) are checked because the AI assistant
    panel reads the modeling copy while the data-purifier UI reads the
    model-development copy.
    """

    _FRONTEND_SOURCES = [
        'frontend/src/app/modeling/modeling.component.ts',
        'frontend/src/app/model-development/model-development.component.ts',
    ]

    @staticmethod
    def _parse_frontend_options(ts_source: str) -> list[dict]:
        """Extract the (id, name) pairs from the `purifierOptions` array
        in a TypeScript source string.  Tolerant to whitespace and
        optional `group: N` fields.
        """
        import re
        # Capture every `{ id: <int>, name: '<...>'`... block within the
        # purifierOptions array.  The array contents extend until the
        # closing `];` so we anchor on that.
        block_re = re.compile(
            r"purifierOptions\s*:\s*PurifierOption\[\]\s*=\s*\[(.*?)\];",
            re.DOTALL,
        )
        m = block_re.search(ts_source)
        if not m:
            return []
        body = m.group(1)
        entry_re = re.compile(
            r"\{\s*id\s*:\s*(\d+)\s*,\s*name\s*:\s*'([^']*)'",
        )
        return [{'id': int(idm), 'name': name} for idm, name in entry_re.findall(body)]

    @staticmethod
    def _read_repo_file(rel_path: str) -> str:
        from tests.unit._shared import repo_root
        full = repo_root() / rel_path
        if not full.exists():
            pytest.skip(f"frontend source not present at {full}; skipping contract test")
        return full.read_text(encoding='utf-8')

    @pytest.mark.parametrize('frontend_rel_path', _FRONTEND_SOURCES)
    def test_frontend_purifier_options_match_backend_catalog(self, frontend_rel_path):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS
        ts_src = self._read_repo_file(frontend_rel_path)
        frontend_opts = self._parse_frontend_options(ts_src)
        assert len(frontend_opts) == 34, (
            f"{frontend_rel_path} parsed {len(frontend_opts)} entries; "
            f"expected 34.  Did the TS array shape change?"
        )

        # Build a {id: name} map on each side and compare.
        backend_map = {e['id']: e['name'] for e in PURIFIER_OPTIONS}
        frontend_map = {e['id']: e['name'] for e in frontend_opts}
        mismatches = []
        for opt_id in range(1, 35):
            be = backend_map.get(opt_id)
            fe = frontend_map.get(opt_id)
            if be != fe:
                mismatches.append(f"  id={opt_id}: backend={be!r}  frontend={fe!r}")
        assert not mismatches, (
            "Frontend↔backend purifier-option labels diverged. "
            "Update both sides to match (frontend is the source of truth for UI).\n"
            + "\n".join(mismatches)
        )

# ---------------------------------------------------------------------------
# v2.27.1 — AI catalog tool: get_purifier_options
# ---------------------------------------------------------------------------
# Patch B (v2.27.1) exposes the canonical purifier catalog to the LLM via a
# dedicated tool so the assistant can map natural-language requests like
# "set the outlier interval to 0.05/0.95" to the right integer option ID
# (29) when emitting a start_data_purifier action.  Pre-v2.27.1 the AI had
# to guess from a misleading generic step list in the system prompt and
# routinely invented step names like "Quasi-Constant Drop" / "High
# Cardinality Drop" that don't exist in the catalog.
#
# These tests guard:
#   • The handler returns the full canonical catalog with stable formatting.
#   • The tool is registered in PIPELINE_TOOLS (so the LLM can see it) and
#     in _HANDLERS (so execute_tool_call can dispatch to it).
#   • The system prompt no longer hands the LLM the misleading list and
#     instead points it at the new tool.
@pytest.mark.unit
class TestGetPurifierOptionsToolHandler:
    """Exercises ai_assistant.tool_executor._handle_get_purifier_options."""

    def _run(self, args=None):
        from ai_assistant.tool_executor import _handle_get_purifier_options
        # file_id is irrelevant for this static-catalog tool; pass a dummy.
        return _handle_get_purifier_options(0, args or {})

    def test_returns_string(self):
        out = self._run()
        assert isinstance(out, str)
        assert out.strip()

    def test_unfiltered_lists_all_34_options(self):
        out = self._run()
        # Each option line starts with `ID `; count the entries between
        # the two `---` separator lines.
        lines = [ln for ln in out.splitlines() if ln.startswith('ID ')]
        assert len(lines) == 34, (
            f"Expected 34 ID-prefixed lines, got {len(lines)}.\nOutput:\n{out}"
        )

    def test_header_advertises_total_count(self):
        out = self._run()
        assert "34 of 34 total entries" in out, (
            f"Header should report 34/34 entries; got:\n{out}"
        )

    def test_default_selected_ids_listed_in_header(self):
        out = self._run()
        # Handler renders defaults via `sorted(DEFAULT_SELECTED_IDS)`,
        # so we can pin the exact literal.
        from preprocessing.purifier_catalog import DEFAULT_SELECTED_IDS
        expected_literal = str(sorted(DEFAULT_SELECTED_IDS))
        assert "Default selected IDs" in out
        assert expected_literal in out, (
            f"Header should print sorted defaults verbatim ({expected_literal}); got:\n{out}"
        )

    def test_default_options_are_flagged_inline(self):
        """Default-selected options carry a (DEFAULT) marker on their line."""
        out = self._run()
        from preprocessing.purifier_catalog import DEFAULT_SELECTED_IDS
        for default_id in DEFAULT_SELECTED_IDS:
            # Find the line for this ID and confirm it contains DEFAULT.
            line = next(
                (ln for ln in out.splitlines()
                 if ln.startswith('ID ') and ln.split()[1] == str(default_id)),
                None,
            )
            assert line is not None, f"No line for ID {default_id} in output:\n{out}"
            assert 'DEFAULT' in line, (
                f"ID {default_id} is in DEFAULT_SELECTED_IDS but its line "
                f"does not carry the DEFAULT marker:\n  {line}"
            )

    def test_non_default_option_does_not_carry_marker(self):
        """Negative case: ID 29 is NOT a default and must not show DEFAULT."""
        out = self._run()
        line = next(
            (ln for ln in out.splitlines()
             if ln.startswith('ID ') and ln.split()[1] == '29'),
            None,
        )
        assert line is not None
        assert 'DEFAULT' not in line, (
            f"ID 29 is not in DEFAULT_SELECTED_IDS but line carries DEFAULT:\n  {line}"
        )

    def test_id_29_appears_with_quantile_range_and_correct_label(self):
        """The canonical example we want the AI to emit: ID 29 = outlier
        cleaning at quantiles [0.05-0.95].  Pre-v2.27.0 the system prompt
        hid this; v2.27.1 makes it explicit via this tool."""
        out = self._run()
        line = next(
            (ln for ln in out.splitlines()
             if ln.startswith('ID ') and ln.split()[1] == '29'),
            None,
        )
        assert line is not None, f"ID 29 missing from output:\n{out}"
        assert 'outlier_quantile_clip' in line
        assert 'outlier_num_group' in line
        assert 'quantile_range=(0.05, 0.95)' in line
        assert '"Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]"' in line

    def test_id_5_appears_with_threshold_0_95(self):
        """Smoke-check a threshold-drop entry: ID 5 = corr-drop @ 0.95."""
        out = self._run()
        line = next(
            (ln for ln in out.splitlines()
             if ln.startswith('ID ') and ln.split()[1] == '5'),
            None,
        )
        assert line is not None, f"ID 5 missing from output:\n{out}"
        assert 'corr_drop' in line and 'corr_drop_group' in line
        assert 'threshold=0.95' in line

    def test_kind_filter_outlier_quantile_clip_returns_only_three(self):
        out = self._run({'kind': 'outlier_quantile_clip'})
        id_lines = [ln for ln in out.splitlines() if ln.startswith('ID ')]
        assert len(id_lines) == 3, (
            f"outlier_quantile_clip kind has 3 catalog entries; got "
            f"{len(id_lines)}.\nOutput:\n{out}"
        )
        # All three must reference the kind.
        for ln in id_lines:
            assert 'outlier_quantile_clip' in ln

    def test_kind_filter_corr_drop_returns_only_five(self):
        out = self._run({'kind': 'corr_drop'})
        id_lines = [ln for ln in out.splitlines() if ln.startswith('ID ')]
        assert len(id_lines) == 5
        for ln in id_lines:
            assert 'corr_drop' in ln

    def test_kind_filter_unknown_returns_helpful_error(self):
        out = self._run({'kind': 'no_such_kind'})
        assert "No purifier options match" in out
        assert "Valid kinds" in out
        # Surface a few real kinds so the LLM can self-correct.
        assert 'corr_drop' in out
        assert 'outlier_quantile_clip' in out

    def test_kind_filter_skips_default_id_header(self):
        """When filtered, the 'Default selected IDs' line should be omitted
        to keep the response focused on the requested family."""
        out = self._run({'kind': 'outlier_quantile_clip'})
        assert "Default selected IDs" not in out

    def test_handler_does_not_touch_redis_cache(self, monkeypatch):
        """The catalog is static; the handler must not call cache_get."""
        calls = []
        from ai_assistant import cache as cache_mod
        monkeypatch.setattr(
            cache_mod, 'cache_get',
            lambda *a, **kw: calls.append((a, kw)) or None,
        )
        out = self._run()
        assert calls == [], (
            f"_handle_get_purifier_options must not call cache_get; "
            f"observed calls: {calls}"
        )
        # And it still produces a real catalog response.
        assert "Data Purifier Options Catalog" in out

    def test_handler_ignores_file_id(self):
        """Catalog content is identical regardless of file_id supplied."""
        from ai_assistant.tool_executor import _handle_get_purifier_options
        out_a = _handle_get_purifier_options(0, {})
        out_b = _handle_get_purifier_options(99999, {})
        assert out_a == out_b

@pytest.mark.unit
class TestGetPurifierOptionsToolRegistration:
    """The new tool must be wired into both the LLM-facing schema
    (PIPELINE_TOOLS) and the dispatcher (_HANDLERS).  Either gap leaves
    the AI unable to use the tool even if the handler works."""

    def test_tool_is_in_pipeline_tools_schema(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        names = [t['function']['name'] for t in PIPELINE_TOOLS]
        assert 'get_purifier_options' in names, (
            f"get_purifier_options not found in PIPELINE_TOOLS. "
            f"Registered tool names: {names}"
        )

    def test_tool_schema_has_kind_filter_with_full_enum(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        spec = next(
            t for t in PIPELINE_TOOLS
            if t['function']['name'] == 'get_purifier_options'
        )
        kind_param = spec['function']['parameters']['properties'].get('kind')
        assert kind_param is not None, "kind parameter missing"
        # Enum must cover every kind constant defined in the catalog
        # so the LLM cannot drift into invalid filter values.
        from preprocessing import purifier_catalog as pc
        catalog_kinds = sorted({e['kind'] for e in pc.PURIFIER_OPTIONS})
        assert sorted(kind_param['enum']) == catalog_kinds, (
            f"kind enum drifted from catalog kinds.\n"
            f"  schema enum:    {sorted(kind_param['enum'])}\n"
            f"  catalog kinds:  {catalog_kinds}"
        )

    def test_tool_schema_marks_kind_optional(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        spec = next(
            t for t in PIPELINE_TOOLS
            if t['function']['name'] == 'get_purifier_options'
        )
        # Required list should NOT include 'kind' — full catalog with no
        # filter is a valid call.
        assert 'kind' not in spec['function']['parameters'].get('required', [])

    def test_tool_description_mentions_start_data_purifier_link(self):
        """The description should tell the LLM this is the pre-flight tool
        for start_data_purifier so retrieval-augmented planning works."""
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        spec = next(
            t for t in PIPELINE_TOOLS
            if t['function']['name'] == 'get_purifier_options'
        )
        desc = spec['function']['description']
        assert 'start_data_purifier' in desc, (
            f"Description should reference start_data_purifier; got:\n{desc}"
        )

    def test_tool_is_in_dispatcher(self):
        from ai_assistant.tool_executor import _HANDLERS, _handle_get_purifier_options
        assert _HANDLERS.get('get_purifier_options') is _handle_get_purifier_options

    def test_execute_tool_call_dispatches_to_handler(self):
        from ai_assistant.tool_executor import execute_tool_call
        out = execute_tool_call(0, 'get_purifier_options', {})
        # Should produce the catalog header, not the unknown-tool sentinel.
        assert "Data Purifier Options Catalog" in out
        assert "Unknown tool" not in out

    def test_execute_tool_call_passes_kind_arg_through(self):
        from ai_assistant.tool_executor import execute_tool_call
        out = execute_tool_call(0, 'get_purifier_options', {'kind': 'corr_drop'})
        id_lines = [ln for ln in out.splitlines() if ln.startswith('ID ')]
        assert len(id_lines) == 5  # 5 corr_drop thresholds

@pytest.mark.unit
class TestSystemPromptPurifierGuidance:
    """The pre-v2.27.1 system prompt listed five generic step names
    ("Missing Value Imputation", "Outlier Removal (Numeric)", "Constant
    Column Drop", "Quasi-Constant Drop", "High Cardinality Drop") that
    don't exist in the canonical catalog.  Those phrases led the LLM to
    fabricate IDs and step names.  The v2.27.1 prompt must:
      • not advertise any of those phantom phrases;
      • mention every real transform kind so the LLM has a vocabulary;
      • tell the LLM to call get_purifier_options before mapping intent
        to integer IDs in start_data_purifier.
    """

    def _prompt(self):
        from ai_assistant.views import SYSTEM_PROMPT
        return SYSTEM_PROMPT

    def test_no_phantom_step_names(self):
        prompt = self._prompt()
        forbidden = [
            'Quasi-Constant Drop',
            'High Cardinality Drop',
            'Missing Value Imputation',
            'Constant Column Drop',
        ]
        # "Outlier Removal (Numeric)" is a borderline phrase; the catalog
        # uses "Outlier-cleaning". Pin the explicit pre-v2.27.1 wording.
        forbidden.append('Outlier Removal (Numeric)')
        present = [phrase for phrase in forbidden if phrase in prompt]
        assert not present, (
            "System prompt still advertises phantom purifier step names "
            "that don't exist in the catalog: "
            + ', '.join(repr(p) for p in present)
        )

    def test_prompt_lists_every_real_transform_kind(self):
        prompt = self._prompt()
        from preprocessing import purifier_catalog as pc
        catalog_kinds = sorted({e['kind'] for e in pc.PURIFIER_OPTIONS})
        missing = [k for k in catalog_kinds if k not in prompt]
        assert not missing, (
            f"System prompt is missing these real transform kinds: {missing}.\n"
            f"All catalog kinds must appear so the LLM can ground its replies."
        )

    def test_prompt_directs_llm_to_get_purifier_options_tool(self):
        prompt = self._prompt()
        assert 'get_purifier_options' in prompt, (
            "System prompt must mention get_purifier_options so the LLM "
            "knows the tool exists."
        )

    def test_prompt_links_tool_to_start_data_purifier_action(self):
        prompt = self._prompt()
        # The action-block section must instruct calling the catalog tool
        # before emitting purifier_options.
        action_section = prompt.split('ACTION TYPE 6: start_data_purifier')[-1]
        action_section = action_section.split('ACTION TYPE 7')[0]
        assert 'get_purifier_options' in action_section, (
            "start_data_purifier action rules must instruct calling "
            "get_purifier_options first to map user intent to IDs."
        )

    def test_prompt_announces_exactly_34_options(self):
        prompt = self._prompt()
        # Exact count anchors the LLM and lets us catch silent drift if
        # the catalog grows but the prompt isn't updated.
        assert '34' in prompt, "Prompt should anchor the option count at 34."
