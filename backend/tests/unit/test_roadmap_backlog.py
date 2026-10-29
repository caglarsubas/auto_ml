"""Remaining scope is planned explicitly and never inferred from historical packets."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


backlog = module('backlog', 'docs/roadmap-tracker/backlog.py')
metrics = module('metrics', 'docs/roadmap-tracker/metrics.py')
roadmap = module('roadmap', 'scripts/render_product_roadmap.py')
pytestmark = pytest.mark.unit


@pytest.fixture
def ledger():
    task = dict(id='D07-T01', title='Bound reads', description='Qualify receipt reads', owner='Platform',
                basis='D07 acceptance gap', priority='P0', phase='queued', order=1, items=['D07'],
                dependencies=[], acceptance=['Queries cancel and restore caller'], blockers=[], evidence=[], packet_refs=[])
    second = dict(copy.deepcopy(task), id='D07-T02', title='Restore profile', order=2, dependencies=['D07-T01'])
    third = dict(copy.deepcopy(task), id='D09-T01', items=['D09'], title='Customer exercise', order=3,
                 dependencies=['D07-T02'], blockers=[dict(kind='external_input', reason='Named operator/profile not recorded',
                                                         owner='Customer', resolution='Record approved exercise scope')])
    return dict(items=[dict(id='D07', status='in_progress'), dict(id='D09', status='planned')],
                implementation_packets=[dict(id='P01', status='tested', items=['D07'])],
                backlog=dict(schema='roadmap_backlog_v1', tasks=[task, second, third]))


def test_dependencies_derive_readiness_and_blockers_require_explicit_input(ledger):
    result = backlog.project_backlog(ledger)
    assert result['counts'] == dict(ready=1, in_progress=0, waiting=1, blocked=1, done=0)
    assert result['open'] == 2 and result['remaining'] == 3
    assert result['tasks'][1]['unmet_dependencies'] == ['D07-T01']
    assert result['covered_outcomes'] == 2 and result['unmapped_outcomes'] == []


def test_done_unlocks_dependents_without_closing_outcomes_or_external_blockers(ledger):
    task = ledger['backlog']['tasks'][0]
    task.update(phase='done', packet_refs=['P01'], evidence=['Retained clean CI/main evidence'])
    result = backlog.project_backlog(ledger)
    assert [task['status'] for task in result['tasks']] == ['done', 'ready', 'blocked']
    assert ledger['items'][0]['status'] == 'in_progress'
    assert result['remaining'] == 2


def test_in_progress_requires_owned_packet_and_ready_dependencies(ledger):
    ledger['backlog']['tasks'][0].update(phase='in_progress', packet_refs=['P01'])
    assert backlog.project_backlog(ledger)['counts']['in_progress'] == 1


@pytest.mark.parametrize('case', ['id', 'duplicate', 'priority', 'phase', 'order', 'duplicate_order', 'title', 'owner',
                                  'description', 'basis', 'items', 'acceptance', 'evidence', 'packet_refs', 'dependencies',
                                  'unknown_dep', 'cycle', 'self_cycle', 'unknown_packet', 'unknown_outcome', 'blocker_reason',
                                  'blocker_owner', 'blocker_resolution', 'blocker_kind', 'blockers', 'empty_tasks', 'schema'])
def test_invalid_planning_records_are_rejected(ledger, case):
    raw, task = ledger['backlog'], ledger['backlog']['tasks'][0]
    if case in ['title', 'owner', 'description', 'basis']:
        task[case] = ' '
    elif case in ['items', 'acceptance']:
        task[case] = []
    elif case in ['evidence', 'packet_refs', 'dependencies']:
        task[case] = ['x', 'x']
    elif case.startswith('blocker_'):
        field = case.removeprefix('blocker_')
        raw['tasks'][2]['blockers'][0][field] = 'unsupported' if field == 'kind' else ''
    elif case == 'blockers':
        task['blockers'] = None
    elif case == 'duplicate':
        raw['tasks'].append(copy.deepcopy(task))
    elif case == 'unknown_dep':
        task['dependencies'] = ['D99-T01']
    elif case == 'cycle':
        task['dependencies'] = ['D07-T02']
    elif case == 'self_cycle':
        task['dependencies'] = ['D07-T01']
    elif case == 'unknown_packet':
        task['packet_refs'] = ['P999']
    elif case == 'unknown_outcome':
        task['items'] = ['D99']
    elif case == 'empty_tasks':
        raw['tasks'] = []
    elif case == 'schema':
        raw['schema'] = 'wrong'
    elif case == 'duplicate_order':
        task['order'] = 2
    else:
        task[case] = {'id': 'unsafe<script>', 'priority': 'P8', 'phase': 'ready', 'order': True}[case]
    with pytest.raises(ValueError):
        backlog.project_backlog(ledger)


@pytest.mark.parametrize('case', ['evidence', 'packet_refs', 'unqualified', 'dependency', 'blocker'])
def test_done_cannot_bypass_evidence_or_unmet_requirements(ledger, case):
    task = ledger['backlog']['tasks'][0]
    task.update(phase='done', evidence=['Qualified'], packet_refs=['P01'])
    if case in ['evidence', 'packet_refs']:
        task[case] = []
    elif case == 'unqualified':
        ledger['implementation_packets'][0]['status'] = 'implemented'
    elif case == 'dependency':
        ledger['backlog']['tasks'][1].update(phase='done', evidence=['Qualified'], packet_refs=['P01'])
        task.update(phase='queued')
    else:
        task['blockers'] = copy.deepcopy(ledger['backlog']['tasks'][2]['blockers'])
    with pytest.raises(ValueError):
        backlog.project_backlog(ledger)


@pytest.mark.parametrize('case', ['packet_refs', 'dependency', 'blocker'])
def test_dispatch_does_not_start_unready_or_unowned_work(ledger, case):
    task = ledger['backlog']['tasks'][0]
    task.update(phase='in_progress', packet_refs=['P01'])
    if case == 'packet_refs':
        task['packet_refs'] = []
    elif case == 'dependency':
        ledger['backlog']['tasks'][1].update(phase='in_progress', packet_refs=['P01'])
    else:
        task['blockers'] = copy.deepcopy(ledger['backlog']['tasks'][2]['blockers'])
    with pytest.raises(ValueError):
        backlog.project_backlog(ledger)


def test_projection_is_pure_and_sorted_by_priority_then_explicit_order(ledger):
    before = copy.deepcopy(ledger)
    ledger['backlog']['tasks'][0]['priority'] = 'P2'
    expected = copy.deepcopy(ledger)
    result = backlog.project_backlog(ledger)
    assert [x['id'] for x in result['tasks']] == ['D07-T02', 'D09-T01', 'D07-T01']
    result['tasks'][0]['acceptance'].append('Cannot mutate source')
    assert ledger == expected and before != ledger


def test_count_delta_tracks_inventory_expansion_and_qualified_work(ledger):
    initial = backlog.project_backlog(ledger)
    ledger['backlog']['baseline'] = dict(schema='roadmap_backlog_baseline_v1', label='Initial inventory',
                                        total=initial['total'], counts=initial['counts'])
    task = ledger['backlog']['tasks'][0]
    task.update(phase='done', packet_refs=['P01'], evidence=['Qualified'])
    result = metrics.status_metrics(ledger)
    assert result['backlog']['delta']['counts'] == dict(ready=0, in_progress=0, waiting=-1, blocked=0, done=1)
    assert result['progress']['backlog']['delta']['counts'] == dict(done=1, open=-1, blocked=0)
    assert result['delivery']['total_scope_known'] is False
    assert result['progress']['outcomes']['counts'] == dict(done=0, open=2, blocked=0)


@pytest.mark.parametrize('bad', [-1, True, '3'])
def test_comparison_counts_must_be_nonnegative_integers(ledger, bad):
    ledger['backlog']['baseline'] = dict(schema='roadmap_backlog_baseline_v1', label='Inventory', total=3,
                                        counts=dict(ready=bad, in_progress=0, waiting=1, blocked=1, done=0))
    with pytest.raises(ValueError):
        backlog.project_backlog(ledger)


def test_future_outcomes_warn_without_inventing_tasks_or_rejecting_legacy(ledger):
    ledger['items'].append(dict(id='D27', status='planned'))
    result = backlog.project_backlog(ledger)
    assert result['unmapped_outcomes'] == ['D27'] and result['total'] == 3
    del ledger['backlog']
    assert backlog.project_backlog(ledger) is None
    assert 'backlog' not in metrics.status_metrics(ledger)


def test_canonical_inventory_covers_every_remaining_outcome_with_actionable_acceptance():
    source = json.loads((ROOT / 'docs/product-roadmap.json').read_text())
    result = backlog.project_backlog(source)
    assert result['covered_outcomes'] == result['outcome_total'] == 26
    assert not result['unmapped_outcomes'] and result['remaining'] > 40
    assert result['counts']['ready'] > 0 and result['counts']['waiting'] > 0 and result['counts']['blocked'] > 0
    assert len([t for t in result['tasks'] if 'D07' in t['items']]) >= 8
    assert 'Remaining roadmap backlog' in roadmap.render(source)
    assert all(t['acceptance'] and t['owner'] and t['basis'] for t in result['tasks'])


@pytest.mark.parametrize('phase', ['in_progress', 'done'])
def test_unrelated_qualified_packet_cannot_claim_task_scope(ledger, phase):
    task = ledger['backlog']['tasks'][0]
    task.update(phase=phase, packet_refs=['P01'], evidence=['Qualified elsewhere'])
    ledger['implementation_packets'][0]['items'] = ['D09']
    with pytest.raises(ValueError, match='does not cover'):
        backlog.project_backlog(ledger)
