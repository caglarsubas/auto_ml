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
from evaluation.eval_utils import assess_deploy_readiness


class DeployNotReadyError(Exception):
    """Raised when model-card readiness blockers prevent score-bundle freeze."""

    def __init__(self, readiness: Dict[str, Any]):
        self.readiness = readiness or {}
        super().__init__(self.readiness.get('summary') or 'Not deploy-ready')


def bundle_dir(file_id: int) -> str:
    return os.path.join(settings.MEDIA_ROOT, 'deployment_bundles', str(file_id))


def assess_file_deploy_readiness(file_id: int) -> Dict[str, Any]:
    """Load evaluation / modeling / lineage artifacts and assess deploy readiness."""
    modeling_path = os.path.join(settings.MEDIA_ROOT, 'modeling', f'{file_id}_status.json')
    modeling: Dict[str, Any] = {}
    if os.path.exists(modeling_path):
        with open(modeling_path, 'r', encoding='utf-8') as f:
            modeling = json.load(f)

    eval_path = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_evaluation.json')
    evaluation: Optional[Dict[str, Any]] = None
    evaluation_present = False
    if os.path.exists(eval_path):
        with open(eval_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        # EvaluationRunView persists { evaluation, model_card, ... }
        if isinstance(raw.get('evaluation'), dict):
            evaluation = raw['evaluation']
        else:
            evaluation = raw
        evaluation_present = True

    card_path = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_model_card.json')
    if evaluation is None and os.path.exists(card_path):
        with open(card_path, 'r', encoding='utf-8') as f:
            card = json.load(f)
        evaluation = {
            'task': card.get('task'),
            'metrics': (card.get('sections') or {}).get('evaluation_outer_test') or {},
            'leakage_scan': (card.get('sections') or {}).get('leakage_scan'),
            'scores_calibrated': ((card.get('sections') or {}).get('deployment_readiness') or {}).get('scores_calibrated'),
            'calibration': ((card.get('sections') or {}).get('modeling') or {}).get('calibration'),
        }
        evaluation_present = bool(evaluation.get('metrics'))

    lineage = load_lineage(file_id) or {}
    return assess_deploy_readiness(
        evaluation,
        lineage,
        modeling,
        evaluation_present=evaluation_present,
    )


def build_score_bundle(file_id: int) -> Dict[str, Any]:
    """Freeze model + feature schema + lineage into a score bundle."""
    readiness = assess_file_deploy_readiness(file_id)
    if not readiness.get('ready'):
        raise DeployNotReadyError(readiness)

    modeling_path = os.path.join(settings.MEDIA_ROOT, 'modeling', f'{file_id}_status.json')
    if not os.path.exists(modeling_path):
        raise FileNotFoundError('Modeling status not found. Run modeling first.')

    with open(modeling_path, 'r', encoding='utf-8') as f:
        modeling = json.load(f)
    model = modeling.get('model') or {}
    algo = model.get('algorithm') or (model.get('model_type') or 'xgboost')
    algo = str(algo).replace('_classifier', '').replace('_regressor', '')
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

    # Pull BU / success criteria / model card / monitoring plan from pipeline + evaluation
    bu = {}
    success_criteria = {}
    monitoring_plan = {
        'recommended_checks': ['psi_vs_train', 'score_distribution', 'target_rate_if_labeled'],
        'psi_bands': {'stable': '<0.10', 'moderate': '0.10-0.25', 'shift': '>0.25'},
        'schema_version': 1,
    }
    try:
        from modeling.models import PipelineRun
        from modeling.crisp_dm import merge_crisp_dm, normalize_business_understanding
        run = PipelineRun.objects.filter(file_id=file_id).order_by('-updated_at').first()
        if run is not None:
            crisp = merge_crisp_dm((run.state or {}).get('crisp_dm'), {
                'business_understanding': (run.state or {}).get('business_understanding'),
            })
            bu = crisp.get('business_understanding') or {}
            success_criteria = (bu.get('success_criteria') or {})
            monitoring_plan['iteration_id'] = crisp.get('iteration_id')
    except Exception:
        from modeling.crisp_dm import empty_business_understanding
        bu = empty_business_understanding()

    card_abs = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_model_card.json')
    model_card = None
    if os.path.exists(card_abs):
        try:
            with open(card_abs, 'r', encoding='utf-8') as f:
                model_card = json.load(f)
            shutil.copy2(card_abs, os.path.join(out, 'model_card.json'))
        except Exception:
            model_card = None

    with open(os.path.join(out, 'business_understanding.json'), 'w', encoding='utf-8') as f:
        json.dump(bu, f, indent=2, default=str)
    with open(os.path.join(out, 'success_criteria.json'), 'w', encoding='utf-8') as f:
        json.dump(success_criteria, f, indent=2, default=str)
    with open(os.path.join(out, 'monitoring_plan.json'), 'w', encoding='utf-8') as f:
        json.dump(monitoring_plan, f, indent=2, default=str)

    freeze_stamp = datetime.now(timezone.utc).isoformat()
    lineage_hash = (lineage or {}).get('lineage_id') or model.get('lineage_id')
    manifest = {
        'schema_version': 2,
        'scoring_schema_version': 2,
        'file_id': int(file_id),
        'created_at': freeze_stamp,
        'immutable_freeze_at': freeze_stamp,
        'immutable_freeze_hash': lineage_hash,
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
        'lineage_id': lineage_hash,
        'model_path_source': model_rel,
        'deploy_ready': True,
        'model_card_path': 'model_card.json' if model_card else None,
        'business_understanding_path': 'business_understanding.json',
        'success_criteria_path': 'success_criteria.json',
        'monitoring_plan_path': 'monitoring_plan.json',
        'monitoring': monitoring_plan,
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


def build_deployment_pack_zip(file_id: int) -> tuple:
    """Zip the frozen score bundle directory for regulatory handoff."""
    import io
    import zipfile

    out = bundle_dir(file_id)
    if not os.path.isdir(out) or not os.path.exists(os.path.join(out, 'manifest.json')):
        raise FileNotFoundError('Deployment bundle not found. Create the bundle first.')
    buf = io.BytesIO()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = f'deployment_pack_{file_id}_{stamp}.zip'
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(out):
            for fn in files:
                abs_path = os.path.join(root, fn)
                arc = os.path.relpath(abs_path, out)
                zf.write(abs_path, arcname=arc)
        zf.writestr(
            'README.txt',
            f'DeclarAI deployment pack\nfile_id={file_id}\ngenerated_utc={stamp}\n'
            'Includes frozen score bundle, BU, success criteria, model card, monitoring plan.\n',
        )
    return buf.getvalue(), name


def score_frame(file_id: int, df: pd.DataFrame) -> Dict[str, Any]:
    """Score a batch DataFrame with the frozen bundle."""
    from modeling.alt_pipelines import load_model_adapter as load_adapter_from_path
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
