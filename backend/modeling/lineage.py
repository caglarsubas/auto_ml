"""Immutable-ish lineage blob for a boosting pipeline run."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from django.conf import settings


def _sha256_json(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]


def build_lineage(
    file_id: int,
    *,
    algorithm: str = 'xgboost',
    processed_file: Optional[str] = None,
    split_meta: Optional[Dict[str, Any]] = None,
    purifier_options: Optional[List[Any]] = None,
    encoding_plan: Optional[List[Dict[str, Any]]] = None,
    encoding_use_native: bool = True,
    feature_names: Optional[List[str]] = None,
    excluded_variables: Optional[List[str]] = None,
    model_params: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    model_path: Optional[str] = None,
    impute_means: Optional[Dict[str, float]] = None,
    scale_pos_weight: Optional[float] = None,
    n_train: Optional[int] = None,
    n_valid: Optional[int] = None,
    n_test: Optional[int] = None,
) -> Dict[str, Any]:
    enc_hash = _sha256_json(encoding_plan or [])
    feat_hash = _sha256_json(feature_names or [])
    lineage = {
        'schema_version': 1,
        'file_id': int(file_id),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'algorithm': algorithm,
        'processed_file': processed_file,
        'split': split_meta or {},
        'purifier_options': purifier_options,
        'encoding': {
            'use_native': bool(encoding_use_native),
            'plan_hash': enc_hash,
            'plan_len': len(encoding_plan or []),
        },
        'features': {
            'names': list(feature_names or []),
            'count': len(feature_names or []),
            'hash': feat_hash,
            'excluded': list(excluded_variables or []),
        },
        'impute_means': impute_means or {},
        'scale_pos_weight': scale_pos_weight,
        'model_params': model_params or {},
        'metrics': metrics or {},
        'model_path': model_path,
        'row_counts': {
            'train': n_train,
            'valid': n_valid,
            'test': n_test,
        },
        'lineage_id': None,
    }
    lineage['lineage_id'] = _sha256_json({
        'file_id': file_id,
        'enc': enc_hash,
        'feat': feat_hash,
        'split': split_meta or {},
        'algo': algorithm,
    })
    return lineage


def save_lineage(file_id: int, lineage: Dict[str, Any]) -> str:
    out_dir = os.path.join(settings.MEDIA_ROOT, 'lineage')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f'{file_id}_lineage.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(lineage, f, indent=2, default=str)
    return os.path.relpath(path, settings.MEDIA_ROOT)


def load_lineage(file_id: int) -> Optional[Dict[str, Any]]:
    path = os.path.join(settings.MEDIA_ROOT, 'lineage', f'{file_id}_lineage.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None
