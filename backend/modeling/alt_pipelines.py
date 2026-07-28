"""Alternate CRISP-DM modeling styles: logit, credit scorecard, anomaly (IsolationForest).

Mirrors booster adapter surfaces enough for Evaluation / Deployment:
predict_proba, save/load, gain_importance stand-ins.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import OneHotEncoder


ALT_ALGORITHMS = {
    'logistic_regression',
    'logit',
    'scorecard',
    'isolation_forest',
    'anomaly',
}


def normalize_alt_algorithm(algorithm: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (canonical_algo, error). None,None if not an alt algorithm."""
    if algorithm is None:
        return None, None
    algo = str(algorithm).strip().lower().replace('-', '_')
    aliases = {
        'logit': 'logistic_regression',
        'logistic': 'logistic_regression',
        'logistic_regression': 'logistic_regression',
        'scorecard': 'scorecard',
        'credit_scoring': 'scorecard',
        'credit_scorecard': 'scorecard',
        'isolation_forest': 'isolation_forest',
        'anomaly': 'isolation_forest',
        'anomaly_detection': 'isolation_forest',
    }
    if algo not in aliases:
        return None, None
    return aliases[algo], None


def is_alt_algorithm(algorithm: Optional[str]) -> bool:
    canon, _ = normalize_alt_algorithm(algorithm)
    return canon is not None


def _cat_cols(X: pd.DataFrame) -> List[str]:
    out = []
    for c in X.columns:
        if hasattr(X[c], 'cat') or str(X[c].dtype) == 'category':
            out.append(str(c))
        elif X[c].dtype == 'object' or pd.api.types.is_string_dtype(X[c]):
            out.append(str(c))
    return out


def _numeric_frame(X: pd.DataFrame) -> pd.DataFrame:
    """One-hot encode categoricals; keep numeric columns. Fit not needed — caller passes already-split frames via DesignMatrix."""
    return X


@dataclass
class DesignMatrix:
    """Train-fit one-hot encoder for sklearn models."""
    feature_names: List[str] = field(default_factory=list)
    cat_features: List[str] = field(default_factory=list)
    num_features: List[str] = field(default_factory=list)
    encoder: Any = None
    encoded_feature_names: List[str] = field(default_factory=list)

    def fit(self, X: pd.DataFrame) -> 'DesignMatrix':
        self.feature_names = list(map(str, X.columns))
        self.cat_features = _cat_cols(X)
        self.num_features = [c for c in self.feature_names if c not in self.cat_features]
        if self.cat_features:
            try:
                self.encoder = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
            except TypeError:
                self.encoder = OneHotEncoder(handle_unknown='ignore', sparse=False)
            self.encoder.fit(X[self.cat_features].astype(str).fillna('__NULL__'))
            try:
                cat_names = list(self.encoder.get_feature_names_out(self.cat_features))
            except Exception:
                cat_names = [f'cat_{i}' for i in range(int(np.asarray(self.encoder.transform(
                    X[self.cat_features].astype(str).fillna('__NULL__')
                )).shape[1]))]
            self.encoded_feature_names = list(self.num_features) + cat_names
        else:
            self.encoder = None
            self.encoded_feature_names = list(self.num_features)
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        parts = []
        if self.num_features:
            num = X.reindex(columns=self.num_features).apply(pd.to_numeric, errors='coerce').fillna(0.0)
            parts.append(num.to_numpy(dtype=float))
        if self.encoder is not None and self.cat_features:
            cats = X.reindex(columns=self.cat_features).astype(str).fillna('__NULL__')
            parts.append(np.asarray(self.encoder.transform(cats), dtype=float))
        if not parts:
            return np.zeros((len(X), 0), dtype=float)
        return np.hstack(parts)


# ---------------------------------------------------------------------------
# WOE / scorecard helpers
# ---------------------------------------------------------------------------

@dataclass
class WoeBin:
    feature: str
    label: str
    woe: float
    iv_contrib: float
    left: Optional[float] = None
    right: Optional[float] = None
    categories: Optional[List[str]] = None


def fit_woe_maps(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    max_bins: int = 10,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """Fit per-feature WOE maps on train; return maps + WOE-transformed frame."""
    y = pd.to_numeric(y, errors='coerce').astype(float)
    mask = y.notna()
    X = X.loc[mask]
    y = y.loc[mask].astype(int)
    maps: Dict[str, Any] = {}
    woe_cols = {}
    for col in X.columns:
        s = X[col]
        bins_meta: List[Dict[str, Any]] = []
        if pd.api.types.is_numeric_dtype(s) and s.nunique(dropna=True) > max_bins:
            try:
                cats, edges = pd.qcut(
                    s.rank(method='first'), q=min(max_bins, max(2, s.nunique())),
                    duplicates='drop', retbins=True,
                )
            except Exception:
                cats, edges = pd.cut(s, bins=min(max_bins, max(2, int(s.nunique()))), duplicates='drop', retbins=True)
            tab = pd.crosstab(cats, y)
            if tab.shape[1] < 2:
                continue
            goods = tab.get(1, pd.Series(0, index=tab.index)).astype(float) + 0.5
            bads = tab.get(0, pd.Series(0, index=tab.index)).astype(float) + 0.5
            good_rate = goods / goods.sum()
            bad_rate = bads / bads.sum()
            woe = np.log(good_rate / bad_rate)
            iv = float(((good_rate - bad_rate) * woe).sum())
            mapping = {}
            for i, idx in enumerate(tab.index):
                mapping[str(idx)] = float(woe.iloc[i])
                bins_meta.append({
                    'label': str(idx),
                    'woe': float(woe.iloc[i]),
                    'iv_contrib': float((good_rate.iloc[i] - bad_rate.iloc[i]) * woe.iloc[i]),
                })
            maps[col] = {
                'kind': 'numeric_qcut',
                'iv': iv if np.isfinite(iv) else None,
                'edges': [float(e) for e in edges] if hasattr(edges, '__iter__') else [],
                'mapping': mapping,
                'bins': bins_meta,
            }
            # transform via qcut labels then map
            woe_cols[col] = cats.astype(str).map(mapping).astype(float).fillna(0.0)
        else:
            cats = s.astype(str).fillna('__NULL__')
            tab = pd.crosstab(cats, y)
            if tab.shape[1] < 2:
                continue
            goods = tab.get(1, pd.Series(0, index=tab.index)).astype(float) + 0.5
            bads = tab.get(0, pd.Series(0, index=tab.index)).astype(float) + 0.5
            good_rate = goods / goods.sum()
            bad_rate = bads / bads.sum()
            woe = np.log(good_rate / bad_rate)
            iv = float(((good_rate - bad_rate) * woe).sum())
            mapping = {str(k): float(woe.loc[k]) for k in tab.index}
            bins_meta = [
                {
                    'label': str(k),
                    'woe': float(woe.loc[k]),
                    'iv_contrib': float((good_rate.loc[k] - bad_rate.loc[k]) * woe.loc[k]),
                    'categories': [str(k)],
                }
                for k in tab.index
            ]
            maps[col] = {
                'kind': 'categorical',
                'iv': iv if np.isfinite(iv) else None,
                'mapping': mapping,
                'bins': bins_meta,
            }
            woe_cols[col] = cats.map(mapping).astype(float).fillna(0.0)
    woe_df = pd.DataFrame(woe_cols, index=X.index)
    return maps, woe_df


def transform_woe(X: pd.DataFrame, maps: Dict[str, Any]) -> pd.DataFrame:
    out = {}
    for col, meta in maps.items():
        if col not in X.columns:
            continue
        mapping = meta.get('mapping') or {}
        s = X[col]
        if meta.get('kind') == 'numeric_qcut' and meta.get('edges'):
            try:
                cats = pd.cut(s, bins=meta['edges'], include_lowest=True)
                out[col] = cats.astype(str).map(mapping).astype(float).fillna(0.0)
            except Exception:
                out[col] = s.astype(str).map(mapping).astype(float).fillna(0.0)
        else:
            out[col] = s.astype(str).fillna('__NULL__').map(mapping).astype(float).fillna(0.0)
    return pd.DataFrame(out, index=X.index)


def coeffs_to_score_points(
    feature_names: Sequence[str],
    coefficients: Sequence[float],
    *,
    pdo: float = 20.0,
    base_score: float = 600.0,
    base_odds: float = 50.0,
) -> List[Dict[str, Any]]:
    """Map logit coefficients to scorecard points (PDO convention)."""
    factor = pdo / np.log(2.0)
    offset = base_score - factor * np.log(base_odds)
    points = []
    for name, coef in zip(feature_names, coefficients):
        # Points contribution per unit WOE ≈ -factor * coef (lower risk → higher score)
        pts = float(-factor * float(coef))
        points.append({
            'feature': str(name),
            'coefficient': float(coef),
            'points_per_woe': pts,
            'pdo': pdo,
            'base_score': base_score,
            'offset': float(offset),
            'factor': float(factor),
        })
    return points


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

class SklearnModelAdapter:
    """Unified adapter for logit / scorecard / isolation forest."""

    name = 'sklearn'
    task = 'classification'

    def __init__(self, algorithm: str = 'logistic_regression'):
        self.algorithm = algorithm
        self.model: Any = None
        self.design: Optional[DesignMatrix] = None
        self.woe_maps: Dict[str, Any] = {}
        self.score_points: List[Dict[str, Any]] = []
        self.feature_names: List[str] = []
        self.cat_features: List[str] = []
        self.best_iteration: int = 0
        self.enable_categorical: bool = False
        self.iv_table: List[Dict[str, Any]] = []

    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_valid: pd.DataFrame,
        y_valid: pd.Series,
        params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> 'SklearnModelAdapter':
        params = params or {}
        if self.algorithm == 'isolation_forest':
            return self._train_iforest(X_train, y_train, X_valid, y_valid, params)
        if self.algorithm == 'scorecard':
            return self._train_scorecard(X_train, y_train, X_valid, y_valid, params)
        return self._train_logit(X_train, y_train, X_valid, y_valid, params)

    def _train_logit(self, X_train, y_train, X_valid, y_valid, params):
        self.design = DesignMatrix().fit(X_train)
        self.feature_names = list(self.design.encoded_feature_names)
        self.cat_features = list(self.design.cat_features)
        self.enable_categorical = bool(self.cat_features)
        Xt = self.design.transform(X_train)
        C = float(params.get('C', 1.0))
        max_iter = int(params.get('max_iter', 500))
        class_weight = params.get('class_weight', 'balanced')
        self.model = LogisticRegression(
            C=C, max_iter=max_iter, class_weight=class_weight,
            solver='lbfgs', random_state=42,
        )
        self.model.fit(Xt, np.asarray(y_train).ravel())
        self.task = 'classification'
        return self

    def _train_scorecard(self, X_train, y_train, X_valid, y_valid, params):
        maps, Xw_train = fit_woe_maps(X_train, y_train)
        self.woe_maps = maps
        self.iv_table = [
            {'feature': f, 'iv': meta.get('iv'), 'n_bins': len(meta.get('bins') or [])}
            for f, meta in maps.items()
        ]
        Xw_train = Xw_train.reindex(index=X_train.index).fillna(0.0)
        # Drop zero-variance
        keep = [c for c in Xw_train.columns if Xw_train[c].nunique() > 1]
        Xw_train = Xw_train[keep]
        self.feature_names = list(Xw_train.columns)
        self.cat_features = []
        self.enable_categorical = False
        C = float(params.get('C', 1.0))
        self.model = LogisticRegression(
            C=C, max_iter=int(params.get('max_iter', 500)),
            class_weight=params.get('class_weight', 'balanced'),
            solver='lbfgs', random_state=42,
        )
        self.model.fit(Xw_train.to_numpy(dtype=float), np.asarray(y_train).ravel())
        coefs = list(np.asarray(self.model.coef_).ravel())
        self.score_points = coeffs_to_score_points(
            self.feature_names, coefs,
            pdo=float(params.get('pdo', 20.0)),
            base_score=float(params.get('base_score', 600.0)),
            base_odds=float(params.get('base_odds', 50.0)),
        )
        self.task = 'classification'
        self.algorithm = 'scorecard'
        return self

    def _train_iforest(self, X_train, y_train, X_valid, y_valid, params):
        self.design = DesignMatrix().fit(X_train)
        self.feature_names = list(self.design.encoded_feature_names)
        self.cat_features = list(self.design.cat_features)
        Xt = self.design.transform(X_train)
        contam = float(params.get('contamination', 0.05))
        n_est = int(params.get('n_estimators', 200))
        self.model = IsolationForest(
            n_estimators=n_est,
            contamination=contam if 0 < contam < 0.5 else 'auto',
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(Xt)
        self.task = 'anomaly'
        self.algorithm = 'isolation_forest'
        return self

    def _matrix(self, X: pd.DataFrame) -> np.ndarray:
        if self.algorithm == 'scorecard':
            Xw = transform_woe(X, self.woe_maps)
            Xw = Xw.reindex(columns=self.feature_names).fillna(0.0)
            return Xw.to_numpy(dtype=float)
        assert self.design is not None
        return self.design.transform(X)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        Xm = self._matrix(X)
        if self.algorithm == 'isolation_forest':
            # Higher = more anomalous; map to (0,1) via rank-ish logistic of -score
            raw = -np.asarray(self.model.score_samples(Xm), dtype=float)
            # Min-max on batch for deployability
            lo, hi = float(np.min(raw)), float(np.max(raw))
            if hi - lo < 1e-12:
                return np.full(len(raw), 0.5)
            return (raw - lo) / (hi - lo)
        proba = self.model.predict_proba(Xm)
        if proba.ndim == 2 and proba.shape[1] >= 2:
            return proba[:, 1]
        return proba.ravel()

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.predict_proba(X)

    def predict_scorecard_scores(self, X: pd.DataFrame) -> np.ndarray:
        """PDO score: offset + factor * log-odds from WOE logit."""
        if self.algorithm != 'scorecard' or not self.score_points:
            return self.predict_proba(X)
        Xm = self._matrix(X)
        log_odds = self.model.decision_function(Xm)
        factor = self.score_points[0]['factor']
        offset = self.score_points[0]['offset']
        return offset + factor * np.asarray(log_odds, dtype=float)

    def gain_importance(self) -> List[Dict[str, Any]]:
        if self.algorithm == 'isolation_forest':
            return []
        if self.model is None or not hasattr(self.model, 'coef_'):
            return []
        coefs = np.abs(np.asarray(self.model.coef_).ravel())
        names = self.feature_names or [f'f{i}' for i in range(len(coefs))]
        pairs = sorted(
            [{'feature': str(n), 'score': float(c)} for n, c in zip(names, coefs)],
            key=lambda x: -x['score'],
        )
        return pairs

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        payload = {
            'algorithm': self.algorithm,
            'task': self.task,
            'feature_names': self.feature_names,
            'cat_features': self.cat_features,
            'woe_maps': self.woe_maps,
            'score_points': self.score_points,
            'iv_table': self.iv_table,
            'design': self.design,
            'model': self.model,
        }
        joblib.dump(payload, path)
        # Sidecar JSON for humans
        meta_path = path + '.meta.json'
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump({
                'algorithm': self.algorithm,
                'task': self.task,
                'feature_names': self.feature_names,
                'n_features': len(self.feature_names),
                'iv_table': self.iv_table,
                'score_points': self.score_points[:50],
            }, f, indent=2, default=str)
        return path

    @classmethod
    def load(cls, path: str, feature_names=None, cat_features=None) -> 'SklearnModelAdapter':
        payload = joblib.load(path)
        obj = cls(algorithm=payload.get('algorithm') or 'logistic_regression')
        obj.task = payload.get('task') or 'classification'
        obj.feature_names = list(payload.get('feature_names') or feature_names or [])
        obj.cat_features = list(payload.get('cat_features') or cat_features or [])
        obj.woe_maps = payload.get('woe_maps') or {}
        obj.score_points = payload.get('score_points') or []
        obj.iv_table = payload.get('iv_table') or []
        obj.design = payload.get('design')
        obj.model = payload.get('model')
        obj.enable_categorical = bool(obj.cat_features)
        return obj

    def model_filename(self, file_id: int) -> str:
        return f'{file_id}_{self.algorithm}.joblib'

    def shap_model(self):
        return None


def get_alt_adapter(algorithm: str) -> SklearnModelAdapter:
    canon, err = normalize_alt_algorithm(algorithm)
    if err or not canon:
        raise ValueError(f'Unsupported alternate algorithm: {algorithm}')
    return SklearnModelAdapter(algorithm=canon)


def load_model_adapter(
    path: str,
    algorithm: Optional[str] = None,
    feature_names: Optional[List[str]] = None,
    cat_features: Optional[List[str]] = None,
):
    """Dispatch booster vs sklearn adapters by algorithm / file extension."""
    from modeling.booster_adapters import load_adapter_from_path, get_adapter

    algo = (algorithm or '').strip().lower()
    lower = (path or '').lower()
    if is_alt_algorithm(algo) or lower.endswith('.joblib') or lower.endswith('.pkl'):
        if is_alt_algorithm(algo) or 'logistic' in lower or 'scorecard' in lower or 'isolation' in lower:
            return SklearnModelAdapter.load(path, feature_names=feature_names, cat_features=cat_features)
    return load_adapter_from_path(
        path, algorithm=algorithm, feature_names=feature_names, cat_features=cat_features,
    )


def evaluate_anomaly_scores(y_true, scores) -> Dict[str, Any]:
    """If labels exist, report ranking metrics; else score distribution only."""
    y = pd.to_numeric(pd.Series(y_true), errors='coerce')
    s = np.asarray(scores, dtype=float).ravel()
    mask = y.notna().to_numpy()
    out: Dict[str, Any] = {
        'task': 'anomaly',
        'n_scored': int(len(s)),
        'score_mean': float(np.mean(s)) if len(s) else None,
        'score_std': float(np.std(s)) if len(s) else None,
    }
    if mask.sum() > 10 and y[mask].nunique() > 1:
        yy = y[mask].astype(int).to_numpy()
        ss = s[mask]
        try:
            out['roc_auc'] = float(roc_auc_score(yy, ss))
        except Exception:
            out['roc_auc'] = None
        try:
            out['pr_auc'] = float(average_precision_score(yy, ss))
        except Exception:
            out['pr_auc'] = None
    return out
