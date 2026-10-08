"""Additive immutable execution packages; legacy file-ID paths are projections.

Hashes detect corruption relative to the recorded manifest. They are not a
signature or an authorization mechanism; storage permissions remain essential.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import uuid
import fcntl
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from django.conf import settings


def digest_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def execution_root(execution_id):
    execution_id = str(uuid.UUID(str(execution_id)))
    return Path(settings.MEDIA_ROOT) / 'execution_runs' / execution_id


def begin_execution(source):
    execution_id = str(uuid.uuid4())
    root = execution_root(execution_id)
    root.mkdir(parents=True, exist_ok=False)
    snapshot = root / ('dataset' + Path(source).suffix.lower())
    shutil.copyfile(source, snapshot)
    return execution_id, root, snapshot


def publish_execution(execution_id, payload):
    root = execution_root(execution_id)
    status_path = root / 'modeling_status.json'
    with status_path.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, allow_nan=False, indent=2)
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {'sha256': digest_file(path), 'bytes': path.stat().st_size}
    manifest = {
        'schema_version': 1, 'execution_id': execution_id,
        'file_id': payload['file_id'], 'files': files,
        'python_version': platform.python_version(),
        'prediction_contract_sha256': (payload.get('model', {}).get('prediction_contract') or {}).get('sha256'),
        'historical_provenance': 'partition-fitted purifier replay; exploratory evidence' if payload.get('model', {}).get('purifier_path') else 'legacy upstream preprocessing provenance unverified',
    }
    manifest['packages'] = {}
    for package in ('Django', 'djangorestframework', 'pandas', 'numpy', 'scikit-learn', 'xgboost', 'lightgbm', 'catboost', 'joblib'):
        try:
            manifest['packages'][package] = version(package)
        except PackageNotFoundError:
            manifest['packages'][package] = None
    with (root / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
    return manifest


def load_execution(execution_id, file_id):
    root = execution_root(execution_id)
    with (root / 'manifest.json').open(encoding='utf-8') as stream:
        manifest = json.load(stream)
    if manifest.get('execution_id') != str(execution_id) or manifest.get('file_id') != file_id:
        raise ValueError('Execution identity does not match the selected dataset.')
    for relative, expected in manifest['files'].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('Execution manifest contains an invalid or missing artifact.')
        if digest_file(path) != expected['sha256'] or path.stat().st_size != expected['bytes']:
            raise ValueError(f'Execution artifact failed integrity verification: {relative}')
    with (root / 'modeling_status.json').open(encoding='utf-8') as stream:
        return json.load(stream), manifest


def replace_projection(source, destination):
    """Publish a complete compatibility file atomically, preserving run originals."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_name(destination.name + '.' + str(uuid.uuid4()) + '.tmp')
    try:
        shutil.copyfile(source, staged)
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)


def publish_assessment(execution_id, receipt_id, payload, card):
    """Append an independently verified assessment without changing a run."""
    load_execution(execution_id, payload['file_id'])
    root = execution_root(execution_id) / 'assessments' / str(uuid.UUID(str(receipt_id)))
    root.mkdir(parents=True, exist_ok=False)
    payload['evaluation_path'] = str((root / 'evaluation.json').relative_to(settings.MEDIA_ROOT))
    payload['model_card_path'] = str((root / 'model_card.json').relative_to(settings.MEDIA_ROOT))
    for name, value in [('evaluation.json', payload), ('model_card.json', card)]:
        with (root / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, default=str, allow_nan=False)
    manifest = {'execution_id': execution_id, 'assessment_id': str(receipt_id),
                'file_id': payload['file_id'], 'files': {
                    name: {'sha256': digest_file(root / name), 'bytes': (root / name).stat().st_size}
                    for name in ('evaluation.json', 'model_card.json')}}
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return root


def load_assessment(execution_id, assessment_id, file_id):
    root = execution_root(execution_id) / 'assessments' / str(uuid.UUID(str(assessment_id)))
    with (root / 'manifest.json').open(encoding='utf-8') as stream:
        manifest = json.load(stream)
    if (manifest.get('execution_id'), manifest.get('assessment_id'), manifest.get('file_id')) != (str(execution_id), str(assessment_id), int(file_id)):
        raise ValueError('Assessment identity does not match the requested execution.')
    for name in ('evaluation.json', 'model_card.json'):
        recorded = manifest['files'][name]
        if digest_file(root / name) != recorded['sha256'] or (root / name).stat().st_size != recorded['bytes']:
            raise ValueError(f'Assessment artifact failed integrity verification: {name}')
    with (root / 'evaluation.json').open(encoding='utf-8') as stream:
        return json.load(stream)


@contextmanager
def projection_lock(file_id):
    directory = Path(settings.MEDIA_ROOT) / 'projection_locks'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f'{int(file_id)}.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def load_development_data(file_id, execution_id=None):
    import pickle
    status_path = Path(settings.MEDIA_ROOT) / 'modeling' / f'{file_id}_status.json'
    if execution_id is None and status_path.exists():
        with status_path.open(encoding='utf-8') as stream:
            execution_id = json.load(stream).get('execution_id')
    if execution_id:
        payload, _ = load_execution(execution_id, int(file_id))
        relative = payload['model']['train_data_path']
    else:
        relative = f'train_data/{file_id}_train_data.pkl'
    with (Path(settings.MEDIA_ROOT) / relative).open('rb') as stream:
        return pickle.load(stream)


def publish_candidate(parent_id, file_id, adapter, features, params, source, adopt=True):
    """Publish a trusted native-model candidate without opening final outcomes.

    Expert models must use the separate isolation service; this native adapter
    path is never allowed to import expert code or deserialize expert state.
    """
    import pickle
    from modeling.calibration_utils import fit_calibrator, save_calibrator
    from modeling.lineage import build_lineage
    parent, manifest = load_execution(parent_id, file_id)
    parent_root = execution_root(parent_id)
    dataset_name = next(name for name in manifest['files'] if name.startswith('dataset.'))
    execution_id, root, _ = begin_execution(parent_root / dataset_name)
    for name in ('raw_input.csv', 'purifier_recipe.json', 'purifier.json'):
        if name in manifest['files']:
            shutil.copyfile(parent_root / name, root / name)
    with open(Path(settings.MEDIA_ROOT) / parent['model']['train_data_path'], 'rb') as stream:
        data = pickle.load(stream)
    for name in ('X_train', 'X_valid', 'X_train_raw', 'X_valid_raw'):
        if name in data:
            data[name] = data[name].loc[:, features]
    data['feature_names'] = list(features)
    data['execution_id'] = execution_id
    data['impute_means'] = {key: value for key, value in data.get('impute_means', {}).items() if key in features}
    data['encoding_report'] = [report for report in data.get('encoding_report', [])
        if report['feature'] in features or set((report.get('mapping') or {}).get('columns') or []).intersection(features)]
    shutil.copyfile(Path(settings.MEDIA_ROOT) / data['holdout_path'], root / 'final_holdout.pkl')
    data['holdout_path'] = str((root / 'final_holdout.pkl').relative_to(Path(settings.MEDIA_ROOT)))
    model_path = root / 'models' / adapter.model_filename(file_id)
    adapter.save(str(model_path))
    model = dict(parent['model'])
    calibration = {'fitted': False}
    calibrator_path = None
    if model.get('task') == 'classification' and len(data['prediction_contract']['class_mapping']) == 2:
        calibrator, calibration = fit_calibrator(data['y_valid'], adapter.predict_proba(data['X_valid']))
        if calibrator is not None:
            calibrator_path = save_calibrator(file_id, calibrator, str(root))
            calibrator_path = str((root / calibrator_path).relative_to(Path(settings.MEDIA_ROOT)))
    data['calibration'], data['calibrator_path'] = calibration, calibrator_path
    data['algorithm'] = adapter.name if adapter.name != 'sklearn' else adapter.algorithm
    from evaluation.eval_utils import evaluate_binary, evaluate_multiclass, evaluate_regression
    if model.get('task') == 'regression':
        validation_metrics = evaluate_regression(data['y_valid'], adapter.predict(data['X_valid']))['metrics']
    elif len(data['prediction_contract']['class_mapping']) > 2:
        validation_metrics = evaluate_multiclass(data['y_valid'], adapter.predict_proba(data['X_valid']))['metrics']
    else:
        validation_metrics = evaluate_binary(data['y_valid'], adapter.predict_proba(data['X_valid']))['metrics']
    data_path = root / 'train_data.pkl'
    with data_path.open('xb') as stream:
        pickle.dump(data, stream)
    relative_model = str(model_path.relative_to(Path(settings.MEDIA_ROOT)))
    lineage = build_lineage(file_id, algorithm=data['algorithm'], model_path=relative_model,
        split_meta=data['split_meta'], feature_names=features, impute_means=data['impute_means'], model_params=params)
    lineage.update(execution_id=execution_id, parent_execution_id=parent_id, source=source,
                   prediction_contract=data['prediction_contract'], encoding_report=data.get('encoding_report', []),
                   purifier=data.get('purifier_state'))
    lineage_path = root / 'lineage.json'
    lineage_path.write_text(json.dumps(lineage, indent=2, default=str), encoding='utf-8')
    model.update(model_path=relative_model, train_data_path=str(data_path.relative_to(Path(settings.MEDIA_ROOT))),
        holdout_path=data['holdout_path'], feature_count=len(features), selected_features=features,
        purifier_path=str((root / 'purifier.json').relative_to(Path(settings.MEDIA_ROOT))) if data.get('purifier_state') else None,
        encoding_report=data['encoding_report'],
        categorical_features_used=[name for name in model.get('categorical_features_used', []) if name in features],
        calibration=calibration, calibrator_path=calibrator_path, algorithm=data['algorithm'],
        lineage_path=str(lineage_path.relative_to(Path(settings.MEDIA_ROOT))), lineage_id=lineage['lineage_id'],
        test_auc=None, test_auc_calibrated=None, test_r2=None, test_rmse=None, test_mae=None,
        candidate_source=source, candidate_params=params, holdout_status='uninspected_by_candidate')
    # Parent diagnostics cannot describe a newly fitted candidate.
    for key in ('valid_auc', 'valid_r2', 'valid_rmse', 'valid_mae', 'train_auc', 'train_r2',
                'cv', 'importances', 'shap_beeswarm', 'beeswarm_png', 'iv_table', 'score_points', 'woe_maps'):
        model.pop(key, None)
    model['development_validation_metrics'] = validation_metrics
    model['valid_auc'] = validation_metrics.get('roc_auc')
    model['valid_r2'] = validation_metrics.get('r2')
    model['best_iteration'] = int(getattr(adapter, 'best_iteration', 0) or 0)
    payload = {**parent, 'execution_id': execution_id, 'parent_execution_id': parent_id, 'model': model, 'algorithm': data['algorithm']}
    with projection_lock(file_id):
        current_path = Path(settings.MEDIA_ROOT) / 'modeling' / f'{file_id}_status.json'
        with current_path.open(encoding='utf-8') as stream:
            current_id = json.load(stream).get('execution_id')
        payload['adoption_status'] = 'adopted' if adopt and current_id == parent_id else ('candidate_only' if not adopt else 'candidate_only_parent_changed')
        publish_execution(execution_id, payload)
        if adopt and current_id == parent_id:
            replace_projection(data_path, Path(settings.MEDIA_ROOT) / 'train_data' / f'{file_id}_train_data.pkl')
            replace_projection(lineage_path, Path(settings.MEDIA_ROOT) / 'lineage' / f'{file_id}_lineage.json')
            replace_projection(root / 'modeling_status.json', current_path)
    return payload
