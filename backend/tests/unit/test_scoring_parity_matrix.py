"""Compare batch scores with the values actually used by protected assessment."""

from pathlib import Path
import dataclasses
import pickle

import numpy as np
import pandas as pd
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory

from declaration.models import Declaration
from deployment.deploy_utils import build_score_bundle, score_frame
from deployment.views import DeploymentScoreView
from evaluation import views as evaluation_views
from modeling import development_assessment, views as modeling_views
from modeling.split_contract import save_split_artifact
from tests.unit.test_governed_foundation import declaration
from tests.unit.test_holdout_evidence import assess


pytestmark = [pytest.mark.unit, pytest.mark.django_db]
TOLERANCE = {'atol': 1e-9, 'rtol': 1e-7}


@dataclasses.dataclass(frozen=True)
class Case:
    algorithm: str
    task: str
    classes: int = 0
    calibrator: str | None = None
    encoder: str | None = None

    @property
    def id(self):
        task = 'binary' if self.classes == 2 and self.task == 'classification' else (
            'multiclass' if self.classes > 2 else self.task
        )
        return f'{self.algorithm}-{task}'


MATRIX = [
    Case('xgboost', 'classification', 2, 'isotonic'),
    Case('xgboost', 'classification', 3),
    Case('xgboost', 'regression', encoder='one_hot_encoding'),
    Case('lightgbm', 'classification', 2, 'platt'),
    Case('lightgbm', 'classification', 3),
    Case('lightgbm', 'regression'),
    Case('catboost', 'classification', 2, 'platt'),
    Case('catboost', 'classification', 3),
    Case('catboost', 'regression'),
    Case('logistic_regression', 'classification', 2, 'platt', encoder='ordinal_encoding'),
    Case('scorecard', 'classification', 2, 'platt'),
    Case('isolation_forest', 'anomaly', 2),
]


@pytest.fixture
def bounded_matrix_fit(monkeypatch):
    """Use real model fits with small budgets and omit plots unrelated to scoring."""
    get_adapter = modeling_views.get_adapter
    development_cv = development_assessment.run_development_cv

    def create(algorithm):
        adapter = get_adapter(algorithm)
        native_train = adapter.train

        def train(X_train, y_train, X_valid, y_valid, params, **options):
            return native_train(
                X_train, y_train, X_valid, y_valid, {**params, 'nthread': 1},
                num_boost_round=12, early_stopping_rounds=4,
            )

        adapter.train = train
        adapter.shap_model = lambda: None
        return adapter

    def bounded_cv(context, X, y, algorithm, params, **options):
        return development_cv(
            context, X, y, algorithm, {**params, 'nthread': 1},
            num_boost_round=8, early_stopping_rounds=3,
        )

    monkeypatch.setattr(modeling_views, 'get_adapter', create)
    monkeypatch.setattr(development_assessment, 'run_development_cv', bounded_cv)


def dataset(case):
    length = 1370 if case.calibrator == 'isotonic' else 240
    rng = np.random.default_rng(181)
    group = rng.integers(0, 3, length)
    income = rng.normal(size=length)
    tenure = rng.normal(size=length)
    latent = income + 0.45 * tenure + (group - 1) * 0.65 + rng.normal(size=length)
    if case.task == 'regression':
        outcomes = np.where(latent > 0, 10., 20.)
    elif case.classes == 3:
        outcomes = np.array(['accepted', 'manual', 'rejected'])[np.digitize(latent, [-.5, .5])]
    else:
        outcomes = np.where(latent > 0, 'accepted', 'rejected')
    frame = pd.DataFrame({'income': income, 'segment': np.array(['007', 'north', 'south'])[group],
                          'tenure': tenure, 'outcome': outcomes})
    frame.loc[frame.index[::11], 'tenure'] = np.nan
    frame.loc[frame.index[::13], 'segment'] = None
    frame.loc[frame.index[-23::4], 'segment'] = '999'
    return frame


def capture_scores(monkeypatch, case):
    if case.task == 'anomaly':
        from modeling import alt_pipelines as module
        function = 'evaluate_anomaly_scores'
    else:
        module = evaluation_views
        function = 'evaluate_' + ('regression' if case.task == 'regression' else (
            'multiclass' if case.classes > 2 else 'binary'
        ))
    metric = getattr(module, function)
    scored = []

    def capture(y, predictions, *args, **kwargs):
        scored.append((y.index.copy(), np.asarray(predictions, dtype=float).copy()))
        return metric(y, predictions, *args, **kwargs)

    monkeypatch.setattr(module, function, capture)
    return scored


@pytest.mark.parametrize('case', MATRIX, ids=lambda case: case.id)
def test_assessed_model_matches_exported_scores(case, _use_tmp_media, settings, bounded_matrix_fit, monkeypatch):
    frame = dataset(case)
    frame['Target'] = 1  # An excluded compatibility column distinct from the label.
    relative = 'data_files/scoring-matrix.csv'
    source = Path(settings.MEDIA_ROOT) / relative
    frame.to_csv(source, index=False)
    declaration_file = Declaration.objects.create(name='matrix', original_name=source.name, file=relative)
    file_id = declaration_file.pk
    save_split_artifact(file_id, frame.index[:-23], frame.index[-23:], {'strategy': 'random'})
    data = {
        'file_id': file_id, 'processed_file': relative, 'algorithm': case.algorithm,
        'business_understanding': declaration(case.task, positive='accepted'),
        'excluded_variables': ['Target'],
    }
    if case.encoder:
        data.update(encoding_plan=[{'feature': 'segment', 'user_lom': 'ordinal' if case.encoder == 'ordinal_encoding' else 'nominal',
                                    'encoding_method': case.encoder, 'nunique': 3,
                                    'ranking': ['007', 'north', 'south']}], encoding_use_native=False)
    factory = APIRequestFactory()
    trained = modeling_views.ModelingStartView.as_view()(factory.post('/modeling/start/', data, format='json'))
    assert trained.status_code == 200, trained.data
    model = trained.data['model']
    assert model['prediction_contract']['task'] == case.task
    if case.classes == 2:
        assert model['prediction_contract']['class_mapping'][1] == {'encoded': 1, 'label': 'accepted'}
    assert (model.get('calibration') or {}).get('method') == case.calibrator
    if case.encoder:
        assert any(report['feature'] == 'segment' and report['mapping']['type'] == case.encoder
                   for report in model['encoding_report'])

    scored = capture_scores(monkeypatch, case)
    if case.algorithm == 'logistic_regression':
        load = evaluation_views.load_execution

        def load_with_legacy_name(*args):
            snapshot, manifest = load(*args)
            return {**snapshot, 'model': {**snapshot['model'], 'model_type': 'historical_regressor_name'}}, manifest

        monkeypatch.setattr(evaluation_views, 'load_execution', load_with_legacy_name)
    assessment = assess(file_id, trained.data['execution_id'], threshold=.42)
    assert assessment.status_code == 200, assessment.data
    rows, reference = scored[0]
    assert set(rows) == set(frame.index[-23:])
    evidence = assessment.data['evaluation']
    assert evidence['task'] == case.task and evidence['scores_calibrated'] is bool(case.calibrator)
    bundle = build_score_bundle(file_id, trained.data['execution_id'], evidence['holdout_access_id'])
    bundle_id = bundle['bundle_id']
    features = pd.read_csv(source).loc[rows, ['income', 'segment', 'tenure']]
    assert features['segment'].eq('999').any() and features['segment'].isna().any() and features['tenure'].isna().any()

    output = score_frame(file_id, features, bundle_id)
    assert output['class_mapping'] == model['prediction_contract']['class_mapping']
    assert output['scores_calibrated'] is bool(case.calibrator)
    assert np.asarray(output['scores']).shape == ((len(rows), case.classes) if case.classes > 2 else (len(rows),))
    np.testing.assert_allclose(output['scores'], reference, **TOLERANCE)

    # Reverse both axes and repeat a row without relying on unique frame indices.
    order = [len(rows) - 1, *range(len(rows) - 1, -1, -1)]
    reordered = features.iloc[order, ::-1]
    chunks = [reordered.iloc[:1], reordered.iloc[1:9], reordered.iloc[9:]]
    replay = np.concatenate([score_frame(file_id, chunk, bundle_id)['scores'] for chunk in chunks])
    np.testing.assert_allclose(replay, reference[order], **TOLERANCE)

    upload = SimpleUploadedFile('reordered.csv', reordered.to_csv(index=False).encode(), content_type='text/csv')
    response = DeploymentScoreView.as_view()(factory.post('/deployment/score/', {
        'file_id': file_id, 'bundle_id': bundle_id, 'file': upload,
    }, format='multipart'))
    assert response.status_code == 200, response.data
    np.testing.assert_allclose(response.data['scores'], reference[order], **TOLERANCE)
    assert response.data['manifest_sha256'] == bundle['manifest_sha256']
    assert response.data['assessment_id'] == evidence['holdout_access_id']
    assert response.data['scores_calibrated'] is bool(case.calibrator)
    # Reading a CSV containing only numeric-looking labels must not erase
    # leading zeros or classify an unknown label as a number.
    numeric_looking = features['segment'].isin(['007', '999']) | features['segment'].isna()
    assert features['segment'].eq('007').any() and not numeric_looking.all()
    narrow = SimpleUploadedFile('one-chunk.csv', features.loc[numeric_looking].to_csv(index=False).encode())
    chunk_response = DeploymentScoreView.as_view()(factory.post('/deployment/score/', {
        'file_id': file_id, 'bundle_id': bundle_id, 'file': narrow,
    }, format='multipart'))
    assert chunk_response.status_code == 200, chunk_response.data
    np.testing.assert_allclose(chunk_response.data['scores'], reference[numeric_looking.to_numpy()], **TOLERANCE)

    if case.calibrator:
        with (Path(settings.MEDIA_ROOT) / model['train_data_path']).open('rb') as stream:
            development = pickle.load(stream)
        assert set(development['calibration']['fit_rows']).isdisjoint(rows)
