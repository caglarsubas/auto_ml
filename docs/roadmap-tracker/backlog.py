"""Dependency-derived planning readiness; completed packets are a separate ledger."""
import copy
import re

STATUSES = ('ready', 'in_progress', 'waiting', 'blocked', 'done')
PHASES = {'queued', 'in_progress', 'done'}
PRIORITIES = {'P0', 'P1', 'P2', 'P3'}
QUALIFIED = {'tested', 'released', 'customer_accepted'}


def project_backlog(ledger):
    raw = ledger.get('backlog')
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get('schema') != 'roadmap_backlog_v1':
        raise ValueError('Invalid roadmap backlog schema')
    tasks = raw.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('Backlog tasks must be a nonempty list')
    outcomes = {x['id'] for x in ledger['items']}
    packets = {x['id']: x for x in ledger.get('implementation_packets', [])}
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError('Invalid backlog task')
        identifier = task.get('id')
        if not isinstance(identifier, str) or not re.fullmatch(r'D[0-9]{2,}-T[0-9]{2,}', identifier) or identifier in by_id:
            raise ValueError('Invalid or duplicate backlog task ID')
        for field in ('title', 'description', 'owner', 'basis'):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise ValueError(f'Missing backlog {field}: {identifier}')
        for field in ('items', 'dependencies', 'acceptance', 'evidence', 'packet_refs'):
            value = task.get(field)
            if (not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value)
                    or len(value) != len(set(value))):
                raise ValueError(f'Invalid backlog {field}: {identifier}')
        if not task['items'] or not set(task['items']) <= outcomes or not task['acceptance']:
            raise ValueError(f'Unknown outcome or missing backlog acceptance: {identifier}')
        if task.get('priority') not in PRIORITIES or task.get('phase') not in PHASES:
            raise ValueError(f'Invalid backlog priority or phase: {identifier}')
        if type(task.get('order')) is not int or task['order'] < 1:
            raise ValueError(f'Invalid backlog order: {identifier}')
        blockers = task.get('blockers')
        if not isinstance(blockers, list):
            raise ValueError(f'Invalid backlog blockers: {identifier}')
        for blocker in blockers:
            if (not isinstance(blocker, dict) or blocker.get('kind') not in {'external_input', 'technical_failure', 'reserved_approval'}
                    or any(not isinstance(blocker.get(f), str) or not blocker[f].strip() for f in ('reason', 'owner', 'resolution'))):
                raise ValueError(f'Backlog blockers require reason, owner and resolution: {identifier}')
        if any(ref not in packets for ref in task['packet_refs']):
            raise ValueError(f'Unknown backlog packet reference: {identifier}')
        packet_outcomes = {item for ref in task['packet_refs'] for item in packets[ref].get('items', [])}
        if task['phase'] in {'done', 'in_progress'} and not set(task['items']) <= packet_outcomes:
            raise ValueError(f'Backlog packet does not cover task outcomes: {identifier}')
        by_id[identifier] = task
    if len({task['order'] for task in tasks}) != len(tasks):
        raise ValueError('Duplicate backlog order')
    visited = set()

    def visit(identifier, path):
        if identifier in path:
            raise ValueError('Backlog dependency cycle')
        if identifier in visited:
            return
        for dep in by_id[identifier]['dependencies']:
            if dep not in by_id:
                raise ValueError(f'Unknown backlog dependency: {dep}')
            visit(dep, path | {identifier})
        visited.add(identifier)
    for identifier in by_id:
        visit(identifier, set())
    projected = []
    for task in tasks:
        unmet = [dep for dep in task['dependencies'] if by_id[dep]['phase'] != 'done']
        if task['phase'] == 'done':
            if (unmet or task['blockers'] or not task['evidence'] or not task['packet_refs']
                    or any(packets[ref]['status'] not in QUALIFIED for ref in task['packet_refs'])):
                raise ValueError(f'Completed backlog task requires qualified packet/evidence and resolved prerequisites: {task["id"]}')
            status = 'done'
        elif task['phase'] == 'in_progress':
            if unmet or task['blockers'] or not task['packet_refs']:
                raise ValueError(f'Active backlog task is not ready or scoped: {task["id"]}')
            status = 'in_progress'
        else:
            status = 'blocked' if task['blockers'] else 'waiting' if unmet else 'ready'
        value = copy.deepcopy(task)
        value.update(status=status, unmet_dependencies=unmet)
        projected.append(value)
    projected.sort(key=lambda t: (t['priority'], t['order']))
    counts = {s: sum(t['status'] == s for t in projected) for s in STATUSES}
    total = len(projected)
    shares = {s: round(counts[s] / total * 100, 1) for s in STATUSES}
    covered = {item for task in tasks for item in task['items']}
    missing = sorted(outcomes - covered)
    baseline = raw.get('baseline')
    delta = None
    if baseline is not None:
        if (not isinstance(baseline, dict) or baseline.get('schema') != 'roadmap_backlog_baseline_v1'
                or not isinstance(baseline.get('label'), str) or not baseline['label'].strip()
                or not isinstance(baseline.get('counts'), dict) or set(baseline['counts']) != set(STATUSES)
                or any(type(n) is not int or n < 0 for n in baseline['counts'].values())
                or type(baseline.get('total')) is not int or sum(baseline['counts'].values()) != baseline['total']):
            raise ValueError('Invalid backlog comparison baseline')
        delta = {'counts': {s: counts[s] - baseline['counts'][s] for s in STATUSES},
                 'percentage_points': {s: round(shares[s] - (baseline['counts'][s] / baseline['total'] * 100
                                                           if baseline['total'] else 0), 1) for s in STATUSES},
                 'total': total - baseline['total']}
    return {'schema': 'roadmap_backlog_projection_v1', 'tasks': projected, 'total': total, 'counts': counts,
            'percentages': shares, 'remaining': total - counts['done'],
            'open': counts['ready'] + counts['in_progress'] + counts['waiting'],
            'covered_outcomes': len(covered), 'outcome_total': len(outcomes), 'unmapped_outcomes': missing,
            'comparison': baseline['label'] if baseline else None, 'delta': delta,
            'scope_note': 'Current remaining-scope inventory; task counts are not effort, release readiness or a guarantee that discovery adds no work.'}
