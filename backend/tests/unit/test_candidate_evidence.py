"""Actual native fits, candidate-specific evidence and adoption/version boundaries."""
import copy
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modeling.booster_adapters import get_adapter, XGBoostAdapter
from modeling.execution_artifacts import begin_execution, load_execution, publish_candidate, publish_execution
from modeling.fit_receipts import input_receipt, receipt_digest, verify_candidate_fit

pytestmark = pytest.mark.unit


def test_parameter_digest_survives_json_integer_key_conversion():
    receipt = {'requested_params': {'class_weight': {0: 1., 2: 2., 10: 3.}}}
    assert receipt_digest(receipt) == receipt_digest(json.loads(json.dumps(receipt)))


@pytest.mark.parametrize('tampered', [False, True])
def test_native_tuning_selection_is_bound_to_candidate_manifest(parent, tampered):
    from tests.unit.test_tuning_evidence import run
    from modeling.tuning_evidence import fit_for_tuning
    execution_id, data, root, current = parent
    parts = (data['X_train'], data['y_train'], data['X_valid'], data['y_valid'], data['validation_context'])
    evidence = run(parts, execution_id=execution_id)
    assert evidence['status'] == 'completed'
    params = evidence['selected_params']
    adapter = fit_for_tuning('xgboost', data['X_train'][['x']], data['y_train'],
                            data['X_valid'][['x']], data['y_valid'], params, task='classification',
                            nthread=1, scale_pos_weight=evidence['scale_pos_weight'], early_stopping_rounds=2,
                            context=data['validation_context'])
    if tampered:
        evidence['search_basis']['configuration']['cv_folds'] = 9
        before = current.read_bytes()
        with pytest.raises(ValueError, match='Tuning evidence does not match'):
            publish_candidate(execution_id, 1, adapter, ['x'], params, 'hyperparameter_search', selection_evidence=evidence)
        assert current.read_bytes() == before
        return
    published = publish_candidate(execution_id, 1, adapter, ['x'], params, 'hyperparameter_search', selection_evidence=evidence)
    status, manifest = load_execution(published['execution_id'], 1)
    assert 'tuning_selection.json' in manifest['files']
    from django.conf import settings
    snapshot = Path(settings.MEDIA_ROOT) / status['model']['tuning_evidence_path']
    assert json.loads(snapshot.read_text()) == evidence
    snapshot.write_text('{}')
    with pytest.raises(ValueError, match='integrity'):
        load_execution(published['execution_id'], 1)


def development(task='classification'):
    rng = np.random.default_rng(23)
    X = pd.DataFrame({'x': rng.normal(size=180), 'unused': rng.normal(size=180)})
    y = pd.Series(X.x * 2 if task == 'regression' else (X.x > 0).astype(int))
    contract = {'class_mapping': [] if task == 'regression' else [{'encoded': 0}, {'encoded': 1}],
                'objective': {'primary_metric': 'rmse' if task == 'regression' else 'roc_auc'}}
    return {'task': task, 'prediction_contract': contract, 'X_train': X.iloc[:120], 'X_valid': X.iloc[120:],
            'y_train': y.iloc[:120], 'y_valid': y.iloc[120:], 'algorithm': 'xgboost',
            'feature_names': list(X.columns), 'split_meta': {'strategy': 'random'},
            'impute_means': {}, 'encoding_report': [], 'validation_context': {
                'frame': X, 'labels': y, 'task': task, 'prediction_contract': contract,
                'target_column': 'outcome', 'split_meta': {'strategy': 'random'},
                'class_weight_policy': 'train_label_ratio'}}


def fitted(data, features=('x',), algorithm='xgboost', rounds=10):
    from modeling.declared_metric import bind_declared_metric
    params = {'task': data['task'], 'objective': 'reg:squarederror' if data['task'] == 'regression' else 'binary:logistic',
              'eval_metric': 'rmse' if data['task'] == 'regression' else 'auc', 'max_depth': 2, 'nthread': 1}
    return get_adapter(algorithm).train(data['X_train'][list(features)], data['y_train'],
        data['X_valid'][list(features)], data['y_valid'], bind_declared_metric(params, data['prediction_contract']),
        num_boost_round=rounds, early_stopping_rounds=3)


@pytest.fixture
def parent(_use_tmp_media, settings, tmp_path):
    data = development()
    source = tmp_path / 'dataset.csv'
    pd.concat([data['X_train'], data['X_valid']]).to_csv(source, index=False)
    execution_id, root, _ = begin_execution(source)
    adapter = fitted(data, ('x', 'unused'), rounds=20)
    model_path = root / 'models' / adapter.model_filename(1)
    adapter.save(str(model_path))
    # The candidate path may copy this file but must never deserialize it.
    holdout = root / 'final_holdout.pkl'
    holdout.write_bytes(b'protected final outcomes: deliberately not a pickle')
    data['holdout_path'] = str(holdout.relative_to(Path(settings.MEDIA_ROOT)))
    data['execution_id'] = execution_id
    train_path = root / 'train_data.pkl'
    train_path.write_bytes(pickle.dumps(data))
    model = {'task': data['task'], 'prediction_contract': data['prediction_contract'],
             'model_path': str(model_path.relative_to(Path(settings.MEDIA_ROOT))),
             'train_data_path': str(train_path.relative_to(Path(settings.MEDIA_ROOT))),
             'holdout_path': data['holdout_path'], 'selected_features': ['x', 'unused'],
             'score': .999, 'leakage_scan': {'parent': True}, 'shap_plot': 'parent-specific',
             'test_auc': .999, 'cv': {'parent': True}, 'split': {'n_test': 40}}
    status = {'status': 'ok', 'file_id': 1, 'execution_id': execution_id, 'model': model}
    publish_execution(execution_id, status)
    current = Path(settings.MEDIA_ROOT) / 'modeling' / '1_status.json'
    current.parent.mkdir(exist_ok=True)
    current.write_text(json.dumps(status))
    return execution_id, data, root, current


@pytest.mark.parametrize('algorithm', ['xgboost', 'lightgbm', 'catboost'])
@pytest.mark.parametrize('task', ['classification', 'regression'])
def test_real_booster_receipts_bind_inputs_and_actual_budget(algorithm, task):
    data = development(task)
    adapter = fitted(data, algorithm=algorithm)
    receipt = verify_candidate_fit(adapter, data, ['x'])
    assert receipt['algorithm'] == algorithm and receipt['task'] == task
    assert receipt['num_boost_round'] == 10 and receipt['early_stopping_rounds'] == 3
    assert receipt['validation_role'] == 'early_stopping'
    assert receipt['runtime']['packages'][algorithm]
    changed = copy.deepcopy(data)
    changed['X_train'].iloc[0, 0] += 1
    with pytest.raises(ValueError, match='train inputs differ'):
        verify_candidate_fit(adapter, changed, ['x'])
    adapter.fit_receipt['num_boost_round'] = 100
    with pytest.raises(ValueError, match='receipt contradicts'):
        verify_candidate_fit(adapter, data, ['x'])


@pytest.mark.parametrize('algorithm', ['logistic_regression', 'scorecard', 'isolation_forest'])
def test_alternate_receipts_preserve_configuration_and_task(algorithm):
    from modeling.alt_pipelines import get_alt_adapter
    data = development()
    params = {'class_weight': {0: 1., 1: 2.}} if algorithm != 'isolation_forest' else {}
    adapter = get_alt_adapter(algorithm).train(data['X_train'], data['y_train'], data['X_valid'], data['y_valid'], params)
    data['task'] = 'anomaly' if algorithm == 'isolation_forest' else 'classification'
    receipt = verify_candidate_fit(adapter, data, ['x', 'unused'])
    assert receipt['validation_role'] == 'not_used_by_fitter'
    assert receipt['num_boost_round'] is None
    params['class_weight'] = {0: 1000}
    assert receipt['requested_params'].get('class_weight') != params['class_weight']


def test_input_receipts_bind_row_order_labels_and_category_semantics():
    X = pd.DataFrame({'category': pd.Categorical(['a', 'b', 'a']), 'x': [1., 2., 3.]}, index=[7, 2, 9])
    y = pd.Series([0, 1, 0], index=X.index)
    original = input_receipt(X, y)
    assert input_receipt(X.iloc[::-1], y.iloc[::-1]) != original
    assert input_receipt(X[['x', 'category']], y) != original
    assert input_receipt(X, 1 - y) != original
    changed = X.copy()
    changed.category = changed.category.cat.reorder_categories(['b', 'a'])
    assert input_receipt(changed, y) != original
    with pytest.raises(ValueError, match='exact feature row order'):
        input_receipt(X, y.iloc[::-1])
    with pytest.raises(ValueError, match='unique dataframe'):
        input_receipt(X.iloc[[0, 0]], y.iloc[[0, 0]])


@pytest.mark.parametrize('rounds', [1, 10])
def test_candidate_has_fresh_metrics_selected_cv_and_preserves_parent(parent, rounds):
    execution_id, data, root, current = parent
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    adapter = fitted(data, rounds=rounds)
    candidate = publish_candidate(execution_id, 1, adapter, ['x'], {'max_depth': 2}, 'test')
    model = candidate['model']
    assert candidate['adoption_status'] == 'adopted'
    assert json.loads(current.read_text())['execution_id'] == candidate['execution_id']
    assert model['test_auc'] is None
    assert 'score' not in model and 'leakage_scan' not in model and 'shap_plot' not in model
    assert model['valid_auc'] == model['development_validation_metrics']['roc_auc']
    assert model['cv']['configuration']['features'] == ['x']
    assert model['cv']['configuration']['feature_scope'] == 'selected'
    assert model['cv']['configuration']['num_boost_round'] == rounds
    assert 'Post-selection' in model['cv']['evidence_scope']
    for fold in model['cv']['fold_provenance']:
        assert fold['native_fit']['train']['features'] == ['x']
        assert fold['native_fit']['num_boost_round'] == rounds
        assert fold['native_fit']['requested_params'] == adapter.fit_receipt['requested_params']
        assert 'class_weight' not in fold
    assert all(p.read_bytes() == before[p.name] for p in root.iterdir() if p.is_file())
    load_execution(execution_id, 1)
    # A second candidate against the same parent is retained but cannot replace the current child.
    stale = publish_candidate(execution_id, 1, adapter, ['x'], {}, 'stale')
    assert stale['adoption_status'] == 'candidate_only_parent_changed'
    assert stale['execution_id'] != candidate['execution_id']
    assert json.loads(current.read_text())['execution_id'] == candidate['execution_id']
    load_execution(stale['execution_id'], 1)


@pytest.mark.parametrize('mismatch', ['values', 'rows', 'labels', 'features', 'unfitted'])
def test_mismatched_candidate_never_stages_or_adopts(parent, mismatch):
    execution_id, data, root, current = parent
    changed = copy.deepcopy(data)
    if mismatch == 'values':
        changed['X_train'].iloc[0, 0] += 1
    elif mismatch == 'rows':
        changed['X_valid'] = changed['X_valid'].iloc[::-1]
        changed['y_valid'] = changed['y_valid'].iloc[::-1]
    elif mismatch == 'labels':
        changed['y_train'] = 1 - changed['y_train']
    adapter = get_adapter() if mismatch == 'unfitted' else fitted(changed, ('x', 'unused') if mismatch == 'features' else ('x',))
    before, directories = current.read_bytes(), set(root.parent.iterdir())
    with pytest.raises(ValueError, match='inputs differ|lacks a recorded native fit'):
        publish_candidate(execution_id, 1, adapter, ['x'], {}, 'wrong')
    assert current.read_bytes() == before
    assert set(root.parent.iterdir()) == directories


@pytest.mark.parametrize('criterion', ['missing', 'changed'])
def test_candidate_with_unbound_or_changed_fit_metric_cannot_publish(parent, criterion):
    from modeling.declared_metric import bind_declared_metric
    execution_id, data, root, current = parent
    params = {'objective': 'binary:logistic', 'eval_metric': 'auc', 'nthread': 1, 'max_depth': 2}
    if criterion == 'changed':
        contract = {**data['prediction_contract'], 'objective': {'primary_metric': 'brier'}}
        params = bind_declared_metric(params, contract)
    adapter = get_adapter('xgboost').train(data['X_train'][['x']], data['y_train'],
        data['X_valid'][['x']], data['y_valid'], params, num_boost_round=5, early_stopping_rounds=2)
    before, directories = current.read_bytes(), set(root.parent.iterdir())
    with pytest.raises(ValueError, match='accepted metric contract'):
        publish_candidate(execution_id, 1, adapter, ['x'], {}, 'wrong_criterion')
    assert current.read_bytes() == before and set(root.parent.iterdir()) == directories


def test_failed_candidate_cv_cannot_publish(parent, monkeypatch):
    execution_id, data, root, current = parent
    def failed(*args, **kwargs):
        raise ValueError('Declared validation cannot be reproduced')
    monkeypatch.setattr('modeling.development_assessment.run_development_cv', failed)
    before, directories = current.read_bytes(), set(root.parent.iterdir())
    with pytest.raises(ValueError, match='cannot be reproduced'):
        publish_candidate(execution_id, 1, fitted(data), ['x'], {}, 'failed')
    assert current.read_bytes() == before and set(root.parent.iterdir()) == directories


def test_expert_adapter_rejected_before_customer_data_access(monkeypatch):
    class ExpertAdapter(XGBoostAdapter):
        pass
    def forbidden(*args):
        raise AssertionError('Must not load customer inputs')
    monkeypatch.setattr('modeling.execution_artifacts.load_execution', forbidden)
    with pytest.raises(ValueError, match='expert execution requires isolation'):
        publish_candidate('untrusted', 1, ExpertAdapter(), ['x'], {}, 'expert')


def test_scorecard_candidate_replaces_parent_with_fresh_scorecard_evidence(parent):
    from modeling.alt_pipelines import get_alt_adapter
    execution_id, data, _, _ = parent
    adapter = get_alt_adapter('scorecard').train(data['X_train'][['x']], data['y_train'],
        data['X_valid'][['x']], data['y_valid'], {'C': .5})
    candidate = publish_candidate(execution_id, 1, adapter, ['x'], {'C': .5}, 'scorecard', adopt=False)
    assert candidate['adoption_status'] == 'candidate_only'
    assert candidate['model']['pipeline_family'] == 'alternate'
    assert candidate['model']['fit_receipt']['effective_params']['C'] == .5
    assert candidate['model']['iv_table'] == adapter.iv_table
    assert candidate['model']['cv']['configuration']['algorithm'] == 'scorecard'
    assert candidate['model']['cv']['configuration']['features'] == ['x']


def test_failed_refit_cannot_reuse_a_previous_fit_receipt():
    data = development()
    adapter = fitted(data)
    with pytest.raises(Exception):
        adapter.train(data['X_train'], data['y_train'], data['X_valid'], data['y_valid'], {'objective': 'invalid'})
    assert adapter.fit_receipt is None
