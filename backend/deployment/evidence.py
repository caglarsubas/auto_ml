"""Exact native handoff evidence and package integrity (not storage signatures)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from evaluation.eval_utils import assess_deploy_readiness
from modeling.execution_artifacts import digest_file, execution_root, load_assessment, load_execution, projection_lock
from modeling.lineage import load_lineage


EXACT_SCORING_SCHEMA = 5


def read_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


def parse_metadata(raw):
    """Keep the JSON decoder's nesting ceiling inside the invalid-input boundary."""
    try:
        return json.loads(raw)
    except RecursionError:
        raise ValueError('Package metadata nesting is unsupported.') from None


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


def _verify_exact_scoring(out, manifest, files, metadata_bytes):
    """Check that frozen scoring state agrees with the copied execution and assessment."""
    from encoding.fitted import scoring_encoding_reports
    from modeling.prediction_contract import contract_business_understanding, frozen_prediction_task
    from preprocessing.replay import subset_purifier

    def evidence(name):
        path = out / name
        recorded = files.get(name) or {}
        raw = metadata_bytes(path) if metadata_bytes else path.read_bytes()
        if len(raw) != recorded.get('bytes') or hashlib.sha256(raw).hexdigest() != recorded.get('sha256'):
            raise ValueError(f'Scoring evidence changed during verification: {name}')
        value = parse_metadata(raw)
        if not isinstance(value, dict):
            raise ValueError(f'Scoring evidence must be an object: {name}')
        return value

    execution_id = manifest.get('execution_id')
    execution = evidence('execution_manifest.json')
    lineage = evidence('lineage.json')
    assessment = evidence('assessment_manifest.json')
    evaluation = evidence('evaluation.json').get('evaluation') or {}
    identity = (manifest['file_id'], execution_id)
    if (not execution_id or (execution.get('file_id'), execution.get('execution_id')) != identity
            or (assessment.get('file_id'), assessment.get('execution_id')) != identity
            or (assessment.get('assessment_id'), evaluation.get('holdout_access_id'), evaluation.get('execution_id'))
            != (manifest.get('assessment_id'), manifest.get('assessment_id'), execution_id)):
        raise ValueError('Scoring identity disagrees with the copied execution or assessment.')
    source_files = execution.get('files') or {}
    for name in ('lineage.json', 'modeling_status.json'):
        if files.get(name) != source_files.get(name):
            raise ValueError(f'Scoring evidence differs from the exact execution: {name}')
    for name in ('evaluation.json', 'model_card.json'):
        if files.get(name) != (assessment.get('files') or {}).get(name):
            raise ValueError(f'Scoring evidence differs from the exact assessment: {name}')

    def native_file(name, source):
        source_root = Path('execution_runs') / execution_id
        if (not isinstance(source, str) or not Path(source).is_relative_to(source_root)
                or files.get(name) != source_files.get(Path(source).relative_to(source_root).as_posix())):
            raise ValueError('Scoring native asset differs from the exact execution.')

    native_file(manifest.get('model_file'), lineage.get('model_path'))
    contract = lineage.get('prediction_contract') or {}
    fit = lineage.get('fit_receipt') or {}
    frozen_prediction_task(contract, manifest.get('task'), evaluation.get('task'), fit.get('task'))
    if evaluation.get('prediction_contract', contract) != contract:
        raise ValueError('Scoring assessment disagrees with the frozen prediction contract.')
    features = manifest.get('feature_names')
    if (not isinstance(features, list) or not features or any(not isinstance(name, str) for name in features)
            or len(set(features)) != len(features) or features != (lineage.get('features') or {}).get('names')
            or not contract or manifest.get('prediction_contract') != contract
            or execution.get('prediction_contract_sha256') != contract.get('sha256')
            or manifest.get('task') != contract.get('task') or not fit or manifest.get('fit_receipt') != fit
            or features != (fit.get('train') or {}).get('features')):
        raise ValueError('Scoring feature order, model or task disagrees with the fitted execution.')
    if manifest.get('algorithm') != fit.get('algorithm'):
        raise ValueError('Scoring algorithm disagrees with the registered native fit.')
    reports = scoring_encoding_reports(lineage.get('encoding_report') or [], features=features)
    impute = {key: mean for key, mean in (lineage.get('impute_means') or {}).items() if key in features}
    if manifest.get('encoding_report') != reports or manifest.get('impute_means') != impute:
        raise ValueError('Required fitted encoding or imputation differs from the recorded execution.')
    cats = [name for name, dtype in zip(features, fit['train']['dtypes'], strict=True) if dtype == 'category']
    levels = manifest.get('categorical_levels')
    if manifest.get('categorical_features') != cats or not isinstance(levels, dict) or set(levels) != set(cats):
        raise ValueError('Required native category inventories differ from the fitted feature schema.')
    for report in reports:
        spec = report.get('mapping') or {}
        if (spec.get('type') or report.get('strategy')) == 'native_categorical':
            name = report['feature']
            if not isinstance(levels.get(name), list) or list(map(str, levels[name])) != spec.get('categories', report.get('categories')):
                raise ValueError(f'Required native category inventory differs from the fitted encoder: {name}')

    purifier = lineage.get('purifier')
    if purifier:
        expected = subset_purifier(purifier, features, reports)
        if (manifest.get('input_stage') != 'raw_unencoded' or manifest.get('purifier_file') != 'purifier.json'
                or manifest.get('input_features') != expected['retained_columns']
                or evidence('purifier.json') != expected):
            raise ValueError('Required fitted purifier differs from the recorded execution.')
    elif manifest.get('input_stage') != 'processed_unencoded' or manifest.get('purifier_file'):
        raise ValueError('Scoring input stage disagrees with the recorded execution.')
    input_columns = set(manifest['input_features'] if purifier else features).union(report['feature'] for report in reports)
    if contract.get('schema_version') == 2 and (
            evidence('business_understanding.json') != contract_business_understanding(contract)
            or input_columns.intersection([contract['target_column'], *contract['forbidden_features']])):
        raise ValueError('Scoring inputs or published declaration disagree with the frozen prediction scope.')
    text_columns = manifest.get('input_text_columns')
    numeric = manifest.get('input_numeric_kinds')
    if (not isinstance(text_columns, list) or any(not isinstance(name, str) for name in text_columns)
            or text_columns != sorted(set(text_columns)) or not set(text_columns).issubset(input_columns)
            or not isinstance(numeric, dict) or not set(numeric).issubset(input_columns - set(text_columns))
            or any(kind not in ('integer', 'float') for kind in numeric.values())):
        raise ValueError('Required scoring input types are missing or invalid.')

    applied = evaluation.get('scores_calibrated')
    cal_file = manifest.get('calibrator_file')
    if applied is not bool((manifest.get('calibration') or {}).get('fitted')) or applied is not bool(cal_file):
        raise ValueError('Required fitted calibration differs from the exact assessment.')
    if applied:
        native_file(cal_file, (evaluation.get('calibration') or {}).get('calibrator_path'))


def verify_bundle(out, file_id, bundle_id=None, *, artifact_digest=digest_file, metadata_bytes=None):
    out = Path(out)
    manifest_path = out / 'manifest.json'
    if not manifest_path.is_file():
        raise FileNotFoundError('Deployment bundle not found. Create the bundle first.')
    # Native jobs supply bounded, regular-file capture. Default/offline callers
    # keep their existing reader; integrity does not provide filesystem custody.
    raw_manifest = metadata_bytes(manifest_path) if metadata_bytes else None
    manifest = parse_metadata(raw_manifest.decode('utf-8')) if raw_manifest is not None else read_json(manifest_path)

    def manifest_digest():
        if raw_manifest is None:
            return digest_file(manifest_path)
        if metadata_bytes(manifest_path) != raw_manifest:
            raise ValueError('Package manifest changed during verification.')
        return hashlib.sha256(raw_manifest).hexdigest()

    if not isinstance(manifest, dict):
        raise ValueError('Package manifest must be an object.')
    selected_id = bundle_id or (out.name if out.parent.name == 'versions' else None)
    if manifest.get('file_id') != file_id or (selected_id and manifest.get('bundle_id') != str(selected_id)):
        raise ValueError('Scoring bundle identity does not match the requested dataset/version.')
    publication = (parse_metadata(metadata_bytes(out / 'publication.json').decode('utf-8'))
                   if metadata_bytes else read_json(out / 'publication.json', {}))
    if not isinstance(publication, dict):
        raise ValueError('Package publication receipt must be an object.')
    handoff = manifest.get('handoff_schema_version')
    if handoff or publication.get('manifest_sha256'):
        identity = {key: manifest.get(key) for key in ('file_id', 'bundle_id', 'execution_id', 'assessment_id')}
        if handoff != 1 or any(publication.get(key) != value for key, value in identity.items()) or publication.get('manifest_sha256') != manifest_digest():
            raise ValueError('Package manifest does not match its publication receipt.')
    files = manifest.get('artifact_integrity') or {}
    if not isinstance(files, dict):
        raise ValueError('Package artifact integrity must be an object.')
    for name, recorded in files.items():
        if not isinstance(name, str) or not isinstance(recorded, dict):
            raise ValueError('Package integrity contains a malformed entry.')
        path = out / name
        if Path(name).name != name or path.is_symlink() or not path.is_file() or artifact_digest(path) != recorded.get('sha256') or path.stat().st_size != recorded.get('bytes'):
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
    if manifest.get('scoring_schema_version') == EXACT_SCORING_SCHEMA:
        _verify_exact_scoring(out, manifest, files, metadata_bytes)
    return manifest, manifest_digest()
