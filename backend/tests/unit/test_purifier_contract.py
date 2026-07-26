"""Unit tests for train-fit purifier contract."""

import numpy as np
import pandas as pd
import pytest

from preprocessing.purifier_contract import (
    remap_indices_to_positions,
    resolve_fit_index,
)


@pytest.mark.unit
def test_resolve_fit_index_full_frame_without_split():
    df = pd.DataFrame({'a': range(20)})
    idx, meta = resolve_fit_index(df, split=None)
    assert meta['fit_scope'] == 'full_frame'
    assert len(idx) == 20


@pytest.mark.unit
def test_resolve_fit_index_outer_train_with_split():
    df = pd.DataFrame({'a': range(40)})
    idx, meta = resolve_fit_index(df, split={'strategy': 'random', 'percent': 25})
    assert meta['fit_scope'] == 'outer_train'
    assert 20 <= meta['n_fit'] <= 35


@pytest.mark.unit
def test_holdout_extreme_does_not_change_clip_bounds():
    """Holdout-only extreme values must not affect train-fitted quantiles."""
    from preprocessing.views import PreprocessingRunView

    n = 100
    rng = np.random.default_rng(0)
    vals = rng.normal(0, 1, size=n).tolist()
    for i in range(75, 100):
        vals[i] = 1e6 if i % 2 == 0 else -1e6
    df = pd.DataFrame({'x': vals, 'Target': [0, 1] * 50})
    train_idx = df.index[:75]
    view = PreprocessingRunView()
    work, _dropped, breakdown, _ = view._apply_options(
        df, {29}, preserve={'Target'}, train_idx=train_idx,
    )
    art = view._last_purifier_artifact
    assert art.get('fit_scope') == 'outer_train'
    bounds = art.get('clip_bounds', {}).get('x')
    assert bounds is not None
    assert abs(bounds['hi']) < 10
    assert abs(bounds['lo']) < 10
    assert work['x'].max() <= bounds['hi'] + 1e-9
    assert work['x'].min() >= bounds['lo'] - 1e-9
    step = next(b for b in breakdown if 'Outlier cleaning' in b['step'])
    assert step['quantile_range'] == [0.05, 0.95]


@pytest.mark.unit
def test_holdout_only_missingness_does_not_drop_column():
    """Train miss_ratio < threshold keeps column even if full-frame would drop."""
    from preprocessing.views import PreprocessingRunView

    n = 100
    df = pd.DataFrame({'x': list(range(n)), 'keep': list(range(n))})
    train_idx = df.index[:50]
    # Null rows 4..99 → train miss_ratio = 46/50 = 0.92 < 0.95; full = 0.96 >= 0.95
    for i in df.index[4:]:
        df.loc[i, 'x'] = None
    view = PreprocessingRunView()
    _work, dropped, _, _ = view._apply_options(df, {17}, train_idx=train_idx)
    assert 'x' not in dropped, f'train-fit must not drop x; dropped={dropped}'
    _w2, dropped_full, _, _ = view._apply_options(df, {17}, split=None)
    assert 'x' in dropped_full


@pytest.mark.unit
def test_remap_indices_align_with_reset_csv_positions():
    df = pd.DataFrame({'a': [10, 20, 30, 40]}, index=[5, 6, 7, 8])
    train = pd.Index([5, 7])
    test = pd.Index([6, 8])
    out, tr_pos, te_pos = remap_indices_to_positions(df, train, test)
    assert list(out.index) == [0, 1, 2, 3]
    assert tr_pos == [0, 2]
    assert te_pos == [1, 3]
    assert out.loc[tr_pos, 'a'].tolist() == [10, 30]
