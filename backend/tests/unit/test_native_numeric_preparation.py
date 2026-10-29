"""Numeric preparation preserves native matrices, fits and fresh input evidence."""

import json
import hashlib

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from modeling import booster_adapters as adapters
from modeling.fit_receipts import input_receipt

pytestmark = pytest.mark.unit


def reference_receipt(X, y):
    labels = y if isinstance(y, pd.Series) else pd.Series(y, index=X.index)
    schema = {
        "features": list(map(str, X.columns)),
        "dtypes": list(map(str, X.dtypes)),
        "label_dtype": str(labels.dtype),
        "n_rows": len(X),
    }
    h = hashlib.sha256(json.dumps(schema, sort_keys=True).encode())
    h.update(pd.util.hash_pandas_object(X, index=True, categorize=False).to_numpy(dtype="<u8").tobytes())
    h.update(pd.util.hash_pandas_object(labels, index=True, categorize=False).to_numpy(dtype="<u8").tobytes())
    cats = {
        str(n): {
            "levels": [{"type": type(v).__name__, "value": str(v)} for v in X[n].cat.categories],
            "ordered": X[n].cat.ordered,
        }
        for n in X
        if isinstance(X[n].dtype, pd.CategoricalDtype)
    }
    h.update(json.dumps(cats, sort_keys=True).encode())
    return {**schema, "sha256": h.hexdigest()}


@pytest.mark.parametrize("dtype", [np.float32, np.float64, np.int8, np.int64, np.uint64, bool])
@pytest.mark.parametrize("task", ["classification", "regression"])
def test_supported_numeric_matrices_and_models_match_dataframe_reference(dtype, task, monkeypatch):
    rng = np.random.default_rng(161)
    values = rng.integers(0, 2 if dtype is bool else 20, size=(24, 3)).astype(dtype)
    if dtype in [np.float32, np.float64]:
        values[1, 1] = np.nan
    if dtype == np.uint64:
        values[2, 1] = 2**63 + 2**38 - 1
    X = pd.DataFrame(values, columns=["a", "b", "c"])
    y = np.arange(len(X)) % 2 if task == "classification" else np.arange(len(X)) / 7
    old = xgb.DMatrix(X, label=y, feature_names=list(X.columns), enable_categorical=False)
    seen = []
    original = xgb.DMatrix.__init__

    def observed(self, data, *args, **kwargs):
        seen.append(data)
        original(self, data, *args, **kwargs)

    monkeypatch.setattr(xgb.DMatrix, "__init__", observed)
    new = adapters._native_xgb_matrix(xgb, X, label=y, feature_names=list(X.columns), enable_categorical=False)
    assert len(seen) == 1
    assert isinstance(
        seen[0],
        np.ndarray
        if xgb.__version__ == "2.1.4" and pd.__version__ == "3.0.6" and np.__version__ == "2.5.3"
        else pd.DataFrame,
    )
    if isinstance(seen[0], np.ndarray):
        assert seen[0].dtype == X.to_numpy().dtype
    assert new.feature_names == old.feature_names and new.feature_types == old.feature_types
    for name in ["indptr", "indices", "data"]:
        np.testing.assert_array_equal(getattr(new.get_data(), name), getattr(old.get_data(), name))
    parameters = dict(
        objective="binary:logistic" if task == "classification" else "reg:squarederror",
        nthread=1,
        max_depth=2,
        seed=161,
    )
    fitted = [xgb.train(parameters, m, num_boost_round=3) for m in [old, new]]
    assert fitted[0].save_raw(raw_format="json") == fitted[1].save_raw(raw_format="json")
    np.testing.assert_array_equal(fitted[0].predict(old), fitted[1].predict(new))


@pytest.mark.parametrize(
    "kind",
    [
        "mixed",
        "extension",
        "categorical",
        "float16",
        "non_native",
        "subclass",
        "empty",
        "version",
        "instrumented",
        "fragmented",
        "pandas_version",
        "numpy_version",
    ],
)
def test_unsupported_profiles_keep_original_dataframe_dispatch(kind, monkeypatch):
    X = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    categorical = False
    if kind == "mixed":
        X["y"] = X.y.astype("int64")
    elif kind == "extension":
        X["x"] = X.x.astype("Float64")
    elif kind == "categorical":
        X["x"] = X.x.astype("category")
        categorical = True
    elif kind == "float16":
        X = X.astype("float16")
    elif kind == "non_native":
        X = pd.DataFrame(np.array([[1, 2], [3, 4]], dtype=">i8"), columns=["x", "y"])
    elif kind == "subclass":

        class Frame(pd.DataFrame):
            pass

        X = Frame(X)
    elif kind == "fragmented":
        X["z"] = [5.0, 6.0]
    elif kind == "empty":
        X = X.iloc[:0]
    elif kind == "version":
        monkeypatch.setattr(xgb, "__version__", "unsupported")
    elif kind == "pandas_version":
        monkeypatch.setattr(pd, "__version__", "99.0.0")
    elif kind == "numpy_version":
        monkeypatch.setattr(np, "__version__", "99.0.0")
    seen = []
    original = xgb.DMatrix.__init__

    def observed(self, data, *args, **kwargs):
        seen.append(data)
        original(self, data, *args, **kwargs)

    monkeypatch.setattr(xgb.DMatrix, "__init__", observed)
    if kind == "instrumented":
        constructor = xgb.DMatrix

        def wrapper(data, **kwargs):
            return constructor(data, **kwargs)

        monkeypatch.setattr(xgb, "DMatrix", wrapper)
    try:
        adapters._native_xgb_matrix(xgb, X, feature_names=list(X.columns), enable_categorical=categorical)
    except (ValueError, TypeError):
        assert kind in ["non_native", "extension"]
    assert len(seen) == 1 and seen[0] is X


def test_matrix_and_receipt_reobserve_changed_values_dtypes_order_and_categories():
    X = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    y = pd.Series([0, 1])
    before = input_receipt(X, y)
    a = adapters._native_xgb_matrix(xgb, X, feature_names=list(X.columns), enable_categorical=False)
    X.iloc[0, 0] = 7.0
    b = adapters._native_xgb_matrix(xgb, X, feature_names=list(X.columns), enable_categorical=False)
    assert not np.array_equal(a.get_data().data, b.get_data().data)
    assert input_receipt(X, y) != before and input_receipt(X, y) == reference_receipt(X, y)
    for frame in [
        X.astype("int64"),
        X[["y", "x"]],
        X.assign(y=pd.Categorical(["a", "b"], categories=["b", "a"], ordered=True)),
    ]:
        assert input_receipt(frame, y) == reference_receipt(frame, y)


@pytest.mark.parametrize("kind", ["numeric", "category", "nullable", "mixed", "indexed", "empty"])
def test_receipt_bytes_match_independent_original_algorithm(kind, monkeypatch):
    X = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    y = pd.Series([0, 1])
    if kind == "category":
        X["y"] = pd.Categorical(["a", "b"], categories=["b", "a"], ordered=True)
    elif kind == "nullable":
        X["x"] = pd.Series([1.0, None], dtype="Float64")
    elif kind == "mixed":
        X["y"] = X.y.astype("int8")
    elif kind == "indexed":
        X.index = y.index = pd.Index(["z", "a"], name="rows")
    elif kind == "fragmented":
        X["z"] = [5.0, 6.0]
    elif kind == "empty":
        X = X.iloc[:0]
        y = y.iloc[:0]
    expected = reference_receipt(X, y)
    seen = []
    original = pd.DataFrame.__getitem__

    def observed(self, key):
        if self is X:
            seen.append(key)
        return original(self, key)

    monkeypatch.setattr(pd.DataFrame, "__getitem__", observed)
    assert input_receipt(X, y) == expected
    if kind in ["numeric", "mixed", "indexed", "empty"]:
        assert not seen


def test_readonly_strided_numeric_views_preserve_matrix_rows_and_memory():
    X = pd.DataFrame(np.arange(60, dtype=float).reshape(20, 3), columns=["x", "y", "z"]).iloc[::2]
    X.to_numpy(copy=False).setflags(write=False)
    old = xgb.DMatrix(X, feature_names=list(X.columns), enable_categorical=False)
    new = adapters._native_xgb_matrix(xgb, X, feature_names=list(X.columns), enable_categorical=False)
    np.testing.assert_array_equal(new.get_data().toarray(), old.get_data().toarray())
    np.testing.assert_array_equal(X.to_numpy(), np.arange(60, dtype=float).reshape(20, 3)[::2])


@pytest.mark.parametrize(
    "kind",
    ["float", "integer", "boolean", "mixed_numeric", "object", "string", "category", "nullable", "datetime", "complex"],
)
def test_category_detection_matches_original_and_rechecks_current_dtypes(kind, monkeypatch):
    X = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    if kind == "integer":
        X = X.astype("int64")
    elif kind == "boolean":
        X = X.astype(bool)
    elif kind == "mixed_numeric":
        X["y"] = X.y.astype("int64")
    elif kind == "object":
        X["x"] = X.x.astype(object)
    elif kind == "string":
        X["x"] = pd.Series(["a", "b"], dtype="str")
    elif kind == "category":
        X["x"] = pd.Categorical(["a", "b"])
    elif kind == "nullable":
        X["x"] = pd.Series([1, None], dtype="Int64")
    elif kind == "datetime":
        X["x"] = pd.date_range("2026-01-01", periods=2)
    elif kind == "complex":
        X["x"] = X.x.astype(complex)
    expected = []
    for name in X:
        if hasattr(X[name], "cat") or str(X[name].dtype) == "category":
            expected.append(str(name))
        elif X[name].dtype == "object" or pd.api.types.is_string_dtype(X[name]):
            expected.append(str(name))
    seen = []
    original = pd.DataFrame.__getitem__

    def observed(self, key):
        if self is X:
            seen.append(key)
        return original(self, key)

    monkeypatch.setattr(pd.DataFrame, "__getitem__", observed)
    assert adapters._cat_cols(X) == expected
    if kind in ["float", "integer", "boolean", "mixed_numeric"]:
        assert not seen
    X["x"] = pd.Categorical(["a", "b"])
    assert "x" in adapters._cat_cols(X)
