"""
Canonical catalog of the 34 data-purifier options.

This module is the single source of truth for:
  • Option IDs (1..34)
  • UI labels (must match frontend purifierOptions array exactly)
  • Group classification (for UI radio-style single-select within a group)
  • Threshold values for threshold-based options
  • Transform kind (for the backend dispatcher in _apply_options)

Why this exists (v2.27.0)
-------------------------
Before v2.27.0 the frontend (model-development.component.ts and
modeling.component.ts) and the backend (_apply_options in
preprocessing/views.py) maintained PARALLEL but DIVERGENT mappings of
option ID → transform.  IDs 9-27 silently ran different transforms
than their UI labels described, e.g. clicking "Sparsity-drop 0.95"
(ID 11) in the UI actually executed "Missing-drop ≥ 0.40" in the
backend.  No tests guarded this contract because no tests exercised
those IDs.  See the v2.27.0 commit body for the realignment matrix.

This module fixes that by:
  • Defining each option once, with its kind/threshold attached.
  • Letting `_apply_options` dispatch off that single source.
  • Powering a new `GET /api/preprocessing/options/` endpoint so the
    frontend can eventually drop its duplicated TS array.
  • Letting the upcoming v2.27.1 AI catalog tool surface the exact
    same labels and threshold mappings the user sees in the UI.

Adding or changing options
--------------------------
1. Update the entry below.
2. Add or update the dispatcher branch in `_apply_options`
   (preprocessing/views.py) so the new kind/threshold actually executes.
3. Mirror the change in the frontend `purifierOptions` arrays.  The
   `test_purifier_catalog_matches_frontend_ts_source` regression test
   enforces equality at the label level.
4. Add a regression test covering the new ID under
   `tests/test_unit.py::TestPurifierApplyOptions`.
"""
from __future__ import annotations

from typing import Optional


# ── Group identifiers ─────────────────────────────────────────────
# These match the `group` field in the frontend PurifierOption
# interface and drive UI radio-style mutual-exclusion (isOptionDisabled
# in model-development.component.ts).  Standalone options (IDs 1-4)
# carry group=None and never disable each other.
GROUP_CORR_DROP = 1
GROUP_SPARSITY_DROP = 2
GROUP_MISSING_DROP = 3
GROUP_COMBINED_DROP = 4
GROUP_OUTLIER_NUM = 5
GROUP_OUTLIER_CAT = 6


# ── Transform kinds ──────────────────────────────────────────────
# Used by _apply_options to dispatch each selected option to the
# correct transform.  Adding a new kind requires both a new constant
# here AND a new branch in the dispatcher.
KIND_COL_DEDUP = 'col_dedup'
KIND_ROW_DEDUP = 'row_dedup'
KIND_ZERO_VAR = 'zero_var_drop'
KIND_PERFECT_CORR = 'perfect_corr_drop'
KIND_CORR_DROP = 'corr_drop'
KIND_SPARSITY_DROP = 'sparsity_drop'
KIND_MISSING_DROP = 'missing_drop'
KIND_COMBINED_DROP = 'combined_drop'      # max(zero_ratio, miss_ratio) >= threshold
KIND_OUTLIER_NUM = 'outlier_quantile_clip'
KIND_OUTLIER_CAT = 'cat_outlier_merge'


# Threshold-drop kinds (drop the feature when the metric MEETS OR
# EXCEEDS the configured threshold).  For these, a LOWER threshold
# drops MORE features → "more aggressive".  When multiple options of
# the same kind are somehow selected (UI normally enforces single-
# select within a group), the dispatcher picks the most aggressive.
_THRESHOLD_DROP_KINDS = frozenset({
    KIND_CORR_DROP,
    KIND_SPARSITY_DROP,
    KIND_MISSING_DROP,
    KIND_COMBINED_DROP,
})


# ── The 34-option canonical catalog ──────────────────────────────
# Each entry is a dict with:
#   id              — 1..34, unique, contiguous
#   name            — UI label.  MUST match the frontend
#                     `purifierOptions` array character-for-character.
#   kind            — KIND_* constant; dispatcher key.
#   group           — GROUP_* constant or None.
#   threshold       — numeric threshold (drop kinds + cat-outlier kind),
#                     None for non-threshold options.
#   quantile_range  — (lo, hi) tuple for outlier-num kind, else None.
PURIFIER_OPTIONS: list[dict] = [
    {'id':  1, 'name': 'Column-wise duplicate drop',
     'kind': KIND_COL_DEDUP,     'group': None,                'threshold': None, 'quantile_range': None},
    {'id':  2, 'name': 'Row-wise duplicate drop',
     'kind': KIND_ROW_DEDUP,     'group': None,                'threshold': None, 'quantile_range': None},
    {'id':  3, 'name': 'Zero-variance drop',
     'kind': KIND_ZERO_VAR,      'group': None,                'threshold': None, 'quantile_range': None},
    {'id':  4, 'name': 'Perfect-correlation drop',
     'kind': KIND_PERFECT_CORR,  'group': None,                'threshold': None, 'quantile_range': None},

    {'id':  5, 'name': 'Corr-drop threshold = 0.95',
     'kind': KIND_CORR_DROP,     'group': GROUP_CORR_DROP,     'threshold': 0.95, 'quantile_range': None},
    {'id':  6, 'name': 'Corr-drop threshold = 0.90',
     'kind': KIND_CORR_DROP,     'group': GROUP_CORR_DROP,     'threshold': 0.90, 'quantile_range': None},
    {'id':  7, 'name': 'Corr-drop threshold = 0.85',
     'kind': KIND_CORR_DROP,     'group': GROUP_CORR_DROP,     'threshold': 0.85, 'quantile_range': None},
    {'id':  8, 'name': 'Corr-drop threshold = 0.80',
     'kind': KIND_CORR_DROP,     'group': GROUP_CORR_DROP,     'threshold': 0.80, 'quantile_range': None},
    {'id':  9, 'name': 'Corr-drop threshold = 0.75',
     'kind': KIND_CORR_DROP,     'group': GROUP_CORR_DROP,     'threshold': 0.75, 'quantile_range': None},

    {'id': 10, 'name': 'Sparsity-drop threshold = 0.99',
     'kind': KIND_SPARSITY_DROP, 'group': GROUP_SPARSITY_DROP, 'threshold': 0.99, 'quantile_range': None},
    {'id': 11, 'name': 'Sparsity-drop threshold = 0.95',
     'kind': KIND_SPARSITY_DROP, 'group': GROUP_SPARSITY_DROP, 'threshold': 0.95, 'quantile_range': None},
    {'id': 12, 'name': 'Sparsity-drop threshold = 0.90',
     'kind': KIND_SPARSITY_DROP, 'group': GROUP_SPARSITY_DROP, 'threshold': 0.90, 'quantile_range': None},
    {'id': 13, 'name': 'Sparsity-drop threshold = 0.85',
     'kind': KIND_SPARSITY_DROP, 'group': GROUP_SPARSITY_DROP, 'threshold': 0.85, 'quantile_range': None},
    {'id': 14, 'name': 'Sparsity-drop threshold = 0.80',
     'kind': KIND_SPARSITY_DROP, 'group': GROUP_SPARSITY_DROP, 'threshold': 0.80, 'quantile_range': None},
    {'id': 15, 'name': 'Sparsity-drop threshold = 0.75',
     'kind': KIND_SPARSITY_DROP, 'group': GROUP_SPARSITY_DROP, 'threshold': 0.75, 'quantile_range': None},

    {'id': 16, 'name': 'Missing-drop threshold = 0.99',
     'kind': KIND_MISSING_DROP,  'group': GROUP_MISSING_DROP,  'threshold': 0.99, 'quantile_range': None},
    {'id': 17, 'name': 'Missing-drop threshold = 0.95',
     'kind': KIND_MISSING_DROP,  'group': GROUP_MISSING_DROP,  'threshold': 0.95, 'quantile_range': None},
    {'id': 18, 'name': 'Missing-drop threshold = 0.90',
     'kind': KIND_MISSING_DROP,  'group': GROUP_MISSING_DROP,  'threshold': 0.90, 'quantile_range': None},
    {'id': 19, 'name': 'Missing-drop threshold = 0.85',
     'kind': KIND_MISSING_DROP,  'group': GROUP_MISSING_DROP,  'threshold': 0.85, 'quantile_range': None},
    {'id': 20, 'name': 'Missing-drop threshold = 0.80',
     'kind': KIND_MISSING_DROP,  'group': GROUP_MISSING_DROP,  'threshold': 0.80, 'quantile_range': None},
    {'id': 21, 'name': 'Missing-drop threshold = 0.75',
     'kind': KIND_MISSING_DROP,  'group': GROUP_MISSING_DROP,  'threshold': 0.75, 'quantile_range': None},

    {'id': 22, 'name': '[Sparsity+Missing]-drop threshold = 0.99',
     'kind': KIND_COMBINED_DROP, 'group': GROUP_COMBINED_DROP, 'threshold': 0.99, 'quantile_range': None},
    {'id': 23, 'name': '[Sparsity+Missing]-drop threshold = 0.95',
     'kind': KIND_COMBINED_DROP, 'group': GROUP_COMBINED_DROP, 'threshold': 0.95, 'quantile_range': None},
    {'id': 24, 'name': '[Sparsity+Missing]-drop threshold = 0.90',
     'kind': KIND_COMBINED_DROP, 'group': GROUP_COMBINED_DROP, 'threshold': 0.90, 'quantile_range': None},
    {'id': 25, 'name': '[Sparsity+Missing]-drop threshold = 0.85',
     'kind': KIND_COMBINED_DROP, 'group': GROUP_COMBINED_DROP, 'threshold': 0.85, 'quantile_range': None},
    {'id': 26, 'name': '[Sparsity+Missing]-drop threshold = 0.80',
     'kind': KIND_COMBINED_DROP, 'group': GROUP_COMBINED_DROP, 'threshold': 0.80, 'quantile_range': None},
    {'id': 27, 'name': '[Sparsity+Missing]-drop threshold = 0.75',
     'kind': KIND_COMBINED_DROP, 'group': GROUP_COMBINED_DROP, 'threshold': 0.75, 'quantile_range': None},

    {'id': 28, 'name': 'Outlier-cleaning [lower-upper] quantiles = [0.01-0.99]',
     'kind': KIND_OUTLIER_NUM,   'group': GROUP_OUTLIER_NUM,   'threshold': None, 'quantile_range': (0.01, 0.99)},
    {'id': 29, 'name': 'Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]',
     'kind': KIND_OUTLIER_NUM,   'group': GROUP_OUTLIER_NUM,   'threshold': None, 'quantile_range': (0.05, 0.95)},
    {'id': 30, 'name': 'Outlier-cleaning [lower-upper] quantiles = [0.10-0.90]',
     'kind': KIND_OUTLIER_NUM,   'group': GROUP_OUTLIER_NUM,   'threshold': None, 'quantile_range': (0.10, 0.90)},

    {'id': 31, 'name': 'Outlier Cleaning (Categorical Features) threshold = 0.001',
     'kind': KIND_OUTLIER_CAT,   'group': GROUP_OUTLIER_CAT,   'threshold': 0.001, 'quantile_range': None},
    {'id': 32, 'name': 'Outlier Cleaning (Categorical Features) threshold = 0.005',
     'kind': KIND_OUTLIER_CAT,   'group': GROUP_OUTLIER_CAT,   'threshold': 0.005, 'quantile_range': None},
    {'id': 33, 'name': 'Outlier Cleaning (Categorical Features) threshold = 0.01',
     'kind': KIND_OUTLIER_CAT,   'group': GROUP_OUTLIER_CAT,   'threshold': 0.01,  'quantile_range': None},
    {'id': 34, 'name': 'Outlier Cleaning (Categorical Features) threshold = 0.05',
     'kind': KIND_OUTLIER_CAT,   'group': GROUP_OUTLIER_CAT,   'threshold': 0.05,  'quantile_range': None},
]


# Defaults pre-checked in the UI when the user lands on the Data
# Purifier Declaration screen.  Centralized here so /api/preprocessing/
# options/ can expose them and the frontend can eventually drop its
# duplicated `defaultOptionIds` array.
DEFAULT_SELECTED_IDS: list[int] = [1, 2, 3, 4, 7, 11, 17, 23, 28, 32]


# ── Internal lookup table ────────────────────────────────────────
_ID_INDEX: dict[int, dict] = {entry['id']: entry for entry in PURIFIER_OPTIONS}


# ── Public helpers ────────────────────────────────────────────────
def get_option(option_id: int) -> Optional[dict]:
    """Return the catalog entry for an option ID, or None if unknown."""
    return _ID_INDEX.get(option_id)


def options_in_group(group_id: int) -> list[dict]:
    """Return catalog entries for the given group, sorted by ID."""
    return sorted([e for e in PURIFIER_OPTIONS if e.get('group') == group_id],
                  key=lambda e: e['id'])


def options_of_kind(kind: str) -> list[dict]:
    """Return catalog entries for the given kind, sorted by ID."""
    return sorted([e for e in PURIFIER_OPTIONS if e['kind'] == kind],
                  key=lambda e: e['id'])


def selected_entries_of_kind(selected_ids, kind: str) -> list[dict]:
    """Return the catalog entries of `kind` that appear in `selected_ids`.

    `selected_ids` may be any iterable (set/list/tuple).  Result is
    sorted by ID for deterministic downstream behavior.
    """
    sel = set(selected_ids)
    return sorted([e for e in options_of_kind(kind) if e['id'] in sel],
                  key=lambda e: e['id'])


def pick_most_aggressive(selected_ids, kind: str) -> Optional[dict]:
    """For threshold-drop kinds, pick the most-aggressive (lowest-threshold)
    selected entry of the given kind.  Returns None when no selected ID
    belongs to the requested kind.

    Only valid for threshold-drop kinds (corr/sparsity/missing/combined).
    For other kinds use `selected_entries_of_kind` and choose explicitly.
    """
    if kind not in _THRESHOLD_DROP_KINDS:
        raise ValueError(
            f"pick_most_aggressive is only defined for threshold-drop kinds; "
            f"got {kind!r}. Use selected_entries_of_kind for non-threshold kinds."
        )
    candidates = selected_entries_of_kind(selected_ids, kind)
    if not candidates:
        return None
    return min(candidates, key=lambda e: e['threshold'])
