"""
Categorical feature encoding utilities.

Primary approach: XGBoost native categorical support (enable_categorical=True).
Fallback strategies based on Level of Measurement (LoM) and unique value count:
  - Nominal → Label Encoding
  - Ordinal, nunique < 5 → One-Hot Encoding (null as a new category)
  - Ordinal, 5 ≤ nunique ≤ 10 → Ordinal Encoding (user provides category ranking)
  - Ordinal, nunique > 10 → Target Encoding (category-target average)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_categorical_features(
    df: pd.DataFrame,
    data_dict: List[Dict],
    target_col: str = 'Target',
    excluded_cols: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Identify categorical features and build an encoding plan for each.

    Returns a list of plan entries (one per categorical feature).
    """
    excluded = set(excluded_cols or [])
    excluded.add(target_col)

    # LoM and description lookup from data dictionary
    lom_lookup: Dict[str, str] = {}
    desc_lookup: Dict[str, str] = {}
    for entry in data_dict:
        fname = entry.get('Feature_Name', '')
        lom = entry.get('Level_of_Measurement', 'unknown')
        lom_lookup[fname] = lom
        desc_lookup[fname] = entry.get('Feature_Description', '')

    plan: List[Dict] = []
    for col in df.columns:
        if col in excluded:
            continue

        lom = lom_lookup.get(col, 'unknown')

        # Skip purely numeric features that are not nominal/ordinal
        if pd.api.types.is_numeric_dtype(df[col]) and lom not in ('nominal', 'ordinal'):
            continue

        # If it's numeric but LoM says nominal, treat as categorical
        # If it's object/string, always treat as categorical
        if pd.api.types.is_numeric_dtype(df[col]) and lom not in ('nominal', 'ordinal'):
            continue

        nunique = int(df[col].nunique(dropna=True))
        try:
            unique_values = sorted(df[col].dropna().unique().tolist(), key=str)
        except Exception:
            unique_values = list(df[col].dropna().unique())

        has_nulls = bool(df[col].isnull().any())
        missing_count = int(df[col].isnull().sum())
        missing_ratio = round(missing_count / max(len(df), 1) * 100, 2)

        # Determine fallback strategy
        fallback, reason = _determine_fallback_strategy(lom, nunique)
        needs_ranking = (lom == 'ordinal' and 5 <= nunique <= 10)

        before_stats = _compute_stats(df[col])

        plan.append({
            'feature': col,
            'description': desc_lookup.get(col, ''),
            'original_lom': lom,
            'user_lom': lom,
            'data_type': str(df[col].dtype),
            'nunique': nunique,
            'unique_values': [str(v) for v in unique_values[:50]],
            'has_nulls': has_nulls,
            'missing_count': missing_count,
            'missing_ratio': missing_ratio,
            'strategy': 'native_categorical',
            'fallback_strategy': fallback,
            'fallback_reason': reason,
            'needs_ranking': needs_ranking,
            'ranking': None,
            'before_stats': before_stats,
        })

    return plan


# ---------------------------------------------------------------------------
# Encoding application
# ---------------------------------------------------------------------------

def apply_encoding(
    df: pd.DataFrame,
    plan: List[Dict],
    target_col: str = 'Target',
    use_native: bool = True,
) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Apply encoding to *df* according to *plan*.

    When *use_native* is True the primary strategy for every feature is
    ``native_categorical`` (convert to ``pd.Categorical``).  The modelling
    code must then pass ``enable_categorical=True`` to XGBoost ``DMatrix``.

    Returns ``(encoded_df, report)`` where *report* documents per-feature
    encoding details including mappings and before/after statistics.
    """
    encoded = df.copy()
    report: List[Dict] = []

    for entry in plan:
        feature = entry.get('feature', '')
        if feature not in encoded.columns:
            continue

        user_lom = entry.get('user_lom', entry.get('original_lom', 'nominal'))
        nunique = entry.get('nunique', 0)
        ranking = entry.get('ranking')

        # Recompute fallback if user changed the LoM
        fallback, reason = _determine_fallback_strategy(user_lom, nunique)

        # Determine encoding strategy:
        # 1. If use_native=True globally, all features use native_categorical
        # 2. If use_native=False, check per-feature encoding_method from plan entry
        #    - 'native' or missing → native_categorical
        #    - explicit method → use that method directly
        encoding_method = entry.get('encoding_method', 'native')
        if use_native:
            strategy = 'native_categorical'
        elif encoding_method in (None, '', 'native'):
            strategy = 'native_categorical'
        else:
            strategy = encoding_method  # label_encoding, one_hot_encoding, frequency_encoding, target_encoding, manual_grouping

        before_stats = _compute_stats(encoded[feature])

        feat_report: Dict[str, Any] = {
            'feature': feature,
            'lom': user_lom,
            'strategy_applied': strategy,
            'fallback_strategy': fallback,
            'fallback_reason': reason,
            'mapping': None,
            'before_stats': before_stats,
            'after_stats': None,
            'new_columns': [feature],
        }

        if strategy == 'native_categorical':
            encoded[feature] = encoded[feature].astype('category')
            cats = list(encoded[feature].cat.categories.astype(str))
            feat_report['mapping'] = {
                'type': 'native_categorical',
                'categories': cats,
            }
            feat_report['after_stats'] = _compute_stats(encoded[feature])
        else:
            manual_mapping = entry.get('manual_mapping')
            encoded, feat_report = _apply_fallback(
                encoded, feature, strategy, ranking, target_col, feat_report,
                manual_mapping=manual_mapping,
            )

        report.append(feat_report)

    return encoded, report


# ---------------------------------------------------------------------------
# Fallback encoders
# ---------------------------------------------------------------------------

def _apply_fallback(
    df: pd.DataFrame,
    feature: str,
    fallback: str,
    ranking: Optional[List[str]],
    target_col: str,
    feat_report: Dict,
    manual_mapping: Optional[Dict] = None,
) -> Tuple[pd.DataFrame, Dict]:
    if fallback == 'label_encoding':
        df, mapping = _label_encode(df, feature)
        feat_report['mapping'] = mapping
        feat_report['strategy_applied'] = 'label_encoding'

    elif fallback == 'one_hot_encoding':
        df, mapping, new_cols = _ohe_encode(df, feature)
        feat_report['mapping'] = mapping
        feat_report['new_columns'] = new_cols
        feat_report['strategy_applied'] = 'one_hot_encoding'

    elif fallback == 'ordinal_encoding':
        if ranking:
            df, mapping = _ordinal_encode(df, feature, ranking)
            feat_report['mapping'] = mapping
            feat_report['strategy_applied'] = 'ordinal_encoding'
        else:
            # No ranking supplied → fall back to label encoding
            df, mapping = _label_encode(df, feature)
            feat_report['mapping'] = mapping
            feat_report['strategy_applied'] = 'label_encoding'
            feat_report['fallback_reason'] += ' (no ranking provided → label encoding)'

    elif fallback == 'target_encoding':
        df, mapping = _target_encode(df, feature, target_col)
        feat_report['mapping'] = mapping
        feat_report['strategy_applied'] = 'target_encoding'

    elif fallback == 'frequency_encoding':
        df, mapping = _frequency_encode(df, feature)
        feat_report['mapping'] = mapping
        feat_report['strategy_applied'] = 'frequency_encoding'

    elif fallback == 'manual_grouping':
        df, mapping = _manual_group_encode(df, feature, manual_mapping)
        feat_report['mapping'] = mapping
        feat_report['strategy_applied'] = 'manual_grouping'

    # After stats on the (possibly replaced) column
    if feature in df.columns:
        feat_report['after_stats'] = _compute_stats(df[feature])
    else:
        # OHE removes the original column
        feat_report['after_stats'] = {'note': 'original column replaced by dummy columns'}

    return df, feat_report


def _label_encode(df: pd.DataFrame, feature: str) -> Tuple[pd.DataFrame, Dict]:
    series = df[feature].copy()
    null_ph = '__NULL__'
    series = series.fillna(null_ph)
    unique_sorted = sorted(series.unique(), key=str)
    mapping = {str(v): i for i, v in enumerate(unique_sorted)}
    df[feature] = series.map(lambda x: mapping.get(str(x), -1)).astype(int)
    return df, {'type': 'label_encoding', 'mapping': mapping}


def _ohe_encode(df: pd.DataFrame, feature: str) -> Tuple[pd.DataFrame, Dict, List[str]]:
    series = df[feature].copy()
    null_cat = f'{feature}_NULL'
    series = series.fillna(null_cat)
    dummies = pd.get_dummies(series, prefix=feature, dtype=int)
    new_cols = list(dummies.columns)
    df = df.drop(columns=[feature])
    df = pd.concat([df, dummies], axis=1)
    return df, {'type': 'one_hot_encoding', 'columns': new_cols, 'original_feature': feature}, new_cols


def _ordinal_encode(df: pd.DataFrame, feature: str, ranking: List[str]) -> Tuple[pd.DataFrame, Dict]:
    mapping = {str(v): i for i, v in enumerate(ranking)}
    series = df[feature].astype(str)
    df[feature] = series.map(lambda x: mapping.get(x, -1) if x != 'nan' else -1).astype(int)
    return df, {'type': 'ordinal_encoding', 'ranking': ranking, 'mapping': mapping}


def _target_encode(df: pd.DataFrame, feature: str, target_col: str) -> Tuple[pd.DataFrame, Dict]:
    if target_col not in df.columns:
        return _label_encode(df, feature)

    global_mean = float(df[target_col].mean())
    # Treat nulls as a category for target encoding
    series_filled = df[feature].fillna('__NULL__')
    means = df.assign(**{feature: series_filled}).groupby(feature)[target_col].mean()
    mapping = {str(k): round(float(v), 6) for k, v in means.items()}
    null_mean = mapping.get('__NULL__', global_mean)
    df[feature] = df[feature].map(
        lambda x: mapping.get(str(x), global_mean) if pd.notna(x) else null_mean,
    ).astype(float)
    return df, {'type': 'target_encoding', 'mapping': mapping, 'global_mean': global_mean}


def _frequency_encode(df: pd.DataFrame, feature: str) -> Tuple[pd.DataFrame, Dict]:
    """Replace each category (including nulls) with its volume-share (frequency ratio)."""
    null_ph = '__NULL__'
    series = df[feature].fillna(null_ph)
    total = len(series)
    vc = series.value_counts()
    mapping = {str(k): round(float(v) / total, 6) for k, v in vc.items()}
    df[feature] = series.map(lambda x: mapping.get(str(x), 0.0)).astype(float)
    return df, {'type': 'frequency_encoding', 'mapping': mapping}


def _manual_group_encode(df: pd.DataFrame, feature: str, manual_mapping: Optional[Dict] = None) -> Tuple[pd.DataFrame, Dict]:
    """Replace categories with user-assigned numeric group numbers."""
    if not manual_mapping:
        # Fallback: label encode if no mapping provided
        return _label_encode(df, feature)

    null_ph = '__NULL__'
    series = df[feature].fillna(null_ph).astype(str)
    # Build clean mapping: str(category) -> numeric value
    clean_map: Dict[str, float] = {}
    for cat, val in manual_mapping.items():
        if val is not None:
            try:
                clean_map[str(cat)] = float(val)
            except (ValueError, TypeError):
                pass
    # Apply mapping; unmapped categories get -1
    df[feature] = series.map(lambda x: clean_map.get(x, -1)).astype(float)
    return df, {'type': 'manual_grouping', 'mapping': clean_map}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _determine_fallback_strategy(lom: str, nunique: int) -> Tuple[str, str]:
    if lom == 'ordinal':
        if nunique < 5:
            return 'one_hot_encoding', (
                f'Ordinal with {nunique} unique values (<5) → One-Hot Encoding (null as category)'
            )
        elif nunique <= 10:
            return 'ordinal_encoding', (
                f'Ordinal with {nunique} unique values (5–10) → Ordinal Encoding (user ranking)'
            )
        else:
            return 'target_encoding', (
                f'Ordinal with {nunique} unique values (>10) → Target Encoding'
            )
    # nominal / unknown / anything else
    return 'label_encoding', 'Nominal feature → Label Encoding'


def _compute_stats(series: pd.Series) -> Dict[str, Any]:
    total = len(series)
    non_null = series.dropna()
    vc = series.value_counts(dropna=False).head(20)

    stats: Dict[str, Any] = {
        'total_count': total,
        'non_null_count': int(non_null.count()),
        'null_count': int(series.isnull().sum()),
        'null_ratio': round(float(series.isnull().mean()) * 100, 2),
        'nunique': int(series.nunique(dropna=True)),
        'top_values': {str(k): int(v) for k, v in vc.items()},
    }

    if pd.api.types.is_numeric_dtype(non_null) and len(non_null) > 0:
        stats['mean'] = round(float(non_null.mean()), 4)
        stats['std'] = round(float(non_null.std()), 4)
        stats['min'] = round(float(non_null.min()), 4)
        stats['max'] = round(float(non_null.max()), 4)

    return stats
