"""Offline, standard-library validation of a separately pinned fold export."""

import argparse
import hashlib
import json
import re
import sys
from itertools import pairwise
from pathlib import Path

MAX_BYTES = 8 * 1024**2
SCOPE = 'development_fold_provenance_v1'
CONSTRAINED_ENCODER_FIELDS = {
    'cross_fit_strategy', 'fit_rows', 'warmup_rows', 'warmup_prior', 'chronological_rows', 'category_key_encoding',
}
ENCODER_FOLD_ERROR = 'Target encoding has invalid fold provenance.'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _row_positions(rows, parent_positions):
    if not isinstance(rows, list) or any(type(row) not in (int, str) or row not in parent_positions for row in rows):
        raise ValueError(ENCODER_FOLD_ERROR)
    return [parent_positions[row] for row in rows]


def _ordered(positions):
    return all(first < second for first, second in pairwise(positions))


def _finite_number(value):
    return type(value) in (int, float) and -sys.float_info.max <= value <= sys.float_info.max


def _valid_target_state(mapping, task):
    def valid_value(value):
        return _finite_number(value) and (task != 'classification' or 0 <= value <= 1)

    values = mapping.get('mapping')
    return (valid_value(mapping.get('global_mean')) and isinstance(values, dict) and bool(values)
            and all(isinstance(key, str) and (key == 'n:' or key.startswith('s:')) and valid_value(value)
                    for key, value in values.items()))


def _verify_constrained_encoder(mapping, outer_train, task, specification):
    mode = mapping.get('cross_fit_strategy')
    if (not CONSTRAINED_ENCODER_FIELDS <= mapping.keys()
            or mode not in ('group', 'oot') or mapping['category_key_encoding'] != 'tagged_string_v1'
            or task not in ('classification', 'regression')
            or mapping.get('oof') is not True or mapping.get('fit_on_train_only') is not True
            or not _valid_target_state(mapping, task)
            or not _finite_number(mapping.get('smoothing')) or mapping['smoothing'] <= 0):
        raise ValueError(ENCODER_FOLD_ERROR)
    if specification is not None:
        required = ('group_column',) if mode == 'group' else ('date_column', 'label_end_column')
        if specification.get('strategy') != mode or any(
            not isinstance(specification.get(key), str) or not specification[key].strip() for key in required
        ):
            raise ValueError(ENCODER_FOLD_ERROR)
    parent_positions = {row: index for index, row in enumerate(outer_train)}
    fit_rows = mapping['fit_rows']
    if _row_positions(fit_rows, parent_positions) != list(range(len(outer_train))):
        raise ValueError(ENCODER_FOLD_ERROR)
    fits = mapping.get('oof_fits')
    if not isinstance(fits, list) or not fits or (mode == 'group' and len(fits) < 2):
        raise ValueError(ENCODER_FOLD_ERROR)
    warmup = mapping['warmup_rows']
    prior = mapping['warmup_prior']
    chronological = mapping['chronological_rows']
    if mode == 'oot':
        chronology = _row_positions(chronological, parent_positions)
        expected_prior = 0.5 if task == 'classification' else 0.0
        if (len(chronology) != len(outer_train) or len(set(chronology)) != len(chronology)
                or not _row_positions(warmup, parent_positions) or chronological[:len(warmup)] != warmup
                or not _finite_number(prior) or prior != expected_prior):
            raise ValueError(ENCODER_FOLD_ERROR)
        positions = {row: index for index, row in enumerate(chronological)}
    else:
        if warmup != [] or prior is not None or chronological is not None:
            raise ValueError(ENCODER_FOLD_ERROR)
        positions = parent_positions

    covered = set(warmup)
    for fold in fits:
        if not isinstance(fold, dict) or not _valid_target_state(fold, task):
            raise ValueError(ENCODER_FOLD_ERROR)
        train = _row_positions(fold.get('train_rows'), positions)
        valid = _row_positions(fold.get('validation_rows'), positions)
        if (len(train) < 2 or not valid or not _ordered(train) or not _ordered(valid)
                or covered.intersection(fold['validation_rows'])):
            raise ValueError(ENCODER_FOLD_ERROR)
        if mode == 'oot':
            start = len(covered)
            if valid != list(range(start, start + len(valid))) or train[-1] >= start:
                raise ValueError(ENCODER_FOLD_ERROR)
        elif len(train) + len(valid) != len(outer_train) or set(train).intersection(valid):
            raise ValueError(ENCODER_FOLD_ERROR)
        covered.update(fold['validation_rows'])
    if len(covered) != len(outer_train):
        raise ValueError('Target encoding has incomplete out-of-fold coverage.')
    return True


def verify_encoder_folds(mapping, outer_train, *, task=None, specification=None):
    """Validate inner membership against the model fit, using only exported state."""
    if CONSTRAINED_ENCODER_FIELDS.intersection(mapping):
        return _verify_constrained_encoder(mapping, outer_train, task, specification)
    fits = mapping.get('oof_fits')
    if fits is None or fits == [] and mapping.get('oof') is False:
        return False
    if ((specification or {}).get('strategy') in ('oot', 'group') or mapping.get('oof') is not True
            or mapping.get('fit_on_train_only') is not True or not isinstance(fits, list) or not fits):
        raise ValueError(ENCODER_FOLD_ERROR)
    outer = set(outer_train)
    covered = set()
    for fit in fits:
        train, valid = fit['train_rows'], fit['validation_rows']
        tr, va = set(train), set(valid)
        if (not isinstance(train, list) or not isinstance(valid, list) or not tr or not va
                or any(type(row) not in (int, str) for row in train + valid)
                or len(tr) != len(train) or len(va) != len(valid) or tr & va or va & covered
                or tr | va != outer or not isinstance(fit['mapping'], dict)):
            raise ValueError(ENCODER_FOLD_ERROR)
        covered.update(va)
    if covered != outer:
        raise ValueError('Target encoding has incomplete out-of-fold coverage.')
    return True


def verify(raw, expected):
    if (not isinstance(raw, bytes) or len(raw) > MAX_BYTES or not isinstance(expected, str)
            or not re.fullmatch('[a-f0-9]{64}', expected) or hashlib.sha256(raw).hexdigest() != expected):
        raise ValueError('Fold evidence bytes do not match the retained export digest.')
    try:
        data = json.loads(raw)
        if (data['schema_version'] != 1 or data['scope'] != SCOPE
                or data['evidence_scope'] != 'exploratory_development'
                or data['production_use_approved'] is not False
                or data['independent_reproduction_verified'] is not False
                or not re.fullmatch('[a-f0-9]{64}', data['result_sha256'])
                or not re.fullmatch('[a-f0-9]{64}', data.get('input_sha256') or data['input_snapshot_sha256'])):
            raise ValueError
        partitions, transforms = data['partitions'], data['transform_states']
        specification = data.get('validation_specification') or {}
        gaps = data['unverified']
        if not isinstance(gaps, list) or any(not isinstance(gap, dict) for gap in gaps):
            raise ValueError
        declared_missing_encoders = {
            (gap['stage'], gap['feature']) for gap in gaps
            if gap.get('reason') == 'inner_target_encoding_folds_unverified'
        }
        missing_encoders = set()
        for table in (partitions, transforms):
            if any(key != _digest(value) for key, value in table.items()):
                raise ValueError
        used_parts, used_states, stages = set(), set(), {}
        for fit in data['fits']:
            stage = fit['stage']
            if not isinstance(stage, str) or not stage or stage in stages:
                raise ValueError
            stages[stage] = fit
            pid, tid = fit['partition_sha256'], fit['transforms_sha256']
            used_parts.add(pid)
            used_states.add(tid)
            p, state = partitions[pid], transforms[tid]
            tr, va = p['train_rows'], p['validation_rows']
            receipt = dict(fit['fit_receipt'])
            sha = receipt.pop('sha256')
            if state['internal'] is not None:
                receipt['fitted_transforms'] = state['internal']
            if _digest(receipt) != sha:
                raise ValueError
            refit = p['validation_role'] == 'unused_train_mirror'
            if (not tr or len(tr) != len(set(tr)) or len(va) != len(set(va)) or set(tr) & set(va)
                    or any(type(row) not in {str, int} for row in tr + va)
                    or len(tr) != receipt['train']['n_rows']
                    or (len(tr) if refit else len(va)) != receipt['valid']['n_rows']
                    or (refit and (va or receipt['train']['sha256'] != receipt['valid']['sha256']))
                    or (not refit and p['validation_role'] != receipt['validation_role'])):
                raise ValueError
            for name, rows in (('train', tr), ('valid', tr if refit else va)):
                row_digest = receipt.get(name + '_rows_sha256')
                if row_digest is not None and _digest(rows) != row_digest:
                    raise ValueError
            for entry in state['encoding']:
                if 'before_stats' in entry or 'after_stats' in entry:
                    raise ValueError
                mapping = entry.get('mapping') or {}
                if mapping.get('type') == 'target_encoding' and not verify_encoder_folds(
                    mapping, tr, task=receipt.get('task'), specification=specification,
                ):
                    missing_encoders.add((stage, entry['feature']))
            if state['purifier'] and (state['purifier']['fit_rows'] != tr
                                      or state['purifier']['raw_input_sha256'] != data['raw_input_sha256']):
                raise ValueError
            if state['internal'] and (state['internal']['fit_partition'] != 'train'
                                     or state['internal']['fit_input_sha256'] != receipt['train']['sha256']):
                raise ValueError
        if (used_parts != set(partitions) or used_states != set(transforms)
                or missing_encoders != declared_missing_encoders):
            raise ValueError
        calibrations = [('model/fit', data.get('calibration') or {})]
        calibrations.extend((item['stage'] + '/fit', item['calibration'])
                            for item in data.get('candidate_assessments', []))
        for stage, calibration in calibrations:
            if calibration.get('fit_partition'):
                model_fit = stages[stage]
                if (calibration['fit_stage'] != stage or calibration['fit_partition'] != 'development_validation'
                        or calibration['fit_rows'] != partitions[model_fit['partition_sha256']]['validation_rows']
                        or calibration['fit_input_sha256'] != model_fit['fit_receipt']['valid']['sha256']
                        or not re.fullmatch('[a-f0-9]{64}', calibration['calibration_input_sha256'])):
                    raise ValueError
        return {'scope': SCOPE, 'job_id': data['job_id'], 'result_sha256': data['result_sha256'],
                'export_sha256': expected, 'fit_count': len(stages), 'partition_count': len(partitions),
                'unverified_count': len(gaps), 'independent_reproduction_verified': False}
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        raise ValueError('Fold evidence is invalid or internally inconsistent.') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--sha256', required=True, help='Digest retained separately from the export')
    args = parser.parse_args()
    try:
        with args.export.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        print(json.dumps(verify(raw, args.sha256), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
