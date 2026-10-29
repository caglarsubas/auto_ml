"""Compact new checkpoints preserve evidence, legacy reads and publication safety."""
import hashlib
import json
import uuid

import pytest

from modeling import sfs_evidence
from modeling.sfs_state import read_recorded_sfs

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('values', [
    {'unicode': '\u20ac\U0001f600', 'spaces': ' a\n b ', 'surrogate': '\ud800'},
    {'float': [.0, -.0, 1e-7, 1e20, 1.2345678901234567, 5e-324]},
    {'integers': [0, -1, 2**64, -(2**100)], 'flags': [True, False, None]},
    {'nested': [{1: 'integer key', '2': 'string key', None: ('tuple',)}]},
    {'forward': [{'selected_features': ['x'], 'metrics': {'roc_auc': .5}}] * 10000},
])
def test_complete_new_checkpoint_matches_independent_legacy_values_and_file_bytes(tmp_path, values):
    path = tmp_path / 'checkpoint.json'
    record = {'status': 'running', 'operation_id': 'same', **values}
    before = json.dumps(record, indent=2, allow_nan=False).encode()
    expected = json.loads(before)
    sfs_evidence.write_sfs_record(path, record)
    raw = path.read_bytes()
    assert read_recorded_sfs(path) == expected
    assert raw == json.dumps(record, separators=(',', ':'), allow_nan=False).encode()
    assert len(raw) <= len(before)
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]
    if 'float' in values:
        assert json.dumps(json.loads(raw)['float']) == json.dumps(expected['float'])


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), float('-inf'), object(), {('bad',): 1}])
def test_serialization_refusal_keeps_exact_legacy_evidence_without_staging(tmp_path, invalid):
    path = tmp_path / 'checkpoint.json'
    original = b'{\n  "status": "running",\n  "operation_id": "legacy",\n  "forward": []\n}'
    path.write_bytes(original)
    with pytest.raises((ValueError, TypeError)):
        sfs_evidence.write_sfs_record(path, {'invalid': invalid})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_legacy_archive_retry_does_not_rewrite_pretty_bytes_or_original_hash(tmp_path):
    operation = str(uuid.uuid4())
    record = {'schema_version': 2, 'status': 'completed', 'operation_id': operation,
              'forward': [], 'backward': []}
    path = tmp_path / ('sfs_run_' + operation + '.json')
    raw = json.dumps({**record, 'archived_at': '2026-10-29T00:00:00+00:00'}, indent=2).encode()
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    assert sfs_evidence.archive_sfs_record(tmp_path, record) == path
    assert path.read_bytes() == raw
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    with pytest.raises(ValueError, match='different evidence'):
        sfs_evidence.archive_sfs_record(tmp_path, {**record, 'status': 'error'})
    assert path.read_bytes() == raw


def test_new_archive_retry_preserves_published_bytes_and_hash(tmp_path):
    record = {'schema_version': 2, 'status': 'completed', 'operation_id': str(uuid.uuid4()),
              'forward': [], 'backward': []}
    path = sfs_evidence.archive_sfs_record(tmp_path, record)
    raw = path.read_bytes()
    assert b'\n' not in raw
    assert sfs_evidence.archive_sfs_record(tmp_path, record) == path
    assert path.read_bytes() == raw
    assert read_recorded_sfs(path)['operation_id'] == record['operation_id']


def test_colliding_encoded_keys_remain_rejected_by_both_record_formats(tmp_path):
    path = tmp_path / 'checkpoint.json'
    record = {'status': 'running', 'nested': {1: 'first', '1': 'second'}}
    path.write_text(json.dumps(record, indent=2))
    with pytest.raises(ValueError, match='record_malformed'):
        read_recorded_sfs(path)
    sfs_evidence.write_sfs_record(path, record)
    with pytest.raises(ValueError, match='record_malformed'):
        read_recorded_sfs(path)
