"""Opt-in bounded mixed-column preparation keeps native validation and exact fits."""
import numpy as np
import pandas as pd
import pytest
import xgboost as xgb
from modeling import booster_adapters as adapters
from modeling.fit_receipts import input_receipt

pytestmark = pytest.mark.unit


def frame(dtype=np.float64, categorical=True):
    values = np.arange(24).astype(dtype)
    if np.dtype(dtype).kind == 'u':
        values[-3:] = [2**63 - 1, 2**63 + 2**38 - 1, 2**64 - 1]
    if np.dtype(dtype) == np.dtype('int64'):
        values[-3:] = [-2**63, -(2**53 + 1), 2**63 - 1]
    if np.dtype(dtype).kind == 'f':
        values[0] = np.nan
        with np.errstate(all='ignore'):
            values[1:7] = [-0., np.nextafter(0., 1.), np.finfo(np.float32).tiny / 2,
                           np.finfo(np.float32).max, -np.finfo(np.float32).max, np.nextafter(.5, 1.)]
    data = pd.DataFrame({'x': values, 'z': np.linspace(-2, 2, 24, dtype=np.float32)})
    if categorical:
        data['category'] = pd.Categorical(['b', 'a', None] * 8, categories=['b', 'a', 'unused'], ordered=True)
    return data


def matrix(data, compact, **kwargs):
    return adapters._native_xgb_matrix(xgb, data, feature_names=list(data.columns),
                                      enable_categorical=any(isinstance(t, pd.CategoricalDtype) for t in data.dtypes),
                                      compact_mixed=compact, **kwargs)


def same(left, right):
    assert left.feature_names == right.feature_names and left.feature_types == right.feature_types
    for name in ['data', 'indices', 'indptr']:
        np.testing.assert_array_equal(getattr(left.get_data(), name), getattr(right.get_data(), name))


@pytest.mark.parametrize('dtype', [np.float32, np.float64, np.int8, np.int64, np.uint64, bool])
@pytest.mark.parametrize('categorical', [False, True])
def test_mixed_matrices_preserve_native_cells_missing_values_types_and_input_receipts(dtype, categorical):
    data = frame(dtype, categorical)
    before = data.copy(deep=True)
    labels = pd.Series(np.arange(len(data)) % 2)
    receipt = input_receipt(data, labels)
    same(matrix(data, False, label=labels), matrix(data, True, label=labels))
    pd.testing.assert_frame_equal(data, before)
    assert input_receipt(data, labels) == receipt


@pytest.mark.parametrize('task', ['classification', 'regression', 'multiclass'])
@pytest.mark.parametrize('categorical', [False, True])
def test_real_fitter_preserves_model_bytes_predictions_receipts_and_round_budget(monkeypatch, task, categorical):
    data = frame(np.int64, categorical)
    labels = pd.Series(np.arange(len(data)) / 7 if task == 'regression' else np.arange(len(data)) % (3 if task == 'multiclass' else 2))
    params = {'task': 'regression' if task == 'regression' else 'classification', 'nthread': 1, 'seed': 162,
              'max_depth': 2, 'tree_method': 'hist', 'objective': 'reg:squarederror' if task == 'regression' else
              'multi:softprob' if task == 'multiclass' else 'binary:logistic'}
    if task == 'multiclass':
        params['num_class'] = 3
    current = adapters._native_xgb_matrix
    calls = []
    def legacy(*args, **kwargs):
        assert kwargs.pop('compact_mixed') is True
        calls.append(True)
        return current(*args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(adapters, '_native_xgb_matrix', legacy)
        old = adapters.XGBoostAdapter().train(data, labels, data, labels, params, num_boost_round=4, early_stopping_rounds=0)
    prepared = []
    actual_prepare = adapters._small_native_numeric_matrix
    def observe(values):
        result = actual_prepare(values)
        prepared.append(result is not None)
        return result
    monkeypatch.setattr(adapters, '_small_native_numeric_matrix', observe)
    new = adapters.XGBoostAdapter().train(data, labels, data, labels, params, num_boost_round=4, early_stopping_rounds=0)
    if (xgb.__version__, pd.__version__, np.__version__) == ('2.1.4', '3.0.6', '2.5.3'):
        assert prepared == [True, True]
    else:
        assert prepared == []
    assert len(calls) == 2 and old.model.num_boosted_rounds() == new.model.num_boosted_rounds() == 4
    assert old.model.save_raw(raw_format='json') == new.model.save_raw(raw_format='json')
    assert old.fit_receipt == new.fit_receipt
    np.testing.assert_array_equal(old.predict_proba(data), new.predict_proba(data))


@pytest.mark.parametrize('kind', ['extension', 'string', 'datetime', 'complex', 'float16', 'non_native', 'overflow', 'large', 'disabled_categories'])
def test_unsupported_storage_budgets_and_category_flags_keep_original_native_dispatch(kind, monkeypatch):
    data = frame(categorical=False)
    categorical = False
    if kind == 'extension':
        data['x'] = data.x.astype('Float64')
    elif kind == 'string':
        data['x'] = data.x.astype('str')
    elif kind == 'datetime':
        data['x'] = pd.date_range('2020-01-01', periods=len(data))
    elif kind == 'complex':
        data['x'] = data.x.astype(complex)
    elif kind == 'float16':
        data['x'] = data.x.astype('float16')
    elif kind == 'non_native':
        data['x'] = np.arange(len(data), dtype='>i8')
    elif kind == 'overflow':
        data.loc[2, 'x'] = 1e300
    elif kind == 'large':
        data = pd.DataFrame({'x': np.arange(2**17+1, dtype=np.int64), 'z': np.zeros(2**17+1, dtype=np.float32)})
    else:
        data['x'] = data.x.astype('category')
    seen = []
    original = xgb.DMatrix.__init__
    def inspect(self, values, *args, **kwargs):
        seen.append(values)
        return original(self, values, *args, **kwargs)
    monkeypatch.setattr(xgb.DMatrix, '__init__', inspect)
    try:
        adapters._native_xgb_matrix(xgb, data, feature_names=list(data.columns), enable_categorical=categorical, compact_mixed=True)
    except (ValueError, TypeError, xgb.core.XGBoostError):
        assert kind not in {'large', 'non_native'}
    assert len(seen) == 1 and seen[0] is data


@pytest.mark.parametrize('categorical', [False, True])
def test_default_helper_remains_compatible_with_original_mixed_dispatch(categorical, monkeypatch):
    data = frame(np.int64, categorical)
    seen = []
    original = xgb.DMatrix.__init__
    def inspect(self, values, *args, **kwargs):
        seen.append(values)
        return original(self, values, *args, **kwargs)
    monkeypatch.setattr(xgb.DMatrix, '__init__', inspect)
    matrix(data, False)
    assert seen == [data]


@pytest.mark.parametrize('module', [xgb, pd, np])
def test_other_versions_retain_the_original_dataframe_route(monkeypatch, module):
    data = frame(np.int64)
    monkeypatch.setattr(module, '__version__', '99.0.0')
    seen = []
    original = xgb.DMatrix.__init__
    def inspect(self, values, *args, **kwargs):
        seen.append(values)
        return original(self, values, *args, **kwargs)
    monkeypatch.setattr(xgb.DMatrix, '__init__', inspect)
    matrix(data, True)
    assert seen == [data]


@pytest.mark.parametrize('invalid', ['labels', 'names', 'infinity'])
def test_native_refusals_survive_opt_in_preparation(invalid):
    data = frame(np.int64)
    options = {'feature_names': list(data.columns), 'enable_categorical': True}
    if invalid == 'labels':
        options['label'] = [0]
    elif invalid == 'names':
        options['feature_names'] = ['missing']
    else:
        data.loc[0, 'z'] = np.inf
    failures = []
    for compact in [False, True]:
        with pytest.raises((ValueError, xgb.core.XGBoostError)) as error:
            adapters._native_xgb_matrix(xgb, data, compact_mixed=compact, **options)
        failures.append(type(error.value))
    assert failures[0] is failures[1]


def test_mutation_reobserves_numeric_cells_category_order_and_missing_codes():
    data = frame(np.int64)
    previous = matrix(data, True)
    data.loc[0, 'x'] = -7
    data['category'] = data.category.cat.reorder_categories(['unused', 'a', 'b'])
    current = matrix(data, True)
    same(current, matrix(data, False))
    assert not np.array_equal(previous.get_data().data, current.get_data().data)


def test_new_preparation_is_detached_and_bounded():
    data = frame(np.int64)
    values, types = adapters._small_native_numeric_matrix(data)
    assert values.dtype == np.float32 and types == ['int', 'float', 'c'] and values.nbytes <= 2**20
    data.loc[0, 'x'] = -99
    assert values[0, 0] == 0
    values[0, 0] = 33
    assert data.x.iloc[0] == -99
