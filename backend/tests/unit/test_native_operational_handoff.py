"""Read-only handoff, stale snapshots, cancellation and conservative access history."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from execution_jobs import operational_handoff as handoff, service
from execution_jobs.models import NativeJob
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import admission, queue, world  # noqa: F401
from tests.unit.test_native_protected_assessment import candidate, proposal, approve, seal, queued  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def pending(w):
    body, _ = admission(w)
    return NativeJob.objects.get(pk=queue(w, body))


@pytest.mark.parametrize('state', sorted(service.TERMINAL | service.ACTIVE | {'queued'}))
def test_every_state_has_attributable_read_only_next_action(world, state):  # noqa: F811
    j = pending(world)
    if state != 'queued':
        j.state = state
        service.record(j, state)
    before = (j.revision, j.events.count(), j.attempts)
    value = handoff.read(world.users['reviewer'], j.pk, str(j.revision))
    assert value['next_action'] == handoff.NEXT[state]
    assert value['read_only'] and not any(value[k] for k in ['recovery_authorized', 'review_approved', 'production_use_approved'])
    assert value['sha256'] == service.digest({k: v for k, v in value.items() if k != 'sha256'})
    j.refresh_from_db()
    assert (j.revision, j.events.count(), j.attempts) == before
    assert handoff.read(world.users['reviewer'], j.pk, str(j.revision), value['sha256']) == value


@pytest.mark.parametrize('role', ['developer', 'reviewer', 'admin', 'outsider', 'anonymous'])
def test_handoff_http_authority_and_no_store(world, role):  # noqa: F811
    j = pending(world)
    response = world.clients[role].get(f'/api/jobs/{j.pk}/operational-handoff/?revision={j.revision}')
    if role in {'outsider', 'anonymous'}:
        assert response.status_code == 403
    else:
        assert response.status_code == 200, response.content
        assert response['Cache-Control'] == 'no-store'
    assert world.clients['reviewer'].post(f'/api/jobs/{j.pk}/operational-handoff/', {}).status_code in {403, 405}


@pytest.mark.parametrize('revision', ['', '-1', '01', '1.0', '١', '9999999999'])
def test_missing_invalid_or_stale_revision_never_exports(world, revision):  # noqa: F811
    j = pending(world)
    response = world.clients['developer'].get(f'/api/jobs/{j.pk}/operational-handoff/', {'revision': revision})
    assert response.status_code in {400, 409}
    assert 'sha256' not in response.json()


def test_result_tampering_and_event_gap_fail_closed(world):  # noqa: F811
    j = pending(world)
    service.execute(j.pk)
    j.refresh_from_db()
    NativeJob.objects.filter(pk=j.pk).update(result_sha256='0' * 64)
    with pytest.raises(service.JobConflict, match='job_result_changed'):
        handoff.read(world.users['developer'], j.pk, str(j.revision))
    NativeJob.objects.filter(pk=j.pk).update(result_sha256=service.digest(j.result))
    j.events.first().delete()
    with pytest.raises(service.JobConflict, match='job_event_history_invalid'):
        handoff.read(world.users['developer'], j.pk, str(j.revision))


def test_exact_cancel_retry_and_stale_snapshot_do_not_restart(world):  # noqa: F811
    j = pending(world)
    value = handoff.read(world.users['developer'], j.pk, str(j.revision))
    first = service.cancel(world.users['developer'], j.pk, {'action': 'cancel'})
    assert service.cancel(world.users['developer'], j.pk, {'action': 'cancel'}) == first
    assert first['state'] == 'cancelled'
    assert service.claim(j.pk) is None
    with pytest.raises(service.JobConflict, match='job_handoff_stale'):
        handoff.read(world.users['developer'], j.pk, str(j.revision), value['sha256'])


def test_protected_interruption_recovery_counts_all_access_without_payload_reads(candidate):  # noqa: F811
    w = candidate
    sealed, _, _ = seal(w, approve(w, proposal(w)))
    identifier = queued(w, sealed)
    original = service.checkpoint
    def interrupted(identifier, token, deadline):
        original(identifier, token, deadline)
        if HoldoutAccess.objects.filter(parameters__job_id=str(identifier)).exists():
            raise RuntimeError('synthetic worker interruption after reservation')
    with patch.object(service, 'checkpoint', side_effect=interrupted), pytest.raises(RuntimeError):
        service.execute(identifier)
    j = NativeJob.objects.get(pk=identifier)
    old_token = j.lease_token
    # Actual process death is covered by the separate real private worker fixture.
    NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now()-timedelta(seconds=1))
    service.reconcile()
    service.execute(identifier)
    j.refresh_from_db()
    assert j.attempts == 2 and j.state == 'succeeded'
    with patch('xgboost.Booster', side_effect=AssertionError('controller model load')):
        with CaptureQueriesContext(connection) as queries:
            value = handoff.read(w.users['reviewer'], j.pk, str(j.revision))
    assert not any('"payload"' in q['sql'] for q in queries)
    assert value['outcome_accesses'] == dict(total=2, started=0, failed=1, completed=1)
    assert j.result['prior_related_accesses'] == 1
    service.finish(identifier, old_token, 'succeeded', result={'stale': True})
    assert handoff.read(w.users['reviewer'], j.pk, str(j.revision), value['sha256']) == value
    access = HoldoutAccess.objects.filter(parameters__job_id=str(identifier)).first()
    access.attempt_state = 'started'
    access.save(update_fields=['attempt_state'])
    with pytest.raises(service.JobConflict, match='job_handoff_stale'):
        handoff.read(w.users['reviewer'], j.pk, str(j.revision), value['sha256'])


@pytest.mark.parametrize('phase', ['running', 'expired'])
def test_protected_cancellation_dominates_finish_and_reconcile(candidate, phase):  # noqa: F811
    w = candidate
    sealed, _, _ = seal(w, approve(w, proposal(w)))
    identifier = queued(w, sealed)
    j, token = service.claim(identifier)
    service.cancel(w.users['reviewer'], identifier, {'action': 'cancel'})
    if phase == 'expired':
        NativeJob.objects.filter(pk=identifier).update(lease_until=timezone.now()-timedelta(seconds=1))
        service.reconcile()
    else:
        service.finish(identifier, token, 'succeeded', result={'forbidden': True})
    j.refresh_from_db()
    assert j.state == 'cancelled' and j.result is None and not j.result_sha256
    assert service.claim(identifier) is None
    assert handoff.read(w.users['reviewer'], j.pk, str(j.revision))['outcome_accesses']['total'] == 0
