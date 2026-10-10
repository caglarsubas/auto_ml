"""Diagnostic inputs that avoid imposing arbitrary order on nominal categories."""
import numpy as np
import pandas as pd

CATEGORY_ENCODINGS = {'label_encoding', 'ordinal_encoding', 'manual_grouping',
    'native_categorical', 'one_hot_encoding', 'frequency_encoding', 'target_encoding'}


def numeric_diagnostic_inputs(frame, encoding_report=None):
    """Training-only mean imputation; category-derived columns stay out of VIF."""
    excluded = {}
    for entry in encoding_report or []:
        mapping = entry.get('mapping') or {}
        kind = mapping.get('type') or entry.get('strategy_applied') or entry.get('strategy')
        if kind in CATEGORY_ENCODINGS:
            for name in [entry.get('feature'), *(mapping.get('columns') or [])]:
                if name in frame.columns:
                    excluded[name] = 'excluded_categorical'
    numeric, means, missing = {}, {}, {}
    for name in frame.columns:
        if name in excluded:
            continue
        if not pd.api.types.is_numeric_dtype(frame[name]) or pd.api.types.is_bool_dtype(frame[name]):
            excluded[name] = 'excluded_nonnumeric'
            continue
        values = frame[name].to_numpy(dtype=float, na_value=np.nan)
        finite = values[np.isfinite(values)]
        missing[name] = int((~np.isfinite(values)).sum())
        if not len(finite):
            excluded[name] = 'no_finite_values'
            continue
        # Scale before summing so large, finite predictor values do not overflow.
        scale = float(np.max(np.abs(finite)))
        mean = float(np.mean(finite / scale) * scale) if scale else 0.0
        means[name] = mean
        values = np.where(np.isfinite(values), values, mean)
        if len(values) < 2:
            excluded[name] = 'insufficient_rows'
        elif np.all(values == values[0]):
            excluded[name] = 'constant'
        else:
            numeric[name] = values
    return pd.DataFrame(numeric, index=frame.index), {
        'excluded': excluded, 'imputation_means': means, 'imputed_counts': missing,
        'imputation': 'Non-finite numeric values use means fitted on these training rows only.',
    }


def numeric_collinearity_frame(frame, encoding_report=None):
    return numeric_diagnostic_inputs(frame, encoding_report)[0]


DIAGNOSTIC_LIMITATIONS = {
    'vif': 'Centered numeric training predictors only; category-derived columns are excluded. Mean imputation changes dependence. VIF is a descriptive auxiliary linear-regression diagnostic, not model importance, causal attribution, a statistical test or an automatic feature-removal gate. Category groups have a separate method and scope; sampling uncertainty remains unqualified. Historical values may use another method.',
    'combined_score': 'A ranking heuristic combining SHAP and gain percentiles; not an effect estimate, statistical test or validation gate.',
    'sequential_patterns': 'Consecutive near-duplicate patterns identify records for review; they do not establish causal relationships.',
}
