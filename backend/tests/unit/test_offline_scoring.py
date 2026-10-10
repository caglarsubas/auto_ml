"""Independent native CSV replay, identity, runtime and archive boundaries."""
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory

from deployment.deploy_utils import build_deployment_pack_zip
from deployment.offline_verify import verify_package, unpack
from deployment.scoring_receipts import byte_digest
from deployment.views import DeploymentScoreView, DeploymentReceiptView
from tests.unit.test_package_handoff import packaged, rows  # noqa: F401
from tests.unit.test_holdout_evidence import trained  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def verification(packaged, tmp_path, settings):
    file_id, _, _, bundle = packaged
    raw = rows().to_csv(index=False).encode()
    upload = SimpleUploadedFile('approved.csv', raw, content_type='text/csv')
    response = DeploymentScoreView.as_view()(APIRequestFactory().post('/api/deployment/score/',
        {'file_id': file_id, 'bundle_id': bundle['bundle_id'], 'file': upload}, format='multipart'))
    assert response.status_code == 200, response.data
    receipt = Path(settings.MEDIA_ROOT) / response.data['scores_path']
    zipped, _ = build_deployment_pack_zip(file_id, bundle['bundle_id'])
    package = tmp_path / 'package.zip'
    package.write_bytes(zipped)
    csv = tmp_path / 'input.csv'
    csv.write_bytes(raw)
    return {'package': package, 'csv': csv, 'receipt': receipt,
            'package_sha256': byte_digest(zipped), 'receipt_sha256': response.data['receipt_sha256'],
            'manifest_sha256': bundle['manifest_sha256'], 'atol': 1e-12, 'rtol': 1e-12,
            'chunk_sizes': (1, 2), 'trust_native_state': True}


def rewrite_receipt(spec, change):
    data = json.loads(spec['receipt'].read_text())
    change(data)
    spec['receipt'].write_text(json.dumps(data))
    # Explicitly repin altered receipt to exercise semantic checks after digest validation.
    spec['receipt_sha256'] = byte_digest(spec['receipt'].read_bytes())


def test_clean_offline_process_without_database_settings_or_original_artifacts(verification, tmp_path):
    spec = verification
    private = tmp_path / 'private-copy'
    private.mkdir()
    args = []
    for key in ('package', 'csv', 'receipt'):
        target = private / spec[key].name
        target.write_bytes(spec[key].read_bytes())
        args.extend(['--' + key, str(target)])
    for key in ('package_sha256', 'receipt_sha256', 'manifest_sha256', 'atol', 'rtol'):
        args.extend(['--' + key.replace('_', '-'), str(spec[key])])
    output = private / 'evidence.json'
    env = {key: value for key, value in os.environ.items() if not key.startswith(('DJANGO', 'DATABASE', 'POSTGRES', 'REDIS'))}
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
    result = subprocess.run([sys.executable, '-m', 'deployment.offline_verify', *args,
        '--trust-native-state', '--chunk-sizes', '1', '2', '--output', str(output)],
        env=env, cwd=private, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output.read_text())
    assert report['status'] == 'passed' and report['rows'] == 3
    assert [check['chunk_size'] for check in report['checks']] == [3, 1, 2]
    assert all(check['passed'] for check in report['checks'])
    assert not any(report[key] for key in ('model_refit_reproduced', 'assessment_reproduced', 'review_approved', 'production_use_approved'))
    assert json.loads(spec['receipt'].read_text())['scores_calibrated'] is True


@pytest.mark.parametrize('key', ['package', 'csv', 'receipt'])
def test_changed_bytes_block_before_native_state(verification, monkeypatch, key):
    verification[key].write_bytes(verification[key].read_bytes() + b' ')
    monkeypatch.setattr('deployment.offline_verify.score_bundle_directory', lambda *a, **k: pytest.fail('native state loaded before validation'))
    with pytest.raises(ValueError, match='digest'):
        verify_package(**verification)


@pytest.mark.parametrize('change,match', [
    (lambda data: data.update(receipt_schema_version=0), 'version-one'),
    (lambda data: data['input'].update(format='excel'), 'CSV inputs'),
    (lambda data: data['input'].update(bytes=0), 'CSV bytes'),
    (lambda data: data['scoring_runtime'].update(python_version='0.0.0'), 'runtime'),
    (lambda data: data.update(n_scored=99), 'row count'),
    (lambda data: data.update(scores=[float('nan')] * 3), 'finite'),
    (lambda data: data.update(scores=[[.1, .9]]), 'finite'),
    (lambda data: data.update(assessment_id='00000000-0000-0000-0000-000000000000'), 'identities'),
    (lambda data: data.update(manifest_sha256='0' * 64), 'manifest'),
    (lambda data: data.update(class_mapping=['reversed']), 'semantics'),
])
def test_bound_receipt_semantics_and_runtime(verification, change, match):
    rewrite_receipt(verification, change)
    with pytest.raises(ValueError, match=match):
        verify_package(**verification)


def test_numerical_disagreement_records_failed_check_and_declared_tolerance(verification):
    rewrite_receipt(verification, lambda data: data.update(scores=[0., 0., 0.]))
    result = verify_package(**verification)
    assert result['status'] == 'failed'
    assert all(not check['passed'] and check['max_absolute_difference'] > 0 for check in result['checks'])
    assert result['atol'] == result['rtol'] == 1e-12


@pytest.mark.parametrize('override', [
    {'trust_native_state': False}, {'atol': -1}, {'rtol': float('inf')},
    {'atol': True}, {'chunk_sizes': (1,)}, {'chunk_sizes': (0, 2)},
    {'manifest_sha256': 'invalid'},
])
def test_explicit_trust_tolerance_and_batch_requirements(verification, override):
    with pytest.raises(ValueError):
        verify_package(**{**verification, **override})


@pytest.mark.parametrize('member', ['../escape', '/absolute', 'nested/file', 'windows\\file', '..'])
def test_archive_paths_cannot_escape(tmp_path, member):
    archive = tmp_path / 'untrusted.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.writestr(member, 'untrusted')
    with pytest.raises(ValueError, match='regular files'):
        unpack(archive, tmp_path)


def test_archive_links_duplicates_and_expansion_limit(tmp_path, monkeypatch):
    archive = tmp_path / 'untrusted.zip'
    info = zipfile.ZipInfo('link')
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.writestr(info, 'elsewhere')
    with pytest.raises(ValueError, match='regular files'):
        unpack(archive, tmp_path)
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.writestr('same', 'one')
        with pytest.warns(UserWarning):
            zipped.writestr('same', 'two')
    with pytest.raises(ValueError, match='duplicate'):
        unpack(archive, tmp_path)
    monkeypatch.setattr('deployment.offline_verify.MAX_BYTES', 1)
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.writestr('large', 'two')
    with pytest.raises(ValueError, match='expanded byte'):
        unpack(archive, tmp_path)


def test_full_receipt_is_exact_beyond_inline_preview(packaged, settings):
    file_id, _, _, bundle = packaged
    raw = rows().loc[rows().index.repeat(201)].to_csv(index=False).encode()
    response = DeploymentScoreView.as_view()(APIRequestFactory().post('/api/deployment/score/',
        {'file_id': file_id, 'bundle_id': bundle['bundle_id'], 'file': SimpleUploadedFile('large.csv', raw)}, format='multipart'))
    assert response.status_code == 200 and response.data['scores_truncated']
    assert 'scores' not in response.data and len(response.data['scores_preview']) == 500
    exact = DeploymentReceiptView.as_view()(APIRequestFactory().get('/api/deployment/receipts/', {'sha256': response.data['receipt_sha256']}),
        file_id=file_id, batch_id=response.data['batch_id'])
    assert exact.status_code == 200 and len(json.loads(exact.content)['scores']) == 603
    assert byte_digest(exact.content) == response.data['receipt_sha256']
    assert json.loads(exact.content)['input']['sha256'] == byte_digest(raw)


def test_legacy_and_unknown_packages_do_not_gain_offline_qualification(verification):
    with zipfile.ZipFile(verification['package']) as original:
        content = {entry.filename: original.read(entry) for entry in original.infolist()}
    manifest = json.loads(content['manifest.json'])
    manifest['algorithm'] = 'expert_python'
    content['manifest.json'] = json.dumps(manifest).encode()
    publication = json.loads(content['publication.json'])
    publication['manifest_sha256'] = byte_digest(content['manifest.json'])
    content['publication.json'] = json.dumps(publication).encode()
    with zipfile.ZipFile(verification['package'], 'w') as changed:
        for name, raw in content.items():
            changed.writestr(name, raw)
    verification['package_sha256'] = byte_digest(verification['package'].read_bytes())
    verification['manifest_sha256'] = publication['manifest_sha256']
    rewrite_receipt(verification, lambda data: data.update(manifest_sha256=publication['manifest_sha256']))
    with pytest.raises(ValueError, match='registered native'):
        verify_package(**verification)
