"""Pure snapshot counts; delivery order is not time, effort or scope completion."""
STATES = ('planned', 'in_progress', 'implemented', 'tested', 'released', 'customer_accepted')
TESTED = {'tested', 'released', 'customer_accepted'}
PROGRESS = ('done', 'open', 'blocked')


def progress_distribution(items, baseline=None):
    counts = dict.fromkeys(PROGRESS, 0)
    for item in items:
        if item['status'] not in STATES:
            raise ValueError('Unknown roadmap state')
        reason = item.get('blocked_reason')
        if reason is not None and (not isinstance(reason, str) or not reason.strip() or item['status'] in TESTED):
            raise ValueError('Blocked records require an explicit reason and an open state')
        counts['blocked' if reason else 'done' if item['status'] in TESTED else 'open'] += 1
    total = len(items)
    shares = {key: round(value / total * 100, 1) if total else 0.0 for key, value in counts.items()}
    delta = None
    if baseline is not None:
        previous = baseline.get('counts') if isinstance(baseline, dict) else None
        previous_total = baseline.get('total') if isinstance(baseline, dict) else None
        if (not isinstance(previous, dict) or set(previous) != set(PROGRESS)
                or type(previous_total) is not int or previous_total < 0
                or any(type(value) is not int or value < 0 for value in previous.values())
                or sum(previous.values()) != previous_total):
            raise ValueError('Invalid progress comparison counts')
        delta = {'total': total - previous_total,
                 'counts': {key: counts[key] - previous[key] for key in PROGRESS},
                 'percentage_points': {key: round((counts[key] / total * 100 if total else 0)
                                                 - (previous[key] / previous_total * 100
                                                    if previous_total else 0), 1) for key in PROGRESS}}
    return {'total': total, 'counts': counts, 'percentages': shares, 'delta': delta}


def status_metrics(ledger):
    def distribution(items):
        counts = {s: 0 for s in STATES}
        for item in items:
            if item['status'] not in counts:
                raise ValueError('Unknown roadmap state')
            counts[item['status']] += 1
        return {'total': len(items), 'counts': counts,
                'percentages': {s: round(n / len(items) * 100, 1) if items else 0.0 for s, n in counts.items()}}

    packets = ledger['implementation_packets']
    outcomes = distribution(ledger['items'])
    delivered = distribution(packets)
    history = []
    tested = d07 = 0
    for packet in packets:
        qualifies = packet['status'] in TESTED
        tested += qualifies
        d07 += qualifies and 'D07' in packet['items'] and packet.get('kind') != 'roadmap_reconciliation'
        history.append({'packet': packet['id'], 'tested': tested, 'd07_tested': d07})
    prior = history[-2] if len(history) > 1 else {'packet': None, 'tested': 0, 'd07_tested': 0}
    baseline = ledger.get('progress_baseline')
    if baseline is not None and (not isinstance(baseline, dict)
            or baseline.get('schema') != 'roadmap_progress_baseline_v1'
            or not isinstance(baseline.get('packet'), str) or not baseline['packet']
            or not isinstance(baseline.get('source_commit'), str) or len(baseline['source_commit']) != 40
            or any(c not in '0123456789abcdef' for c in baseline['source_commit'])
            or not all(isinstance(baseline.get(key), dict) for key in ('outcomes', 'packets'))):
        raise ValueError('Invalid progress comparison source')
    result = {'schema': 'roadmap_status_metrics_v1', 'outcomes': outcomes, 'packets': delivered,
            'progress': {'comparison': ({'packet': baseline['packet'], 'source_commit': baseline['source_commit']}
                                        if baseline else None),
                         'outcomes': progress_distribution(ledger['items'], baseline['outcomes'] if baseline else None),
                         'packets': progress_distribution(packets, baseline['packets'] if baseline else None)},
            'delivery': {'tested': tested, 'd07_tested': d07, 'previous_packet': prior['packet'],
                         'tested_added': tested - prior['tested'], 'd07_added': d07 - prior['d07_tested'],
                         'recent': history[-12:], 'total_scope_known': False}}

    # Load the sibling by its source path: both the tracker and renderer import
    # metrics as a standalone module without modifying global import paths.
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('roadmap_backlog', Path(__file__).with_name('backlog.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    backlog = module.project_backlog(ledger)
    if backlog is not None:
        result['backlog'] = backlog
        prior = ledger['backlog'].get('baseline')
        old = None
        if prior:
            old = {'total': prior['total'], 'counts': {'done': prior['counts']['done'],
                   'open': sum(prior['counts'][s] for s in ('ready', 'in_progress', 'waiting')),
                   'blocked': prior['counts']['blocked']}}
        records = [{'status': 'tested' if task['status'] == 'done' else 'planned',
                    **({'blocked_reason': '; '.join(b['reason'] for b in task['blockers'])}
                       if task['status'] == 'blocked' else {})} for task in backlog['tasks']]
        result['progress']['backlog'] = progress_distribution(records, old)
        result['progress']['backlog_comparison'] = backlog['comparison']
    return result
