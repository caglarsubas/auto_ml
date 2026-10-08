"""Native fit receipts bind development inputs/configuration; they are not signatures."""
from __future__ import annotations

import hashlib
import json
import platform
from functools import lru_cache
from importlib.metadata import version

import numpy as np
import pandas as pd


def input_receipt(X, y):
    if not isinstance(X, pd.DataFrame) or not X.index.is_unique or not X.columns.is_unique:
        raise ValueError('Native fit inputs require unique dataframe rows and columns.')
    labels = y if isinstance(y, pd.Series) else pd.Series(y, index=X.index)
    if not labels.index.equals(X.index) or len(labels) != len(X):
        raise ValueError('Native fit labels must preserve the exact feature row order.')
    schema = {'features': list(map(str, X.columns)), 'dtypes': list(map(str, X.dtypes)),
              'label_dtype': str(labels.dtype), 'n_rows': len(X)}
    h = hashlib.sha256(json.dumps(schema, sort_keys=True).encode())
    h.update(pd.util.hash_pandas_object(X, index=True, categorize=False).to_numpy(dtype='<u8').tobytes())
    h.update(pd.util.hash_pandas_object(labels, index=True, categorize=False).to_numpy(dtype='<u8').tobytes())
    # Category order is also part of a native categorical feature's semantics.
    categories = {str(name): {'levels': [{'type': type(level).__name__, 'value': str(level)} for level in X[name].cat.categories], 'ordered': X[name].cat.ordered}
                  for name in X if isinstance(X[name].dtype, pd.CategoricalDtype)}
    h.update(json.dumps(categories, sort_keys=True).encode())
    return {**schema, 'sha256': h.hexdigest()}


@lru_cache
def runtime_versions(algorithm):
    packages = ['numpy', 'pandas', 'scikit-learn' if algorithm == 'sklearn' else algorithm]
    return {'python': platform.python_version(), 'packages': {package: version(package) for package in packages}}


def receipt_digest(receipt):
    # JSON changes integer parameter keys to strings. Canonicalize that change
    # before sorting so a persisted multiclass class-weight map keeps its digest.
    persisted = json.loads(json.dumps(receipt, allow_nan=False))
    return hashlib.sha256(json.dumps(persisted, sort_keys=True, allow_nan=False).encode()).hexdigest()


def record_native_fit(adapter, X_train, y_train, X_valid, y_valid, requested_params,
                      effective_params, num_boost_round=None, early_stopping_rounds=None):
    receipt = {'schema_version': 1, 'algorithm': adapter.algorithm if adapter.name == 'sklearn' else adapter.name,
               'task': adapter.task, 'train': input_receipt(X_train, y_train),
               'valid': input_receipt(X_valid, y_valid), 'requested_params': dict(requested_params),
               'effective_params': dict(effective_params), 'num_boost_round': num_boost_round,
               'early_stopping_rounds': early_stopping_rounds,
               'training_eval_metric': getattr(adapter, 'training_eval_metric', None),
               'runtime': runtime_versions(adapter.name),
               'validation_role': ('not_used_by_fitter' if adapter.name == 'sklearn' else
                                   'early_stopping' if early_stopping_rounds else 'evaluation_only'),
               'qualification': 'Native controller record; effective parameters are those supplied to the fitter (resolved defaults for CatBoost/sklearn). Not independent reproduction or actor authentication.'}
    # Preserve native metric/weight parameter types while detaching containers.
    def primitive(value):
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, dict):
            return {primitive(key): primitive(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [primitive(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ValueError('Native fit parameters must be recorded primitive values.')
    receipt = primitive(receipt)
    receipt['sha256'] = receipt_digest(receipt)
    adapter.fit_receipt = receipt
    return receipt


def verify_candidate_fit(adapter, data, features):
    from modeling.booster_adapters import XGBoostAdapter, LightGBMAdapter, CatBoostAdapter
    from modeling.alt_pipelines import SklearnModelAdapter
    if type(adapter) not in (XGBoostAdapter, LightGBMAdapter, CatBoostAdapter, SklearnModelAdapter):
        raise ValueError('Candidate publication supports registered native adapters only; expert execution requires isolation.')
    receipt = getattr(adapter, 'fit_receipt', None)
    if not receipt:
        raise ValueError('Candidate lacks a recorded native fit. Refit against the selected execution before publication.')
    unsigned = {key: value for key, value in receipt.items() if key != 'sha256'}
    expected = receipt_digest(unsigned)
    algorithm = adapter.algorithm if adapter.name == 'sklearn' else adapter.name
    if receipt['sha256'] != expected or receipt['algorithm'] != algorithm or receipt['task'] != data['task'] or adapter.task != data['task']:
        raise ValueError('Candidate fit receipt contradicts its task, algorithm or recorded configuration.')
    for partition in ('train', 'valid'):
        if input_receipt(data['X_' + partition][features], data['y_' + partition]) != receipt[partition]:
            raise ValueError(f'Candidate {partition} inputs differ from the selected immutable execution; refit before publication.')
    return receipt
