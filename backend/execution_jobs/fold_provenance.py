"""Read exact, development-only fold evidence for a completed governed job."""

import hashlib
import json
import uuid

from execution_jobs import csv_scoring, history, legacy_execution as legacy, legacy_selection_provenance, service, training_search
from execution_jobs.models import NativeJob
from modeling.fold_evidence import FoldEvidence
from modeling.verify_fold_provenance import MAX_BYTES, SCOPE


def _conflict():
    raise service.JobConflict('job_fold_provenance_unavailable')


def _artifact_bytes(job, relative):
    result = job.result
    files = result.get('files')
    if not isinstance(files, dict) or result.get('files_sha256') != service.digest(files):
        _conflict()
    entry = files.get(relative)
    if not isinstance(entry, dict) or type(entry.get('bytes')) is not int or not 0 < entry['bytes'] <= MAX_BYTES:
        _conflict()
    raw = legacy.read(legacy.output_root(job) / legacy.relative(relative), entry['bytes'])
    if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
        _conflict()
    return raw


def _read_artifact(job, relative):
    value = json.loads(_artifact_bytes(job, relative))
    if not isinstance(value, dict):
        _conflict()
    return value


def _snapshot(job, execution):
    if not isinstance(execution, str) or str(uuid.UUID(execution)) != execution:
        _conflict()
    base = f'execution_runs/{execution}/'
    manifest = _read_artifact(job, base + 'manifest.json')
    if (manifest.get('file_id'), manifest.get('execution_id')) != (job.dataset_id, execution):
        _conflict()
    files = manifest['files']
    if any(files.get(name) != job.result['files'].get(base + name)
           for name in ('modeling_status.json', 'lineage.json')):
        _conflict()
    status = _read_artifact(job, base + 'modeling_status.json')
    lineage = _read_artifact(job, base + 'lineage.json')
    if (status.get('file_id'), status.get('execution_id'), lineage.get('file_id'), lineage.get('execution_id')) != (
            job.dataset_id, execution, job.dataset_id, execution):
        _conflict()
    model = status['model']
    if (model.get('fit_receipt') != lineage.get('fit_receipt')
            or model.get('prediction_contract') != lineage.get('prediction_contract')
            or model.get('encoding_report') != lineage.get('encoding_report')
            or 'cv' in lineage and model.get('cv') != lineage['cv']):
        _conflict()
    if lineage.get('split', {}).get('membership') != model['split'].get('membership'):
        _conflict()
    membership = model['split']['membership']
    train, valid, protected = (membership[key] for key in ('train', 'valid', 'test'))
    if (not all(isinstance(rows, list) and len(rows) == len(set(rows)) for rows in (train, valid, protected))
            or set(train) & set(valid) or set(train + valid) & set(protected)):
        _conflict()
    state = {'purifier': lineage.get('purifier'), 'encoding': lineage.get('encoding_report', []),
             'impute_means': lineage.get('impute_means', {}),
             'upstream_limitation': None if lineage.get('purifier') else 'Upstream preparation provenance unverified.'}
    split = model['split']
    config = split.get('split_config') or {}
    state['validation_specification'] = {
        'strategy': split.get('strategy'),
        **{key: config[key] for key in ('group_column', 'date_column', 'label_end_column', 'cutoff') if key in config},
    }
    state['prediction_contract_sha256'] = manifest['prediction_contract_sha256']
    if service.require_digest(state['prediction_contract_sha256']) != (model.get('prediction_contract') or {}).get('sha256'):
        _conflict()
    state['input_snapshot_sha256'] = service.require_digest(files['dataset.csv']['sha256'])
    if state['purifier']:
        state['raw_input_sha256'] = service.require_digest(files['raw_input.csv']['sha256'])
        if state['raw_input_sha256'] != state['purifier']['raw_input_sha256']:
            _conflict()
    state['parent_execution_id'] = lineage.get('parent_execution_id')
    if state['parent_execution_id'] != status.get('parent_execution_id'):
        _conflict()
    return model, state, train, valid


def _model_evidence(output, stage, model, state, train, valid):
    output.record(stage + '/fit', model.get('fit_receipt'), state, train_rows=train, valid_rows=valid)
    cv = model.get('cv') or {}
    if cv.get('status') == 'completed':
        rows = cv.get('fold_provenance')
        if not isinstance(rows, list) or len(rows) != cv.get('n_splits'):
            _conflict()
        for i, row in enumerate(rows, 1):
            output.fold(f'{stage}/cv/{i}', row)
    elif cv:
        output.gaps.append({'stage': stage + '/cv', 'reason': 'development_cv_unavailable'})
    calibration = model.get('calibration') or {}
    if calibration.get('fitted'):
        fit = model['fit_receipt']
        state = calibration.get('fitted_transform')
        if not state:
            output.gaps.append({'stage': stage + '/calibration', 'reason': 'historical_calibration_state_unavailable'})
        elif calibration.get('fit_partition') != 'development_validation' or calibration.get('fit_rows') != valid or (
                calibration.get('fit_input_sha256') != fit['valid']['sha256']):
            _conflict()
        else:
            return {'fit_rows': valid, 'fit_stage': stage + '/fit', 'fit_partition': 'development_validation',
                    'fit_input_sha256': calibration['fit_input_sha256'],
                    'calibration_input_sha256': service.require_digest(calibration.get('calibration_input_sha256')),
                    'state': state}
    return {'status': 'historical_unverified' if calibration.get('fitted') else 'not_fitted'}


def _native(job):
    result = job.result
    plan = job.specification['training']
    refit = result['refit_preprocessing']
    all_rows = list(range(len(refit['train_rows'])))
    if refit['train_rows'] != all_rows or refit['valid_rows'] or result.get('final_holdout_accessed') is not False:
        _conflict()
    output = FoldEvidence(all_rows)
    if (service.digest(plan) != job.specification['training_sha256']
            or result.get('scope') != training_search.KIND
            or result.get('job_id') != str(job.pk) or result.get('input_sha256') != plan['source']['sha256']
            or result.get('training_sha256') != job.specification['training_sha256']
            or result.get('prediction_contract') != plan['prediction_contract']):
        _conflict()
    for i, candidate in enumerate(result['candidates'], 1):
        if len(candidate['folds']) != len(plan['folds']):
            _conflict()
        for j, (row, declared) in enumerate(zip(candidate['folds'], plan['folds']), 1):
            state = {**row['preprocessing'], 'upstream_limitation': None}
            if any(state[key] != declared[key] for key in ('train_rows', 'valid_rows')):
                _conflict()
            output.fold(f'candidate/{i}/fold/{j}', {**state, 'fit_receipt': row['fit_receipt']})
    output.record('refit', result['refit_receipt'], {**refit, 'upstream_limitation': None},
                  train_rows=all_rows, valid_rows=[], refit=True)
    return {**output.result(), 'input_sha256': result['input_sha256'],
            'validation_specification': plan['options']['validation'],
            'prediction_contract_sha256': plan['prediction_contract'].get('sha256')}


def _legacy(actor, job, scopes):
    result = job.result
    plan = job.specification['legacy']
    operation = plan['operation']
    if (service.digest(plan) != job.specification['legacy_sha256']
            or result.get('scope') != legacy.KIND or result.get('job_id') != str(job.pk)
            or result.get('operation') != operation or result.get('source') != plan.get('source')
            or result.get('plan_sha256') != job.specification['legacy_sha256']
            or result.get('inputs_sha256') != service.digest(plan['inputs'])):
        _conflict()
    source = None
    source_evidence = {}
    if operation != 'training':
        source_ref = plan['source']
        service.execution_reference(source_ref, 'job_id', 'result_sha256')
        source = NativeJob.objects.get(pk=source_ref['job_id'])
        scopes.extend(service.read_authority(actor, source))
        if (source.state != 'succeeded' or source.project_id != job.project_id or source.dataset_id != job.dataset_id
                or service.execution_specification(source).get('kind') != legacy.KIND
                or source.result_sha256 != source_ref['result_sha256']):
            _conflict()
        source_evidence = {'source_job_id': str(source.pk), 'source_execution_id': source_ref['execution_id'],
                           'source_result_sha256': source.result_sha256}
    if operation in ('training', 'champion'):
        execution = result['payload']['execution_id']
        model, state, train, valid = _snapshot(job, execution)
        if state['parent_execution_id'] != source_evidence.get('source_execution_id'):
            _conflict()
        output = FoldEvidence(train + valid, raw_input_sha256=state.get('raw_input_sha256'))
        calibration = _model_evidence(output, 'model', model, state, train, valid)
        return {**output.result(), **source_evidence, 'execution_id': execution, 'calibration': calibration,
                'input_snapshot_sha256': state['input_snapshot_sha256'],
                'raw_input_sha256': state.get('raw_input_sha256'),
                'validation_specification': state['validation_specification'],
                'prediction_contract_sha256': state['prediction_contract_sha256']}
    if source is None:
        _conflict()
    execution = source_evidence['source_execution_id']
    _, state, train, valid = _snapshot(source, execution)
    output = FoldEvidence(train + valid, raw_input_sha256=state.get('raw_input_sha256'))
    payload = result['payload']
    candidates = {}
    parent_rows = set(train)
    if operation == 'sfs':
        extra = (_artifact_bytes(job, legacy_selection_provenance.NAME)
                 if legacy_selection_provenance.NAME in result['files'] else b'')
        for key, baseline in (payload.get('baselines') or {}).items():
            for i, row in enumerate(baseline['fold_provenance'], 1):
                output.fold(f'baseline/{key}/{i}', row, parent_rows=parent_rows)
        for key in ('forward', 'backward', 'forward_from_backward', 'rejected_steps'):
            for i, step in enumerate(payload.get(key) or [], 1):
                prefix = f'{key}/{i}'
                output.record(prefix + '/selected', step.get('fit_receipt'), state, train_rows=train, valid_rows=valid)
                for j, row in enumerate(step.get('validation_provenance') or [], 1):
                    output.fold(f'{prefix}/selected/cv/{j}', row, parent_rows=parent_rows)
                _selection_step(output, prefix, step, extra, state, train, valid, parent_rows)
        for key in ('forward', 'backward', 'forward_from_backward'):
            identifier = payload.get(key + '_execution_id')
            if identifier:
                candidates[key] = identifier
    elif operation == 'hpo':
        for trial in payload.get('trial_attempts') or []:
            if trial.get('status') != 'completed':
                output.gaps.append({'stage': f'trial/{trial["trial_index"]}', 'reason': trial['status']})
        for trial in payload.get('trials') or []:
            prefix = f'trial/{trial["trial_index"]}'
            for i, row in enumerate(trial['validation_provenance'], 1):
                output.fold(f'{prefix}/cv/{i}', row, parent_rows=parent_rows)
            output.record(prefix + '/fit', trial.get('fit_receipt'), state, train_rows=train, valid_rows=valid)
        for i, curve in enumerate(payload.get('validation_curves') or [], 1):
            for j, point in enumerate(curve['points'], 1):
                prefix = f'curve/{i}/point/{j}'
                if point['status'] != 'complete':
                    output.gaps.append({'stage': prefix, 'reason': point['status']})
                for k, row in enumerate(point.get('validation_provenance') or [], 1):
                    output.fold(f'{prefix}/cv/{k}', row, parent_rows=parent_rows)
        if payload.get('execution_id'):
            candidates['winner'] = payload['execution_id']
    else:
        _conflict()
    assessments = []
    for name, identifier in candidates.items():
        model, candidate_state, tr, va = _snapshot(job, identifier)
        if (tr != train or va != valid or candidate_state['parent_execution_id'] != execution
                or any(candidate_state.get(key) != state.get(key) for key in (
                'input_snapshot_sha256', 'raw_input_sha256', 'validation_specification', 'prediction_contract_sha256'))):
            _conflict()
        stage = f'candidate/{name}'
        calibration = _model_evidence(output, stage, model, candidate_state, tr, va)
        assessments.append({'stage': stage, 'execution_id': identifier, 'calibration': calibration})
    return {**output.result(), **source_evidence,
            'input_snapshot_sha256': state['input_snapshot_sha256'],
            'raw_input_sha256': state.get('raw_input_sha256'), 'candidate_assessments': assessments,
            'validation_specification': state['validation_specification'],
            'prediction_contract_sha256': state['prediction_contract_sha256']}


def _selection_step(output, prefix, step, raw, state, train, valid, parent_rows):
    reference = step.get('additional_fits')
    if not reference or reference.get('status') == 'evidence_budget_exceeded':
        reason = reference['status'] if reference else 'historical_additional_selection_fits_unavailable'
        output.gaps.append({'stage': prefix, 'reason': reason})
        return
    evidence = legacy_selection_provenance.read(raw, reference)
    screening, other = evidence['screening'], evidence['other_top_k']
    if (set(step['screening_scores']) != set(screening)
            or set(step['top_k_evaluated']) - {step['feature_name']} != set(other)):
        _conflict()
    for j, (name, fit) in enumerate(screening.items(), 1):
        stage = f'{prefix}/screen/{j}'
        if fit['train']['features'] != fit['valid']['features']:
            _conflict()
        output.record(stage, fit, state, train_rows=train, valid_rows=valid, candidate_feature=name)
    for j, (name, folds) in enumerate(other.items(), 1):
        if len(folds) != len(step['validation_provenance']):
            _conflict()
        for k, row in enumerate(folds, 1):
            output.fold(f'{prefix}/other_top_k/{j}/{k}', row, candidate_feature=name, parent_rows=parent_rows)


def export(actor, identifier, expected):
    expected = service.require_digest(expected)
    with history._bounded_read():
        job = NativeJob.objects.get(pk=identifier)
        scopes = service.read_authority(actor, job)
        kind = service.execution_specification(job).get('kind')
        if job.state != 'succeeded' or job.result_sha256 != expected or kind not in {legacy.KIND, training_search.KIND}:
            _conflict()
        try:
            evidence = _native(job) if kind == training_search.KIND else _legacy(actor, job, scopes)
            value = {**evidence, 'scope': SCOPE, 'job_id': str(job.pk), 'file_id': job.dataset_id,
                     'project_id': str(job.project_id), 'result_sha256': expected}
            raw = csv_scoring.canonical_bytes(value)
        except service.JobConflict:
            raise
        except (KeyError, ValueError, TypeError, OSError, AttributeError, RecursionError):
            _conflict()
        if len(raw) > MAX_BYTES:
            raise service.JobConflict('job_fold_provenance_budget_exceeded')
        for scope in scopes:
            service.projects.recheck(scope)
        return raw
