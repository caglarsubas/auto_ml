"""Probability calibration helpers for boosting classifiers.

Fit on the modeling validation holdout (never the locked outer test), then
apply in Evaluation / Deployment so reported probabilities are decision-ready.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import numpy as np
from joblib import dump as joblib_dump, load as joblib_load
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss


def fit_calibrator(
    y_true,
    y_proba,
    method: str = 'auto',
    min_isotonic_samples: int = 200,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Fit a probability calibrator on validation predictions.

    ``method``:
      - ``isotonic``: IsotonicRegression (needs enough samples)
      - ``platt`` / ``sigmoid``: logistic regression on scores
      - ``auto``: isotonic when n >= min_isotonic_samples else Platt

    Returns ``(calibrator, meta)``. Calibrator exposes ``.transform(proba)``.
    """
    y_true = np.asarray(y_true).astype(int).ravel()
    y_proba = np.asarray(y_proba, dtype=float).ravel()
    meta: Dict[str, Any] = {
        'method': None,
        'n_samples': int(len(y_true)),
        'brier_before': None,
        'brier_after': None,
        'log_loss_before': None,
        'log_loss_after': None,
        'fitted': False,
    }
    if len(y_true) < 20 or len(np.unique(y_true)) < 2:
        meta['warning'] = 'Insufficient validation samples/classes for calibration.'
        return None, meta

    try:
        meta['brier_before'] = float(brier_score_loss(y_true, y_proba))
        meta['log_loss_before'] = float(log_loss(y_true, np.clip(y_proba, 1e-7, 1 - 1e-7), labels=[0, 1]))
    except Exception:
        pass

    chosen = (method or 'auto').strip().lower()
    if chosen == 'auto':
        chosen = 'isotonic' if len(y_true) >= min_isotonic_samples else 'platt'
    if chosen in ('sigmoid', 'logistic'):
        chosen = 'platt'

    calibrator: Any = None
    try:
        if chosen == 'isotonic':
            calibrator = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0)
            calibrator.fit(y_proba, y_true)
        else:
            # Platt scaling: logistic on the raw score
            lr = LogisticRegression(solver='lbfgs', max_iter=1000)
            lr.fit(y_proba.reshape(-1, 1), y_true)
            calibrator = _PlattWrapper(lr)
            chosen = 'platt'
    except Exception as e:
        meta['warning'] = f'Calibration fit failed: {e}'
        return None, meta

    calibrated = apply_calibrator(calibrator, y_proba)
    try:
        meta['brier_after'] = float(brier_score_loss(y_true, calibrated))
        meta['log_loss_after'] = float(log_loss(y_true, np.clip(calibrated, 1e-7, 1 - 1e-7), labels=[0, 1]))
    except Exception:
        pass
    meta['method'] = chosen
    meta['fitted'] = True
    return calibrator, meta


class _PlattWrapper:
    """Thin wrapper so Platt and Isotonic share ``.transform(proba)``."""

    def __init__(self, lr: LogisticRegression):
        self.lr = lr

    def transform(self, proba) -> np.ndarray:
        x = np.asarray(proba, dtype=float).ravel().reshape(-1, 1)
        return self.lr.predict_proba(x)[:, 1]


def apply_calibrator(calibrator: Any, y_proba) -> np.ndarray:
    if calibrator is None:
        return np.asarray(y_proba, dtype=float).ravel()
    proba = np.asarray(y_proba, dtype=float).ravel()
    if hasattr(calibrator, 'transform'):
        out = calibrator.transform(proba)
    elif hasattr(calibrator, 'predict'):
        out = calibrator.predict(proba)
    else:
        return proba
    return np.clip(np.asarray(out, dtype=float).ravel(), 0.0, 1.0)


def save_calibrator(file_id: int, calibrator: Any, media_root: str) -> Optional[str]:
    if calibrator is None:
        return None
    out_dir = os.path.join(media_root, 'models')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f'{file_id}_calibrator.joblib')
    joblib_dump(calibrator, path)
    return os.path.relpath(path, media_root)


def load_calibrator(path: str, media_root: Optional[str] = None) -> Any:
    full = path
    if media_root and not os.path.isabs(path):
        full = os.path.join(media_root, path)
    return joblib_load(full)
