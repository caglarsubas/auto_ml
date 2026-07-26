"""Unit tests for model-card deploy readiness gate (v2.55)."""

import pytest

from evaluation.eval_utils import assess_deploy_readiness, build_model_card


@pytest.mark.unit
def test_assess_ready_when_lineage_eval_and_no_high_leakage():
    readiness = assess_deploy_readiness(
        evaluation={'task': 'classification', 'metrics': {'roc_auc': 0.8}, 'scores_calibrated': True},
        lineage={'lineage_id': 'L1', 'split': {'strategy': 'random'}, 'features': {'count': 5}},
        modeling_status={'model': {'feature_count': 5, 'leakage_scan': {'n_high': 0}}},
    )
    assert readiness['ready'] is True
    assert readiness['blocking'] == []
    assert readiness['checklist_coverage']['evaluation_outer_test']['status'] == 'enforced'


@pytest.mark.unit
def test_assess_blocks_missing_evaluation():
    readiness = assess_deploy_readiness(
        evaluation=None,
        lineage={'lineage_id': 'L1', 'split': {}},
        evaluation_present=False,
    )
    assert readiness['ready'] is False
    codes = {b['code'] for b in readiness['blocking']}
    assert 'evaluation_missing' in codes


@pytest.mark.unit
def test_assess_blocks_missing_lineage_and_high_leakage():
    readiness = assess_deploy_readiness(
        evaluation={'metrics': {'roc_auc': 0.7}, 'leakage_scan': {'n_high': 2}},
        lineage={},
        modeling_status={'model': {'leakage_scan': {'n_high': 2}}},
    )
    assert readiness['ready'] is False
    codes = {b['code'] for b in readiness['blocking']}
    assert 'lineage_missing' in codes
    assert 'leakage_high' in codes


@pytest.mark.unit
def test_model_card_embeds_readiness_gate():
    card = build_model_card(
        9,
        {'task': 'classification', 'metrics': {'roc_auc': 0.9}},
        lineage={'lineage_id': 'abc', 'split': {'strategy': 'oot'}, 'features': {'count': 3}},
        modeling_status={'model': {'model_type': 'xgboost_classifier', 'leakage_scan': {'n_high': 0}}},
    )
    assert card['deploy_ready'] is True
    dr = card['sections']['deployment_readiness']
    assert dr['ready'] is True
    assert 'blocking' in dr
    assert 'checklist_coverage' in dr
    assert any('monitoring' in c.lower() for c in card['human_checks_remaining'])


@pytest.mark.unit
def test_build_score_bundle_raises_when_not_ready(tmp_path, settings):
    from deployment.deploy_utils import DeployNotReadyError, build_score_bundle

    settings.MEDIA_ROOT = str(tmp_path)
    with pytest.raises(DeployNotReadyError) as exc:
        build_score_bundle(42)
    assert exc.value.readiness['ready'] is False
    assert any(b['code'] == 'evaluation_missing' for b in exc.value.readiness['blocking'])
