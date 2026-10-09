"""Numeric diagnostics: affine invariance, explicit states and immutable inputs."""
import json
import pickle
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from rest_framework.test import APIClient

from modeling.collinearity import ARRAY, META, centered_inputs, detail, load_snapshot, vif, write_snapshot
from modeling.diagnostics import numeric_diagnostic_inputs
from modeling.execution_artifacts import begin_execution, digest_file, publish_execution

pytestmark = pytest.mark.unit


def frame():
    rng = np.random.default_rng(15)
    x = rng.normal(size=240)
    return pd.DataFrame({'x': x, 'y': .7 * x + rng.normal(size=240), 'z': rng.normal(size=240)})


def test_centered_vif_matches_intercept_reference_and_pairwise_formula():
    from statsmodels.api import OLS, add_constant
    data = frame() + 100
    matrix = centered_inputs(data)
    for index, column in enumerate(data):
        reference = 1 / (1 - OLS(data[column], add_constant(data.drop(columns=column))).fit().rsquared)
        assert vif(matrix, index)['vif'] == pytest.approx(reference, rel=1e-10)
    pair = centered_inputs(data[['x', 'y']])
    assert vif(pair, 0)['vif'] == pytest.approx(1 / (1 - np.corrcoef(pair.T)[0, 1] ** 2))
    assert vif(centered_inputs(data[['x']]), 0)['vif'] == pytest.approx(1)


@pytest.mark.parametrize('offset,scale', [(100., 1.), (1e8, -20.), (0., 1e200), (0., 1e-200)])
def test_affine_changes_preserve_dependence(offset, scale):
    data = frame()
    original = centered_inputs(data)
    changed = centered_inputs(data * scale + offset)
    for index in range(3):
        assert vif(changed, index)['vif'] == pytest.approx(vif(original, index)['vif'], rel=1e-8)


def test_large_offset_small_variation_and_opposite_extremes_stay_finite():
    data = pd.DataFrame({'large': 1e15 + np.arange(80) / 8, 'other': np.sin(np.arange(80))})
    assert np.isfinite(centered_inputs(data)).all()
    assert vif(centered_inputs(data), 0)['vif_status'] == 'finite'
    extreme = pd.DataFrame({'x': [-1e308, 1e308, 0., 1e308], 'y': [1., 3., 2., 0.]})
    assert np.isfinite(centered_inputs(extreme)).all()


def test_singular_and_sample_saturated_are_explicit_not_huge_finite_numbers(tmp_path):
    x = np.arange(20.)
    report = write_snapshot(tmp_path, 1, 'run', pd.DataFrame({'x': x, 'duplicate': 2*x+10}))
    assert report['features']['x']['vif_status'] == 'unbounded'
    assert report['features']['x']['vif'] is None
    assert json.loads((tmp_path / META).read_text())['features']['x']['vif'] is None
    data = centered_inputs(pd.DataFrame({'x': [1., 3., 4.], 'y': [4., 1., 7.], 'z': [1., 2., 9.]}))
    assert vif(data, 0)['sample_saturated'] is True
    assert vif(data, 0)['vif_status'] == 'unbounded'
    result = detail(report, centered_inputs(pd.DataFrame({'x': x, 'duplicate': 2*x+10})), 'x')
    assert result['contributions'][0]['vif_without'] == pytest.approx(1)
    assert result['contributions'][0]['vif_drop'] is None


def test_numerically_indistinguishable_and_solver_failure_have_explicit_states(monkeypatch):
    data = frame()[['x', 'y']]
    data['y'] = data.x + 1e-15 * data.y
    assert vif(centered_inputs(data), 0)['vif_status'] == 'unbounded'
    monkeypatch.setattr(np.linalg, 'lstsq', lambda *a, **k: (_ for _ in ()).throw(np.linalg.LinAlgError()))
    result = vif(centered_inputs(frame()), 0)
    assert result['vif'] is None and result['reason'] == 'linear_solver_failed'


@pytest.mark.parametrize('codes', [[0, 1, 2], [8, -20, 3]])
def test_category_permutations_and_encoded_groups_are_excluded(codes):
    data = frame().iloc[:3].copy()
    data['category'] = codes
    data['group_a'] = [1., 0., 1.]
    data['group_b'] = [0., 1., 0.]
    data['group_numeric'] = [4., 8., 3.]
    report = [{'feature': 'category', 'mapping': {'type': 'label_encoding'}},
              {'feature': 'group', 'mapping': {'type': 'one_hot_encoding', 'columns': ['group_a', 'group_b']}}]
    numeric, preparation = numeric_diagnostic_inputs(data, report)
    assert list(numeric) == ['x', 'y', 'z', 'group_numeric']
    assert preparation['excluded'] == dict.fromkeys(['category', 'group_a', 'group_b'], 'excluded_categorical')


@pytest.mark.parametrize('kind', ['ordinal_encoding', 'manual_grouping', 'native_categorical', 'frequency_encoding', 'target_encoding'])
def test_other_category_derived_methods_are_not_numeric_vif(kind):
    numeric, preparation = numeric_diagnostic_inputs(frame(), [{'feature': 'x', 'mapping': {'type': kind}}])
    assert 'x' not in numeric and preparation['excluded']['x'] == 'excluded_categorical'


def test_nonfinite_imputation_and_ineligible_columns_are_disclosed(tmp_path):
    data = pd.DataFrame({'x': pd.Series([1., None, 3.], dtype='Float64'), 'constant': [1., 1., 1.],
                         'missing': [np.inf, np.nan, -np.inf], 'text': ['a', 'b', 'c'], 'flag': [True, False, True]})
    report = write_snapshot(tmp_path, 1, 'run', data)
    assert report['preparation']['imputation_means']['x'] == 2
    assert report['preparation']['imputed_counts']['x'] == 1
    assert report['features']['x']['vif'] == pytest.approx(1)
    for name, state in [('constant', 'constant'), ('missing', 'no_finite_values'), ('text', 'excluded_nonnumeric'), ('flag', 'excluded_nonnumeric')]:
        assert report['features'][name]['vif_status'] == state
    assert numeric_diagnostic_inputs(data.iloc[:1])[1]['excluded']['x'] == 'insufficient_rows'
    assert 'training rows only' in report['preparation']['imputation']


def test_budget_blocks_diagnostic_without_sampling_or_solves(tmp_path, monkeypatch):
    monkeypatch.setattr('modeling.collinearity.MAX_WORK', 1)
    with patch('numpy.linalg.lstsq', side_effect=AssertionError('must not solve')):
        report = write_snapshot(tmp_path, 1, 'run', frame())
    assert report['status'] == 'budget_exceeded' and report['columns'] == list(frame())
    assert report['row_count'] == len(frame())
    assert all(row['vif_status'] == 'budget_exceeded' for row in report['features'].values())


@pytest.fixture
def archive(_use_tmp_media, tmp_path):
    def create(include=True, file_id=1):
        source = tmp_path / 'source.csv'
        frame().to_csv(source, index=False)
        execution_id, root, _ = begin_execution(source)
        if include:
            write_snapshot(root, file_id, execution_id, frame())
        # Verifying manifest bytes is permitted; reading fitted state or final outcomes is not.
        (root / 'train_data.pkl').write_bytes(b'deliberately not a pickle')
        (root / 'final_holdout.pkl').write_bytes(b'sealed outcomes: deliberately not a pickle')
        publish_execution(execution_id, {'status': 'ok', 'file_id': file_id, 'execution_id': execution_id, 'model': {}})
        return execution_id, root
    return create


def reseal(root, relative):
    """Trusted controller fixture: malformed content with a matching integrity manifest."""
    manifest = json.loads((root / 'manifest.json').read_text())
    path = root / relative
    manifest['files'][relative] = {'sha256': digest_file(path), 'bytes': path.stat().st_size}
    (root / 'manifest.json').write_text(json.dumps(manifest))


def test_exact_archive_ignores_mutable_projection_and_never_deserializes(archive, settings):
    from pathlib import Path
    old, _ = archive()
    newer, root = archive()
    projection = Path(settings.MEDIA_ROOT) / 'modeling'
    projection.mkdir(exist_ok=True)
    (projection / '1_status.json').write_text(json.dumps({'execution_id': newer}))
    (projection / '1_train_data.pkl').write_bytes(b'untrusted mutable projection')
    with patch.object(pickle, 'load', side_effect=AssertionError('no pickle reads')):
        summary, matrix = load_snapshot(1, old)
        assert summary['execution_id'] == old
        assert detail(summary, matrix, 'x')['vif_status'] == 'finite'
    with pytest.raises(ValueError, match='identity'):
        load_snapshot(2, old)
    (root / ARRAY).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='integrity'):
        load_snapshot(1, newer)


@pytest.mark.parametrize('malformation', ['object_array', 'missing_matrix', 'invalid_metadata', 'bad_normalization', 'wrong_identity'])
def test_invalid_native_artifacts_fail_closed(archive, malformation):
    execution, root = archive()
    if malformation in ('object_array', 'missing_matrix', 'bad_normalization'):
        arrays = {'matrix': np.array([object()], dtype=object)} if malformation == 'object_array' else {'other': np.zeros(2)} if malformation == 'missing_matrix' else {'matrix': np.ones((240, 3))}
        np.savez(root / ARRAY, **arrays)
        reseal(root, ARRAY)
    else:
        metadata = json.loads((root / META).read_text())
        metadata['columns' if malformation == 'invalid_metadata' else 'execution_id'] = None
        (root / META).write_text(json.dumps(metadata))
        reseal(root, META)
    with pytest.raises(ValueError):
        load_snapshot(1, execution)


def test_legacy_archive_does_not_inherit_new_method(archive):
    execution, _ = archive(include=False)
    with pytest.raises(ValueError, match='Refit a new version'):
        load_snapshot(1, execution)


@pytest.mark.auth_boundary
@pytest.mark.django_db
def test_real_session_csrf_exact_identity_and_missing_feature(archive, django_user_model):
    execution, _ = archive()
    path = '/api/modeling/vif-detail/'
    payload = {'file_id': 1, 'execution_id': execution, 'feature': 'x'}
    client = APIClient(enforce_csrf_checks=True)
    assert client.post(path, payload, format='json').status_code == 403
    django_user_model.objects.create_user(username='diagnostic-test', password='synthetic-diagnostic-pass')
    token = client.get('/api/auth/session/').json()['csrf_token']
    login = client.post('/api/auth/login/', {'username': 'diagnostic-test', 'password': 'synthetic-diagnostic-pass'}, format='json', HTTP_X_CSRFTOKEN=token)
    assert login.status_code == 200
    assert client.post(path, payload, format='json').status_code == 403
    client.credentials(HTTP_X_CSRFTOKEN=login.json()['csrf_token'])
    with patch.object(pickle, 'load', side_effect=AssertionError('must not deserialize')):
        response = client.post(path, payload, format='json')
    assert response.status_code == 200 and response.json()['execution_id'] == execution
    assert client.post(path, {'file_id': 1, 'feature': 'x'}, format='json').status_code == 400
    assert client.post(path, {**payload, 'feature': 'absent'}, format='json').status_code == 404
    assert client.post(path, {**payload, 'file_id': 2}, format='json').status_code == 409


def test_assistant_does_not_render_unbounded_as_missing(monkeypatch):
    from ai_assistant import tool_executor
    monkeypatch.setattr(tool_executor, 'read_vif_decomposition', lambda _: {'x': {'vif': None, 'vif_status': 'unbounded', 'execution_id': 'run-a', 'method': 'centered_scaled_auxiliary_ols_v1', 'limitations': 'No automatic removal gate', 'top_correlations': []}})
    result = tool_executor._handle_get_vif_decomposition(1, {'feature': 'x'})
    assert 'State=unbounded' in result and 'execution=run-a' in result and 'No automatic removal gate' in result
