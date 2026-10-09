"""Outcome-access accounting for immutable native executions.

Identity uses the frozen source and row membership, never predictions, objective,
selected features or encoded positive-class meaning. Hashes are not signatures.
The shared-filesystem lock qualifies the current single-installation profile;
distributed audit durability and confirmatory protocols remain separate work.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import re
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from modeling.models import HoldoutAccess


LIMITATION = ('All assessments are exploratory. Reusing final outcomes, including overlapping '
    'rows and failed access attempts, cannot establish independent confirmation. Unknown '
    'historical access is not evidence of an unused holdout. Source edits/reordered imports '
    'are not linked automatically; independent review and confirmatory protocols remain required.')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def holdout_spec(source_sha256, target_column, rows, source_kind):
    rows = [row.item() if hasattr(row, 'item') else row for row in rows]
    if (not re.fullmatch('[0-9a-f]{64}', str(source_sha256))
            or not isinstance(target_column, str) or not target_column
            or source_kind not in ('raw_snapshot', 'processed_snapshot')
            or not rows or any(type(row) not in (str, int) for row in rows)
            or len({json.dumps(row) for row in rows}) != len(rows)):
        raise ValueError('Final assessment requires a valid frozen source, target and unique row membership.')
    rows = sorted(rows, key=lambda row: json.dumps(row))
    spec = {'schema_version': 1, 'source_sha256': source_sha256,
            'target_column': target_column, 'rows': rows, 'source_kind': source_kind}
    # Source representation is provenance, not a way to reset outcome identity.
    spec['sha256'] = _digest({key: spec[key] for key in ('source_sha256', 'target_column', 'rows')})
    return spec


def verify_holdout_spec(spec, model=None, manifest=None):
    if not spec:
        return None  # Additive legacy migration: missing evidence stays unknown.
    expected = holdout_spec(spec.get('source_sha256'), spec.get('target_column'),
        spec.get('rows') or [], spec.get('source_kind'))
    if spec != expected:
        raise ValueError('Final-outcome identity is invalid or altered. Create a verified execution.')
    if model is not None and manifest is not None:
        files = manifest.get('files') or {}
        source = 'raw_input.csv' if spec['source_kind'] == 'raw_snapshot' else next(
            (name for name in files if name.startswith('dataset.')), '')
        contract = model.get('prediction_contract') or {}
        membership = (model.get('split') or {}).get('membership') or {}
        if (files.get(source, {}).get('sha256') != spec['source_sha256']
                or contract.get('target_column') != spec['target_column']
                or holdout_spec(spec['source_sha256'], spec['target_column'],
                    membership.get('test') or [], spec['source_kind']) != spec):
            raise ValueError('Final-outcome identity does not match the frozen source, target or split.')
    return spec


def holdout_history(spec, file_id, *, exclude_id=None, limit=50, offset=0):
    """Read receipts only; this operation never opens final inputs or labels."""
    spec = verify_holdout_spec(spec)
    query = Q(file_id=file_id, holdout_key='') if spec else Q(file_id=file_id)
    if spec:
        query |= Q(dataset_sha256=spec['source_sha256'])
    records = HoldoutAccess.objects.filter(query).exclude(pk=exclude_id).order_by('accessed_at', 'id')
    matches, exact, overlap, unknown = [], 0, 0, 0
    rows = set(spec['rows']) if spec else set()
    for receipt in records:
        prior = receipt.holdout_spec
        if not spec or not receipt.holdout_key or not prior:
            relation, n_overlap = 'historical_identity_unknown', None
            unknown += 1
        elif prior.get('target_column') != spec['target_column']:
            continue
        else:
            verify_holdout_spec(prior)
            if receipt.holdout_key != prior['sha256']:
                raise ValueError('Recorded final-outcome access identity is inconsistent.')
            n_overlap = len(rows.intersection(prior['rows']))
            if not n_overlap:
                continue
            if prior['sha256'] == spec['sha256']:
                relation = 'same_final_rows'
                exact += 1
            else:
                relation = 'overlapping_final_rows'
                overlap += 1
        matches.append({'access_id': str(receipt.pk),
            'execution_id': str(receipt.execution_id) if receipt.execution_id else None,
            'file_id': receipt.file_id, 'accessed_at': receipt.accessed_at.isoformat(),
            'actor': receipt.actor_snapshot or {'identity': 'historical_or_unattributed'},
            'attempt_state': receipt.attempt_state, 'evidence_status': receipt.evidence_status,
            'relation': relation, 'overlap_rows': n_overlap, 'parameters': receipt.parameters})
    return {'schema_version': 1, 'holdout_key': spec['sha256'] if spec else None,
        'identity_status': 'verified_snapshot' if spec else 'historical_unverified',
        'same_final_rows_accesses': exact, 'overlapping_final_rows_accesses': overlap,
        'unknown_history_accesses': unknown, 'total_related_accesses': len(matches),
        'records': matches[offset:offset + limit], 'offset': offset, 'limit': limit,
        'next_offset': offset + limit if offset + limit < len(matches) else None,
        'evidence_status': 'exploratory', 'limitation': LIMITATION}


def reserve_holdout_access(spec, file_id, execution_id, actor, parameters, dataset_sha256=''):
    """Commit an attributable reservation before any outcome deserialization.

    Serialize reservations for the same source/target, across different splits
    and file IDs. Started/failed attempts count conservatively as possible access.
    """
    spec = verify_holdout_spec(spec)
    key = _digest([spec['source_sha256'], spec['target_column']]) if spec else _digest(['legacy', file_id])
    directory = Path(settings.MEDIA_ROOT) / 'holdout_access_locks'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (key + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with transaction.atomic():
                history = holdout_history(spec, file_id)
                authenticated = actor is not None and actor.is_authenticated
                receipt = HoldoutAccess.objects.create(execution_id=execution_id, file_id=file_id,
                    dataset_sha256=spec['source_sha256'] if spec else dataset_sha256,
                    holdout_key=spec['sha256'] if spec else '', holdout_spec=spec or {},
                    actor=actor if authenticated else None,
                    actor_snapshot={'id': actor.pk, 'username': actor.get_username()} if authenticated else {'identity': 'unattributed'},
                    parameters=parameters, attempt_state='started')
            return receipt, history
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
