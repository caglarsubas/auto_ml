"""Canonical ledger invariants and deterministic projection; no runtime feature claims."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
module_spec = importlib.util.spec_from_file_location('roadmap', ROOT / 'scripts/render_product_roadmap.py')
roadmap = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(roadmap)
pytestmark = pytest.mark.unit


@pytest.fixture
def ledger():
    return json.loads(roadmap.LEDGER.read_text())


def test_projection_is_current_and_deterministic(ledger):
    projection = roadmap.render(ledger)
    assert projection == roadmap.OUTPUT.read_text()
    assert projection == roadmap.render(copy.deepcopy(ledger))
    assert 'Canonical implementation queue' in projection
    assert 'documentation only' in projection


def test_future_outcome_extension_preserves_original_ids(ledger):
    future = copy.deepcopy(ledger['items'][-1])
    future.update(id='D27', title='Future bounded outcome', dependencies=['D26'])
    ledger['items'].append(future)
    assert 'D27' in roadmap.render(ledger)


def test_documentation_evidence_does_not_promote_mapped_outcomes(ledger):
    future = copy.deepcopy(ledger['items'][-1])
    future.update(id='D27', title='Planned outcome', status='planned', evidence=[], dependencies=[])
    ledger['items'].append(future)
    packet = copy.deepcopy(next(packet for packet in ledger['implementation_packets']
                                if packet.get('kind') == 'roadmap_reconciliation'))
    packet.update(id='P99', status='tested', items=['D27'], evidence=['Documentation checks'])
    ledger['implementation_packets'].append(packet)
    before = copy.deepcopy(ledger)
    roadmap.render(ledger)
    assert ledger == before
    assert roadmap.validate(ledger)['D27']['status'] == 'planned'
    assert roadmap.validate(ledger)['D27']['evidence'] == []


def test_original_schema_still_accepts_seventeen_outcomes():
    item = dict(milestone='M1', title='Outcome', description='Bounded work', acceptance='Observable result',
                owner='Backend', sources=['Approved requirement'], status='planned', evidence=[], dependencies=[])
    legacy = dict(schema_version=1, updated='2026-10-07', baseline_commit='dac05741', vision='Governed models',
                  delivery='Evidence before release', direction=['Private deployment'], architecture=['Shared runtime'],
                  release_acceptance=['Reproduction'], decisions=['Human authority'], research_sources=[],
                  milestones=[dict(id='M1', title='Foundation', purpose='Correctness', gate='Qualification')],
                  items=[dict(item, id=f'D{i:02}') for i in range(1, 18)])
    assert len(roadmap.validate(legacy)) == 17
    assert 'D17' in roadmap.render(legacy)


@pytest.mark.parametrize('field', ['title', 'description', 'owner', 'acceptance', 'sources', 'status', 'milestone', 'dependencies', 'evidence'])
def test_required_outcome_metadata_cannot_disappear(ledger, field):
    ledger['items'][-1].pop(field)
    with pytest.raises(ValueError):
        roadmap.render(ledger)


@pytest.mark.parametrize('field', ['title', 'description', 'remaining', 'items', 'status', 'evidence'])
def test_required_packet_metadata_cannot_disappear(ledger, field):
    ledger['implementation_packets'][-1].pop(field)
    with pytest.raises(ValueError):
        roadmap.render(ledger)


@pytest.mark.parametrize('case', [
    'duplicate_outcome', 'invalid_id', 'missing_original', 'unknown_dependency', 'cycle',
    'duplicate_dependency', 'invalid_status', 'unknown_milestone', 'duplicate_milestone',
    'duplicate_packet', 'unknown_packet_outcome', 'invalid_packet_kind', 'unknown_queue_outcome',
    'duplicate_queue_order', 'unknown_pilot_outcome', 'unknown_release_outcome',
    'unknown_reconciled_outcome', 'missing_source', 'missing_priority_delta', 'short_base', 'missing_queue',
])
def test_invalid_references_and_states_are_rejected(ledger, case):
    item = ledger['items'][-1]
    if case == 'duplicate_outcome':
        ledger['items'].append(copy.deepcopy(item))
    elif case == 'invalid_id':
        item['id'] = 'D00'
    elif case == 'missing_original':
        ledger['items'].pop(0)
    elif case == 'unknown_dependency':
        item['dependencies'] = ['D99']
    elif case == 'cycle':
        ledger['items'][0]['dependencies'] = ['D26']
    elif case == 'duplicate_dependency':
        item['dependencies'] = ['D01', 'D01']
    elif case == 'invalid_status':
        item['status'] = 'done'
    elif case == 'unknown_milestone':
        item['milestone'] = 'absent'
    elif case == 'duplicate_milestone':
        ledger['milestones'].append(copy.deepcopy(ledger['milestones'][0]))
    elif case == 'duplicate_packet':
        ledger['implementation_packets'].append(copy.deepcopy(ledger['implementation_packets'][0]))
    elif case == 'unknown_packet_outcome':
        ledger['implementation_packets'][-1]['items'] = ['D99']
    elif case == 'invalid_packet_kind':
        ledger['implementation_packets'][-1]['kind'] = 'fake_release'
    elif case == 'unknown_queue_outcome':
        ledger['implementation_queue'][0]['items'] = ['D99']
    elif case == 'duplicate_queue_order':
        ledger['implementation_queue'][1]['order'] = 1
    elif case == 'unknown_pilot_outcome':
        ledger['release_qualification']['pilot_required_outcomes'] = ['D99']
    elif case == 'unknown_release_outcome':
        ledger['release_qualification']['broader_release_required_outcomes'] = ['D99']
    elif case == 'unknown_reconciled_outcome':
        ledger['reconciliation']['added_outcomes'] = ['D99']
    elif case == 'missing_source':
        ledger['reconciliation'].pop('source_thread_id')
    elif case == 'missing_priority_delta':
        ledger['reconciliation']['priority_delta'] = []
    elif case == 'short_base':
        ledger['reconciliation']['implementation_base'] = '506945f9'
    elif case == 'missing_queue':
        ledger['implementation_queue'] = []
    with pytest.raises(ValueError):
        roadmap.render(ledger)


@pytest.mark.parametrize('state', ['implemented', 'tested', 'released', 'customer_accepted'])
@pytest.mark.parametrize('record', ['outcome', 'packet'])
def test_evidence_required_for_delivery_states(ledger, state, record):
    target = ledger['items'][-1] if record == 'outcome' else ledger['implementation_packets'][-1]
    target.update(status=state, evidence=[])
    with pytest.raises(ValueError, match='evidence|Evidence'):
        roadmap.render(ledger)


def test_cli_drift_check_rejects_modified_projection(ledger, tmp_path, monkeypatch):
    source, projection = tmp_path / 'ledger.json', tmp_path / 'roadmap.md'
    source.write_text(json.dumps(ledger))
    projection.write_text(roadmap.render(ledger))
    monkeypatch.setattr(roadmap, 'LEDGER', source)
    monkeypatch.setattr(roadmap, 'OUTPUT', projection)
    monkeypatch.setattr('sys.argv', ['render_product_roadmap.py', '--check'])
    roadmap.main()
    projection.write_text(projection.read_text() + 'unauthorized projection edit\n')
    with pytest.raises(SystemExit, match='projection differs'):
        roadmap.main()
