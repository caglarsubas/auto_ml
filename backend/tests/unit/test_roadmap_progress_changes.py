"""Progress comparisons include open and explicitly blocked work, with honest totals."""

import copy
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
spec = importlib.util.spec_from_file_location('progress_metrics', Path(__file__).resolve().parents[3] / 'docs/roadmap-tracker/metrics.py')
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


@pytest.mark.parametrize('state,group', [(state, 'done' if state in metrics.TESTED else 'open') for state in metrics.STATES])
def test_every_record_remains_in_exactly_one_progress_bucket(state, group):
    value = metrics.progress_distribution([{'status': state}])
    assert value['counts'] == {key: int(key == group) for key in metrics.PROGRESS}
    assert value['percentages'][group] == 100.0 and value['delta'] is None


def test_prerequisites_do_not_invent_blockers_and_explicit_reasons_are_separate():
    records = [{'status': 'planned', 'dependencies': ['D07']},
               {'status': 'in_progress', 'blocked_reason': 'Customer restore environment unavailable'},
               {'status': 'tested'}]
    before = copy.deepcopy(records)
    value = metrics.progress_distribution(records)
    assert value['counts'] == {'done': 1, 'open': 1, 'blocked': 1}
    assert value['total'] == 3 and records == before


def test_resolving_a_blocker_and_completing_work_reports_all_signed_changes():
    previous = metrics.progress_distribution([{'status': 'tested'}, {'status': 'in_progress', 'blocked_reason': 'Review needed'},
                                             {'status': 'planned'}])
    current = metrics.progress_distribution([{'status': 'tested'}, {'status': 'tested'}, {'status': 'planned'}], previous)
    assert current['counts'] == {'done': 2, 'open': 1, 'blocked': 0}
    assert current['delta']['counts'] == {'done': 1, 'open': 0, 'blocked': -1}
    assert current['delta']['percentage_points'] == {'done': 33.3, 'open': 0.0, 'blocked': -33.3}
    assert current['delta']['total'] == 0


def test_adding_unfinished_work_increases_open_and_the_denominator_without_fake_completion():
    previous = {'total': 2, 'counts': {'done': 2, 'open': 0, 'blocked': 0}}
    current = metrics.progress_distribution([{'status': 'tested'}, {'status': 'tested'}, {'status': 'in_progress'}], previous)
    assert current['delta']['counts'] == {'done': 0, 'open': 1, 'blocked': 0}
    assert current['delta']['total'] == 1
    assert current['percentages'] == {'done': 66.7, 'open': 33.3, 'blocked': 0.0}
    assert current['delta']['percentage_points'] == {'done': -33.3, 'open': 33.3, 'blocked': 0.0}


def test_empty_comparisons_have_zero_shares_and_no_unknown_history_is_invented():
    value = metrics.progress_distribution([])
    assert value['total'] == 0 and value['delta'] is None
    assert value['percentages'] == dict.fromkeys(metrics.PROGRESS, 0.0)
    changed = metrics.progress_distribution([{'status': 'planned'}], value)
    assert changed['delta']['counts'] == {'done': 0, 'open': 1, 'blocked': 0}


@pytest.mark.parametrize('record', [
    {'status': 'tested', 'blocked_reason': 'Contradiction'},
    {'status': 'in_progress', 'blocked_reason': ''},
    {'status': 'planned', 'blocked_reason': 123},
])
def test_invalid_or_contradictory_blockers_fail_instead_of_changing_the_counts(record):
    with pytest.raises(ValueError, match='Blocked records'):
        metrics.progress_distribution([record])


@pytest.mark.parametrize('previous', [
    {'total': True, 'counts': {'done': 1, 'open': 0, 'blocked': 0}},
    {'total': 1, 'counts': {'done': 1, 'open': 0}},
    {'total': 1, 'counts': {'done': -1, 'open': 2, 'blocked': 0}},
    {'total': 1, 'counts': {'done': 0, 'open': 0, 'blocked': 0}},
    {'total': 1, 'counts': {'done': '1', 'open': 0, 'blocked': 0}},
])
def test_malformed_comparison_counts_are_rejected(previous):
    with pytest.raises(ValueError, match='comparison counts'):
        metrics.progress_distribution([], previous)


def test_outcomes_and_packets_keep_independent_versioned_comparisons_without_mutation():
    baseline = {'schema': 'roadmap_progress_baseline_v1', 'packet': 'P153', 'source_commit': 'a' * 40,
                'outcomes': {'total': 1, 'counts': {'done': 0, 'open': 1, 'blocked': 0}},
                'packets': {'total': 1, 'counts': {'done': 1, 'open': 0, 'blocked': 0}}}
    ledger = {'items': [{'status': 'planned'}], 'implementation_packets': [
        {'id': 'P153', 'status': 'tested', 'items': ['D07']},
        {'id': 'P154', 'status': 'in_progress', 'items': ['D07']}], 'progress_baseline': baseline}
    before = copy.deepcopy(ledger)
    value = metrics.status_metrics(ledger)
    assert value['progress']['comparison'] == {'packet': 'P153', 'source_commit': 'a' * 40}
    assert value['progress']['outcomes']['delta']['counts'] == {'done': 0, 'open': 0, 'blocked': 0}
    assert value['progress']['packets']['delta']['counts'] == {'done': 0, 'open': 1, 'blocked': 0}
    assert value['delivery']['tested'] == 1 and value['delivery']['total_scope_known'] is False
    assert ledger == before


@pytest.mark.parametrize('field,value', [('schema', 'unknown'), ('source_commit', 'not-a-commit'), ('packet', ''), ('outcomes', None), ('packets', None)])
def test_invalid_comparison_identity_is_rejected(field, value):
    baseline = {'schema': 'roadmap_progress_baseline_v1', 'packet': 'P153', 'source_commit': 'a' * 40,
                'outcomes': {'total': 0, 'counts': dict.fromkeys(metrics.PROGRESS, 0)},
                'packets': {'total': 0, 'counts': dict.fromkeys(metrics.PROGRESS, 0)}}
    baseline[field] = value
    with pytest.raises(ValueError, match='comparison source'):
        metrics.status_metrics({'items': [], 'implementation_packets': [], 'progress_baseline': baseline})
