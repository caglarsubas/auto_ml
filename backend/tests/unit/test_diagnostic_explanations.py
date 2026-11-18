"""Qualification of explanatory limitations through recorded diagnostic entry points."""

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from rest_framework.test import APIRequestFactory

from declaration.models import Declaration
from modeling.crisp_dm import sequential_pattern_evidence
from modeling.crisp_views import CrispSequentialPatternsView
from modeling.execution_artifacts import begin_execution, load_execution, publish_execution
from modeling.views import FeatureExplainabilityView, ModelingStartView
from tests.unit.test_governed_foundation import declaration

pytestmark = pytest.mark.unit


@pytest.fixture
def publish_diagnostics(settings, tmp_path, db):
    settings.MEDIA_ROOT = str(tmp_path)
    source = tmp_path / 'source.csv'
    source.write_text('x,z,outcome\n14,1,0\n12,2,1\n')

    def publish(train, *, contract=None, algorithm='xgboost', encoding_report=(), metadata_encoding_report=()):
        execution, directory, _ = begin_execution(source)
        model = directory / 'models' / 'diagnostic.json'
        model.parent.mkdir()
        model.write_text('{}')
        training = directory / 'development.pkl'
        training.write_bytes(pickle.dumps({
            'algorithm': algorithm,
            'prediction_contract': contract or {'task': 'classification', 'class_mapping': [0, 1]},
            'encoding_report': list(encoding_report),
            'X_train': train,
            'X_train_raw': train,
            'X_valid': train.set_axis([index + 1000 for index in range(len(train))]),
            'X_valid_raw': train.set_axis([index + 1000 for index in range(len(train))]),
        }))
        (directory / 'final_holdout.pkl').write_bytes(b'protected outcomes cannot enter diagnostics')
        publish_execution(execution, {'execution_id': execution, 'file_id': 41, 'model': {
            'model_path': str(model.relative_to(tmp_path)),
            'train_data_path': str(training.relative_to(tmp_path)),
            'encoding_report': list(metadata_encoding_report),
        }})
        return execution

    return publish


def explain(**payload):
    body = {'file_id': 41, 'feature_name': 'x', **payload}
    return FeatureExplainabilityView.as_view()(APIRequestFactory().post('/', body, format='json'))


def sequential(file_id=41, **query):
    return CrispSequentialPatternsView.as_view()(APIRequestFactory().get('/', query), file_id=file_id)


def forbidden(*args, **kwargs):
    raise AssertionError('The unavailable diagnostic attempted to evaluate a model or unverified input.')


@pytest.mark.parametrize('task,classes,algorithm', [
    ('classification', 3, 'xgboost'),
    ('anomaly', 2, 'isolation_forest'),
    ('classification', 2, 'logistic_regression'),
])
def test_unsupported_models_report_reason_before_computing_explanations(publish_diagnostics, monkeypatch, task, classes, algorithm):
    execution = publish_diagnostics(pd.DataFrame({'x': [1., 2.]}),
        contract={'task': task, 'class_mapping': list(range(classes))}, algorithm=algorithm)
    monkeypatch.setattr('modeling.views.xgb.Booster.load_model', forbidden)
    monkeypatch.setattr('modeling.views.shap.TreeExplainer', forbidden)
    response = explain(execution_id=execution)
    assert response.status_code == 409
    assert response.data['status'] == 'unavailable'
    assert response.data['error_code'] == 'interactive_explanation_unsupported'
    assert 'beeswarm' not in response.data and 'partial_dependence' not in response.data


@pytest.mark.parametrize('kind', ['native_categorical', 'label_encoding', 'one_hot_encoding'])
def test_categorical_pdp_blocks_native_and_encoded_category_grids(publish_diagnostics, monkeypatch, kind):
    native = kind == 'native_categorical'
    train = pd.DataFrame({'x': pd.Categorical(['A', 'B']) if native else [0, 1]})
    report = [] if native else [{'feature': 'source_category' if kind == 'one_hot_encoding' else 'x',
        'strategy_applied': kind, 'mapping': {'columns': ['x']} if kind == 'one_hot_encoding' else {}}]
    execution = (publish_diagnostics(train, metadata_encoding_report=report) if kind == 'one_hot_encoding'
                 else publish_diagnostics(train, encoding_report=report))
    monkeypatch.setattr('modeling.views.xgb.Booster.load_model', forbidden)
    monkeypatch.setattr('modeling.views.shap.TreeExplainer', forbidden)
    response = explain(execution_id=execution)
    assert response.status_code == 409
    assert response.data['status'] == 'unavailable' and response.data['error_code'] == 'categorical_pdp_unavailable'
    assert 'category-aware grid' in response.data['error']


def test_multioutput_shap_is_unavailable_without_collapsing_outputs(publish_diagnostics, monkeypatch):
    execution = publish_diagnostics(pd.DataFrame({'x': [1., 2.]}))
    class ModelFixture:
        feature_names = ['x']

        def load_model(self, path):
            pass

    monkeypatch.setattr('modeling.views.xgb.Booster', ModelFixture)
    monkeypatch.setattr('modeling.views.shap.TreeExplainer', lambda *args, **kwargs:
        type('MultiOutputFixture', (), {'shap_values': lambda _, data: np.ones((data.num_row(), 1, 2))})())
    response = explain(execution_id=execution)
    assert response.status_code == 409
    assert response.data['error_code'] == 'single_output_shap_unavailable'
    assert 'beeswarm' not in response.data and 'partial_dependence' not in response.data


def test_historical_diagnostics_report_absent_provenance_before_loading_legacy_inputs(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    historic = tmp_path / 'train_data' / '41_train_data.pkl'
    historic.parent.mkdir()
    historic.write_bytes(b'unverified training and final outcomes')
    monkeypatch.setattr('modeling.views.xgb.Booster.load_model', forbidden)
    monkeypatch.setattr('pandas.read_csv', forbidden)
    monkeypatch.setattr('pickle.load', forbidden)
    response = explain(processed_file='data_files/unverified.csv')
    assert response.status_code == 409
    assert response.data['error_code'] == 'explanation_provenance_unverified'
    response = sequential()
    assert response.status_code == 409
    assert response.data['error_code'] == 'sequential_provenance_unverified'


def test_sequential_api_verifies_exact_training_rows_and_reports_association(publish_diagnostics, settings):
    frame = pd.DataFrame({'event_time': [4, 1, 2, 3], 'sector': ['a', 'a', 'a', 'b'],
                          'state': [1, 0, 0, 0]}, index=[14, 11, 12, 13])
    execution = publish_diagnostics(frame)
    projection = Path(settings.MEDIA_ROOT) / 'modeling' / '41_status.json'
    projection.parent.mkdir()
    projection.write_text(json.dumps({'execution_id': execution}))
    response = sequential()
    assert response.status_code == 200
    report = response.data
    assert report['execution_id'] == execution
    assert report['evidence_partition'] == 'training_only'
    assert report['scope'] == 'associational_near_duplicate_patterns'
    assert 'associations for review' in report['limitation']
    assert report['ordering'] == 'time_column' and report['time_col'] == 'event_time'
    assert report['n_training_rows'] == report['n_rows_scanned'] == 4
    assert report['sample_stride'] == 1 and not report['candidate_limit_reached']
    assert report['n_candidates'] == 2
    assert [(row['row_a'], row['row_b'], row['changed_features']) for row in report['candidates']] == [
        ('12', '13', ['sector']), ('13', '14', ['sector', 'state']),
    ]
    assert sequential(execution_id=execution).data == report
    assert sequential(file_id=42, execution_id=execution).data['error_code'] == 'sequential_execution_unverified'
    response = sequential(execution_id=execution, time_col='wrong')
    assert response.status_code == 400
    assert response.data['error_code'] == 'sequential_order_unavailable'


def test_sequential_scan_reports_sampling_and_candidate_truncation():
    frame = pd.DataFrame({'a': range(801), 'b': [0] * 801, 'candidate_flag': [False] * 801})
    report = sequential_pattern_evidence(frame)
    assert report['time_col'] is None and report['ordering'] == 'input_order'
    assert report['n_training_rows'] == 801 and report['sample_stride'] == 2
    assert report['candidate_limit_reached'] and report['n_rows_scanned'] == 26
    assert len(report['candidates']) == 25 and report['candidates'][0]['row_b'] == '2'
    no_pairs = sequential_pattern_evidence(frame.assign(a=0))
    assert no_pairs['n_rows_scanned'] == 401
    assert not no_pairs['candidate_limit_reached'] and not no_pairs['candidates']


@pytest.mark.django_db
def test_published_combined_importance_retains_heuristic_and_equal_tie_ranks(_use_tmp_media, settings, monkeypatch):
    class TiedShap:
        def shap_values(self, matrix):
            return np.ones(matrix.shape)
    monkeypatch.setattr('modeling.views.shap.TreeExplainer', lambda *args, **kwargs: TiedShap())
    rng = np.random.default_rng(147)
    x = rng.normal(size=160)
    frame = pd.DataFrame({'x': x, 'z': rng.normal(size=len(x)),
                          'outcome': np.where(x > 0, 'bad', 'good')})
    relative = 'data_files/importance.csv'
    frame.to_csv(Path(settings.MEDIA_ROOT) / relative, index=False)
    dataset = Declaration.objects.create(name='importance', original_name='importance.csv', file=relative)
    response = ModelingStartView.as_view()(APIRequestFactory().post('/', {
        'file_id': dataset.pk, 'processed_file': relative, 'algorithm': 'xgboost',
        'business_understanding': declaration(),
    }, format='json'))
    assert response.status_code == 200, response.data
    model = response.data['model']
    retained, _ = load_execution(response.data['execution_id'], dataset.pk)
    rows = retained['model']['selected_features']
    assert len(rows) == 2
    assert retained['model']['diagnostic_limitations'] == model['diagnostic_limitations']
    limitation = model['diagnostic_limitations']['combined_score']
    assert 'ranking heuristic' in limitation and 'validation decisions require separate evidence' in limitation
    assert all(row['shap_percentile'] == 1.0 and row['signed_impact'] == 0 for row in rows)
    from xgboost import Booster
    saved = Booster()
    saved.load_model(Path(settings.MEDIA_ROOT) / model['model_path'])
    assert saved.num_boosted_rounds() == model['best_iteration'] + 1
    gain = saved.get_score(importance_type='gain')
    assert {row['feature']: row['gain'] for row in rows} == {name: gain.get(name, 0.) for name in frame.columns[:-1]}
    assert [row['combined_score'] for row in rows] == sorted((row['combined_score'] for row in rows), reverse=True)
    for row in rows:
        independent_gain_rank = sum(other['gain'] <= row['gain'] for other in rows) / len(rows)
        assert row['gain_percentile'] == independent_gain_rank
        assert row['combined_score'] == pytest.approx(independent_gain_rank ** .5)
