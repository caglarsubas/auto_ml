"""Status shares and delivery counts use explicit independent denominators."""
import copy
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
spec = importlib.util.spec_from_file_location('roadmap_metrics', Path(__file__).resolve().parents[3] / 'docs/roadmap-tracker/metrics.py')
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def ledger(n=147):
    return {'items': [{'status': 'planned'} for _ in range(15)] + [{'status': 'in_progress'} for _ in range(11)],
            'implementation_packets': [{'id': f'P{i:02}', 'status': 'tested', 'items': ['D07'] if i > 20 else ['D01']}
                                       for i in range(1, n + 1)]}


def test_new_tested_delivery_increases_counts_while_outcome_percentages_stay_truthful():
    before = metrics.status_metrics(ledger())
    after = metrics.status_metrics(ledger(148))
    assert after['outcomes'] == before['outcomes']
    assert after['outcomes']['percentages']['planned'] == 57.7
    assert after['outcomes']['percentages']['in_progress'] == 42.3
    assert after['delivery']['tested'] == 148 and after['delivery']['d07_tested'] == 128
    assert after['delivery']['tested_added'] == after['delivery']['d07_added'] == 1
    assert after['delivery']['previous_packet'] == 'P147'
    assert after['packets']['percentages']['tested'] == before['packets']['percentages']['tested'] == 100.0
    assert after['delivery']['total_scope_known'] is False


@pytest.mark.parametrize('state', metrics.STATES)
def test_latest_packet_state_is_counted_without_inventing_completion(state):
    value = ledger(148)
    value['implementation_packets'][-1]['status'] = state
    result = metrics.status_metrics(value)
    assert result['delivery']['tested_added'] == (1 if state in metrics.TESTED else 0)
    assert result['packets']['counts'][state] == (148 if state == 'tested' else 1)
    assert result['outcomes']['counts']['planned'] == 15


def test_reconciliation_does_not_inflate_d07_implementation_counts():
    value = ledger(148)
    value['implementation_packets'][-1]['kind'] = 'roadmap_reconciliation'
    result = metrics.status_metrics(value)
    assert result['delivery']['tested'] == 148 and result['delivery']['d07_tested'] == 127
    assert result['delivery']['d07_added'] == 0


@pytest.mark.parametrize('n', [0, 1, 12, 13, 148])
def test_recent_history_is_bounded_ledger_order_and_total_counts_are_not_windowed(n):
    value = ledger(n)
    before = copy.deepcopy(value)
    result = metrics.status_metrics(value)
    history = result['delivery']['recent']
    assert len(history) == min(n, 12) and result['delivery']['tested'] == n
    assert [p['tested'] for p in history] == list(range(max(1, n - 11), n + 1))
    assert value == before
    if n:
        assert history[-1]['packet'] == f'P{n:02}'


def test_empty_population_has_no_division_or_implied_total_product_scope():
    result = metrics.status_metrics({'items': [], 'implementation_packets': []})
    assert result['outcomes']['total'] == result['packets']['total'] == 0
    assert all(p == 0 for p in result['outcomes']['percentages'].values())
    assert result['delivery']['previous_packet'] is None and result['delivery']['total_scope_known'] is False


def test_unknown_status_is_rejected_instead_of_disappearing_from_the_denominator():
    value = ledger()
    value['implementation_packets'][0]['status'] = 'unknown'
    with pytest.raises(ValueError, match='Unknown roadmap state'):
        metrics.status_metrics(value)
