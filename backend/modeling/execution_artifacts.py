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
    from modeling.holdout_evidence import verify_holdout_spec
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
    spec = payload.get('model', {}).get('holdout_spec')
    if spec:
        manifest['holdout_spec'] = verify_holdout_spec(spec, payload['model'], manifest)
    for package in ('Django', 'djangorestframework', 'pandas', 'numpy', 'scikit-learn', 'xgboost', 'lightgbm', 'catboost', 'joblib'):
        try:
            manifest['packages'][package] = version(package)
        except PackageNotFoundError:
            manifest['packages'][package] = None
    with (root / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
    from access_control.projects import governed, register_artifact
    if governed():
        from django.db import transaction
        with transaction.atomic():
            for path in sorted(root.rglob('*')):
                if path.is_file() and path.suffix.lower() in {'.json', '.csv', '.png', '.svg', '.pdf'}:
                    register_artifact(path, file_id=payload['file_id'])
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
        payload = json.load(stream)
    from modeling.holdout_evidence import verify_holdout_spec
    spec = payload.get('model', {}).get('holdout_spec')
    if spec != manifest.get('holdout_spec'):
        raise ValueError('Final-outcome identity does not match the execution manifest.')
    verify_holdout_spec(spec, payload.get('model', {}), manifest)
    return payload, manifest


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
    from access_control.projects import governed, register_artifact
    if governed():
        from django.db import transaction
        with transaction.atomic():
            for name in ('evaluation.json', 'model_card.json', 'manifest.json'):
                register_artifact(root / name, file_id=payload['file_id'])
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


def publish_candidate(parent_id, file_id, adapter, features, params, source, adopt=True, selection_evidence=None):
    """Publish fresh, input-bound native evidence without inspecting final labels."""
    import pickle
    import pandas as pd
    from modeling.calibration_utils import fit_calibrator, save_calibrator
    from modeling.development_assessment import development_metrics, run_development_cv
    from modeling.fit_receipts import verify_candidate_fit
    from modeling.lineage import build_lineage
    # Reject expert implementations before loading customer development inputs.
    from modeling.booster_adapters import XGBoostAdapter, LightGBMAdapter, CatBoostAdapter
    from modeling.alt_pipelines import SklearnModelAdapter, evaluate_anomaly_scores
    if type(adapter) not in (XGBoostAdapter, LightGBMAdapter, CatBoostAdapter, SklearnModelAdapter):
        raise ValueError('Candidate publication supports registered native adapters only; expert execution requires isolation.')
    if not isinstance(features, list) or not features or not all(isinstance(name, str) for name in features) or len(set(features)) != len(features):
        raise ValueError('Candidate features must be a nonempty, unique ordered list of column names.')
    parent, manifest = load_execution(parent_id, file_id)
    parent_root = execution_root(parent_id)
    with open(Path(settings.MEDIA_ROOT) / parent['model']['train_data_path'], 'rb') as stream:
        data = pickle.load(stream)
    fit_receipt = verify_candidate_fit(adapter, data, features)
    for name in ('X_train', 'X_valid', 'X_train_raw', 'X_valid_raw'):
        if name in data:
            data[name] = data[name].loc[:, features]
    algorithm = fit_receipt['algorithm']
    task = data['task']
    contract = data['prediction_contract']
    costs = (contract.get('objective') or {}).get('cost_matrix')
    class_count = len(contract.get('class_mapping') or [])
    metrics = {}
    for partition in ('train', 'valid'):
        X, y = data['X_' + partition], data['y_' + partition]
        predictions = adapter.predict(X) if task == 'regression' else adapter.predict_proba(X)
        if task == 'anomaly':
            import numpy as np
            if np.asarray(predictions).shape != (len(y),) or not np.isfinite(predictions).all():
                raise ValueError('Candidate rankings must preserve every row and be finite.')
            metrics[partition] = evaluate_anomaly_scores(y, predictions)
        else:
            metrics[partition] = development_metrics(y, predictions, task, class_count, costs)
    context = data.get('validation_context')
    if context:
        # Candidate parameters are frozen after selection, including any selected weight.
        # Initial automatic fold-local weighting remains a separate policy.
        candidate_context = {**context, 'class_weight_policy': None}
        cv = run_development_cv(candidate_context, pd.concat([data['X_train'], data['X_valid']]),
            pd.concat([data['y_train'], data['y_valid']]), algorithm, fit_receipt['requested_params'],
            num_boost_round=fit_receipt['num_boost_round'] if fit_receipt['num_boost_round'] is not None else 500,
            early_stopping_rounds=fit_receipt['early_stopping_rounds'] or 0, all_declared_features=False)
        cv['evidence_scope'] = 'Post-selection development CV; selection already used these data. Exploratory, not independent assessment.'
        cv['class_weight_policy'] = 'Fixed candidate fitter parameters; not re-estimated from CV labels.'
    else:
        cv = {'schema_version': 2, 'task': task, 'status': 'unavailable',
              'limitations': ['Historical execution lacks a recorded development validation context; parent CV is not inherited.']}
    if selection_evidence is not None:
        from modeling.fit_receipts import receipt_digest
        basis = selection_evidence.get('search_basis') or {}
        if (selection_evidence.get('status') != 'completed' or selection_evidence.get('selected_params') != params
                or basis.get('execution_id') != parent_id
                or basis.get('sha256') != receipt_digest({key: value for key, value in basis.items() if key != 'sha256'})):
            raise ValueError('Tuning evidence does not match the selected execution/configuration.')
    # All fit/metric/CV checks precede staging or adoption. No failed candidate is published.
    dataset_name = next(name for name in manifest['files'] if name.startswith('dataset.'))
    execution_id, root, _ = begin_execution(parent_root / dataset_name)
    for name in ('raw_input.csv', 'purifier_recipe.json', 'purifier.json'):
        if name in manifest['files']:
            shutil.copyfile(parent_root / name, root / name)
    if selection_evidence is not None:
        (root / 'tuning_selection.json').write_text(json.dumps(selection_evidence, indent=2, allow_nan=False), encoding='utf-8')
    data['feature_names'], data['execution_id'], data['fit_receipt'] = list(features), execution_id, fit_receipt
    data['impute_means'] = {key: value for key, value in data.get('impute_means', {}).items() if key in features}
    data['encoding_report'] = [report for report in data.get('encoding_report', [])
        if report['feature'] in features or set((report.get('mapping') or {}).get('columns') or []).intersection(features)]
    # Byte-copy the protected assessment input; candidate development never deserializes it.
    shutil.copyfile(Path(settings.MEDIA_ROOT) / data['holdout_path'], root / 'final_holdout.pkl')
    data['holdout_path'] = str((root / 'final_holdout.pkl').relative_to(Path(settings.MEDIA_ROOT)))
    model_path = root / 'models' / adapter.model_filename(file_id)
    adapter.save(str(model_path))
    calibration = {'fitted': False}
    calibrator_path = None
    if task == 'classification' and class_count == 2:
        calibrator, calibration = fit_calibrator(data['y_valid'], adapter.predict_proba(data['X_valid']))
        if calibrator is not None:
            calibrator_path = str((root / save_calibrator(file_id, calibrator, str(root))).relative_to(Path(settings.MEDIA_ROOT)))
    data['calibration'], data['calibrator_path'], data['algorithm'] = calibration, calibrator_path, algorithm
    data['scale_pos_weight'] = fit_receipt['requested_params'].get('scale_pos_weight')
    data_path = root / 'train_data.pkl'
    with data_path.open('xb') as stream:
        pickle.dump(data, stream)
    relative_model = str(model_path.relative_to(Path(settings.MEDIA_ROOT)))
    lineage = build_lineage(file_id, algorithm=algorithm, model_path=relative_model,
        split_meta=data['split_meta'], feature_names=features, impute_means=data['impute_means'],
        model_params=fit_receipt['effective_params'], metrics=metrics,
        n_train=len(data['y_train']), n_valid=len(data['y_valid']))
    lineage.update(execution_id=execution_id, parent_execution_id=parent_id, source=source,
                   prediction_contract=contract, encoding_report=data.get('encoding_report', []),
                   purifier=data.get('purifier_state'), fit_receipt=fit_receipt, cv=cv)
    lineage_path = root / 'lineage.json'
    lineage_path.write_text(json.dumps(lineage, indent=2, allow_nan=False), encoding='utf-8')
    # Only invariant declarations and input provenance can cross a model change.
    invariant = ('prediction_contract', 'holdout_spec', 'input_stage', 'purifier_provenance', 'diagnostic_limitations',
                 'impute_fit_on_train_only')
    model = {key: parent['model'][key] for key in invariant if key in parent['model']}
    model.update(model_type=f'{algorithm}_{"regressor" if task == "regression" else "anomaly" if task == "anomaly" else "classifier"}',
        task=task, pipeline_family='alternate' if type(adapter) is SklearnModelAdapter else 'boosting',
        model_path=relative_model, train_data_path=str(data_path.relative_to(Path(settings.MEDIA_ROOT))),
        holdout_path=data['holdout_path'], feature_count=len(features), selected_features=list(features),
        purifier_path=str((root / 'purifier.json').relative_to(Path(settings.MEDIA_ROOT))) if data.get('purifier_state') else None,
        encoding_report=data['encoding_report'], categorical_features_used=list(adapter.cat_features),
        enable_categorical=bool(adapter.enable_categorical),
        calibration=calibration, calibrator_path=calibrator_path, algorithm=algorithm, fit_receipt=fit_receipt,
        scale_pos_weight=fit_receipt['requested_params'].get('scale_pos_weight'),
        lineage_path=str(lineage_path.relative_to(Path(settings.MEDIA_ROOT))), lineage_id=lineage['lineage_id'],
        split={**data['split_meta'], 'n_train': len(data['y_train']), 'n_valid': len(data['y_valid']),
               'n_test': (parent['model'].get('split') or {}).get('n_test')},
        sfs_ready=task != 'anomaly' and type(adapter) is not SklearnModelAdapter and class_count <= 2,
        test_auc=None, test_auc_calibrated=None, test_r2=None, test_rmse=None, test_mae=None,
        candidate_source=source, candidate_params=params, holdout_status='uninspected_by_candidate',
        development_train_metrics=metrics['train'], development_validation_metrics=metrics['valid'],
        valid_auc=metrics['valid'].get('roc_auc'), valid_r2=metrics['valid'].get('r2'),
        valid_rmse=metrics['valid'].get('rmse'), valid_mae=metrics['valid'].get('mae'),
        train_auc=metrics['train'].get('roc_auc'), train_r2=metrics['train'].get('r2'),
        cv=cv, importances={'gain': adapter.gain_importance()},
        explanation_limitation='Candidate SHAP/leakage diagnostics have not been recomputed; parent diagnostics are not inherited.',
        best_iteration=int(getattr(adapter, 'best_iteration', 0) or 0))
    from modeling.collinearity import write_snapshot
    model['collinearity'] = write_snapshot(root, file_id, execution_id, data['X_train'][features], data['encoding_report'])
    if selection_evidence is not None:
        model['tuning_evidence_path'] = str((root / 'tuning_selection.json').relative_to(Path(settings.MEDIA_ROOT)))
        model['tuning_basis_sha256'] = selection_evidence['search_basis']['sha256']
    if type(adapter) is SklearnModelAdapter and algorithm == 'scorecard':
        model.update(iv_table=adapter.iv_table, score_points=adapter.score_points, woe_maps=adapter.woe_maps)
    payload = {'status': 'ok', 'job_status': 'completed', 'file_id': file_id,
               'execution_id': execution_id, 'parent_execution_id': parent_id, 'model': model,
               'algorithm': algorithm, 'metrics': {'qualification': 'Candidate-specific development evidence; exploratory.'}}
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
