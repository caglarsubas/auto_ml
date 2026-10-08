"""Diagnostic inputs that avoid imposing arbitrary order on nominal categories."""
import numpy as np
import pandas as pd


def numeric_collinearity_frame(frame, encoding_report=None):
    numeric = frame.select_dtypes(include=['number']).copy()
    coded_categories = [entry['feature'] for entry in encoding_report or []
        if ((entry.get('mapping') or {}).get('type') or entry.get('strategy_applied') or entry.get('strategy'))
        in ('label_encoding', 'ordinal_encoding', 'manual_grouping', 'native_categorical')]
    numeric = numeric.drop(columns=coded_categories, errors='ignore')
    numeric = numeric.replace([np.inf, -np.inf], np.nan).dropna(axis=1, how='all')
    numeric = numeric.fillna(numeric.mean())
    return numeric.loc[:, numeric.var() > 0]


DIAGNOSTIC_LIMITATIONS = {
    'vif': 'Numeric predictors only. Nominal category codes are excluded; categorical dependence needs a separate grouped diagnostic. VIF is descriptive and does not establish causality.',
    'combined_score': 'A ranking heuristic combining SHAP and gain percentiles; not an effect estimate, statistical test or validation gate.',
    'sequential_patterns': 'Consecutive near-duplicate patterns identify records for review; they do not establish causal relationships.',
}
