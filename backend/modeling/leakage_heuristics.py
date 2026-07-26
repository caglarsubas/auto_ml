"""Pre-train leakage / suspicious-feature heuristics for boosting.

These are hard *warnings* surfaced in the modeling response and model card —
they do not block training (analysts may have legitimate high-IV features).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


_ID_NAME_RE = re.compile(
    r'(^id$|_id$|^uuid$|customer.?id|account.?id|application.?id|loan.?id|user.?id)',
    re.I,
)
_TIME_NAME_RE = re.compile(
    r'(date|time|timestamp|datetime|_at$|^asof|as_of)',
    re.I,
)
_LEAK_NAME_RE = re.compile(
    r'(target|label|default_flag|outcome|actual_|realized_|post[_-]?event|future_)',
    re.I,
)


def _woe_iv(series: pd.Series, y: pd.Series, bins: int = 10) -> Optional[float]:
    """Information Value for a numeric/categorical feature vs binary target."""
    try:
        y = pd.to_numeric(y, errors='coerce')
        mask = y.notna()
        s = series.loc[mask]
        yy = y.loc[mask].astype(int)
        if yy.nunique() < 2 or len(yy) < 30:
            return None
        if pd.api.types.is_numeric_dtype(s) and s.nunique(dropna=True) > bins:
            try:
                cats = pd.qcut(s.rank(method='first'), q=min(bins, s.nunique()), duplicates='drop')
            except Exception:
                cats = pd.cut(s, bins=min(bins, max(2, s.nunique())), duplicates='drop')
        else:
            cats = s.astype(str).fillna('__NULL__')
        tab = pd.crosstab(cats, yy)
        if tab.shape[1] < 2:
            return None
        goods = tab.iloc[:, 1].astype(float) + 0.5
        bads = tab.iloc[:, 0].astype(float) + 0.5
        good_rate = goods / goods.sum()
        bad_rate = bads / bads.sum()
        woe = np.log(good_rate / bad_rate)
        iv = float(((good_rate - bad_rate) * woe).sum())
        return iv if np.isfinite(iv) else None
    except Exception:
        return None


def scan_leakage_risks(
    X: pd.DataFrame,
    y: pd.Series,
    feature_names: Optional[Sequence[str]] = None,
    excluded: Optional[Sequence[str]] = None,
    iv_suspicious: float = 0.5,
    corr_suspicious: float = 0.95,
    unique_ratio_id: float = 0.95,
) -> Dict[str, Any]:
    """Return structured leakage warnings for the modeling feature matrix."""
    cols = list(feature_names or X.columns)
    excluded_set = set(excluded or [])
    warnings: List[Dict[str, Any]] = []
    y_num = pd.to_numeric(y, errors='coerce')

    for col in cols:
        if col in excluded_set or col not in X.columns:
            continue
        s = X[col]
        reasons: List[str] = []
        severity = 'info'

        # Name-based suspects
        if _ID_NAME_RE.search(str(col)):
            reasons.append('name looks like an identifier')
            severity = 'high'
        if _TIME_NAME_RE.search(str(col)):
            reasons.append('name looks like a timestamp / as-of field')
            severity = 'high' if severity != 'high' else severity
        if _LEAK_NAME_RE.search(str(col)):
            reasons.append('name resembles a target / post-event outcome')
            severity = 'high'

        # Near-unique IDs (skip continuous floats — nearly always unique by nature)
        try:
            nunique = int(s.nunique(dropna=True))
            n = max(int(s.notna().sum()), 1)
            uniq_ratio = nunique / n
            is_continuous_float = (
                pd.api.types.is_float_dtype(s)
                and nunique > min(40, max(10, n // 3))
            )
            if (
                uniq_ratio >= unique_ratio_id
                and n >= 50
                and not is_continuous_float
            ):
                reasons.append(f'near-unique values (unique_ratio={uniq_ratio:.2f})')
                severity = 'high'
        except Exception:
            uniq_ratio = None

        # Target correlation / IV
        iv = None
        corr = None
        try:
            if pd.api.types.is_numeric_dtype(s) and y_num.notna().sum() >= 30:
                corr = float(pd.Series(s).corr(y_num))
                if corr is not None and np.isfinite(corr) and abs(corr) >= corr_suspicious:
                    reasons.append(f'|corr(target)|={abs(corr):.3f} ≥ {corr_suspicious}')
                    severity = 'high'
        except Exception:
            corr = None
        iv = _woe_iv(s, y_num)
        if iv is not None and iv >= iv_suspicious:
            reasons.append(f'IV={iv:.3f} ≥ {iv_suspicious} (suspicious — check leakage)')
            if severity != 'high':
                severity = 'medium'

        if reasons:
            warnings.append({
                'feature': str(col),
                'severity': severity,
                'reasons': reasons,
                'iv': None if iv is None else round(float(iv), 4),
                'corr_target': None if corr is None or not np.isfinite(corr) else round(float(corr), 4),
            })

    warnings.sort(key=lambda w: {'high': 0, 'medium': 1, 'info': 2}.get(w['severity'], 9))
    n_high = sum(1 for w in warnings if w['severity'] == 'high')
    n_medium = sum(1 for w in warnings if w['severity'] == 'medium')
    summary = (
        f'{len(warnings)} suspicious feature(s) '
        f'({n_high} high, {n_medium} medium). '
        'Review Model_Usage exclusions before trusting validation metrics.'
        if warnings else 'No automated leakage warnings.'
    )
    return {
        'n_warnings': len(warnings),
        'n_high': n_high,
        'n_medium': n_medium,
        'warnings': warnings[:50],
        'summary': summary,
        'thresholds': {
            'iv_suspicious': iv_suspicious,
            'corr_suspicious': corr_suspicious,
            'unique_ratio_id': unique_ratio_id,
        },
    }
