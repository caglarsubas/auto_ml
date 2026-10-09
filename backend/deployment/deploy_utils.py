"""Deployment score-bundle helpers for boosting models."""

from __future__ import annotations

import json
import os
import shutil
import uuid
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from django.conf import settings

from encoding.fitted import apply_fitted_encoding
from modeling.execution_artifacts import digest_file, execution_root, projection_lock, replace_projection
from deployment.evidence import current_selection, resolve_handoff, verify_bundle


class DeployNotReadyError(Exception):
    """Raised when model-card readiness blockers prevent score-bundle freeze."""

    def __init__(self, readiness: Dict[str, Any]):
        self.readiness = readiness or {}
        super().__init__(self.readiness.get('summary') or 'Not deploy-ready')


def bundle_dir(file_id: int, bundle_id=None) -> str:
    base = Path(settings.MEDIA_ROOT) / 'deployment_bundles' / str(file_id)
    pointer = base / 'current.json'
    if bundle_id is None and pointer.is_file():
        with pointer.open(encoding='utf-8') as stream:
            bundle_id = json.load(stream)['bundle_id']
    if bundle_id is not None:
        return str(base / 'versions' / str(uuid.UUID(str(bundle_id))))
    return str(base)


def assess_file_deploy_readiness(file_id: int, execution_id=None, assessment_id=None) -> Dict[str, Any]:
    return resolve_handoff(file_id, execution_id, assessment_id)['readiness']


def build_score_bundle(file_id: int, execution_id=None, assessment_id=None) -> Dict[str, Any]:
    """Stage and publish an exact native package; failures cannot publish a version."""
    context = resolve_handoff(file_id, execution_id, assessment_id)
    readiness = context['readiness']
    if not readiness.get('ready'):
        raise DeployNotReadyError(readiness)
    parent = Path(settings.MEDIA_ROOT) / 'deployment_bundles' / str(file_id)
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.staging-', dir=parent) as staged:
        return _build_score_bundle(file_id, context, staged)


def _build_score_bundle(file_id, context, out):
    modeling = context['modeling']
    model = modeling.get('model') or {}
    exact_assessment = context['assessment'] if context['execution_id'] else None
    algo = model.get('algorithm') or (model.get('model_type') or 'xgboost')
    algo = str(algo).replace('_classifier', '').replace('_regressor', '')
    model_rel = model.get('model_path') or f'models/{file_id}_xgb_classifier.json'
    model_abs = os.path.join(settings.MEDIA_ROOT, model_rel) if not os.path.isabs(model_rel) else model_rel
    if not os.path.exists(model_abs):
        raise FileNotFoundError(f'Model artifact missing: {model_rel}')

    train_pkl = os.path.join(settings.MEDIA_ROOT, model.get('train_data_path') or f'train_data/{file_id}_train_data.pkl')
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
        if not modeling.get('execution_id') and os.path.exists(hp_path):
            try:
                with open(hp_path, 'r', encoding='utf-8') as hf:
                    hp = json.load(hf)
                feats = [c for c in (hp.get('features') or []) if c in feature_names]
                if feats:
                    feature_names = feats
            except Exception:
                pass

    lineage = context['lineage']
    bundle_id = str(uuid.uuid4())
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

    if (model.get('calibration') or {}).get('fitted') and not calibrator_file:
        raise ValueError('Required calibrator is missing; package publication is blocked.')

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
        run = None if context['execution_id'] else PipelineRun.objects.filter(file_id=file_id).order_by('-updated_at').first()
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

    contract = model.get('prediction_contract') or {}
    if contract:
        bu = {'problem_type': contract['task'], 'target_contract': contract['target_contract'],
              'population': contract['population'], 'prediction_horizon': contract['prediction_horizon'],
              'success_criteria': contract['objective'], 'forbidden_features': contract['forbidden_features']}
        success_criteria = contract['objective']
    card_abs = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_model_card.json')
    model_card = None
    if exact_assessment:
        model_card = exact_assessment['model_card']
        source = execution_root(context['execution_id'])
        assessment_root = source / 'assessments' / context['assessment_id']
        for name in ('evaluation.json', 'model_card.json'):
            shutil.copyfile(assessment_root / name, Path(out) / name)
        shutil.copyfile(assessment_root / 'manifest.json', Path(out) / 'assessment_manifest.json')
        shutil.copyfile(source / 'manifest.json', Path(out) / 'execution_manifest.json')
        shutil.copyfile(source / 'modeling_status.json', Path(out) / 'modeling_status.json')
    elif os.path.exists(card_abs):
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
    purifier = td.get('purifier_state') if os.path.exists(train_pkl) else None
    if model.get('purifier_path') and not purifier:
        raise ValueError('Required fitted purifier is missing; package publication is blocked.')
    if purifier:
        from preprocessing.replay import subset_purifier
        purifier = subset_purifier(purifier, feature_names, td.get('encoding_report') or [])
        with open(os.path.join(out, 'purifier.json'), 'x', encoding='utf-8') as stream:
            json.dump(purifier, stream, indent=2, allow_nan=False)
    manifest = {
        'schema_version': 4 if purifier else 3,
        'scoring_schema_version': 4 if purifier else 3,
        'bundle_id': bundle_id,
        'handoff_schema_version': 1,
        'execution_id': context['execution_id'],
        'assessment_id': context['assessment_id'],
        'readiness': context['readiness'],
        'prediction_contract': contract,
        'fit_receipt': model.get('fit_receipt'),
        'task': model.get('task') or 'classification',
        'encoding_report': td.get('encoding_report', []) if os.path.exists(train_pkl) else [],
        'input_stage': 'raw_unencoded' if purifier else ('processed_unencoded' if contract else 'legacy_model_features'),
        'purifier_file': 'purifier.json' if purifier else None,
        'purifier_provenance': 'partition_fitted' if purifier else 'legacy_unverified',
        'input_features': purifier['retained_columns'] if purifier else None,
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
        'package_purpose': 'development_review_and_batch_scoring_handoff',
        'production_use_approved': False,
        'evidence_status': context['readiness']['evidence_status'],
        'model_card_path': 'model_card.json' if model_card else None,
        'business_understanding_path': 'business_understanding.json',
        'success_criteria_path': 'success_criteria.json',
        'monitoring_plan_path': 'monitoring_plan.json',
        'monitoring': monitoring_plan,
    }
    with open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    if context['execution_id']:
        shutil.copyfile(Path(settings.MEDIA_ROOT) / model['lineage_path'], Path(out) / 'lineage.json')
    else:
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

    manifest['artifact_integrity'] = {path.name: {'sha256': digest_file(path), 'bytes': path.stat().st_size}
        for path in Path(out).iterdir() if path.is_file() and path.name != 'manifest.json'}
    manifest['immutable_freeze_hash'] = hashlib.sha256(json.dumps(manifest['artifact_integrity'], sort_keys=True).encode()).hexdigest()
    with open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
    publication = {key: manifest[key] for key in ('file_id', 'bundle_id', 'execution_id', 'assessment_id')}
    publication['manifest_sha256'] = digest_file(Path(out) / 'manifest.json')
    (Path(out) / 'publication.json').write_text(json.dumps(publication, indent=2), encoding='utf-8')
    verify_bundle(out, file_id, bundle_id)
    if context['execution_id']:
        # Verify the copied native inputs against the original recorded evidence,
        # including modifications during staging, before any publication.
        from modeling.execution_artifacts import load_execution, load_assessment
        load_execution(context['execution_id'], file_id)
        load_assessment(context['execution_id'], context['assessment_id'], file_id)
        source = execution_root(context['execution_id'])
        for source_path, name in [(Path(model_abs), model_basename),
                (source / 'modeling_status.json', 'modeling_status.json'),
                (source / 'manifest.json', 'execution_manifest.json'),
                (source / 'lineage.json', 'lineage.json')]:
            if digest_file(source_path) != digest_file(Path(out) / name):
                raise ValueError('Native handoff input changed during package staging.')
        if calibrator_file and digest_file(cal_abs) != digest_file(Path(out) / calibrator_file):
            raise ValueError('Calibrator changed during package staging.')
        assessment_root = source / 'assessments' / context['assessment_id']
        for name in ('evaluation.json', 'model_card.json', 'manifest.json'):
            copied = 'assessment_manifest.json' if name == 'manifest.json' else name
            if digest_file(assessment_root / name) != digest_file(Path(out) / copied):
                raise ValueError('Assessment changed during package staging.')
    destination = Path(bundle_dir(file_id, bundle_id))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with projection_lock(file_id):
        adoption = 'adopted'
        if context['execution_id'] and current_selection(file_id) != (context['execution_id'], context['execution_id'], context['assessment_id']):
            adoption = 'version_only_current_changed'
        os.rename(out, destination)
        if adoption == 'adopted':
            replace_projection(destination / 'publication.json', destination.parent.parent / 'current.json')
    return bundle_summary(file_id, bundle_id, adoption)


def bundle_summary(file_id, bundle_id=None, adoption_status=None):
    out = bundle_dir(file_id, bundle_id)
    manifest, digest = verify_bundle(out, file_id, bundle_id)
    return {'status': 'ok', 'file_id': file_id, 'bundle_id': manifest.get('bundle_id'),
            'execution_id': manifest.get('execution_id'), 'assessment_id': manifest.get('assessment_id'),
            'manifest_sha256': digest, 'adoption_status': adoption_status,
            'bundle_path': os.path.relpath(out, settings.MEDIA_ROOT), 'manifest': manifest}


def build_deployment_pack_zip(file_id: int, bundle_id=None) -> tuple:
    """Zip only recorded package files for review and batch scoring handoff."""
    import io
    import zipfile

    out = bundle_dir(file_id, bundle_id)
    manifest, _ = verify_bundle(out, file_id, bundle_id)
    buf = io.BytesIO()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = f'deployment_pack_{file_id}_{stamp}_{uuid.uuid4().hex}.zip'
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        names = set(manifest.get('artifact_integrity') or {}) | {'manifest.json'}
        if not manifest.get('artifact_integrity') and not manifest.get('handoff_schema_version') and not manifest.get('execution_id'):
            # Inspectable historical packages lack a recorded integrity map.
            # Include known sidecars only, and disclose their unverified provenance.
            legacy = [manifest.get('model_file') or 'model.json', manifest.get('calibrator_file'),
                'lineage.json', 'model_card.json', 'business_understanding.json',
                'success_criteria.json', 'monitoring_plan.json', 'train_reference_head.csv']
            names.update(name for name in legacy if name and Path(name).name == name
                and (Path(out) / name).is_file() and not (Path(out) / name).is_symlink())
        if (Path(out) / 'publication.json').is_file():
            names.add('publication.json')
        for filename in sorted(names):
            zf.write(Path(out) / filename, arcname=filename)
        zf.writestr(
            'README.txt',
            f'DeclarAI review and batch scoring pack\nfile_id={file_id}\nbundle_id={manifest.get("bundle_id")}\ngenerated_utc={stamp}\n'
            'Evidence is exploratory or historically unverified; production use is not approved.\n'
            'Includes frozen score bundle, BU, success criteria, model card, monitoring plan.\n',
        )
    return buf.getvalue(), name


def score_frame(file_id: int, df: pd.DataFrame, bundle_id=None) -> Dict[str, Any]:
    """Score a batch DataFrame with the frozen bundle."""
    from modeling.alt_pipelines import load_model_adapter as load_adapter_from_path
    from evaluation.eval_utils import feature_psi_report

    out = bundle_dir(file_id, bundle_id)
    manifest, manifest_digest = verify_bundle(out, file_id, bundle_id)
    if manifest.get('input_stage') == 'raw_unencoded':
        from preprocessing.replay import apply_purifier
        if manifest.get('purifier_file') != 'purifier.json' or 'purifier.json' not in (manifest.get('artifact_integrity') or {}):
            raise ValueError('Required fitted purifier is missing from the scoring bundle.')
        with open(os.path.join(out, 'purifier.json'), encoding='utf-8') as stream:
            df = apply_purifier(df, json.load(stream))
    if manifest.get('input_stage') in ('processed_unencoded', 'raw_unencoded'):
        df = apply_fitted_encoding(df, manifest.get('encoding_report') or [])
    model_file = manifest.get('model_file') or 'model.json'
    model_path = os.path.join(out, model_file)
    if not os.path.exists(model_path):
        # Backward compat with older bundles that always used model.json
        alt = os.path.join(out, 'model.json')
        if not manifest.get('execution_id') and not manifest.get('handoff_schema_version') and os.path.exists(alt):
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
    proba = np.asarray(adapter.predict(X) if manifest.get('task') == 'regression' else adapter.predict_proba(X), dtype=float)
    multiclass = proba.ndim == 2 and proba.shape[1] > 1
    if not multiclass:
        proba = proba.ravel()
    if len(proba) != len(df) or not np.isfinite(proba).all():
        raise ValueError('Scoring output must be finite and preserve row alignment.')
    scores_calibrated = False
    cal_file = manifest.get('calibrator_file')
    if cal_file:
        cal_path = os.path.join(out, cal_file)
        if not os.path.exists(cal_path):
            raise ValueError('Required calibrator is missing from the scoring bundle. Rebuild a complete bundle.')
        try:
            from modeling.calibration_utils import apply_calibrator, load_calibrator
            calibrator = load_calibrator(cal_path)
            proba = apply_calibrator(calibrator, proba)
            scores_calibrated = True
        except Exception as error:
            raise ValueError('Required calibrator could not be applied; uncalibrated scoring is blocked.') from error
    elif (manifest.get('calibration') or {}).get('fitted'):
        raise ValueError('Bundle declares fitted calibration but has no calibrator artifact.')

    monitoring: Dict[str, Any] = {
        'score_mean': float(np.mean(proba)) if len(proba) and not multiclass else None,
        'score_std': float(np.std(proba)) if len(proba) and not multiclass else None,
        'score_p50': float(np.median(proba)) if len(proba) and not multiclass else None,
        'scores_calibrated': scores_calibrated,
    }
    if multiclass:
        monitoring['class_probability_mean'] = np.mean(proba, axis=0).tolist() if len(proba) else []
    # Optional PSI vs train reference snapshot if present in bundle sidecar
    # Also accept a lightweight CSV reference written at bundle time (optional)
    ref_csv = os.path.join(out, 'train_reference_head.csv')
    try:
        if 'train_reference_head.csv' in (manifest.get('artifact_integrity') or {}):
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
        'scores': proba.tolist(),
        'class_mapping': (manifest.get('prediction_contract') or {}).get('class_mapping'),
        'score_semantics': 'class probabilities' if multiclass else ('anomaly ranking; not a probability' if manifest.get('task') == 'anomaly' else manifest.get('task')),
        'bundle_id': manifest.get('bundle_id'),
        'execution_id': manifest.get('execution_id'),
        'assessment_id': manifest.get('assessment_id'),
        'manifest_sha256': manifest_digest,
        'evidence_status': manifest.get('evidence_status', 'legacy_provenance_unverified'),
        'production_use_approved': False,
        'input_stage': manifest.get('input_stage'),
        'scores_calibrated': scores_calibrated,
        'feature_count': len(feature_names),
        'algorithm': manifest.get('algorithm'),
        'lineage_id': manifest.get('lineage_id'),
        'monitoring': monitoring,
    }
