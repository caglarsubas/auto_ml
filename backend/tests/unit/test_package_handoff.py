"""Exact package selection, publication, integrity and immutable scoring receipts."""
import io
import json
import pickle
import uuid
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from rest_framework.test import APIRequestFactory

from declaration.models import Declaration
from deployment import deploy_utils
from deployment.deploy_utils import assess_file_deploy_readiness, build_score_bundle, build_deployment_pack_zip, bundle_dir, score_frame
from deployment.views import DeploymentBundleView, DeploymentPackView, DeploymentScoreView, DeploymentStatusView
from evaluation.views import EvaluationPackView
from modeling.execution_artifacts import digest_file, execution_root
from modeling.views import ModelingStartView
from tests.unit.test_holdout_evidence import assess, declaration, trained  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def packaged(trained):
    file_id, model = trained
    response = assess(file_id, model['execution_id'])
    assert response.status_code == 200, response.data
    assessment_id = response.data['evaluation']['holdout_access_id']
    return file_id, model['execution_id'], assessment_id, build_score_bundle(file_id)


def rows():
    return pd.DataFrame({'x': [1., 2., 3.], 'other': [2., 1., 0.]})


def test_readiness_and_original_evidence_ignore_mutable_content(packaged, settings):
    file_id, execution_id, assessment_id, first = packaged
    projection = Path(settings.MEDIA_ROOT) / 'evaluation' / f'{file_id}_evaluation.json'
    modified = json.loads(projection.read_text())
    modified['evaluation']['metrics'] = {}
    modified['evaluation']['leakage_scan'] = {'n_high': 99}
    projection.write_text(json.dumps(modified))
    (Path(settings.MEDIA_ROOT) / 'lineage' / f'{file_id}_lineage.json').write_text('{}')
    assert assess_file_deploy_readiness(file_id)['ready']
    bundle = build_score_bundle(file_id, execution_id, assessment_id)
    out = Path(bundle_dir(file_id, bundle['bundle_id']))
    original = execution_root(execution_id) / 'assessments' / assessment_id
    for name in ('evaluation.json', 'model_card.json'):
        assert (out / name).read_bytes() == (original / name).read_bytes()
    assert bundle['manifest']['production_use_approved'] is False
    result = score_frame(file_id, rows(), first['bundle_id'])
    assert (result['execution_id'], result['assessment_id'], result['manifest_sha256']) == (execution_id, assessment_id, first['manifest_sha256'])


def test_historical_assessment_packages_do_not_replace_current_bundle(packaged):
    file_id, execution_id, old_assessment, first = packaged
    new = assess(file_id, execution_id, threshold=.7)
    current = build_score_bundle(file_id)
    historical = build_score_bundle(file_id, execution_id, old_assessment)
    assert historical['adoption_status'] == 'version_only_current_changed'
    assert deploy_utils.bundle_summary(file_id)['bundle_id'] == current['bundle_id']
    assert current['assessment_id'] == new.data['evaluation']['holdout_access_id']
    assert score_frame(file_id, rows(), first['bundle_id'])['scores'] == score_frame(file_id, rows(), historical['bundle_id'])['scores']


def test_changes_during_staging_cannot_adopt_a_stale_package(packaged, settings, monkeypatch):
    file_id, execution_id, assessment_id, first = packaged
    original = deploy_utils.verify_bundle
    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        path = Path(settings.MEDIA_ROOT) / 'modeling' / f'{file_id}_status.json'
        projected = json.loads(path.read_text())
        projected['execution_id'] = str(uuid.uuid4())
        path.write_text(json.dumps(projected))
        return result
    monkeypatch.setattr(deploy_utils, 'verify_bundle', change)
    later = build_score_bundle(file_id, execution_id, assessment_id)
    assert later['adoption_status'] == 'version_only_current_changed'
    assert json.loads((Path(settings.MEDIA_ROOT) / 'deployment_bundles' / str(file_id) / 'current.json').read_text())['bundle_id'] == first['bundle_id']


def test_failed_staging_leaves_no_version_or_current_change(packaged, settings, monkeypatch):
    file_id, execution_id, assessment_id, first = packaged
    parent = Path(settings.MEDIA_ROOT) / 'deployment_bundles' / str(file_id)
    versions = set((parent / 'versions').iterdir())
    pointer = (parent / 'current.json').read_bytes()
    def fail(*args, **kwargs):
        raise ValueError('simulated staging failure')
    monkeypatch.setattr(deploy_utils, 'verify_bundle', fail)
    with pytest.raises(ValueError, match='staging failure'):
        build_score_bundle(file_id, execution_id, assessment_id)
    assert set((parent / 'versions').iterdir()) == versions
    assert (parent / 'current.json').read_bytes() == pointer
    assert not list(parent.glob('.staging-*'))


def test_package_request_resumes_after_publication_without_readopting_over_newer_bundle(packaged, settings, monkeypatch):
    file_id, execution, assessment, initial = packaged
    request_id = str(uuid.uuid4())
    parent = Path(settings.MEDIA_ROOT) / 'deployment_bundles' / str(file_id)
    pointer = parent / 'current.json'

    def interrupt(source, destination):
        assert destination == pointer
        assert source.parent.name == request_id and source.is_file()
        raise OSError('interrupted adoption')

    with monkeypatch.context() as patch:
        patch.setattr(deploy_utils, 'replace_projection', interrupt)
        with pytest.raises(OSError, match='interrupted adoption'):
            build_score_bundle(file_id, execution, assessment, request_id=request_id)
    assert deploy_utils.bundle_summary(file_id)['bundle_id'] == initial['bundle_id']
    published = deploy_utils.bundle_summary(file_id, request_id)
    resumed = build_score_bundle(file_id, execution, assessment, request_id=request_id)
    assert resumed['manifest_sha256'] == published['manifest_sha256']
    assert resumed['adoption_status'] == 'adopted'
    assert deploy_utils.bundle_summary(file_id)['bundle_id'] == request_id
    before = set((parent / 'versions').iterdir())

    with monkeypatch.context() as patch:
        patch.setattr(deploy_utils, 'replace_projection', lambda *_: pytest.fail('replayed an adopted pointer'))
        replayed = build_score_bundle(file_id, execution, assessment, request_id=request_id)
    assert replayed == resumed and set((parent / 'versions').iterdir()) == before
    latest = build_score_bundle(file_id, execution, assessment)
    stale = build_score_bundle(file_id, execution, assessment, request_id=request_id)
    assert stale['bundle_id'] == request_id and stale['adoption_status'] == 'version_only_current_changed'
    assert deploy_utils.bundle_summary(file_id)['bundle_id'] == latest['bundle_id']


@pytest.mark.parametrize('change', ['model_file', 'calibrator_file', 'feature_names', 'assessment_id', 'removed_model', 'removed_calibrator', 'missing_publication', 'size', 'model_bytes', 'path_escape'])
def test_integrity_blocks_before_any_native_deserialization(packaged, monkeypatch, change):
    file_id, _, _, bundle = packaged
    out = Path(bundle_dir(file_id, bundle['bundle_id']))
    path = out / 'manifest.json'
    manifest = json.loads(path.read_text())
    if change in ('model_file', 'calibrator_file'):
        manifest[change] = '../elsewhere.pkl'
    elif change == 'feature_names':
        manifest[change] = list(reversed(manifest[change]))
    elif change == 'assessment_id':
        manifest[change] = str(uuid.uuid4())
    elif change == 'removed_model':
        del manifest['artifact_integrity'][manifest['model_file']]
    elif change == 'removed_calibrator':
        del manifest['artifact_integrity'][manifest['calibrator_file']]
    elif change == 'missing_publication':
        (out / 'publication.json').unlink()
    elif change == 'size':
        manifest['artifact_integrity'][manifest['model_file']]['bytes'] += 1
    elif change == 'model_bytes':
        (out / manifest['model_file']).write_bytes(b'invalid native state')
    elif change == 'path_escape':
        manifest['artifact_integrity']['../elsewhere.pkl'] = {'sha256': '0'*64, 'bytes': 0}
    path.write_text(json.dumps(manifest))
    def forbidden(*args, **kwargs):
        raise AssertionError('No native deserialization is allowed before verification')
    monkeypatch.setattr(pickle, 'load', forbidden)
    with pytest.raises(ValueError):
        score_frame(file_id, rows(), bundle['bundle_id'])
    with pytest.raises(ValueError):
        build_deployment_pack_zip(file_id, bundle['bundle_id'])


def test_required_artifacts_cannot_be_omitted_even_with_matching_receipt(packaged):
    file_id, _, _, bundle = packaged
    out = Path(bundle_dir(file_id, bundle['bundle_id']))
    manifest = json.loads((out / 'manifest.json').read_text())
    del manifest['artifact_integrity'][manifest['model_file']]
    (out / 'manifest.json').write_text(json.dumps(manifest))
    receipt = json.loads((out / 'publication.json').read_text())
    receipt['manifest_sha256'] = digest_file(out / 'manifest.json')
    (out / 'publication.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='Required scoring/evidence artifact'):
        score_frame(file_id, rows(), bundle['bundle_id'])


@pytest.mark.parametrize('omission, message', [
    ('calibration', 'Required fitted calibration'),
    ('impute_means', 'Required fitted encoding or imputation'),
    ('input_text_columns', 'Required scoring input types'),
])
def test_scoring_state_cannot_be_omitted_with_matching_receipt(packaged, monkeypatch, omission, message):
    file_id, _, _, result = packaged
    bundle_id = result['bundle_id']
    out = Path(bundle_dir(file_id, bundle_id))
    manifest_path, publication_path = out / 'manifest.json', out / 'publication.json'
    manifest = json.loads(manifest_path.read_text())
    if omission == 'calibration':
        name = manifest.pop('calibrator_file')
        assert name and manifest['calibration']['fitted']
        del manifest['artifact_integrity'][name]
        (out / name).unlink()
    del manifest[omission]
    manifest_path.write_text(json.dumps(manifest))
    publication = json.loads(publication_path.read_text())
    publication['manifest_sha256'] = digest_file(manifest_path)
    publication_path.write_text(json.dumps(publication))
    monkeypatch.setattr(pickle, 'load', lambda *args, **kwargs: pytest.fail('unexpected native load'))
    with pytest.raises(ValueError, match=message):
        score_frame(file_id, rows(), bundle_id)
    with pytest.raises(ValueError, match=message):
        build_deployment_pack_zip(file_id, bundle_id)


def test_export_uses_calibration_from_training_when_model_metadata_omits_it(trained):
    file_id, result = trained
    execution_id = result['execution_id']
    out = execution_root(execution_id)
    status_path, manifest_path = out / 'modeling_status.json', out / 'manifest.json'
    status = json.loads(status_path.read_text())
    assert status['model'].pop('calibration')['fitted']
    assert status['model'].pop('calibrator_path')
    status_path.write_text(json.dumps(status))
    manifest = json.loads(manifest_path.read_text())
    manifest['files'][status_path.name] = {'sha256': digest_file(status_path), 'bytes': status_path.stat().st_size}
    manifest_path.write_text(json.dumps(manifest))

    response = assess(file_id, execution_id)
    assert response.status_code == 200, response.data
    evaluation = response.data['evaluation']
    assert evaluation['scores_calibrated']
    bundle = build_score_bundle(file_id, execution_id, evaluation['holdout_access_id'])
    assert bundle['manifest']['calibrator_file'] == Path(evaluation['calibration']['calibrator_path']).name
    assert score_frame(file_id, rows(), bundle['bundle_id'])['scores_calibrated']


def test_frozen_numeric_imputation_is_independent_of_missing_chunk_dtype(packaged):
    file_id, _, _, bundle = packaged
    frame = pd.DataFrame({'x': [2.0, None, 3.0], 'other': [None, 4.0, 1.0]})
    bundle_id = bundle['bundle_id']
    full = score_frame(file_id, frame, bundle_id)['scores']
    singles = [score_frame(file_id, pd.DataFrame([record], dtype=object)[['other', 'x']], bundle_id)['scores'][0]
               for record in frame.to_dict('records')]
    assert full == pytest.approx(singles, abs=1e-10)
    with pytest.raises(ValueError, match='feature names must be unique'):
        score_frame(file_id, frame[['x', 'other', 'x']], bundle_id)


def test_frozen_numeric_category_inventory_survives_integer_and_missing_chunks(settings, _use_tmp_media, db):
    frame = pd.DataFrame({'code': [7, 9] * 80, 'x': list(range(80)) * 2,
                          'outcome': ['bad', 'good'] * 80})
    relative = 'data_files/typed-category.csv'
    frame.to_csv(Path(settings.MEDIA_ROOT) / relative, index=False)
    dataset = Declaration.objects.create(name='typed category', original_name='typed-category.csv', file=relative)
    request = APIRequestFactory().post('/modeling/start/', {'file_id': dataset.pk,
        'processed_file': relative, 'algorithm': 'logistic_regression',
        'encoding_plan': [{'feature': 'code', 'encoding_method': 'native'}],
        'business_understanding': declaration()}, format='json')
    model = ModelingStartView.as_view()(request)
    assert model.status_code == 200, model.data
    response = assess(dataset.pk, model.data['execution_id'])
    assert response.status_code == 200, response.data
    bundle = build_score_bundle(dataset.pk)
    assert set(bundle['manifest']['categorical_levels']['code']) == {'7', '9'}
    assert bundle['manifest']['input_numeric_kinds'] == {'code': 'integer'}
    records = [{'code': code, 'x': 20} for code in [7, None, 9, 99]]
    full = score_frame(dataset.pk, pd.DataFrame(records), bundle['bundle_id'])['scores']
    singles = [score_frame(dataset.pk, pd.DataFrame([record]), bundle['bundle_id'])['scores'][0] for record in records]
    assert abs(full[0] - full[2]) > 0.3
    assert full[1] == pytest.approx(full[3], abs=1e-10)
    assert full == pytest.approx(singles, abs=1e-10)


def test_download_is_exact_unique_and_excludes_unrecorded_files(packaged):
    file_id, _, _, bundle = packaged
    out = Path(bundle_dir(file_id, bundle['bundle_id']))
    (out / 'unrecorded-private-data.txt').write_text('must not export')
    raw, name = build_deployment_pack_zip(file_id, bundle['bundle_id'])
    _, second_name = build_deployment_pack_zip(file_id, bundle['bundle_id'])
    assert name != second_name
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert 'unrecorded-private-data.txt' not in archive.namelist()
        assert archive.read('manifest.json') == (out / 'manifest.json').read_bytes()
        assert json.loads(archive.read('manifest.json'))['assessment_id'] == bundle['assessment_id']


def test_api_conflicts_exact_status_pack_and_scoring_receipt(packaged, settings):
    file_id, execution_id, assessment_id, bundle = packaged
    factory = APIRequestFactory()
    for method in ('get', 'post'):
        request = getattr(factory, method)('/deployment/bundle/', {'file_id': file_id, 'execution_id': execution_id}, **({'format': 'json'} if method == 'post' else {}))
        assert DeploymentBundleView.as_view()(request).status_code == 409
    (Path(settings.MEDIA_ROOT) / 'deployment').mkdir(exist_ok=True)
    (Path(settings.MEDIA_ROOT) / 'deployment' / f'{file_id}_bundle.json').write_text('{}')
    status = DeploymentStatusView.as_view()(factory.get('/deployment/status/', {'bundle_id': bundle['bundle_id']}), file_id=file_id)
    assert status.data['manifest_sha256'] == bundle['manifest_sha256']
    result = DeploymentScoreView.as_view()(factory.post('/deployment/score/', {'file_id': file_id, 'bundle_id': bundle['bundle_id'], 'rows': rows().to_dict('records')}, format='json'))
    assert result.status_code == 200, result.data
    receipt = json.loads((Path(settings.MEDIA_ROOT) / result.data['scores_path']).read_text())
    assert (receipt['execution_id'], receipt['assessment_id'], receipt['manifest_sha256']) == (execution_id, assessment_id, bundle['manifest_sha256'])
    exported = DeploymentPackView.as_view()(factory.post('/deployment/pack/', {'file_id': file_id, 'bundle_id': bundle['bundle_id']}, format='json'))
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert json.loads(archive.read('manifest.json'))['bundle_id'] == bundle['bundle_id']
    evaluation_exports = [EvaluationPackView.as_view()(factory.post('/evaluation/pack/', {'file_id': file_id, 'execution_id': execution_id, 'assessment_id': assessment_id}, format='json')) for _ in range(2)]
    assert all(response.status_code == 200 for response in evaluation_exports)
    assert evaluation_exports[0]['Content-Disposition'] != evaluation_exports[1]['Content-Disposition']


def test_historical_unversioned_packages_remain_exportable_with_explicit_limits(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    out = Path(bundle_dir(42))
    out.mkdir(parents=True)
    (out / 'manifest.json').write_text(json.dumps({'schema_version': 2, 'file_id': 42, 'model_file': 'model.json'}))
    (out / 'model.json').write_text('historical model')
    (out / 'unrecorded-private.txt').write_text('private')
    raw, _ = build_deployment_pack_zip(42)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.read('model.json') == b'historical model'
        assert 'unrecorded-private.txt' not in archive.namelist()
        assert b'historically unverified' in archive.read('README.txt')


def test_exact_historical_request_ignores_corrupt_compatibility_projections(packaged, settings):
    file_id, execution_id, assessment_id, bundle = packaged
    root = Path(settings.MEDIA_ROOT)
    (root / 'modeling' / f'{file_id}_status.json').write_text('invalid json')
    (root / 'evaluation' / f'{file_id}_evaluation.json').write_text('invalid json')
    assert assess_file_deploy_readiness(file_id, execution_id, assessment_id)['ready']
    later = build_score_bundle(file_id, execution_id, assessment_id)
    assert later['adoption_status'] == 'version_only_current_changed'
    assert deploy_utils.bundle_summary(file_id)['bundle_id'] == bundle['bundle_id']
