"""Shared booster adapters for XGBoost / LightGBM / CatBoost.

Keeps the boosting pipeline algorithm-agnostic while preserving the existing
product flow (native categoricals, early stopping, gain importance, SHAP).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _cat_cols(X: pd.DataFrame) -> List[str]:
    out = []
    for c in X.columns:
        if hasattr(X[c], 'cat') or str(X[c].dtype) == 'category':
            out.append(str(c))
        elif X[c].dtype == 'object' or pd.api.types.is_string_dtype(X[c]):
            out.append(str(c))
    return out


def _codes_frame(X: pd.DataFrame, cat_cols: Sequence[str]) -> pd.DataFrame:
    """LightGBM-friendly frame: categoricals as codes, NaN preserved."""
    out = X.copy()
    for c in cat_cols:
        if c not in out.columns:
            continue
        if hasattr(out[c], 'cat'):
            codes = out[c].cat.codes.astype(float)
            codes = codes.replace(-1, np.nan)
            out[c] = codes
        else:
            out[c] = pd.Categorical(out[c]).codes.astype(float)
            out[c] = out[c].replace(-1, np.nan)
    return out


def _is_regression(params: Optional[Dict[str, Any]]) -> bool:
    if not params:
        return False
    task = str(params.get('task') or '').strip().lower()
    if task in ('regression', 'regressor', 'reg'):
        return True
    obj = str(params.get('objective') or '').strip().lower()
    return obj.startswith('reg:') or obj in ('regression', 'rmse', 'mae', 'huber')


class BoosterAdapter(ABC):
    name: str = 'base'

    def __init__(self):
        self.model: Any = None
        self.feature_names: List[str] = []
        self.cat_features: List[str] = []
        self.best_iteration: int = 0
        self.enable_categorical: bool = False
        self.task: str = 'classification'

    @abstractmethod
    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_valid: pd.DataFrame,
        y_valid: pd.Series,
        params: Dict[str, Any],
        num_boost_round: int = 500,
        early_stopping_rounds: int = 50,
    ) -> 'BoosterAdapter':
        raise NotImplementedError

    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Raw score prediction (classification probability or regression value)."""
        return self.predict_proba(X)

    @abstractmethod
    def save(self, path: str) -> str:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def load(cls, path: str, feature_names: Optional[List[str]] = None,
             cat_features: Optional[List[str]] = None) -> 'BoosterAdapter':
        raise NotImplementedError

    @abstractmethod
    def gain_importance(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def shap_model(self) -> Any:
        """Object accepted by shap.TreeExplainer."""
        return self.model

    def model_filename(self, file_id: int) -> str:
        kind = 'regressor' if self.task == 'regression' else 'classifier'
        return f'{file_id}_{self.name}_{kind}.json'


class XGBoostAdapter(BoosterAdapter):
    name = 'xgboost'

    def train(self, X_train, y_train, X_valid, y_valid, params,
              num_boost_round=500, early_stopping_rounds=50):
        import xgboost as xgb
        self.feature_names = list(map(str, X_train.columns))
        self.cat_features = _cat_cols(X_train)
        self.enable_categorical = len(self.cat_features) > 0
        self.task = 'regression' if _is_regression(params) else 'classification'
        p = {k: v for k, v in dict(params).items() if k != 'task'}
        if self.task == 'regression':
            p.setdefault('objective', 'reg:squarederror')
            p.setdefault('eval_metric', 'rmse')
            p.pop('num_class', None)
            p.pop('scale_pos_weight', None)
        if self.enable_categorical:
            p['enable_categorical'] = True
        dtrain = xgb.DMatrix(
            X_train, label=y_train, feature_names=self.feature_names,
            enable_categorical=self.enable_categorical,
        )
        dvalid = xgb.DMatrix(
            X_valid, label=y_valid, feature_names=self.feature_names,
            enable_categorical=self.enable_categorical,
        )
        self.model = xgb.train(
            p, dtrain, num_boost_round=num_boost_round,
            evals=[(dvalid, 'valid')],
            early_stopping_rounds=early_stopping_rounds if early_stopping_rounds else None,
            verbose_eval=False,
        )
        self.best_iteration = int(getattr(self.model, 'best_iteration', num_boost_round) or num_boost_round)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        import xgboost as xgb
        dmat = xgb.DMatrix(
            X[self.feature_names] if self.feature_names else X,
            feature_names=self.feature_names or list(map(str, X.columns)),
            enable_categorical=self.enable_categorical,
        )
        try:
            if self.best_iteration is not None and self.best_iteration >= 0:
                return np.asarray(
                    self.model.predict(dmat, iteration_range=(0, int(self.best_iteration) + 1)),
                    dtype=float,
                ).ravel()
        except Exception:
            pass
        return np.asarray(self.model.predict(dmat), dtype=float).ravel()

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self.model.save_model(path)
        return path

    @classmethod
    def load(cls, path: str, feature_names=None, cat_features=None):
        import xgboost as xgb
        obj = cls()
        obj.model = xgb.Booster()
        obj.model.load_model(path)
        obj.feature_names = list(feature_names or [])
        obj.cat_features = list(cat_features or [])
        obj.enable_categorical = bool(obj.cat_features)
        obj.task = 'regression' if 'regressor' in os.path.basename(path).lower() else 'classification'
        try:
            obj.best_iteration = int(getattr(obj.model, 'best_iteration', 0) or 0)
        except Exception:
            obj.best_iteration = 0
        return obj

    def gain_importance(self) -> List[Dict[str, Any]]:
        try:
            raw = self.model.get_score(importance_type='gain')
        except Exception:
            return []
        items = sorted(((str(k), float(v)) for k, v in raw.items()), key=lambda kv: kv[1], reverse=True)
        # Strip f-prefix / map to feature names when possible
        out = []
        for k, v in items:
            name = k
            if k.startswith('f') and k[1:].isdigit() and self.feature_names:
                idx = int(k[1:])
                if 0 <= idx < len(self.feature_names):
                    name = self.feature_names[idx]
            out.append({'feature': name, 'score': v})
        return out

    def model_filename(self, file_id: int) -> str:
        kind = 'regressor' if self.task == 'regression' else 'classifier'
        return f'{file_id}_xgb_{kind}.json'


class LightGBMAdapter(BoosterAdapter):
    name = 'lightgbm'

    def train(self, X_train, y_train, X_valid, y_valid, params,
              num_boost_round=500, early_stopping_rounds=50):
        import lightgbm as lgb
        self.feature_names = list(map(str, X_train.columns))
        self.cat_features = _cat_cols(X_train)
        self.enable_categorical = len(self.cat_features) > 0
        self.task = 'regression' if _is_regression(params) else 'classification'
        Xtr = X_train.copy()
        Xva = X_valid.copy()
        # LightGBM prefers category dtype for native cats
        for c in self.cat_features:
            if c in Xtr.columns:
                Xtr[c] = Xtr[c].astype('category')
            if c in Xva.columns:
                Xva[c] = Xva[c].astype('category')
        p = {
            'objective': 'binary',
            'metric': 'auc',
            'verbosity': -1,
            'seed': int(params.get('seed', 42)),
            'learning_rate': float(params.get('eta', params.get('learning_rate', 0.05))),
            'max_depth': int(params.get('max_depth', 4)),
            'min_child_weight': float(params.get('min_child_weight', 2)),
            'subsample': float(params.get('subsample', 0.8)),
            'colsample_bytree': float(params.get('colsample_bytree', 0.7)),
            'reg_alpha': float(params.get('alpha', params.get('reg_alpha', 0.1))),
            'reg_lambda': float(params.get('lambda', params.get('reg_lambda', 1.5))),
        }
        if self.task == 'regression':
            p['objective'] = 'regression'
            p['metric'] = 'rmse'
        elif 'num_class' in params:
            p['objective'] = 'multiclass'
            p['num_class'] = int(params['num_class'])
            p['metric'] = 'multi_logloss'
        if 'scale_pos_weight' in params and self.task != 'regression':
            p['scale_pos_weight'] = float(params['scale_pos_weight'])
        dtrain = lgb.Dataset(Xtr, label=y_train, categorical_feature=self.cat_features or 'auto', free_raw_data=False)
        dvalid = lgb.Dataset(Xva, label=y_valid, reference=dtrain, categorical_feature=self.cat_features or 'auto', free_raw_data=False)
        callbacks = [lgb.log_evaluation(period=0)]
        if early_stopping_rounds:
            callbacks.append(lgb.early_stopping(early_stopping_rounds, verbose=False))
        self.model = lgb.train(
            p, dtrain, num_boost_round=num_boost_round,
            valid_sets=[dvalid], valid_names=['valid'],
            callbacks=callbacks,
        )
        self.best_iteration = int(getattr(self.model, 'best_iteration', num_boost_round) or num_boost_round)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        Xc = X[self.feature_names].copy() if self.feature_names else X.copy()
        for c in self.cat_features:
            if c in Xc.columns:
                Xc[c] = Xc[c].astype('category')
        ntree = self.best_iteration if self.best_iteration and self.best_iteration > 0 else None
        return np.asarray(self.model.predict(Xc, num_iteration=ntree), dtype=float).ravel()

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self.model.save_model(path)
        return path

    @classmethod
    def load(cls, path: str, feature_names=None, cat_features=None):
        import lightgbm as lgb
        obj = cls()
        obj.model = lgb.Booster(model_file=path)
        obj.feature_names = list(feature_names or obj.model.feature_name() or [])
        obj.cat_features = list(cat_features or [])
        obj.enable_categorical = bool(obj.cat_features)
        obj.task = 'regression' if 'regressor' in os.path.basename(path).lower() else 'classification'
        obj.best_iteration = int(getattr(obj.model, 'best_iteration', 0) or 0)
        return obj

    def gain_importance(self) -> List[Dict[str, Any]]:
        try:
            names = self.feature_names or self.model.feature_name()
            gains = self.model.feature_importance(importance_type='gain')
            pairs = sorted(zip(names, gains), key=lambda kv: float(kv[1]), reverse=True)
            return [{'feature': str(k), 'score': float(v)} for k, v in pairs if float(v) > 0]
        except Exception:
            return []

    def model_filename(self, file_id: int) -> str:
        kind = 'regressor' if self.task == 'regression' else 'classifier'
        return f'{file_id}_lgbm_{kind}.txt'


class CatBoostAdapter(BoosterAdapter):
    name = 'catboost'

    def train(self, X_train, y_train, X_valid, y_valid, params,
              num_boost_round=500, early_stopping_rounds=50):
        from catboost import CatBoostClassifier, CatBoostRegressor, Pool
        self.feature_names = list(map(str, X_train.columns))
        self.cat_features = _cat_cols(X_train)
        self.enable_categorical = len(self.cat_features) > 0
        self.task = 'regression' if _is_regression(params) else 'classification'
        cat_idx = [self.feature_names.index(c) for c in self.cat_features if c in self.feature_names]
        Xtr = X_train.copy()
        Xva = X_valid.copy()
        for c in self.cat_features:
            Xtr[c] = Xtr[c].astype(str).fillna('__NULL__')
            Xva[c] = Xva[c].astype(str).fillna('__NULL__')
        train_pool = Pool(Xtr, y_train, cat_features=cat_idx or None, feature_names=self.feature_names)
        valid_pool = Pool(Xva, y_valid, cat_features=cat_idx or None, feature_names=self.feature_names)
        cb_kwargs: Dict[str, Any] = {
            'iterations': int(num_boost_round),
            'learning_rate': float(params.get('eta', params.get('learning_rate', 0.05))),
            'depth': int(params.get('max_depth', 4)),
            'l2_leaf_reg': float(params.get('lambda', params.get('reg_lambda', 1.5))),
            'subsample': float(params.get('subsample', 0.8)),
            'random_seed': int(params.get('seed', 42)),
            'verbose': False,
            'allow_writing_files': False,
        }
        if self.task == 'regression':
            cb_kwargs['loss_function'] = 'RMSE'
            cb_kwargs['eval_metric'] = 'RMSE'
            self.model = CatBoostRegressor(**cb_kwargs)
        else:
            loss = 'MultiClass' if 'num_class' in params else 'Logloss'
            cb_kwargs['loss_function'] = loss
            cb_kwargs['eval_metric'] = 'AUC' if loss == 'Logloss' else 'MultiClass'
            if 'scale_pos_weight' in params and params['scale_pos_weight'] is not None:
                cb_kwargs['scale_pos_weight'] = float(params['scale_pos_weight'])
            self.model = CatBoostClassifier(**cb_kwargs)
        self.model.fit(
            train_pool, eval_set=valid_pool,
            early_stopping_rounds=early_stopping_rounds or None,
            verbose=False,
        )
        try:
            self.best_iteration = int(self.model.get_best_iteration() or num_boost_round)
        except Exception:
            self.best_iteration = int(num_boost_round)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        from catboost import Pool
        Xc = X[self.feature_names].copy() if self.feature_names else X.copy()
        for c in self.cat_features:
            if c in Xc.columns:
                Xc[c] = Xc[c].astype(str).fillna('__NULL__')
        cat_idx = [list(Xc.columns).index(c) for c in self.cat_features if c in Xc.columns]
        pool = Pool(Xc, cat_features=cat_idx or None, feature_names=list(map(str, Xc.columns)))
        if self.task == 'regression' or not hasattr(self.model, 'predict_proba'):
            return np.asarray(self.model.predict(pool), dtype=float).ravel()
        proba = self.model.predict_proba(pool)
        proba = np.asarray(proba)
        if proba.ndim == 2 and proba.shape[1] >= 2:
            return proba[:, 1].astype(float)
        return proba.ravel().astype(float)

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self.model.save_model(path)
        return path

    @classmethod
    def load(cls, path: str, feature_names=None, cat_features=None):
        from catboost import CatBoostClassifier, CatBoostRegressor
        obj = cls()
        is_reg = 'regressor' in os.path.basename(path).lower()
        obj.task = 'regression' if is_reg else 'classification'
        obj.model = CatBoostRegressor() if is_reg else CatBoostClassifier()
        obj.model.load_model(path)
        obj.feature_names = list(feature_names or [])
        obj.cat_features = list(cat_features or [])
        obj.enable_categorical = bool(obj.cat_features)
        try:
            obj.best_iteration = int(obj.model.get_best_iteration() or 0)
        except Exception:
            obj.best_iteration = 0
        return obj

    def gain_importance(self) -> List[Dict[str, Any]]:
        try:
            importances = self.model.get_feature_importance()
            names = self.feature_names or [f'f{i}' for i in range(len(importances))]
            pairs = sorted(zip(names, importances), key=lambda kv: float(kv[1]), reverse=True)
            return [{'feature': str(k), 'score': float(v)} for k, v in pairs if float(v) > 0]
        except Exception:
            return []

    def model_filename(self, file_id: int) -> str:
        kind = 'regressor' if self.task == 'regression' else 'classifier'
        return f'{file_id}_catboost_{kind}.cbm'


_ADAPTERS = {
    'xgboost': XGBoostAdapter,
    'lightgbm': LightGBMAdapter,
    'catboost': CatBoostAdapter,
}


def available_boosting_algorithms() -> Dict[str, bool]:
    """Return {algo: importable?} for UI/API honesty."""
    status = {'xgboost': True, 'lightgbm': False, 'catboost': False}
    try:
        import lightgbm  # noqa: F401
        status['lightgbm'] = True
    except Exception:
        pass
    try:
        import catboost  # noqa: F401
        status['catboost'] = True
    except Exception:
        pass
    try:
        import xgboost  # noqa: F401
        status['xgboost'] = True
    except Exception:
        status['xgboost'] = False
    return status


def get_adapter(algorithm: Optional[str] = None) -> BoosterAdapter:
    algo = (algorithm or 'xgboost').strip().lower()
    if algo not in _ADAPTERS:
        raise ValueError(f'Unsupported boosting algorithm: {algorithm}')
    avail = available_boosting_algorithms()
    if not avail.get(algo):
        raise ImportError(
            f'{algo} is not installed in this environment. '
            f'Install the package or select an available booster: '
            f'{[k for k, v in avail.items() if v]}'
        )
    return _ADAPTERS[algo]()


def load_adapter_from_path(
    path: str,
    algorithm: Optional[str] = None,
    feature_names: Optional[List[str]] = None,
    cat_features: Optional[List[str]] = None,
) -> BoosterAdapter:
    algo = (algorithm or 'xgboost').strip().lower()
    lower = path.lower()
    if algorithm is None:
        if lower.endswith('.cbm') or 'catboost' in lower:
            algo = 'catboost'
        elif lower.endswith('.txt') or 'lgbm' in lower or 'lightgbm' in lower:
            algo = 'lightgbm'
        else:
            algo = 'xgboost'
    cls = _ADAPTERS[algo]
    return cls.load(path, feature_names=feature_names, cat_features=cat_features)
