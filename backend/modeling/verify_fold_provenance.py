"""Offline, standard-library validation of a separately pinned fold export."""

import argparse
import hashlib
import json
import re
from pathlib import Path

MAX_BYTES = 8 * 1024**2
SCOPE = 'development_fold_provenance_v1'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


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
            if state['purifier'] and state['purifier']['fit_rows'] != tr:
                raise ValueError
            if state['internal'] and (state['internal']['fit_partition'] != 'train'
                                     or state['internal']['fit_input_sha256'] != receipt['train']['sha256']):
                raise ValueError
        if used_parts != set(partitions) or used_states != set(transforms):
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
        gaps = data['unverified']
        if not isinstance(gaps, list):
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
