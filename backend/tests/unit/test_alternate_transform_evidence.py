"""Portable fit evidence for the transformations internal to alternate models."""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from modeling.alt_pipelines import get_alt_adapter
from modeling.development_validation import prepare_fold
from modeling.fit_receipts import receipt_digest
from tests.unit.test_fold_local_preparation import temporal_context  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('algorithm', ['logistic_regression', 'scorecard', 'isolation_forest'])
def test_fitted_state_is_portable_and_bound_to_the_training_partition(temporal_context, algorithm):
    c = temporal_context
    rows = c['frame'].index
    train, valid = rows[:41], rows[48:72]
    X, V, _ = prepare_fold(c, train, valid)
    changed = copy.deepcopy(c)
    changed['frame'].loc[valid, 'x'] = 1e12
    changed['frame'].loc[valid, 'unplanned'] = 'validation-only-level'
    repeated_X, changed_V, _ = prepare_fold(changed, train, valid)
    pd.testing.assert_frame_equal(X, repeated_X)

    params = {'n_estimators': 5} if algorithm == 'isolation_forest' else {}
    adapter = get_alt_adapter(algorithm).train(X, c['labels'].loc[train], V, c['labels'].loc[valid], params)
    replay = get_alt_adapter(algorithm).train(repeated_X, c['labels'].loc[train], changed_V, c['labels'].loc[valid], params)
    receipt = json.loads(json.dumps(adapter.fit_receipt, allow_nan=False))
    evidence = receipt['fitted_transforms']
    assert receipt.pop('sha256') == receipt_digest(receipt)
    assert evidence['fit_partition'] == 'train'
    assert evidence['fit_input_sha256'] == receipt['train']['sha256']
    assert evidence == replay.fit_receipt['fitted_transforms']
    assert receipt['valid']['sha256'] != replay.fit_receipt['valid']['sha256']
    step = evidence['steps'][0]
    assert step['output_features'] == adapter.feature_names
    if algorithm == 'scorecard':
        x = step['features']['x']
        assert x['kind'] == 'numeric_quantile_v2'
        np.testing.assert_allclose(x['edges'], np.quantile(X['x'], np.linspace(0, 1, 11)))
        assert 'validation-only-level' not in step['features']['unplanned']['mapping']
    else:
        assert step['categories'] == [['early', 'middle']]
        assert step['categorical_features'] == ['unplanned']
        if algorithm == 'isolation_forest':
            ref = evidence['steps'][1]['score_range']
            raw = -adapter.model.score_samples(adapter.design.transform(X))
            assert ref == pytest.approx([float(raw.min()), float(raw.max())])


def test_nonwinning_search_candidates_retain_their_folds(temporal_context, monkeypatch):
    from execution_jobs import selection_provenance
    from modeling.sfs_utils import run_sfs_with_progress

    c = temporal_context
    train, valid = c['frame'].index[:88], c['frame'].index[94:]
    X, V, _ = prepare_fold(c, train, valid)
    y, y_valid = c['labels'].loc[train], c['labels'].loc[valid]
    recorded = {}
    monkeypatch.setattr(selection_provenance, 'record', recorded.update)
    result = run_sfs_with_progress(X, y, V, y_valid, X, V, ['forward'], {'max_features': 1},
                                   cv_folds=2, top_k=2, validation_context=c)
    assert result['status'] == 'completed', result.get('error')
    step = result['forward'][0]
    assert set(recorded['screening']) == set(X.columns)
    for name, fit in recorded['screening'].items():
        assert fit['train']['features'] == [name]
        assert fit['train']['n_rows'] == len(train)
        assert fit['valid']['n_rows'] == len(valid)
    nonwinner, = set(step['top_k_evaluated']) - {step['feature_name']}
    assert list(recorded['other_top_k']) == [nonwinner]
    for fold in recorded['other_top_k'][nonwinner]:
        tr = c['frame'].loc[fold['train_rows']]
        va = c['frame'].loc[fold['valid_rows']]
        assert tr.end.max() < va.date.min()
        assert set(tr.entity).isdisjoint(va.entity)
        assert fold['native_fit']['train']['features'] == [nonwinner]
