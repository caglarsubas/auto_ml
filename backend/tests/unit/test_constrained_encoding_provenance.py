"""Corrupted inner encoding receipts fail export and offline verification."""

import hashlib
import json
from copy import deepcopy

import pytest

from modeling.fit_receipts import receipt_digest
from modeling.fold_evidence import FoldEvidence
from modeling.verify_fold_provenance import SCOPE, verify, verify_encoder_folds


pytestmark = pytest.mark.unit


def _state(mode):
    temporal = mode == 'oot'
    return {
        'type': 'target_encoding',
        'mapping': {'s:cohort': 0.75, 'n:': 0.25},
        'global_mean': 0.5,
        'smoothing': 10.0,
        'oof': True,
        'fit_on_train_only': True,
        'category_key_encoding': 'tagged_string_v1',
        'cross_fit_strategy': mode,
        'fit_rows': [40, 10, 30, 20],
        'warmup_rows': [10, 20] if temporal else [],
        'warmup_prior': 0.5 if temporal else None,
        'chronological_rows': [10, 20, 30, 40] if temporal else None,
        'oof_fits': [
            {'train_rows': [10, 20], 'validation_rows': [30, 40], 'mapping': {'s:cohort': 0.25}, 'global_mean': 0.5},
        ] if temporal else [
            {'train_rows': [10, 20], 'validation_rows': [40, 30], 'mapping': {'s:cohort': 0.25}, 'global_mean': 0.5},
            {'train_rows': [40, 30], 'validation_rows': [10, 20], 'mapping': {'n:': 0.25}, 'global_mean': 0.5},
        ],
    }


def _specification(mode):
    if mode == 'oot':
        return {'strategy': mode, 'date_column': 'event_date', 'label_end_column': 'label_end'}
    return {'strategy': mode, 'group_column': 'entity'}


def _export(mapping, mode):
    train = [40, 10, 30, 20]
    validation = [100]
    fit = {
        'task': 'classification', 'validation_role': 'evaluation_only',
        'train': {'n_rows': len(train)}, 'valid': {'n_rows': len(validation)},
        'train_rows_sha256': receipt_digest(train), 'valid_rows_sha256': receipt_digest(validation),
    }
    fit['sha256'] = receipt_digest(fit)
    specification = _specification(mode)
    retained = FoldEvidence(train + validation, validation_specification=specification)
    retained.record(
        'model/fit', fit, {'encoding': [{'feature': 'cohort', 'mapping': mapping}]},
        train_rows=train, valid_rows=validation,
    )
    return {
        **retained.result(), 'scope': SCOPE, 'job_id': 'synthetic',
        'input_sha256': 'a' * 64, 'result_sha256': 'b' * 64, 'validation_specification': specification,
    }


def _verify(export):
    raw = json.dumps(export).encode()
    return verify(raw, hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('mode', ['oot', 'group'])
def test_constrained_encoder_round_trips_from_export_to_offline_reader(mode):
    result = _verify(_export(_state(mode), mode))
    assert result['fit_count'] == 1
    assert result['unverified_count'] == 0


def test_constrained_encoder_rejects_invalid_parent_membership_and_temporal_warmup():
    recorded = _state('oot')
    train = recorded['fit_rows']
    changes = (
        {'fit_rows': list(reversed(train))},
        {'warmup_prior': 0.0},
        {'warmup_rows': [10, 30]},
        {'oof_fits': [{**recorded['oof_fits'][0], 'train_rows': [10, 40]}]},
        {'oof_fits': [{**recorded['oof_fits'][0], 'validation_rows': [40]}]},
        {'mapping': {'invalid': 0.5}},
        {'mapping': {'s:cohort': float('inf')}},
    )
    for change in changes:
        with pytest.raises(ValueError, match='invalid fold provenance'):
            verify_encoder_folds({**recorded, **change}, train, task='classification')
    with pytest.raises(ValueError, match='invalid fold provenance'):
        verify_encoder_folds(recorded, train, task='classification', specification={'strategy': 'oot'})


def test_offline_verification_rejects_rehashed_group_evidence_and_preserves_historical_gaps():
    recorded = _state('group')
    export = _export(recorded, 'group')
    [fit] = export['fits']
    state = deepcopy(export['transform_states'].pop(fit['transforms_sha256']))
    [encoding] = state['encoding']
    encoding['mapping']['oof_fits'][0]['train_rows'] = [40, 20]
    fit['transforms_sha256'] = receipt_digest(state)
    export['transform_states'][fit['transforms_sha256']] = state
    with pytest.raises(ValueError, match='internally inconsistent'):
        _verify(export)

    old = {'type': 'target_encoding', 'mapping': {'cohort': 0.5}, 'global_mean': 0.5, 'oof': True}
    historical = _export(old, 'group')
    assert _verify(historical)['unverified_count'] == 1
    historical['unverified'] = []
    with pytest.raises(ValueError, match='internally inconsistent'):
        _verify(historical)
