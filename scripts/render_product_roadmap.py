#!/usr/bin/env python3
"""Validate the development ledger and render its human-readable projection."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'docs/product-roadmap.json'
OUTPUT = ROOT / 'docs/PRODUCT_DEVELOPMENT_ROADMAP.md'
STATES = {'planned', 'in_progress', 'implemented', 'tested', 'released', 'customer_accepted'}


def render(data):
    items = data['items']
    by_id = {item['id']: item for item in items}
    if set(by_id) != {f'D{i:02}' for i in range(1, 18)} or len(items) != 17:
        raise ValueError('The ledger must contain D01–D17 exactly once.')
    milestones = {m['id'] for m in data['milestones']}
    for item in items:
        if item['status'] not in STATES or item['milestone'] not in milestones:
            raise ValueError(f'Invalid state/milestone for {item["id"]}')
        if not item['acceptance'] or not item['sources'] or not item['owner']:
            raise ValueError(f'Missing acceptance/source/owner for {item["id"]}')
        if item['status'] in {'tested', 'released', 'customer_accepted'} and not item['evidence']:
            raise ValueError(f'Evidence required for {item["id"]}')
        if any(dep not in by_id for dep in item['dependencies']):
            raise ValueError(f'Unknown dependency for {item["id"]}')
    def visit(key, path):
        if key in path:
            raise ValueError(f'Dependency cycle: {key}')
        for dep in by_id[key]['dependencies']:
            visit(dep, path | {key})
    for key in by_id:
        visit(key, set())
    packets = data.get('implementation_packets', [])
    if len({packet['id'] for packet in packets}) != len(packets):
        raise ValueError('Implementation packet IDs must be unique.')
    for packet in packets:
        if (packet['status'] not in STATES or not packet['description']
                or any(item not in by_id for item in packet['items'])):
            raise ValueError(f'Invalid implementation packet: {packet["id"]}')
        if packet['status'] in {'tested', 'released', 'customer_accepted'} and not packet['evidence']:
            raise ValueError(f'Packet evidence required: {packet["id"]}')
    lines = [
        '# DeclarAI product development roadmap', '',
        (f'Updated {data["updated"]}. Generated from `product-roadmap.json`; edit the ledger and run '
         '`python3 scripts/render_product_roadmap.py`.'), '', data['vision'], '',
        '## Release direction', '', *[f'- {v}' for v in data['direction']], '',
        ('Outcome status is separate from packet evidence. Implemented, tested, released, and '
         'customer accepted are distinct states. No dates or capacity estimates are commitments.'), '',
    ]
    if packets:
        lines += ['## Implementation evidence', '',
                  'Packet checks do not close the acceptance criteria of a roadmap outcome or milestone.', '']
        for packet in packets:
            lines += [f'### {packet["id"]} — {packet["title"]}', '',
                      f'**Packet status:** {packet["status"]}. **Mapped outcomes:** ' + ', '.join(packet['items']) + '.', '',
                      packet['description'], '', '**Evidence:** ' + ('; '.join(packet['evidence']) or 'Qualification pending.'), '',
                      '**Remaining:** ' + packet['remaining'], '']
    qualification = data.get('release_qualification')
    if qualification:
        lines += ['**Release qualification:** ' + qualification['status'] + '. Design-partner acceptance and value gates: '
                  + qualification['design_partner_acceptance'] + ' / ' + qualification['value_gate'] + '.', '']
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
