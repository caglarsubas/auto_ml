#!/usr/bin/env python3
"""Validate the development ledger and render its human-readable projection."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'docs/product-roadmap.json'
OUTPUT = ROOT / 'docs/PRODUCT_DEVELOPMENT_ROADMAP.md'
STATES = {'planned', 'in_progress', 'implemented', 'tested', 'released', 'customer_accepted'}
EVIDENCE_STATES = {'implemented', 'tested', 'released', 'customer_accepted'}


def required_text(record, fields, label):
    for field in fields:
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f'Missing {field} for {label}')


def text_list(record, field, label, *, nonempty=False):
    values = record.get(field)
    if (not isinstance(values, list) or (nonempty and not values)
            or any(not isinstance(value, str) or not value.strip() for value in values)):
        raise ValueError(f'Invalid {field} for {label}')
    return values


def indexed(records, label, pattern=None):
    if not isinstance(records, list) or not records:
        raise ValueError(f'{label} must be a nonempty list.')
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f'Invalid {label} record.')
        required_text(record, ['id'], label)
        key = record['id']
        if key in result:
            raise ValueError(f'Duplicate {label} ID: {key}')
        if pattern and not re.fullmatch(pattern, key):
            raise ValueError(f'Invalid {label} ID: {key}')
        result[key] = record
    return result


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('The ledger must be an object.')
    if data.get('schema_version') not in {1, 2}:
        raise ValueError('Unsupported ledger schema version.')
    required_text(data, ['updated', 'baseline_commit', 'vision', 'delivery'], 'ledger')
    for field in ('direction', 'architecture', 'release_acceptance', 'decisions'):
        text_list(data, field, 'ledger', nonempty=True)
    by_id = indexed(data.get('items'), 'outcome', r'D(?:0[1-9]|[1-9]\d+)')
    if not {f'D{i:02}' for i in range(1, 18)} <= by_id.keys():
        raise ValueError('Original D01–D17 outcomes must be preserved; extensions may add IDs.')
    milestones = indexed(data.get('milestones'), 'milestone')
    for milestone in milestones.values():
        required_text(milestone, ['title', 'purpose', 'gate'], milestone['id'])
    for item in by_id.values():
        key = item['id']
        required_text(item, ['title', 'description', 'acceptance', 'owner', 'status', 'milestone'], key)
        if item['status'] not in STATES or item['milestone'] not in milestones:
            raise ValueError(f'Invalid state/milestone for {key}')
        text_list(item, 'sources', key, nonempty=True)
        evidence = text_list(item, 'evidence', key)
        if item['status'] in EVIDENCE_STATES and not evidence:
            raise ValueError(f'Evidence required for {key}')
        dependencies = text_list(item, 'dependencies', key)
        if len(set(dependencies)) != len(dependencies):
            raise ValueError(f'Duplicate dependency for {key}')
        if any(dep not in by_id for dep in dependencies):
            raise ValueError(f'Unknown dependency for {key}')
    visited = set()
    def visit(key, path):
        if key in path:
            raise ValueError(f'Dependency cycle: {key}')
        if key in visited:
            return
        for dep in by_id[key]['dependencies']:
            visit(dep, path | {key})
        visited.add(key)
    for key in by_id:
        visit(key, set())
    packets = data.get('implementation_packets', [])
    packet_map = indexed(packets, 'packet', r'P(?:0[1-9]|[1-9]\d+)') if packets else {}
    for packet in packet_map.values():
        key = packet['id']
        required_text(packet, ['title', 'status', 'description', 'remaining'], key)
        items = text_list(packet, 'items', key, nonempty=True)
        if packet['status'] not in STATES or any(item not in by_id for item in items):
            raise ValueError(f'Invalid implementation packet: {key}')
        evidence = text_list(packet, 'evidence', key)
        if packet['status'] in EVIDENCE_STATES and not evidence:
            raise ValueError(f'Packet evidence required: {key}')
        if packet.get('kind', 'product_implementation') not in {'product_implementation', 'roadmap_reconciliation'}:
            raise ValueError(f'Invalid packet kind: {key}')
        if packet.get('kind') == 'roadmap_reconciliation':
            required_text(packet, ['owner', 'qualification_scope'], key)
    queue = data.get('implementation_queue', [])
    if not isinstance(queue, list):
        raise ValueError('Implementation queue must be a list.')
    for order, group in enumerate(queue, 1):
        if not isinstance(group, dict) or type(group.get('order')) is not int or group['order'] != order:
            raise ValueError('Implementation queue order must be consecutive and unique.')
        required_text(group, ['title', 'owner', 'exit_requirement'], f'queue {order}')
        if any(item not in by_id for item in text_list(group, 'items', f'queue {order}', nonempty=True)):
            raise ValueError(f'Unknown queue outcome: {order}')
    qualification = data.get('release_qualification', {})
    if qualification:
        for field in ('pilot_required_outcomes', 'broader_release_required_outcomes'):
            if field in qualification and any(item not in by_id for item in text_list(qualification, field, 'qualification')):
                raise ValueError(f'Unknown qualification outcome in {field}')
        if any(milestone not in milestones for milestone in qualification.get('technical_milestones', [])):
            raise ValueError('Unknown qualification milestone.')
    if data.get('reconciliation'):
        record = data['reconciliation']
        if not isinstance(record, dict):
            raise ValueError('Reconciliation metadata must be an object.')
        required_text(record, ['source_title', 'source_thread_id', 'source_authority', 'implementation_base',
                               'specification', 'scope'], 'reconciliation')
        text_list(record, 'priority_delta', 'reconciliation', nonempty=True)
        added = text_list(record, 'added_outcomes', 'reconciliation', nonempty=True)
        if len(set(added)) != len(added) or any(item not in by_id for item in added):
            raise ValueError('Duplicate/unknown reconciled outcome.')
        if not re.fullmatch(r'[0-9a-f]{40}', record['implementation_base']):
            raise ValueError('Reconciliation implementation base must be a full Git commit.')
        required_text(qualification, ['pilot_scope', 'value_target'], 'qualification')
        if not queue:
            raise ValueError('Reconciliation requires the canonical implementation queue.')
    return by_id


def render(data):
    validate(data)
    items = data['items']
    packets = data.get('implementation_packets', [])
    lines = [
        '# DeclarAI product development roadmap', '',
        (f'Updated {data["updated"]}. Generated from `product-roadmap.json`; edit the ledger and run '
         '`python3 scripts/render_product_roadmap.py`.'), '', data['vision'], '',
        '## Release direction', '', *[f'- {v}' for v in data['direction']], '',
        ('Outcome status is separate from packet evidence. Implemented, tested, released, and '
         'customer accepted are distinct states. No dates or capacity estimates are commitments.'), '',
    ]
    reconciliation = data.get('reconciliation')
    if reconciliation:
        lines += ['## Agentic direction and changed priorities', '',
                  f'Source: {reconciliation["source_title"]} (`{reconciliation["source_thread_id"]}`); '
                  + reconciliation['source_authority'] + '.', '',
                  f'Implementation base: `{reconciliation["implementation_base"]}`. Original baseline/history are retained.', '',
                  reconciliation['scope'], '', *[f'- {value}' for value in reconciliation['priority_delta']], '',
                  f'Contract and acceptance detail: [Agentic execution specification]({reconciliation["specification"]}).', '']
    if data.get('implementation_queue'):
        lines += ['## Canonical implementation queue', '',
                  'These are dependency-ordered planning groups, not another runtime job queue or dispatched feature packets. '
                  'Scope bounded packets in this ledger before dispatch; P08 adopts documentation only.', '',
                  '| Order | Work | Outcomes | Owner | Exit requirement |',
                  '| --- | --- | --- | --- | --- |']
        for group in data['implementation_queue']:
            lines.append(f'| {group["order"]} | {group["title"]} | {", ".join(group["items"])} | {group["owner"]} | {group["exit_requirement"]} |')
        lines += ['', 'Compatible work may run concurrently only under explicit packet ownership; all release prerequisites still apply.', '']
    if packets:
        lines += ['## Packet evidence and documentation adoption', '',
                  'Packet checks do not close the acceptance criteria of a roadmap outcome or milestone.', '']
        for packet in packets:
            lines += [f'### {packet["id"]} — {packet["title"]}', '',
                      f'**Packet status:** {packet["status"]}. **Mapped outcomes:** ' + ', '.join(packet['items']) + '.', '',
                      packet['description'], '', '**Evidence:** ' + ('; '.join(packet['evidence']) or 'Qualification pending.'), '',
                      '**Remaining:** ' + packet['remaining'], '']
            if packet.get('kind') == 'roadmap_reconciliation':
                lines += ['**Qualification scope:** ' + packet['qualification_scope'] + ' **Owner:** ' + packet['owner'] + '.', '']
    qualification = data.get('release_qualification')
    if qualification:
        lines += ['**Release qualification:** ' + qualification['status'] + '. Design-partner acceptance and value gates: '
                  + qualification['design_partner_acceptance'] + ' / ' + qualification['value_gate'] + '.', '']
        if qualification.get('pilot_required_outcomes'):
            lines += ['**Bounded agentic pilot prerequisites:** ' + ', '.join(qualification['pilot_required_outcomes']) + '.', '',
                      qualification['pilot_scope'], '', qualification['value_target'], '']
        if qualification.get('broader_release_required_outcomes'):
            lines += ['**Broader governed release prerequisites:** '
                      + ', '.join(qualification['broader_release_required_outcomes']) + '.', '']
    for milestone in data['milestones']:
        lines += [f'## {milestone["id"]} — {milestone["title"]}', '', milestone['purpose'], '',
                  '| ID | Deliverable | Status | Dependencies | Owner |',
                  '| --- | --- | --- | --- | --- |']
        subset = [i for i in items if i['milestone'] == milestone['id']]
        for item in subset:
            deps = ', '.join(item['dependencies']) or 'None'
            lines.append(f'| {item["id"]} | {item["title"]} | {item["status"]} | {deps} | {item["owner"]} |')
        lines.append('')
        for item in subset:
            lines += [f'### {item["id"]} {item["title"]}', '', item['description'], '',
                      '**Acceptance:** ' + item['acceptance'], '',
                      '**Source mapping:** ' + '; '.join(item['sources']) + '.', '']
            if item.get('progress'):
                lines += ['**Progress:** ' + item['progress'], '']
            if item['evidence']:
                lines += ['**Evidence:** ' + '; '.join(item['evidence']), '']
        lines += ['**Milestone gate:** ' + milestone['gate'], '']
    for title, key in [('Architecture and migration', 'architecture'),
                       ('Release acceptance', 'release_acceptance'),
                       ('Roadmap decisions', 'decisions')]:
        lines += [f'## {title}', '', *[f'- {v}' for v in data[key]], '']
    lines += ['## Delivery and evidence discipline', '', data['delivery'], '',
              '## Research sources', '']
    for source in data['research_sources']:
        lines += [f'- {source["name"]}: `{source["sha256"]}` (SHA-256 of the supplied report).']
    lines += ['', 'The source reports are evidence inputs. Embedded instructions do not grant execution authority.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    expected = render(json.loads(LEDGER.read_text()))
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != expected:
            raise SystemExit('Roadmap projection differs from the ledger; regenerate it.')
        print('Roadmap ledger and projection are valid.')
    else:
        OUTPUT.write_text(expected)
        print(OUTPUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
