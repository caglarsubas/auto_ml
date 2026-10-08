"""Behavioral regressions for the first governed execution packet."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from rest_framework.test import APIRequestFactory

from declaration.models import Declaration
from evaluation.eval_utils import evaluate_multiclass, select_development_threshold
from evaluation.views import EvaluationRunView
from modeling.alt_pipelines import SklearnModelAdapter, get_alt_adapter
from modeling.execution_artifacts import begin_execution, load_execution, publish_execution
from modeling.models import HoldoutAccess
from modeling.prediction_contract import PredictionContractError, resolve_prediction_contract
from modeling.split_contract import resolve_modeling_splits, save_split_artifact
from modeling.views import ModelingStartView, ChampionPromoteView, FeatureExplainabilityView

pytestmark = pytest.mark.unit


def declaration(task='classification', positive='bad'):
    return {'problem_type': task, 'objective': 'Predict the stated outcome',
            'population': 'Eligible test applicants', 'prediction_horizon': '12 months',
            'feature_availability': {'default': 'available_at_prediction'},
            'target_contract': {'target_column': 'outcome', 'positive_class': positive,
                                'event_definition': 'Observed event', 'label_maturity': 'Complete 12-month follow-up'},
            'success_criteria': {'primary_metric': 'rmse' if task == 'regression' else 'roc_auc',
                                 'cost_matrix': {'fn_cost': 4, 'fp_cost': 1}}}


def test_declared_regression_with_two_distinct_values():
    frame = pd.DataFrame({'x': range(20), 'outcome': [10., 20.] * 10})
    contract, labels = resolve_prediction_contract(frame, declaration('regression'), 'xgboost')
    assert contract['task'] == 'regression'
    assert set(labels) == {10., 20.}


def test_many_class_classification_and_reversed_positive_meaning():
    frame = pd.DataFrame({'outcome': [f'class-{i}' for i in range(65)] * 2})
    contract, labels = resolve_prediction_contract(frame, declaration(), 'xgboost')
    assert len(contract['class_mapping']) == 65 and labels.nunique() == 65
    binary = pd.DataFrame({'outcome': ['good', 'bad', 'good', 'bad']})
    _, y = resolve_prediction_contract(binary, declaration(positive='good'), 'xgboost')
    assert y.tolist() == [1, 0, 1, 0]


@pytest.mark.parametrize('values,task,algorithm,positive', [
    ([1, None, 0], 'classification', 'xgboost', 1),
    ([1, float('inf'), 0], 'regression', 'xgboost', None),
    ([1, 2, 3], 'regression', 'scorecard', None),
    (['good', 'bad'], 'classification', 'xgboost', None),
])
def test_invalid_labels_and_unsupported_combinations(values, task, algorithm, positive):
    with pytest.raises(PredictionContractError):
        resolve_prediction_contract(pd.DataFrame({'outcome': values}), declaration(task, positive), algorithm)


def test_temporal_inner_split_uses_dates_and_purges_overlapping_labels(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    dates = pd.date_range('2025-01-01', periods=100, freq='D', tz='UTC')
    frame = pd.DataFrame({'date': dates, 'label_end': dates + pd.Timedelta(days=4)})
    y = pd.Series([0, 1] * 50)
    save_split_artifact(1, frame.index[:80][::-1], frame.index[80:],
                        {'strategy': 'oot', 'date_column': 'date', 'label_end_column': 'label_end'})
    tr, va, te, meta = resolve_modeling_splits(frame, y, 1)
    assert frame.loc[tr, 'label_end'].max() < frame.loc[va, 'date'].min()
    assert frame.loc[va, 'label_end'].max() < frame.loc[te, 'date'].min()
    assert meta['membership']['valid'] == list(va)


@pytest.mark.parametrize('train,test', [(list(range(60)), list(range(59, 100))), (list(range(60)) + [999], list(range(60, 100)))])
def test_stale_or_overlapping_split_never_falls_back(settings, tmp_path, train, test):
    settings.MEDIA_ROOT = str(tmp_path)
    frame = pd.DataFrame({'x': range(100)})
    save_split_artifact(1, train, test, {'strategy': 'oot'})
    with pytest.raises(ValueError):
        resolve_modeling_splits(frame, pd.Series([0, 1] * 50), 1)


def test_group_membership_preserved_in_all_partitions(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    frame = pd.DataFrame({'entity': np.repeat(np.arange(20), 5), 'x': range(100)})
    save_split_artifact(1, frame.index[:80], frame.index[80:], {'strategy': 'group', 'group_column': 'entity'})
    tr, va, te, _ = resolve_modeling_splits(frame, pd.Series([0, 1] * 50), 1)
    assert set(frame.loc[tr, 'entity']).isdisjoint(frame.loc[va, 'entity'])
    assert set(frame.loc[tr, 'entity']).isdisjoint(frame.loc[te, 'entity'])


def test_anomaly_scores_invariant_to_chunks_order_and_serialization(tmp_path):
    rng = np.random.default_rng(5)
    X = pd.DataFrame({'x': rng.normal(size=120), 'y': rng.normal(size=120)})
    y = pd.Series([0, 1] * 60)
    adapter = get_alt_adapter('isolation_forest').train(X[:80], y[:80], X[80:], y[80:], {'n_estimators': 30})
    expected = adapter.predict_proba(X[80:])
    single_rows = np.concatenate([adapter.predict_proba(X.iloc[[i]]) for i in range(80, 120)])
    assert np.allclose(expected, single_rows)
    assert np.allclose(adapter.predict_proba(X[80:].iloc[::-1])[::-1], expected)
    path = str(tmp_path / 'model.joblib')
    adapter.save(path)
    assert np.allclose(SklearnModelAdapter.load(path).predict_proba(X[80:]), expected)


@pytest.mark.parametrize('metric', ['log_loss', 'brier', 'f1', 'expected_cost'])
def test_anomaly_contract_rejects_probability_and_unreviewed_policy_metrics(metric):
    business = declaration('anomaly', positive=1)
    business['success_criteria']['primary_metric'] = metric
    with pytest.raises(PredictionContractError, match='incompatible'):
        resolve_prediction_contract(pd.DataFrame({'outcome': [0, 1] * 20}), business, 'isolation_forest')


@pytest.mark.django_db
def test_anomaly_assessment_reports_rankings_without_holdout_threshold_search(_use_tmp_media, settings):
    rng = np.random.default_rng(15)
    frame = pd.DataFrame({'x': rng.normal(size=160), 'outcome': [0, 1] * 80})
    relative = 'data_files/anomaly.csv'
    frame.to_csv(Path(settings.MEDIA_ROOT) / relative, index=False)
    file = Declaration.objects.create(name='anomaly', original_name='anomaly.csv', file=relative)
    factory = APIRequestFactory()
    trained = ModelingStartView.as_view()(factory.post('/modeling/start/', {
        'file_id': file.pk, 'processed_file': relative, 'algorithm': 'isolation_forest',
        'business_understanding': declaration('anomaly', positive=1),
    }, format='json'))
    assert trained.status_code == 200, trained.data
    response = EvaluationRunView.as_view()(factory.post('/evaluation/run/', {
        'file_id': file.pk, 'execution_id': trained.data['execution_id'],
    }, format='json'))
    assert response.status_code == 200, response.data
    evidence = response.data['evaluation']
    assert evidence['task'] == 'anomaly' and evidence['threshold_table'] == []
    assert 'not a probability' in evidence['score_semantics']
    assert 'brier' not in evidence['metrics'] and 'log_loss' not in evidence['metrics']


@pytest.mark.django_db
@pytest.mark.parametrize('task', ['regression', 'classification'])
def test_native_booster_contract_survives_assessment_and_scoring(_use_tmp_media, settings, task):
    """Exercise both sides of the old cardinality heuristic through real XGBoost."""
    from deployment.deploy_utils import build_score_bundle, score_frame
    from modeling.alt_pipelines import load_model_adapter
    import pickle
    rng = np.random.default_rng(32)
    if task == 'regression':
        x = rng.normal(size=240)
        outcomes = np.where(x > 0, 10., 20.)
    else:
        outcomes = np.tile([f'class-{i}' for i in range(65)], 20)
        x = np.tile(np.arange(65), 20) + rng.normal(scale=.1, size=len(outcomes))
    frame = pd.DataFrame({'x': x, 'outcome': outcomes})
    relative = 'data_files/booster.csv'
    frame.to_csv(Path(settings.MEDIA_ROOT) / relative, index=False)
    file = Declaration.objects.create(name='booster', original_name='booster.csv', file=relative)
    factory = APIRequestFactory()
    trained = ModelingStartView.as_view()(factory.post('/modeling/start/', {
        'file_id': file.pk, 'processed_file': relative, 'algorithm': 'xgboost',
        'business_understanding': declaration(task),
    }, format='json'))
    assert trained.status_code == 200, trained.data
    model = trained.data['model']
    assert model['prediction_contract']['task'] == task
    with (Path(settings.MEDIA_ROOT) / model['train_data_path']).open('rb') as stream:
        development = pickle.load(stream)
    assert 'y_test' not in development
    assessed = EvaluationRunView.as_view()(factory.post('/evaluation/run/', {
        'file_id': file.pk, 'execution_id': trained.data['execution_id'],
    }, format='json'))
    assert assessed.status_code == 200, assessed.data
    assert assessed.data['evaluation']['task'] == task
    bundle = build_score_bundle(file.pk)
    scores = np.asarray(score_frame(file.pk, frame[['x']], bundle_id=bundle['bundle_id'])['scores'])
    chunks = np.concatenate([np.asarray(score_frame(file.pk, frame[['x']].iloc[i:i+37])['scores'])
                             for i in range(0, len(frame), 37)])
    assert np.allclose(scores, chunks, atol=1e-9)
    with (Path(settings.MEDIA_ROOT) / model['holdout_path']).open('rb') as stream:
        holdout = pickle.load(stream)
    adapter = load_model_adapter(str(Path(settings.MEDIA_ROOT) / model['model_path']), algorithm='xgboost')
    expected = adapter.predict(holdout['X_test']) if task == 'regression' else adapter.predict_proba(holdout['X_test'])
    assert np.allclose(scores[holdout['X_test'].index], expected, atol=1e-9)
    if task == 'classification':
        assert scores.shape == (len(frame), 65)
        assert len(bundle['manifest']['prediction_contract']['class_mapping']) == 65


def test_execution_packages_preserve_versions_and_detect_tampering(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    source = tmp_path / 'data.csv'
    source.write_text('x,outcome\n1,0\n2,1\n')
    first, root, _ = begin_execution(source)
    publish_execution(first, {'file_id': 1, 'model': {}})
    original = (root / 'dataset.csv').read_bytes()
    source.write_text('x,outcome\n100,0\n200,1\n')
    second, _, _ = begin_execution(source)
    publish_execution(second, {'file_id': 1, 'model': {}})
    assert first != second and (root / 'dataset.csv').read_bytes() == original
    assert load_execution(first, 1)[0]['file_id'] == 1
    (root / 'dataset.csv').write_text('tampered')
    with pytest.raises(ValueError, match='integrity'):
        load_execution(first, 1)


def test_threshold_selection_and_multiclass_evaluation():
    choice, _ = select_development_threshold([0, 0, 1, 1], [0.1, 0.4, 0.5, 0.9], 10, 1)
    assert choice['threshold'] <= .5
    p = np.eye(3) * .8 + .2 / 3
    evaluation = evaluate_multiclass([0, 1, 2], p)
    assert evaluation['metrics']['accuracy'] == 1 and len(evaluation['confusion_matrix']) == 3


@pytest.mark.django_db
def test_real_training_and_assessment_preserve_exact_execution(_use_tmp_media, settings, monkeypatch):
    rng = np.random.default_rng(12)
    x = rng.normal(size=160)
    frame = pd.DataFrame({'x': x, 'category': np.tile(['a', 'b', None, 'c'], 40), 'outcome': np.where(x > 0, 'bad', 'good')})
    relative = 'data_files/processed.csv'
    frame.to_csv(Path(settings.MEDIA_ROOT) / relative, index=False)
    file = Declaration.objects.create(name='test', original_name='processed.csv', file=relative)
    factory = APIRequestFactory()
    def train():
        response = ModelingStartView.as_view()(factory.post('/modeling/start/', {
            'file_id': file.pk, 'processed_file': relative, 'algorithm': 'logistic_regression',
            'business_understanding': declaration(),
            'encoding_plan': [{'feature': 'category', 'user_lom': 'nominal', 'nunique': 3,
                               'encoding_method': 'one_hot_encoding'}], 'encoding_use_native': False,
        }, format='json'))
        assert response.status_code == 200, response.data
        assert response.data['model']['test_auc'] is None
        return response.data
    first = train()
    model_path = Path(settings.MEDIA_ROOT) / first['model']['model_path']
    model_bytes = model_path.read_bytes()
    second = train()
    assert first['execution_id'] != second['execution_id']
    assert model_path.read_bytes() == model_bytes
    import pickle
    with (Path(settings.MEDIA_ROOT) / first['model']['train_data_path']).open('rb') as stream:
        development = pickle.load(stream)
    assert 'y_test' not in development and 'X_test' not in development
    assert set(development['validation_context']['frame'].index).isdisjoint(development['split_meta']['membership']['test'])
    assessment = EvaluationRunView.as_view()(factory.post('/evaluation/run/', {'file_id': file.pk, 'execution_id': first['execution_id']}, format='json'))
    assert assessment.status_code == 200, assessment.data
    evidence = assessment.data['evaluation']
    assert evidence['execution_id'] == first['execution_id']
    assert evidence['threshold_selection_partition'] == 'development_validation'
    assert len(evidence['threshold_table']) == 1
    assert evidence['evidence_status'] == 'exploratory'
    assert HoldoutAccess.objects.filter(execution_id=first['execution_id']).count() == 1
    assert load_execution(first['execution_id'], file.pk)[0]['execution_id'] == first['execution_id']
    from deployment.deploy_utils import build_score_bundle, score_frame
    with pytest.raises(ValueError, match='different execution'):
        build_score_bundle(file.pk)
    assessed_latest = EvaluationRunView.as_view()(factory.post('/evaluation/run/', {'file_id': file.pk, 'execution_id': second['execution_id']}, format='json'))
    assert assessed_latest.status_code == 200, assessed_latest.data
    bundle = build_score_bundle(file.pk)
    inputs = frame[['x', 'category']]
    scores = score_frame(file.pk, inputs)['scores']
    chunks = [score_frame(file.pk, inputs.iloc[i:i + 7])['scores'] for i in range(0, len(frame), 7)]
    assert np.allclose(scores, np.concatenate(chunks))
    assert np.allclose(scores, score_frame(file.pk, inputs.iloc[::-1])['scores'][::-1])
    with (Path(settings.MEDIA_ROOT) / second['model']['holdout_path']).open('rb') as stream:
        holdout = pickle.load(stream)
    from modeling.alt_pipelines import load_model_adapter
    from modeling.calibration_utils import apply_calibrator, load_calibrator
    adapter = load_model_adapter(str(Path(settings.MEDIA_ROOT) / second['model']['model_path']), algorithm='logistic_regression')
    expected = adapter.predict_proba(holdout['X_test'])
    expected = apply_calibrator(load_calibrator(second['model']['calibrator_path'], settings.MEDIA_ROOT), expected)
    assert np.allclose(expected, np.asarray(scores)[holdout['X_test'].index], atol=1e-9)
    unseen = inputs.iloc[:2].copy()
    unseen.category = ['unseen', None]
    unseen.x = [np.nan, .5]
    assert len(score_frame(file.pk, unseen)['scores']) == 2
    with pytest.raises(ValueError, match='Missing required source'):
        score_frame(file.pk, inputs[['x']])
    older_manifest = (Path(settings.MEDIA_ROOT) / bundle['bundle_path']) / 'manifest.json'
    older_bytes = older_manifest.read_bytes()
    rebuilt = build_score_bundle(file.pk)
    assert rebuilt['bundle_id'] != bundle['bundle_id']
    assert older_manifest.read_bytes() == older_bytes
    assert np.allclose(scores, score_frame(file.pk, inputs, bundle_id=bundle['bundle_id'])['scores'])
    stale = ChampionPromoteView.as_view()(factory.post('/modeling/champion/',
        {'file_id': file.pk, 'execution_id': first['execution_id'], 'features': ['x']}, format='json'))
    assert stale.status_code == 409
    adopted = ChampionPromoteView.as_view()(factory.post('/modeling/champion/',
        {'file_id': file.pk, 'execution_id': second['execution_id'], 'features': ['x']}, format='json'))
    assert adopted.status_code == 200, adopted.data
    assert adopted.data['champion']['execution_id'] != second['execution_id']
    assert adopted.data['champion']['production_use_approved'] is False
    def broken_calibrator(*args):
        raise ValueError('invalid calibration artifact')
    monkeypatch.setattr('modeling.calibration_utils.apply_calibrator', broken_calibrator)
    with pytest.raises(ValueError, match='uncalibrated scoring is blocked'):
        score_frame(file.pk, inputs, bundle_id=bundle['bundle_id'])


@pytest.mark.parametrize('calibrator', [None, object()])
def test_invalid_calibrator_cannot_return_raw_scores(calibrator):
    from modeling.calibration_utils import apply_calibrator
    with pytest.raises(ValueError):
        apply_calibrator(calibrator, [.1, .9])


@pytest.mark.parametrize('mode', ['apply', 'exploratory'])
def test_expert_python_never_runs_in_controller_when_isolation_is_unavailable(monkeypatch, mode):
    from ai_assistant import action_executor
    def forbidden_load(*args, **kwargs):
        raise AssertionError('Unapproved code must not even load customer data.')
    monkeypatch.setattr(action_executor, '_load_dataframe', forbidden_load)
    result = action_executor.dispatch_action(123, 'execute_code', {'code': "df['x'] = 1", 'mode': mode})
    assert result['status'] == 'error'
    assert result['error_code'] == 'expert_isolation_unavailable'
    assert result['changes'] is None


def test_assessment_evidence_detects_tampering(settings, tmp_path):
    from modeling.execution_artifacts import publish_assessment, load_assessment
    import uuid
    settings.MEDIA_ROOT = str(tmp_path)
    source = tmp_path / 'data.csv'
    source.write_text('x,outcome\n1,0\n2,1\n')
    execution, _, _ = begin_execution(source)
    publish_execution(execution, {'file_id': 3, 'model': {}})
    receipt = str(uuid.uuid4())
    payload = {'file_id': 3, 'evaluation': {}, 'model_card': {}}
    root = publish_assessment(execution, receipt, payload, {})
    assert load_assessment(execution, receipt, 3) == payload
    (root / 'model_card.json').write_text('{"modified": true}')
    with pytest.raises(ValueError, match='integrity'):
        load_assessment(execution, receipt, 3)


def test_fold_local_imputation_and_temporal_hpo_provenance():
    from modeling.development_validation import development_folds, prepare_fold
    from modeling.hyperparam_utils import _evaluate_config
    n = 100
    frame = pd.DataFrame({'x': np.tile([0., 1.], n // 2), 'date': pd.date_range('2025-01-01', periods=n), 'outcome': [0, 1] * (n // 2)})
    context = {'frame': frame, 'labels': frame.outcome, 'target_column': 'outcome', 'task': 'classification',
               'excluded_features': ['date'], 'split_meta': {'strategy': 'oot', 'split_config': {'date_column': 'date'}}}
    train, valid = next(development_folds(context, frame.index, frame.outcome, 2))
    frame.loc[valid, 'x'] = np.nan
    X_tr, X_va, receipt = prepare_fold(context, train, valid, ['x'])
    assert X_va.x.tolist() == [X_tr.x.mean()] * len(valid)
    frame.loc[valid, 'x'] = np.tile([0., 1.], (len(valid) + 1) // 2)[:len(valid)]
    trial = _evaluate_config(frame[['x']], frame.outcome, frame[['x']].iloc[-20:], frame.outcome.iloc[-20:],
                             {'max_depth': 2, 'n_estimators': 10}, 2, False, 1, .5,
                             validation_context=context)
    assert len(trial['validation_provenance']) == 2
    for fold in trial['validation_provenance']:
        assert frame.loc[fold['train_rows'], 'date'].max() < frame.loc[fold['valid_rows'], 'date'].min()


def test_categorical_code_order_does_not_enter_vif():
    from modeling.diagnostics import numeric_collinearity_frame
    data = pd.DataFrame({'x': [1., 2., 3.], 'category': pd.Categorical(['a', 'b', 'c'], categories=['a', 'b', 'c'])})
    reversed_codes = data.copy()
    reversed_codes.category = reversed_codes.category.cat.reorder_categories(['c', 'b', 'a'])
    pd.testing.assert_frame_equal(numeric_collinearity_frame(data), numeric_collinearity_frame(reversed_codes))
    assert numeric_collinearity_frame(data).columns.tolist() == ['x']
    encoded = pd.DataFrame({'x': [1., 2., 3.], 'category': [0, 1, 2]})
    permuted = encoded.copy()
    permuted.category = [2, 0, 1]
    report = [{'feature': 'category', 'strategy_applied': 'label_encoding'}]
    pd.testing.assert_frame_equal(numeric_collinearity_frame(encoded, report), numeric_collinearity_frame(permuted, report))


def test_feature_diagnostics_use_verified_development_rows_only(settings, tmp_path, monkeypatch):
    import pickle
    from modeling.booster_adapters import fit_booster
    settings.MEDIA_ROOT = str(tmp_path)
    frame = pd.DataFrame({'x': np.linspace(-2, 2, 30), 'outcome': ['good'] * 15 + ['bad'] * 15})
    source = tmp_path / 'source.csv'
    frame.to_csv(source, index=False)
    contract, y = resolve_prediction_contract(frame, declaration(), 'xgboost')
    execution, root, _ = begin_execution(source)
    X = frame[['x']]
    train = pd.Index([i for i in range(25) if i % 5])
    valid = pd.Index([i for i in range(25) if not i % 5])
    adapter = fit_booster('xgboost', X.loc[train], y.loc[train], X.loc[valid], y.loc[valid], {'n_estimators': 12}, early_stopping_rounds=3)
    model = root / 'models' / adapter.model_filename(8)
    adapter.save(str(model))
    data = {'algorithm': 'xgboost', 'task': 'classification', 'prediction_contract': contract,
            'X_train': X.loc[train], 'X_valid': X.loc[valid], 'X_train_raw': X.loc[train], 'X_valid_raw': X.loc[valid],
            'y_train': y.loc[train], 'y_valid': y.loc[valid], 'execution_id': execution}
    path = root / 'development.pkl'
    path.write_bytes(pickle.dumps(data))
    # If the diagnostic attempted to deserialize final evidence, this would fail.
    (root / 'final_holdout.pkl').write_bytes(b'sealed outcomes: deliberately not a pickle')
    publish_execution(execution, {'file_id': 8, 'execution_id': execution, 'model': {
        'model_path': str(model.relative_to(tmp_path)), 'train_data_path': str(path.relative_to(tmp_path))}})
    def no_mutable_csv(*args, **kwargs):
        raise AssertionError('Diagnostics cannot read the full processed dataset.')
    monkeypatch.setattr(pd, 'read_csv', no_mutable_csv)
    response = FeatureExplainabilityView.as_view()(APIRequestFactory().post('/modeling/feature-explainability/',
        {'file_id': 8, 'execution_id': execution, 'feature_name': 'x', 'n_samples': 40}, format='json'))
    assert response.status_code == 200, response.data.get('error')
    assert response.data['evidence_partition'] == 'development_only'
    assert len(response.data['beeswarm']['feature_values_raw']) == 25
