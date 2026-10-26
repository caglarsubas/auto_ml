"""Immutable JSON values, raw-byte integrity and historical readability."""
import copy
import hashlib
import json
import math
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from django.conf import settings

from execution_jobs import service, training_search
from modeling import execution_artifacts as artifacts

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def execution(tmp_path, _use_tmp_media):
    source = tmp_path / 'input.csv'
    source.write_text('x,outcome\n1,0\n2,1\n')
    identifier, root, _ = artifacts.begin_execution(source)
    return identifier, root, dict(file_id=42, execution_id=identifier, model={})


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('value', [None, True, 123, -0.0, 1e-300, 1e300,
    'İ🙂\n\t"\\\u0000\ud800', {'features': ['x', 'y'], 'scores': [0., .5, 1.]}])
def test_execution_values_and_recorded_bytes_round_trip(execution, value):
    identifier, root, payload = execution
    payload['model']['value'] = value
    before = copy.deepcopy(payload)
    manifest = artifacts.publish_execution(identifier, payload)
    loaded, recorded = artifacts.load_execution(identifier, 42)
    assert canonical(loaded) == canonical(json.loads(json.dumps(before, indent=2, allow_nan=False)))
    assert canonical(payload) == canonical(before)
    assert recorded == manifest
    raw = (root / 'modeling_status.json').read_bytes()
    assert manifest['files']['modeling_status.json'] == dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    if value == 0. and isinstance(value, float):
        assert math.copysign(1., loaded['model']['value']) == -1.


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), object(), {1, 2}])
def test_invalid_metadata_cannot_publish_a_manifest(execution, value):
    identifier, root, payload = execution
    dataset = (root / 'dataset.csv').read_bytes()
    payload['model']['invalid'] = value
    with pytest.raises((TypeError, ValueError)):
        artifacts.publish_execution(identifier, payload)
    assert not (root / 'manifest.json').exists()
    assert (root / 'dataset.csv').read_bytes() == dataset


def test_cyclic_metadata_cannot_publish_a_manifest(execution):
    identifier, root, payload = execution
    payload['model']['cycle'] = payload
    with pytest.raises(ValueError, match='Circular reference'):
        artifacts.publish_execution(identifier, payload)
    assert not (root / 'manifest.json').exists()


def test_execution_collision_preserves_all_existing_bytes(execution):
    identifier, root, payload = execution
    artifacts.publish_execution(identifier, payload)
    before = snapshot(root)
    with pytest.raises(FileExistsError):
        artifacts.publish_execution(identifier, {**payload, 'model': {'changed': True}})
    assert snapshot(root) == before


@pytest.mark.parametrize('legacy', [False, True])
def test_existing_indented_executions_remain_readable(execution, legacy):
    identifier, root, payload = execution
    payload['model']['values'] = [1, -0., 1e-20, 'reviewed values']
    manifest = artifacts.publish_execution(identifier, payload)
    if legacy:
        path = root / 'modeling_status.json'
        path.write_text(json.dumps(payload, indent=2, allow_nan=False))
        manifest['files'][path.name] = dict(sha256=artifacts.digest_file(path), bytes=path.stat().st_size)
        (root / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False))
    before = snapshot(root)
    loaded, _ = artifacts.load_execution(identifier, 42)
    assert canonical(loaded) == canonical(payload)
    assert snapshot(root) == before


@pytest.mark.parametrize('legacy', [False, True])
def test_equivalent_json_whitespace_still_fails_raw_byte_integrity(execution, legacy):
    identifier, root, payload = execution
    artifacts.publish_execution(identifier, payload)
    path = root / 'modeling_status.json'
    path.write_text(json.dumps(payload, indent=2) if legacy else path.read_text() + '\n')
    assert json.loads(path.read_text()) == payload
    with pytest.raises(ValueError, match='integrity'):
        artifacts.load_execution(identifier, 42)


@pytest.mark.parametrize('value', [date(2026, 10, 27), datetime(2026, 10, 27, tzinfo=timezone.utc), uuid.UUID(int=31)])
def test_assessment_default_conversion_preserves_parent_and_manifest(execution, value):
    identifier, root, parent = execution
    artifacts.publish_execution(identifier, parent)
    before = snapshot(root)
    assessment = uuid.uuid4()
    payload = dict(file_id=42, model={}, assessed_at=value)
    card = dict(independent_review='development only', assessed_at=value)
    location = artifacts.publish_assessment(identifier, assessment, payload, card)
    loaded = artifacts.load_assessment(identifier, assessment, 42)
    assert canonical(loaded) == canonical(json.loads(json.dumps(payload, indent=2, default=str, allow_nan=False)))
    assert json.loads((location / 'model_card.json').read_text()) == json.loads(json.dumps(card, default=str))
    assert all((root / name).read_bytes() == raw for name, raw in before.items())
    manifest = json.loads((location / 'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        raw = (location / name).read_bytes()
        assert expected == dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def test_assessment_collision_preserves_review_and_parent(execution):
    identifier, root, parent = execution
    artifacts.publish_execution(identifier, parent)
    assessment = uuid.uuid4()
    artifacts.publish_assessment(identifier, assessment, dict(file_id=42, model={}), {'review': 'original'})
    before = snapshot(root)
    with pytest.raises(FileExistsError):
        artifacts.publish_assessment(identifier, assessment, dict(file_id=42, model={}), {'review': 'changed'})
    assert snapshot(root) == before


def test_native_runtime_binds_metadata_writer_source():
    name = 'modeling/execution_artifacts.py'
    observed = service.runtime(training_search.KIND)
    assert observed['sources'][name] == hashlib.sha256((Path(settings.BASE_DIR) / name).read_bytes()).hexdigest()
