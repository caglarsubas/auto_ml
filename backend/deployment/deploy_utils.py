"""Deployment score-bundle helpers for boosting models."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from django.conf import settings

from modeling.lineage import load_lineage


def bundle_dir(file_id: int) -> str:
    return os.path.join(settings.MEDIA_ROOT, 'deployment_bundles', str(file_id))


def build_score_bundle(file_id: int) -> Dict[str, Any]:
    """Freeze model + feature schema + lineage into a score bundle."""
    modeling_path = os.path.join(settings.MEDIA_ROOT, 'modeling', f'{file_id}_status.json')
    if not os.path.exists(modeling_path):
        raise FileNotFoundError('Modeling status not found. Run modeling first.')

    with open(modeling_path, 'r', encoding='utf-8') as f:
        modeling = json.load(f)
    model = modeling.get('model') or {}
    algo = model.get('algorithm') or (model.get('model_type') or 'xgboost').replace('_classifier', '')
    model_rel = model.get('model_path') or f'models/{file_id}_xgb_classifier.json'
    model_abs = os.path.join(settings.MEDIA_ROOT, model_rel) if not os.path.isabs(model_rel) else model_rel
    if not os.path.exists(model_abs):
        raise FileNotFoundError(f'Model artifact missing: {model_rel}')

    train_pkl = os.path.join(settings.MEDIA_ROOT, 'train_data', f'{file_id}_train_data.pkl')
    feature_names: List[str] = []
    impute_means: Dict[str, float] = {}
    categorical_features: List[str] = list(model.get('categorical_features_used') or [])
    if os.path.exists(train_pkl):
        import pickle
        with open(train_pkl, 'rb') as f:
            td = pickle.load(f)
        feature_names = list(td.get('feature_names') or (td.get('X_train').columns.tolist() if td.get('X_train') is not None else []))
        impute_means = dict(td.get('impute_means') or {})
        algo = td.get('algorithm') or algo
        # Prefer HP / SFS feature subset when available
        hp_path = os.path.join(settings.MEDIA_ROOT, 'hyperparam_results', f'{file_id}_hyperparam.json')
        if os.path.exists(hp_path):
            try:
                with open(hp_path, 'r', encoding='utf-8') as hf:
                    hp = json.load(hf)
                feats = [c for c in (hp.get('features') or []) if c in feature_names]
                if feats:
                    feature_names = feats
            except Exception:
                pass

    lineage = load_lineage(file_id) or {}
    out = bundle_dir(file_id)
    os.makedirs(out, exist_ok=True)
    model_basename = os.path.basename(model_abs)
    bundled_model = os.path.join(out, model_basename)
    shutil.copy2(model_abs, bundled_model)

    calibrator_rel = model.get('calibrator_path')
    calibrator_file = None
    if calibrator_rel:
        cal_abs = (
            os.path.join(settings.MEDIA_ROOT, calibrator_rel)
            if not os.path.isabs(calibrator_rel) else calibrator_rel
        )
        if os.path.exists(cal_abs):
            calibrator_file = os.path.basename(cal_abs)
            shutil.copy2(cal_abs, os.path.join(out, calibrator_file))
        else:
            # Fall back to train_data pointer
            if os.path.exists(train_pkl):
                import pickle
                with open(train_pkl, 'rb') as f:
                    td = pickle.load(f)
                calibrator_rel = td.get('calibrator_path') or calibrator_rel
                if calibrator_rel:
                    cal_abs = (
                        os.path.join(settings.MEDIA_ROOT, calibrator_rel)
                        if not os.path.isabs(calibrator_rel) else calibrator_rel
                    )
                    if os.path.exists(cal_abs):
                        calibrator_file = os.path.basename(cal_abs)
                        shutil.copy2(cal_abs, os.path.join(out, calibrator_file))

    # Categorical level freeze from train raw if possible
    cat_levels: Dict[str, List[str]] = {}
    if os.path.exists(train_pkl):
        import pickle
        with open(train_pkl, 'rb') as f:
            td = pickle.load(f)
        Xtr = td.get('X_train')
        if Xtr is not None:
            for c in categorical_features:
                if c in Xtr.columns and hasattr(Xtr[c], 'cat'):
                    cat_levels[c] = [str(v) for v in Xtr[c].cat.categories.tolist()]

    manifest = {
        'schema_version': 1,
        'file_id': int(file_id),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'algorithm': algo,
        'model_file': model_basename,
        'feature_names': feature_names,
        'categorical_features': categorical_features,
        'categorical_levels': cat_levels,
        'impute_means': impute_means,
        'scale_pos_weight': model.get('scale_pos_weight') or lineage.get('scale_pos_weight'),
        'enable_categorical': bool(model.get('enable_categorical')),
        'calibrator_file': calibrator_file,
        'calibration': model.get('calibration') or {},
        'lineage_id': lineage.get('lineage_id') or model.get('lineage_id'),
        'model_path_source': model_rel,
        'monitoring': {
            'recommended_checks': ['psi_vs_train', 'score_distribution', 'target_rate_if_labeled'],
            'psi_bands': {'stable': '<0.10', 'moderate': '0.10-0.25', 'shift': '>0.25'},
        },
    }
    with open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    if lineage:
        with open(os.path.join(out, 'lineage.json'), 'w', encoding='utf-8') as f:
            json.dump(lineage, f, indent=2, default=str)

    # Small train reference for batch-score PSI monitoring (head sample)
    try:
        if os.path.exists(train_pkl):
            import pickle
            with open(train_pkl, 'rb') as f:
                td = pickle.load(f)
            Xtr = td.get('X_train')
            if Xtr is not None and feature_names:
                cols = [c for c in feature_names if c in Xtr.columns]
                if cols:
                    Xtr[cols].head(500).to_csv(
                        os.path.join(out, 'train_reference_head.csv'), index=False,
                    )
    except Exception:
        pass

    return {
        'status': 'ok',
        'file_id': file_id,
        'bundle_path': os.path.relpath(out, settings.MEDIA_ROOT),
        'manifest': manifest,
    }


def score_frame(file_id: int, df: pd.DataFrame) -> Dict[str, Any]:
    """Score a batch DataFrame with the frozen bundle."""
    from modeling.booster_adapters import load_adapter_from_path
    from evaluation.eval_utils import feature_psi_report

    out = bundle_dir(file_id)
    manifest_path = os.path.join(out, 'manifest.json')
    if not os.path.exists(manifest_path):
        raise FileNotFoundError('Deployment bundle not found. Create the bundle first.')

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    model_file = manifest.get('model_file') or 'model.json'
    model_path = os.path.join(out, model_file)
    if not os.path.exists(model_path):
        # Backward compat with older bundles that always used model.json
        alt = os.path.join(out, 'model.json')
        if os.path.exists(alt):
            model_path = alt
        else:
            raise FileNotFoundError('Deployment model artifact missing from bundle.')

    feature_names = list(manifest.get('feature_names') or [])
    missing = [c for c in feature_names if c not in df.columns]
    if missing:
        raise ValueError(f'Missing required features: {missing[:20]}' + ('…' if len(missing) > 20 else ''))

    X = df[feature_names].copy()
    impute_means = manifest.get('impute_means') or {}
    for c, m in impute_means.items():
        if c in X.columns and pd.api.types.is_numeric_dtype(X[c]):
            X[c] = X[c].fillna(m)

    cat_feats = set(manifest.get('categorical_features') or [])
    cat_levels = manifest.get('categorical_levels') or {}
    for c in cat_feats:
        if c not in X.columns:
            continue
        levels = cat_levels.get(c)
        if levels:
            X[c] = pd.Categorical(X[c].astype(str), categories=levels)
        else:
            X[c] = X[c].astype('category')

    adapter = load_adapter_from_path(
        model_path,
        algorithm=manifest.get('algorithm') or 'xgboost',
        feature_names=feature_names,
        cat_features=list(cat_feats),
    )
    proba = np.asarray(adapter.predict_proba(X), dtype=float).ravel()
    scores_calibrated = False
    cal_file = manifest.get('calibrator_file')
    if cal_file:
        cal_path = os.path.join(out, cal_file)
        if os.path.exists(cal_path):
            try:
                from modeling.calibration_utils import apply_calibrator, load_calibrator
                calibrator = load_calibrator(cal_path)
                proba = apply_calibrator(calibrator, proba)
                scores_calibrated = True
            except Exception:
                scores_calibrated = False

    monitoring: Dict[str, Any] = {
        'score_mean': float(np.mean(proba)) if len(proba) else None,
        'score_std': float(np.std(proba)) if len(proba) else None,
        'score_p50': float(np.median(proba)) if len(proba) else None,
        'scores_calibrated': scores_calibrated,
    }
    # Optional PSI vs train reference snapshot if present in bundle sidecar
    ref_path = os.path.join(out, 'train_reference.parquet')
    # Also accept a lightweight CSV reference written at bundle time (optional)
    ref_csv = os.path.join(out, 'train_reference_head.csv')
    try:
        if os.path.exists(ref_csv):
            ref = pd.read_csv(ref_csv)
            common = [c for c in feature_names if c in ref.columns and c in X.columns]
            if common:
                monitoring['psi_vs_train_ref'] = feature_psi_report(ref[common], X[common], top_n=15)
    except Exception as mon_err:
        monitoring['psi_error'] = str(mon_err)

    return {
        'status': 'ok',
        'file_id': file_id,
        'n_scored': int(len(proba)),
        'scores': [float(x) for x in proba],
        'scores_calibrated': scores_calibrated,
        'feature_count': len(feature_names),
        'algorithm': manifest.get('algorithm'),
        'lineage_id': manifest.get('lineage_id'),
        'monitoring': monitoring,
    }
