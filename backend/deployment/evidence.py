"""Exact native handoff evidence and package integrity (not storage signatures)."""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from evaluation.eval_utils import assess_deploy_readiness
from modeling.execution_artifacts import digest_file, execution_root, load_assessment, load_execution, projection_lock
from modeling.lineage import load_lineage


def read_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


def current_selection(file_id):
    root = Path(settings.MEDIA_ROOT)
    try:
        modeling = read_json(root / 'modeling' / f'{file_id}_status.json', {})
        assessment = read_json(root / 'evaluation' / f'{file_id}_evaluation.json', {})
        evaluation = assessment.get('evaluation') or {}
        return modeling.get('execution_id'), evaluation.get('execution_id'), evaluation.get('holdout_access_id')
    except (OSError, ValueError, TypeError, AttributeError):
        # Exact historical publication remains possible; corrupt compatibility
        # projections cannot confer authority to adopt it as current.
        return None, None, None


def execution_artifact(execution_id, manifest, relative):
    """Require an exact recorded native input before loading/copying it."""
    root = execution_root(execution_id).resolve()
    path = (Path(settings.MEDIA_ROOT) / str(relative)).resolve()
    if not path.is_relative_to(root) or path.relative_to(root).as_posix() not in manifest['files']:
        raise ValueError('Required handoff artifact is outside the verified execution manifest.')
    return path


def resolve_handoff(file_id, execution_id=None, assessment_id=None):
    explicit = bool(execution_id)
    if bool(execution_id) != bool(assessment_id):
        raise ValueError('Select execution_id and assessment_id together.')
    root = Path(settings.MEDIA_ROOT)
    projected, selected = {}, {}
    if not explicit:
        with projection_lock(file_id):
            projected = read_json(root / 'modeling' / f'{file_id}_status.json', {})
            selected = read_json(root / 'evaluation' / f'{file_id}_evaluation.json', {})
    if not execution_id:
        execution_id = projected.get('execution_id')
        evaluation = selected.get('evaluation') or {}
        if execution_id and evaluation and evaluation.get('execution_id') != execution_id:
            raise ValueError('Final assessment belongs to a different execution. Evaluate this exact version before packaging.')
        assessment_id = evaluation.get('holdout_access_id') if execution_id else None
    manifest = None
    if execution_id:
        modeling, manifest = load_execution(execution_id, file_id)
        execution_artifact(execution_id, manifest, str(execution_root(execution_id) / 'modeling_status.json'))
        model = modeling['model']
        if any(not model.get(key) for key in ('model_path', 'train_data_path', 'lineage_path')):
            raise ValueError('Required native handoff paths are missing from the execution.')
        for key in ('model_path', 'train_data_path', 'lineage_path', 'calibrator_path', 'purifier_path'):
            if model.get(key):
                execution_artifact(execution_id, manifest, model[key])
        # An implicit request must not silently repair a modified model projection.
        if not explicit and projected.get('execution_id') == execution_id and projected.get('model', {}).get('model_path') != model.get('model_path'):
            raise ValueError('Model changed since its execution snapshot. Create a new version before packaging.')
        lineage = read_json(root / model['lineage_path'], {})
        assessment = load_assessment(execution_id, assessment_id, file_id) if assessment_id else {}
        evaluation = assessment.get('evaluation')
        if evaluation and (evaluation.get('execution_id'), evaluation.get('holdout_access_id')) != (execution_id, assessment_id):
            raise ValueError('Assessment payload does not match the selected execution/assessment.')
    else:
        modeling, assessment = projected, selected
        evaluation = selected.get('evaluation') or selected or None
        lineage = load_lineage(file_id) or {}
        if not evaluation:
            card = read_json(root / 'evaluation' / f'{file_id}_model_card.json', {})
            sections = card.get('sections') or {}
            if sections.get('evaluation_outer_test'):
                evaluation = {'task': card.get('task'), 'metrics': sections['evaluation_outer_test'],
                    'leakage_scan': sections.get('leakage_scan'),
                    'scores_calibrated': (sections.get('deployment_readiness') or {}).get('scores_calibrated')}
    readiness = assess_deploy_readiness(evaluation, lineage, modeling, evaluation_present=bool(evaluation))
    readiness.update(execution_id=execution_id, assessment_id=assessment_id,
        evidence_status='exploratory' if execution_id else 'legacy_provenance_unverified',
        production_use_approved=False)
    if readiness['ready']:
        readiness['summary'] = 'Package checks passed. Independent review and production-use approval remain separate.'
    return {'modeling': modeling, 'assessment': assessment, 'lineage': lineage,
            'execution_manifest': manifest, 'readiness': readiness,
            'execution_id': execution_id, 'assessment_id': assessment_id}


def verify_bundle(out, file_id, bundle_id=None):
    out = Path(out)
    manifest_path = out / 'manifest.json'
    if not manifest_path.is_file():
        raise FileNotFoundError('Deployment bundle not found. Create the bundle first.')
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError('Package manifest must be an object.')
    selected_id = bundle_id or (out.name if out.parent.name == 'versions' else None)
    if manifest.get('file_id') != file_id or (selected_id and manifest.get('bundle_id') != str(selected_id)):
        raise ValueError('Scoring bundle identity does not match the requested dataset/version.')
    publication = read_json(out / 'publication.json', {})
    if not isinstance(publication, dict):
        raise ValueError('Package publication receipt must be an object.')
    handoff = manifest.get('handoff_schema_version')
    if handoff or publication.get('manifest_sha256'):
        identity = {key: manifest.get(key) for key in ('file_id', 'bundle_id', 'execution_id', 'assessment_id')}
        if handoff != 1 or any(publication.get(key) != value for key, value in identity.items()) or publication.get('manifest_sha256') != digest_file(manifest_path):
            raise ValueError('Package manifest does not match its publication receipt.')
    files = manifest.get('artifact_integrity') or {}
    if not isinstance(files, dict):
        raise ValueError('Package artifact integrity must be an object.')
    for name, recorded in files.items():
        if not isinstance(name, str) or not isinstance(recorded, dict):
            raise ValueError('Package integrity contains a malformed entry.')
        path = out / name
        if Path(name).name != name or path.is_symlink() or not path.is_file() or digest_file(path) != recorded.get('sha256') or path.stat().st_size != recorded.get('bytes'):
            raise ValueError(f'Scoring artifact failed integrity verification: {name}')
    # Current and earlier governed schemas cannot select unverified native state.
    if handoff or int(manifest.get('schema_version') or 0) >= 3:
        required = [manifest.get('model_file')]
        if manifest.get('calibrator_file') or (manifest.get('calibration') or {}).get('fitted'):
            required.append(manifest.get('calibrator_file'))
        if manifest.get('input_stage') == 'raw_unencoded':
            required.append(manifest.get('purifier_file'))
        if handoff:
            required += ['lineage.json', 'business_understanding.json', 'success_criteria.json', 'monitoring_plan.json']
            if manifest.get('execution_id'):
                required += ['modeling_status.json', 'execution_manifest.json', 'assessment_manifest.json', 'evaluation.json', 'model_card.json']
        if any(not isinstance(name, str) or name not in files for name in required):
            raise ValueError('Required scoring/evidence artifact is missing from the verified manifest.')
    for key in ('model_file', 'calibrator_file', 'purifier_file'):
        name = manifest.get(key)
        if name and (not isinstance(name, str) or Path(name).name != name or (out / name).is_symlink()):
            raise ValueError('Scoring manifest contains an invalid artifact path.')
    manifest_digest = digest_file(manifest_path)
    return manifest, manifest_digest
