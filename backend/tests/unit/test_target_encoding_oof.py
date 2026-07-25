"""Target encoding must fit on train rows only (OOF) when fit_idx is provided."""

import pandas as pd
import pytest

from encoding.encoding_utils import _target_encode


def test_target_encode_holdout_uses_train_mapping_only():
    # Category 'leak' appears only in test with target=1; train never sees it.
    # With train-only fit it must fall back to the train prior (0.5).
    df = pd.DataFrame({
        'feat': ['a', 'a', 'b', 'b', 'leak', 'leak'],
        'Target': [0, 0, 1, 1, 1, 1],
    })
    train_idx = pd.Index([0, 1, 2, 3])
    out, mapping = _target_encode(df.copy(), 'feat', 'Target', fit_idx=train_idx)
    assert mapping.get('oof') is True
    assert mapping.get('fit_on_train_only') is True
    assert mapping['global_mean'] == pytest.approx(0.5)
    assert 'leak' not in mapping['mapping']
    assert out.loc[4, 'feat'] == pytest.approx(0.5)
    assert out.loc[5, 'feat'] == pytest.approx(0.5)


def test_target_encode_legacy_in_sample_still_works():
    df = pd.DataFrame({
        'feat': ['a', 'a', 'b', 'b'],
        'Target': [0, 0, 1, 1],
    })
    out, mapping = _target_encode(df.copy(), 'feat', 'Target', fit_idx=None)
    assert mapping.get('oof') is False
    assert out.loc[0, 'feat'] == pytest.approx(0.0)
    assert out.loc[2, 'feat'] == pytest.approx(1.0)
