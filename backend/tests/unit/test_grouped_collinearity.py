"""Independent determinant references, category invariance and exact native evidence."""
import json
import pickle
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from rest_framework.test import APIClient

from modeling.collinearity import META, write_snapshot
from modeling.execution_artifacts import begin_execution, digest_file, publish_execution
from modeling.grouped_collinearity import ARRAY, METHOD, _basis, group_metric, load_snapshot, snapshot

pytestmark = pytest.mark.unit


def fixture_frame():
    rng = np.random.default_rng(28)
    category = np.tile([0, 1, 2, 3], 60)
    return pd.DataFrame({'category': category, 'x': category + rng.normal(size=len(category)),
                         'z': rng.normal(size=len(category))})


def reports(kind='label_encoding'):
    return [{'feature': 'category', 'mapping': {'type': kind}}]


def determinant_reference(frame):
    # Independent full-rank treatment contrasts, rather than the implementation's SVD bases.
    dummies = pd.get_dummies(frame.category, dtype=float).iloc[:, 1:].to_numpy()
    design = np.column_stack([dummies, frame[['x', 'z']].to_numpy()])
    correlation = np.corrcoef(design, rowvar=False)
    df = dummies.shape[1]
    return np.linalg.det(correlation[:df, :df]) * np.linalg.det(correlation[df:, df:]) / np.linalg.det(correlation)


@pytest.mark.parametrize('kind', ['label_encoding', 'ordinal_encoding', 'manual_grouping', 'native_categorical'])
def test_nominal_groups_match_independent_full_rank_determinant(kind):
    frame = fixture_frame()
    if kind == 'native_categorical':
        frame.category = pd.Categorical(frame.category.map(str))
    summary, _ = snapshot(frame, reports(kind))
    group = summary['groups']['category']
    assert summary['status'] == 'available' and group['df'] == 3
    assert group['gvif'] == pytest.approx(determinant_reference(frame), rel=1e-10)
    assert group['adjusted_gvif'] == pytest.approx(group['gvif'] ** (1 / 6))
    assert summary['groups']['x']['df'] == 1


@pytest.mark.parametrize('mapping', [[40, -2, 9, 100], ['d', 'b', 'a', 'c']])
def test_arbitrary_codes_row_order_and_numeric_affine_changes_preserve_metrics(mapping):
    original = fixture_frame()
    changed = original.copy()
    changed.category = changed.category.map(dict(enumerate(mapping)))
    changed.x = -20 * changed.x + 1e4
    changed.z = 9 * changed.z - 11
    changed = changed.sample(frac=1, random_state=28)[['z', 'category', 'x']]
    a, _ = snapshot(original, reports())
    b, _ = snapshot(changed, reports())
    for name in a['groups']:
        assert a['groups'][name]['gvif'] == pytest.approx(b['groups'][name]['gvif'], rel=1e-10)
        assert a['groups'][name]['df'] == b['groups'][name]['df']


@pytest.mark.parametrize('drop_reference', [False, True])
def test_full_or_reference_one_hot_groups_do_not_inflate_internal_redundancy(drop_reference):
    frame = fixture_frame()
    dummies = pd.get_dummies(frame.category, prefix='c', dtype=float)
    if drop_reference:
        dummies = dummies.iloc[:, 1:]
    # A similarly prefixed numeric column is not incorrectly folded into the group.
    encoded = pd.concat([dummies, frame[['x', 'z']].rename(columns={'z': 'c_numeric'})], axis=1)
    report = [{'feature': 'category', 'mapping': {'type': 'one_hot_encoding', 'columns': list(dummies)}}]
    summary, _ = snapshot(encoded, report)
    group = summary['groups']['category']
    assert group['status'] == 'finite' and group['df'] == 3
    assert group['gvif'] == pytest.approx(determinant_reference(frame), rel=1e-10)
    assert summary['groups']['c_numeric']['kind'] == 'numeric'
    subset, _ = snapshot(encoded[['c_1', 'x']], report)
    assert subset['groups']['category']['columns'] == ['c_1']
    assert subset['groups']['category']['df'] == 1
    numeric, _ = snapshot(encoded[['x']], report)
    assert numeric['status'] == 'not_applicable'


def test_nonsingular_contrast_basis_changes_preserve_subspace_volume():
    frame = fixture_frame()
    indicators = pd.get_dummies(frame.category, dtype=float).iloc[:, 1:].to_numpy()
    others = _basis(frame[['x', 'z']].to_numpy())
    changed = indicators @ np.array([[1., 2., 0.], [0., 1., 3.], [2., 0., 1.]])
    assert group_metric(_basis(indicators), others)['gvif'] == pytest.approx(determinant_reference(frame), rel=1e-10)
    assert group_metric(_basis(changed), others)['gvif'] == pytest.approx(determinant_reference(frame), rel=1e-10)


def test_binary_group_equals_numeric_vif_and_adjusted_value_is_its_square_root():
    frame = fixture_frame()
    frame.category = (frame.category > 1).astype(int)
    summary, _ = snapshot(frame, reports())
    target = frame.category.to_numpy(dtype=float)
    others = np.column_stack([np.ones(len(frame)), frame[['x', 'z']].to_numpy()])
    residual = target - others @ np.linalg.lstsq(others, target, rcond=None)[0]
    reference = np.sum((target - target.mean()) ** 2) / np.sum(residual ** 2)
    assert summary['groups']['category']['gvif'] == pytest.approx(reference, rel=1e-10)
    assert summary['groups']['category']['adjusted_gvif'] == pytest.approx(np.sqrt(reference))


def test_duplicate_category_groups_and_numeric_partition_dependence_are_unbounded():
    frame = fixture_frame()
    frame['copy'] = frame.category.map({0: 10, 1: -1, 2: 99, 3: 0})
    summary, _ = snapshot(frame, reports() + [{'feature': 'copy', 'mapping': {'type': 'label_encoding'}}])
    for name in ['category', 'copy']:
        assert summary['groups'][name]['status'] == 'unbounded'
        assert summary['groups'][name]['gvif'] is None
    frame = fixture_frame()
    frame.x = frame.category * 5. + 10
    summary, _ = snapshot(frame, reports())
    assert summary['groups']['category']['status'] == summary['groups']['x']['status'] == 'unbounded'
    assert summary['groups']['z']['status'] == 'finite'


def test_missing_constant_unused_levels_and_training_mean_imputation_are_disclosed():
    frame = fixture_frame()
    frame.loc[0, 'category'] = np.nan
    frame.loc[1, 'x'] = np.nan
    summary, _ = snapshot(frame, reports())
    assert summary['groups']['category']['df'] == 4
    assert summary['groups']['category']['support_counts'][0] == 1
    assert summary['preparation']['imputed_counts']['x'] == 1
    frame.category = 0
    summary, _ = snapshot(frame, reports())
    assert summary['groups']['category']['status'] == 'constant'
    assert summary['groups']['category']['df'] == 0
    assert summary['groups']['x']['status'] == 'finite'


def test_balanced_crossed_categories_have_unit_dependence_without_labels():
    frame = pd.DataFrame([(a, b) for _ in range(6) for a in ['a', 'b', 'c'] for b in range(4)], columns=['category', 'other'])
    summary, _ = snapshot(frame, reports() + [{'feature': 'other', 'mapping': {'type': 'native_categorical'}}])
    assert summary['groups']['category']['gvif'] == pytest.approx(1)
    assert summary['groups']['other']['gvif'] == pytest.approx(1)


def test_saturation_and_overflow_are_distinct_from_solver_failure():
    frame = pd.DataFrame({'category': [0, 1, 2], 'x': [0., 1., 0.], 'z': [0., 0., 1.]})
    summary, _ = snapshot(frame, reports())
    assert summary['groups']['category']['status'] == 'unbounded'
    assert summary['groups']['category']['sample_saturated'] is True
    rng = np.random.default_rng(29)
    values = rng.normal(size=(50, 40))
    basis, _ = np.linalg.qr(values - values.mean(axis=0))
    target, perpendicular = basis[:, :20], basis[:, 20:]
    result = group_metric(target, target + 1e-10 * perpendicular)
    assert result['status'] == 'overflow' and result['gvif'] is None
    assert result['log_gvif'] > np.log(np.finfo(float).max)
    assert result['adjusted_gvif'] == pytest.approx(1e10, rel=1e-5)


@pytest.mark.parametrize('kind', ['frequency_encoding', 'target_encoding'])
def test_lossy_encodings_block_the_whole_conditioning_set(kind):
    summary, matrix = snapshot(fixture_frame(), reports(kind))
    assert summary['status'] == 'unavailable' and matrix.shape == (0, 0)
    assert summary['blocked_groups']['category'] == 'original_category_partition_unavailable'
    assert all(row['gvif'] is None for row in summary['groups'].values())


@pytest.mark.parametrize('case', ['overlap', 'duplicate', 'malformed', 'invalid_one_hot', 'unrecorded_text'])
def test_ambiguous_or_invalid_groups_do_not_silently_drop_predictors(case):
    frame = fixture_frame()
    report = reports()
    if case == 'overlap':
        report += [{'feature': 'other', 'mapping': {'type': 'one_hot_encoding', 'columns': ['category']}}]
    elif case == 'duplicate':
        report += reports()
    elif case == 'malformed':
        report[0]['mapping'] = {'type': 'one_hot_encoding', 'columns': 'category'}
    elif case == 'invalid_one_hot':
        report[0]['mapping'] = {'type': 'one_hot_encoding', 'columns': ['category']}
    else:
        frame['unknown'] = 'text'
    summary, _ = snapshot(frame, report)
    assert summary['status'] == 'unavailable'
    assert all(row['gvif'] is None for row in summary['groups'].values())


@pytest.mark.parametrize('bound', ['MAX_WORK', 'MAX_COLUMNS', 'MAX_ROWS'])
def test_budget_precedes_indicator_allocation_or_solves(monkeypatch, bound):
    monkeypatch.setattr('modeling.grouped_collinearity.' + bound, 1)
    with patch('numpy.linalg.svd', side_effect=AssertionError('must not solve')):
        summary, matrix = snapshot(fixture_frame(), reports())
    assert summary['status'] == 'budget_exceeded' and matrix.shape == (0, 0)
    assert summary['budget']['expanded_columns'] == 6
    assert all(row['status'] == 'budget_exceeded' for row in summary['groups'].values())


def test_insufficient_rows_and_solver_failures_have_explicit_states(monkeypatch):
    assert snapshot(fixture_frame().iloc[:1], reports())[0]['reason'] == 'insufficient_rows'
    monkeypatch.setattr(np.linalg, 'svd', lambda *a, **k: (_ for _ in ()).throw(np.linalg.LinAlgError()))
    assert snapshot(fixture_frame(), reports())[0]['reason'] == 'linear_solver_failed'
    assert group_metric(np.ones((2, 1)), np.ones((2, 1)))['reason'] == 'linear_solver_failed'


@pytest.fixture
def archive(db, _use_tmp_media, tmp_path):
    def create():
        frame = fixture_frame()
        source = tmp_path / 'source.csv'
        frame.to_csv(source, index=False)
        execution, root, _ = begin_execution(source)
        summary = write_snapshot(root, 1, execution, frame, reports())
        (root / 'train_data.pkl').write_bytes(b'not a pickle')
        (root / 'final_holdout.pkl').write_bytes(b'sealed outcomes, not a pickle')
        publish_execution(execution, {'status': 'ok', 'file_id': 1, 'execution_id': execution, 'model': {'collinearity': summary}})
        return execution, root
    return create


def reseal(root, relative):
    manifest = json.loads((root / 'manifest.json').read_text())
    path = root / relative
    manifest['files'][relative] = {'sha256': digest_file(path), 'bytes': path.stat().st_size}
    (root / 'manifest.json').write_text(json.dumps(manifest))


def test_exact_native_replay_does_not_read_fitted_state_or_final_outcomes(archive):
    execution, _ = archive()
    archive()  # Newer execution does not replace the requested one.
    with patch.object(pickle, 'load', side_effect=AssertionError('no pickle reads')):
        summary = load_snapshot(1, execution)
    assert summary['execution_id'] == execution and summary['method'] == METHOD
    assert summary['groups']['category']['gvif'] == pytest.approx(determinant_reference(fixture_frame()), rel=1e-10)
    with pytest.raises(ValueError):
        load_snapshot(2, execution)


@pytest.mark.parametrize('case', ['tampered', 'object', 'missing_matrix', 'bad_basis', 'oversized_array', 'extra_entry', 'layout', 'dimensions', 'provenance', 'method', 'identity', 'metric', 'missing_archive'])
def test_malformed_or_tampered_native_evidence_fails_closed(archive, case):
    execution, root = archive()
    if case == 'tampered':
        (root / ARRAY).write_bytes(b'changed')
    elif case == 'missing_archive':
        manifest = json.loads((root / 'manifest.json').read_text())
        manifest['files'].pop(ARRAY)
        (root / 'manifest.json').write_text(json.dumps(manifest))
    elif case in {'object', 'missing_matrix', 'bad_basis', 'oversized_array', 'extra_entry'}:
        values = {'matrix': np.array([object()], dtype=object)} if case == 'object' else {'other': np.zeros(1)} if case == 'missing_matrix' else {'matrix': np.ones((240, 50 if case == 'oversized_array' else 5))}
        if case == 'extra_entry':
            values['extra'] = np.zeros(1)
        np.savez(root / ARRAY, **values)
        reseal(root, ARRAY)
    else:
        metadata = json.loads((root / META).read_text())
        grouped = metadata['grouped']
        if case == 'layout':
            grouped['groups']['x']['slice'] = [0, 1]
        elif case == 'dimensions':
            grouped['budget']['expanded_columns'] = 99
        elif case == 'provenance':
            grouped['groups']['x']['columns'] = ['category']
        elif case == 'method':
            grouped['method'] = 'invented'
        elif case == 'identity':
            grouped['execution_id'] = 'other'
        else:
            grouped['groups']['category']['gvif'] = 1
        (root / META).write_text(json.dumps(metadata))
        reseal(root, META)
    with pytest.raises(ValueError):
        load_snapshot(1, execution)


@pytest.mark.auth_boundary
def test_grouped_api_requires_real_session_csrf_and_exact_supported_identity(archive, django_user_model):
    execution, _ = archive()
    path = '/api/modeling/vif-detail/'
    payload = {'file_id': 1, 'execution_id': execution, 'feature': 'category', 'diagnostic': 'grouped'}
    client = APIClient(enforce_csrf_checks=True)
    assert client.post(path, payload, format='json').status_code == 403
    django_user_model.objects.create_user(username='grouped-test', password='synthetic-grouped-pass')
    token = client.get('/api/auth/session/').json()['csrf_token']
    login = client.post('/api/auth/login/', {'username': 'grouped-test', 'password': 'synthetic-grouped-pass'}, format='json', HTTP_X_CSRFTOKEN=token)
    assert login.status_code == 200
    assert client.post(path, payload, format='json').status_code == 403
    client.credentials(HTTP_X_CSRFTOKEN=login.json()['csrf_token'])
    with patch.object(pickle, 'load', side_effect=AssertionError('no deserialization')):
        response = client.post(path, payload, format='json')
    assert response.status_code == 200 and response.json()['df'] == 3
    assert response.json()['gvif'] == pytest.approx(determinant_reference(fixture_frame()), rel=1e-10)
    assert client.post(path, {**payload, 'feature': 'missing'}, format='json').status_code == 404
    assert client.post(path, {**payload, 'file_id': 2}, format='json').status_code == 409
    assert client.post(path, {**payload, 'execution_id': None}, format='json').status_code == 400
    assert client.post(path, {**payload, 'diagnostic': 'unknown'}, format='json').status_code == 400


@pytest.mark.django_db(transaction=True)
@pytest.mark.auth_boundary
def test_grouped_diagnostics_recheck_current_project_role(archive, django_user_model):
    from access_control.models import Project, ProjectMembership, ProjectPolicy
    from access_control.projects import bind_dataset
    from declaration.models import Declaration

    execution, _ = archive()
    ProjectPolicy.objects.create()
    project = Project.objects.create(name='Grouped evidence')
    dataset = Declaration.objects.create(id=1, name='Grouped', original_name='source.csv', file='source.csv')
    bind_dataset(dataset, project.pk, source='synthetic_fixture')
    user = django_user_model.objects.create_user(username='grouped-reviewer')
    membership = ProjectMembership.objects.create(project=project, actor=user, role='reviewer')
    client = APIClient()
    client.force_login(user)
    path = '/api/modeling/vif-detail/'
    payload = {'file_id': 1, 'execution_id': execution, 'feature': 'category', 'diagnostic': 'grouped'}
    assert client.post(path, payload, format='json').status_code == 200
    membership.active = False
    membership.save()
    with patch('modeling.grouped_collinearity.load_snapshot', side_effect=AssertionError('deny before reading')):
        assert client.post(path, payload, format='json').status_code == 403


def test_assistant_context_preserves_group_method_states_and_limitations():
    from ai_assistant.views import _format_context, SYSTEM_PROMPT

    grouped, _ = snapshot(fixture_frame(), reports())
    grouped['execution_id'] = 'run-a'
    text = _format_context({'grouped_collinearity': grouped}, 'modeling')
    assert 'execution=run-a' in text and METHOD in text
    assert 'df=3' in text and 'state=finite' in text and 'sqrt(VIF), not VIF' in text
    assert 'Sampling uncertainty' in text and 'feature-removal threshold' in text
    assert 'VIF > 5' not in SYSTEM_PROMPT
