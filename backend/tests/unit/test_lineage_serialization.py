"""Lineage value compatibility, historical bytes and native artifact integrity."""
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from modeling import lineage
from modeling import execution_artifacts as artifacts
from tests.unit.test_candidate_evidence import fitted, parent  # noqa: F401
from tests.unit.test_package_reviews import packaged  # noqa: F401

pytestmark = pytest.mark.unit


def test_legacy_lineage_values_default_conversion_and_historical_readability(_use_tmp_media, settings):
    payload = {'lineage_id': 'stable', 'date': date(2026, 10, 28), 'metrics': {'x': -0., 'nested': [1, 'İ🙂\n']}}
    relative = lineage.save_lineage(1, payload)
    expected = json.loads(json.dumps(payload, indent=2, default=str))
    path = Path(settings.MEDIA_ROOT) / relative
    assert lineage.load_lineage(1) == expected
    assert path.read_text() == json.dumps(payload, separators=(',', ':'), default=str)
    historical = json.dumps(expected, indent=2).encode()
    path.write_bytes(historical)
    assert lineage.load_lineage(1) == expected
    assert path.read_bytes() == historical
    assert payload['date'] == date(2026, 10, 28)


def test_initial_native_lineage_is_bound_to_raw_artifact_bytes(packaged, settings):
    file_id, execution_id, _, _ = packaged
    payload, manifest = artifacts.load_execution(execution_id, file_id)
    path = Path(settings.MEDIA_ROOT) / payload['model']['lineage_path']
    raw = path.read_bytes()
    value = json.loads(raw)
    assert value['execution_id'] == execution_id and value['fit_receipt'] == payload['model']['fit_receipt']
    assert raw == json.dumps(value, separators=(',', ':')).encode()
    assert manifest['files'][path.name] == dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    path.write_bytes(raw + b'\n')
    assert json.loads(path.read_bytes()) == value
    with pytest.raises(ValueError, match='integrity'):
        artifacts.load_execution(execution_id, file_id)


def test_candidate_lineage_retains_parent_bytes_and_rejects_whitespace_tampering(parent, settings):
    identifier, data, root, _ = parent
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    candidate = artifacts.publish_candidate(identifier, 1, fitted(data, rounds=3), ['x'], {'max_depth': 2}, 'test', adopt=False)
    payload, manifest = artifacts.load_execution(candidate['execution_id'], 1)
    path = Path(settings.MEDIA_ROOT) / payload['model']['lineage_path']
    raw = path.read_bytes()
    value = json.loads(raw)
    assert value['parent_execution_id'] == identifier
    assert raw == json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
    assert manifest['files'][path.name] == dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    assert all((root / name).read_bytes() == original for name, original in before.items())
    path.write_text(json.dumps(value, indent=2))
    with pytest.raises(ValueError, match='integrity'):
        artifacts.load_execution(candidate['execution_id'], 1)
