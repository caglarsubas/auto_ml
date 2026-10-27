"""Numeric prediction avoids transient matrices without changing native scores."""
import json

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from modeling.booster_adapters import XGBoostAdapter

pytestmark = pytest.mark.unit


def trained(task='binary', dtype=np.float64, categorical=False, booster='gbtree'):
    rng = np.random.default_rng(253)
    X = pd.DataFrame(rng.normal(size=(96, 4)).astype(dtype), columns=['a', 'b', 'c', 'd'])
    X.loc[::7, 'b'] = np.nan
    y = pd.Series(np.tile(np.arange(3), 32) if task == 'multiclass' else
                  X.a * 2 + X.c if task == 'regression' else (X.a > 0).astype(int))
    if categorical:
        X['d'] = pd.Categorical(np.tile(['low', 'middle', 'high'], 32))
    params = dict(objective={'binary': 'binary:logistic', 'regression': 'reg:squarederror',
                             'multiclass': 'multi:softprob'}[task], nthread=1, seed=42,
                  tree_method='hist', max_depth=2, eta=.1, booster=booster)
    if task == 'multiclass':
        params['num_class'] = 3
    adapter = XGBoostAdapter().train(X[:64], y[:64], X[64:], y[64:], params,
                                    num_boost_round=16, early_stopping_rounds=0)
    return adapter, X[64:][::-1].copy()


def reference(adapter, frame):
    matrix = xgb.DMatrix(frame[adapter.feature_names] if adapter.feature_names else frame,
                         feature_names=adapter.feature_names or list(map(str, frame.columns)),
                         enable_categorical=adapter.enable_categorical)
    rounds = (0, int(adapter.best_iteration) + 1) if adapter.best_iteration is not None and adapter.best_iteration >= 0 else (0, 0)
    return np.asarray(adapter.model.predict(matrix, iteration_range=rounds), dtype=float)


def no_matrix(*args, **kwargs):
    raise AssertionError('A transient prediction matrix was allocated')


@pytest.mark.parametrize('task', ['binary', 'regression', 'multiclass'])
@pytest.mark.parametrize('dtype', [np.float32, np.float64])
@pytest.mark.parametrize('rounds', [0, 4, None])
def test_numeric_prediction_matches_matrix_reference_replay_and_chunks(task, dtype, rounds, tmp_path, monkeypatch):
    adapter, frame = trained(task, dtype)
    adapter.best_iteration = rounds
    expected = reference(adapter, frame)
    path = str(tmp_path / 'model.json')
    adapter.save(path)
    loaded = XGBoostAdapter.load(path, feature_names=adapter.feature_names)
    np.testing.assert_array_equal(reference(loaded, frame), expected)
    before = frame.copy(deep=True)
    reordered = frame[list(reversed(frame.columns))].assign(ignored=2.)
    monkeypatch.setattr(xgb, 'DMatrix', no_matrix)
    for model in [adapter, loaded]:
        for data in [frame, reordered]:
            np.testing.assert_array_equal(model.predict_proba(data), expected)
            for size in [1, 7]:
                chunks = [model.predict_proba(data.iloc[start:start + size]) for start in range(0, len(data), size)]
                np.testing.assert_array_equal(np.concatenate(chunks), expected)
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize('scenario', ['integer', 'nullable', 'categorical', 'empty', 'object', 'unnamed',
                                      'tampered_names', 'linear', 'dart', 'half', 'gpu_config',
                                      'positive_infinity', 'negative_infinity', 'out_of_range',
                                      'missing_types', 'wrong_categorical_flag'])
def test_other_inputs_retain_the_matrix_path_and_its_validation(scenario, monkeypatch):
    adapter, frame = trained(categorical=scenario in {'categorical', 'wrong_categorical_flag'},
                             booster={'linear': 'gblinear', 'dart': 'dart'}.get(scenario, 'gbtree'))
    if scenario == 'integer':
        frame = frame.fillna(0).astype('int64')
    elif scenario == 'nullable':
        frame = frame.astype('Float64')
    elif scenario == 'empty':
        frame = frame.iloc[:0]
    elif scenario == 'object':
        frame = frame.astype(str)
    elif scenario == 'unnamed':
        adapter.model.feature_names = None
    elif scenario == 'tampered_names':
        adapter.model.feature_names = ['other_' + name for name in adapter.feature_names]
    elif scenario == 'missing_types':
        adapter.model.feature_types = None
    elif scenario == 'wrong_categorical_flag':
        adapter.enable_categorical = False
        frame['d'] = frame['d'].cat.codes.astype(float)
    elif scenario == 'half':
        frame = frame.astype('float16')
    elif scenario in {'positive_infinity', 'negative_infinity', 'out_of_range'}:
        frame.iloc[0, 0] = {'positive_infinity': np.inf, 'negative_infinity': -np.inf, 'out_of_range': 1e40}[scenario]
    elif scenario == 'gpu_config':
        config = json.loads(adapter.model.save_config())
        config['learner']['generic_param']['device'] = 'cuda:0'
        monkeypatch.setattr(adapter.model, 'save_config', lambda: json.dumps(config))
    error = None
    try:
        expected = reference(adapter, frame)
    except (ValueError, xgb.core.XGBoostError) as exc:
        error = type(exc)
    original, calls = xgb.DMatrix, []

    def observed(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(xgb, 'DMatrix', observed)
    if error:
        with pytest.raises(error):
            adapter.predict_proba(frame)
    else:
        np.testing.assert_array_equal(adapter.predict_proba(frame), expected)
    assert calls == [True]


@pytest.mark.parametrize('task', ['binary', 'regression'])
@pytest.mark.parametrize('dtype', [np.float32, np.float64])
def test_float_boundaries_preserve_native_split_decisions(task, dtype, monkeypatch):
    adapter, frame = trained(task, dtype)
    rows = []

    def visit(node):
        if 'split' in node:
            value = dtype(node['split_condition'])
            for edge in [np.nextafter(value, dtype(-np.inf)), value, np.nextafter(value, dtype(np.inf))]:
                row = dict.fromkeys(adapter.feature_names, dtype(0))
                row[node['split']] = edge
                rows.append(row)
            for child in node['children']:
                visit(child)

    for tree in adapter.model.get_dump(dump_format='json'):
        visit(json.loads(tree))
    assert rows
    data = pd.DataFrame(rows, dtype=dtype)
    expected = reference(adapter, data)
    monkeypatch.setattr(xgb, 'DMatrix', no_matrix)
    np.testing.assert_array_equal(adapter.predict_proba(data), expected)


def test_native_prediction_failure_is_not_hidden_by_a_matrix_retry(monkeypatch):
    adapter, frame = trained()

    def refused(*args, **kwargs):
        raise RuntimeError('Native prediction refused')

    monkeypatch.setattr(adapter.model, 'inplace_predict', refused)
    monkeypatch.setattr(xgb, 'DMatrix', no_matrix)
    with pytest.raises(RuntimeError, match='Native prediction refused'):
        adapter.predict_proba(frame)
