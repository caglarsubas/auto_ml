"""Independent metric references, real native fits and failed publication paths."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import mean_squared_error, confusion_matrix

from modeling import hyperparam_utils as hp
from modeling.tuning_evidence import resolve_tuning_objective
from tests.unit.test_sfs_objective import data

pytestmark = pytest.mark.unit


def run(parts=None, **options):
    X, y, V, z, context = parts or data()
    space = {name: {'enabled': False} for name in hp.DEFAULT_PARAM_SPACE}
    space['max_depth'] = {'enabled': True, 'min': 1, 'max': 2}
    params = dict(X_train=X, y_train=y, X_test=V, y_test=z, task=context['task'],
                  validation_context=context, param_space=space, fixed_params={'n_estimators': 5},
                  features=['x'], cv_folds=2, n_iter=2, search_method='grid', grid_points_per_param=2,
                  validation_curve_points=2, n_jobs=2, early_stopping_rounds=2, execution_id='source-run')
    params.update(options)
    return hp.run_hyperparam_search_with_progress(**params)


@pytest.mark.parametrize('algorithm', ['xgboost', 'lightgbm', 'catboost'])
@pytest.mark.parametrize('task,metric', [('regression', 'mse'), ('classification', 'expected_cost'), ('classification', 'pr_auc')])
def test_real_tuning_uses_declared_metric_and_retains_fit_and_curve_evidence(algorithm, task, metric):
    parts = data(task, metric)
    parts[-1]['prediction_contract']['objective']['cost_matrix'] = {'fn_cost': 7, 'fp_cost': 2}
    result = run(parts, algorithm=algorithm)
    assert result['status'] == 'completed', result.get('error')
    assert result['selection_objective']['primary_metric'] == metric
    assert result['selection_objective']['direction'] == ('maximize' if metric == 'pr_auc' else 'minimize')
    assert result['n_attempted'] == 2 and result['n_failed'] == 0
    winner = result['trials'][result['selected_trial_index']]
    assert winner['params'] == result['selected_params'] == result['best_points'][metric]['params']
    scores = [trial['cv'][metric]['mean'] for trial in result['trials']]
    assert winner['cv'][metric]['mean'] == (max(scores) if metric == 'pr_auc' else min(scores))
    for trial in result['trials']:
        assert trial['cv'][metric]['n_valid'] == trial['cv'][metric]['n_total'] == 2
        assert len(trial['fold_metrics']) == 2
        for fold in trial['validation_provenance']:
            assert fold['fit_receipt']['train']['features'] == ['x']
            assert fold['fit_receipt']['num_boost_round'] == 5
            assert not set(fold['train_rows']).intersection(fold['valid_rows'])
        assert trial['fit_receipt']['early_stopping_rounds'] == 2
        assert trial['search_basis_sha256'] == result['search_basis']['sha256']
    points = result['validation_curves'][0]['points']
    assert all(point['status'] == 'complete' and len(point['validation_provenance']) == 2 for point in points)
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('task,metric', [('regression', 'mse'), ('classification', 'expected_cost')])
def test_trial_values_match_independent_predictions(task, metric):
    parts = data(task, metric)
    parts[-1]['prediction_contract']['objective']['cost_matrix'] = {'fn_cost': 7, 'fp_cost': 2}
    result = run(parts)
    X, y, V, z, context = parts
    winner = result['trials'][result['selected_trial_index']]
    from modeling.tuning_evidence import fit_for_tuning
    adapter = fit_for_tuning('xgboost', X[['x']], y, V[['x']], z, winner['params'], task=task,
                             nthread=1, scale_pos_weight=result['scale_pos_weight'], early_stopping_rounds=2, context=context)
    p = adapter.predict(V[['x']])
    if task == 'regression':
        reference = mean_squared_error(z, p)
    else:
        tn, fp, fn, tp = confusion_matrix(z, p >= .5, labels=[0, 1]).ravel()
        reference = (fn * 7 + fp * 2) / len(z)
    assert winner['test'][metric] == pytest.approx(reference)


@pytest.mark.parametrize('method', ['random', 'grid', 'optuna'])
def test_unavailable_primary_never_selects_fallback_configuration(method):
    result = run(data(metric='r2', constant=True), search_method=method)
    assert result['status'] == 'error' and 'complete finite declared objective' in result['error']
    assert result['n_trials'] == 2 and result['n_failed'] == 2
    assert all(row['status'] == 'objective_unavailable' for row in result['trial_attempts'])
    assert result['trials'][0]['cv']['r2']['mean'] is None
    assert not result['best_points'] and 'selected_params' not in result
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('method', ['random', 'grid', 'optuna'])
def test_fit_errors_remain_attributable_to_each_configuration(monkeypatch, method):
    def fail(*args, **kwargs):
        raise ValueError('deliberate fitter failure')
    monkeypatch.setattr(hp, '_evaluate_config', fail)
    result = run(search_method=method)
    assert result['status'] == 'error' and result['n_attempted'] == 2
    assert all(row['status'] == 'failed' and row['params']['n_estimators'] == 5 and
               row['error'] == 'deliberate fitter failure' for row in result['trial_attempts'])


def test_failed_curve_is_gap_without_fabricated_spread_or_guidance(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError('curve unavailable')
    monkeypatch.setattr(hp, '_evaluate_cv_only', fail)
    result = run()
    assert result['status'] == 'completed' and result['n_failed_curve_points'] == 2
    assert result['validation_curves'][0]['cv_mean'] == [None, None]
    assert result['validation_curves'][0]['cv_std'] == [None, None]
    assert not result['guidance']
    assert all(point['error'] == 'curve unavailable' for point in result['validation_curves'][0]['points'])


def test_minimizing_guidance_ignores_missing_points():
    result = hp._build_guidance([{'param': 'max_depth', 'type': 'int', 'values': [1, 2, 3],
                                 'cv_mean': [None, 2, 1], 'train_mean': [None, 1, .5]}], 'rmse')
    assert result[0]['type'] == 'zoom_out' and result[0]['suggested_range'] == [2, 4]


@pytest.mark.parametrize('task,requested_metric', [('regression', 'roc_auc'), ('classification', 'rmse'), ('regression', 'unknown')])
def test_task_incompatible_objectives_fail_explicitly(task, requested_metric):
    with pytest.raises(ValueError, match='unsupported'):
        resolve_tuning_objective(task, data(task)[-1], requested_metric)


def test_aliases_resolve_and_contradictory_objective_direction_or_threshold_fail():
    context = data('classification', 'auc')[-1]
    assert resolve_tuning_objective('classification', context, 'roc_auc')['primary_metric'] == 'roc_auc'
    with pytest.raises(ValueError, match='contradicts'):
        resolve_tuning_objective('classification', context, 'pr_auc')
    context['prediction_contract']['objective']['direction'] = 'minimize'
    with pytest.raises(ValueError, match='direction contradicts'):
        resolve_tuning_objective('classification', context)
    context['prediction_contract']['objective'].pop('direction')
    with pytest.raises(ValueError, match='threshold metrics use 0.5'):
        resolve_tuning_objective('classification', context, threshold=.3)
    with pytest.raises(ValueError, match='finite'):
        resolve_tuning_objective('classification', context, threshold=float('nan'))


@pytest.mark.parametrize('features', [[], ['missing'], ['x', 'x']])
def test_features_cannot_silently_fall_back_to_all_columns(features):
    with pytest.raises(ValueError, match='features'):
        run(features=features)


def test_accepted_loss_cannot_use_undefined_native_auc_early_stopping():
    parts = data('classification', 'brier')
    parts = list(parts)
    parts[3] = parts[3].copy()
    parts[3].iloc[:] = 1
    result = run(parts)
    assert result['status'] == 'error'
    assert all('both declared classes' in attempt['error'] for attempt in result['trial_attempts'])


def test_search_basis_binds_raw_inputs_and_budget_but_excludes_protected_rows():
    parts = data()
    first = run(parts)
    changed = copy.deepcopy(parts)
    changed[-1]['frame'].iloc[0, 0] += 5
    second = run(changed)
    assert first['search_basis']['sha256'] != second['search_basis']['sha256']
    third = run(parts, n_jobs=1)
    assert first['search_basis']['sha256'] != third['search_basis']['sha256']
    changed = copy.deepcopy(parts)
    changed[-1]['frame'].loc[100] = [999, 999]
    assert first['search_basis']['sha256'] == run(changed)['search_basis']['sha256']


@pytest.mark.parametrize('failure', ['search', 'stopped', 'refit', 'publication', 'configuration'])
def test_api_failures_never_publish_or_report_completed(monkeypatch, _use_tmp_media, settings, failure):
    from rest_framework.test import APIRequestFactory
    from modeling import views
    X, y, V, z, context = data()
    saved = {'X_train': X, 'y_train': y, 'X_valid': V, 'y_valid': z, 'task': 'regression',
             'algorithm': 'xgboost', 'validation_context': context, 'prediction_contract': context['prediction_contract'],
             'execution_id': 'source-run'}
    root = Path(settings.MEDIA_ROOT)
    (root / 'train_data').mkdir()
    (root / 'train_data' / '1_train_data.pkl').touch()
    monkeypatch.setattr(views, 'load_development_data', lambda *args: saved)
    views.HYPERPARAM_PROGRESS.pop(1, None)
    def search(**kwargs):
        if failure == 'configuration':
            raise ValueError('Invalid fixed configuration')
        kwargs['status_callback']({'status': 'error', 'error': 'candidate not persisted yet'})
        assert views.HYPERPARAM_PROGRESS[1]['status'] == 'running'
        if failure in ('search', 'stopped'):
            return {'status': 'error' if failure == 'search' else 'stopped', 'error': 'No valid winner'}
        return {'status': 'completed', 'features': ['x'], 'selected_params': {'n_estimators': 5}}
    monkeypatch.setattr(views, 'run_hyperparam_search_with_progress', search)
    def fail(*args, **kwargs):
        raise ValueError('deliberate refit/publication failure')
    if failure == 'refit':
        monkeypatch.setattr('modeling.tuning_evidence.fit_for_tuning', fail)
    if failure == 'publication':
        monkeypatch.setattr(views, 'publish_candidate', fail)
    else:
        monkeypatch.setattr(views, 'publish_candidate', lambda *args, **kwargs: pytest.fail('Invalid search cannot publish'))
    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(views.threading, 'Thread', InlineThread)
    factory = APIRequestFactory()
    response = views.HyperparamStartView.as_view()(factory.post('/hp', {'file_id': 1}, format='json'))
    assert response.status_code == 200
    result = views.HyperparamResultsView.as_view()(factory.get('/hp'), file_id=1)
    assert not result.data['hyperparam_completed']
    assert result.data['status'] == ('stopped' if failure == 'stopped' else 'error')
    assert views.HYPERPARAM_PROGRESS[1]['status'] == result.data['status']
    if failure != 'stopped':
        assert views.HYPERPARAM_PROGRESS[1]['error'] == result.data['error']
    assert 'execution_id' not in result.data
    views.HYPERPARAM_PROGRESS.pop(1, None)


def test_malformed_predictions_fail_instead_of_inventing_metric():
    with pytest.raises(ValueError, match='finite'):
        hp._compute_metrics([0, 1], [np.nan, .8])
    with pytest.raises(ValueError, match='probability'):
        hp._compute_metrics([0, 1], [-1, 3])


def test_cancellation_preserves_attempts_without_completion():
    flag = {}
    def stop_after_trial(info):
        if info.get('completed_trials'):
            flag['stop_requested'] = True
    result = run(stop_flag=flag, status_callback=stop_after_trial)
    assert result['status'] == 'stopped'
    assert result['trial_attempts'] and result['trials']
    assert not result['validation_curves']


def test_missing_optuna_fallback_is_explicit_and_bound_to_basis(monkeypatch):
    import builtins
    original = builtins.__import__
    def without_optuna(name, *args, **kwargs):
        if name == 'optuna':
            raise ImportError('Optional backend unavailable')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', without_optuna)
    result = run(search_method='bayesian')
    assert result['status'] == 'completed'
    assert result['search_method_requested'] == 'bayesian' and result['search_method'] == 'random'
    assert result['search_basis']['configuration']['search_method_resolved'] == 'random'
    assert any('falling back' in warning for warning in result['space_warnings'])


def test_api_refit_reuses_search_weight_when_parent_has_no_fixed_weight(monkeypatch, _use_tmp_media, settings):
    from rest_framework.test import APIRequestFactory
    from modeling import views
    X, y, V, z, context = data('classification', 'roc_auc')
    selected = run((X, y, V, z, context), n_jobs=1, early_stopping_rounds=50)
    winner = selected['trials'][selected['selected_trial_index']]
    assert selected['scale_pos_weight'] != 1
    saved = {'X_train': X, 'y_train': y, 'X_valid': V, 'y_valid': z, 'task': 'classification',
             'algorithm': 'xgboost', 'validation_context': context, 'prediction_contract': context['prediction_contract'],
             'execution_id': 'source-run', 'scale_pos_weight': None}
    root = Path(settings.MEDIA_ROOT)
    (root / 'train_data').mkdir()
    (root / 'train_data' / '1_train_data.pkl').touch()
    monkeypatch.setattr(views, 'load_development_data', lambda *args: saved)
    monkeypatch.setattr(views, 'run_hyperparam_search_with_progress', lambda **kwargs: selected)
    published = []
    def publish(parent_id, file_id, adapter, features, params, source, **kwargs):
        assert adapter.fit_receipt == winner['fit_receipt']
        assert params == winner['params'] and features == ['x']
        published.append(adapter)
        return {'model': {'model_path': 'candidate/model.json'}, 'execution_id': 'new-candidate', 'adoption_status': 'adopted'}
    monkeypatch.setattr(views, 'publish_candidate', publish)
    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(views.threading, 'Thread', InlineThread)
    views.HYPERPARAM_PROGRESS.pop(1, None)
    factory = APIRequestFactory()
    response = views.HyperparamStartView.as_view()(factory.post('/hp', {'file_id': 1}, format='json'))
    assert response.status_code == 200 and len(published) == 1
    result = views.HyperparamResultsView.as_view()(factory.get('/hp'), file_id=1)
    assert result.data['hyperparam_completed'] and result.data['refit_receipt'] == winner['fit_receipt']
    views.HYPERPARAM_PROGRESS.pop(1, None)
