"""Pure snapshot counts; delivery order is not time, effort or scope completion."""
STATES = ('planned', 'in_progress', 'implemented', 'tested', 'released', 'customer_accepted')
TESTED = {'tested', 'released', 'customer_accepted'}


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
    return {'schema': 'roadmap_status_metrics_v1', 'outcomes': outcomes, 'packets': delivered,
            'delivery': {'tested': tested, 'd07_tested': d07, 'previous_packet': prior['packet'],
                         'tested_added': tested - prior['tested'], 'd07_added': d07 - prior['d07_tested'],
                         'recent': history[-12:], 'total_scope_known': False}}
