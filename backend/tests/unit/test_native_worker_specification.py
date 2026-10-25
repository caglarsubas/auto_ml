"""Malformed saved worker metadata is denied without losing durable evidence."""
import copy
import time
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import DatabaseError, models
from django.utils import timezone

from access_control import projects
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob
from tests.unit.test_native_checkpoint_payloads import worker, row, checkpoint_reads, assert_projection  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
INVALID = [None, [], ['private'], 'private', 0, False, {}, {'kind': None},
           {'kind': []}, {'kind': {}}, {'kind': 0}, {'kind': False}]
FAULTS = ['missing_id', 'null_id', 'list_id', 'invalid_id',
          'missing_digest', 'null_digest', 'list_digest', 'invalid_digest']
KINDS = [service.training_scoring.KIND, service.native_assessment.KIND]


def specification(w, kind):
    spec = {'kind': kind, 'runtime': service.runtime(kind), 'limits': service.limits(kind)}
    if kind == service.training_scoring.KIND:
        result = {'candidate': 'frozen reference'}
        trained = NativeJob.objects.create(
            id=uuid.uuid4(), project=w.project, dataset=w.job.dataset, actor=w.actor,
            actor_snapshot={}, authority=w.job.authority, specification={'kind': service.training_search.KIND},
            request_sha256='c' * 64, state='succeeded', result=result, result_sha256=service.digest(result),
            expires_at=timezone.now() + timedelta(hours=1))
        spec.update(training_job_id=str(trained.pk), training_result_sha256=trained.result_sha256)
        w.trained = trained
    elif kind == service.native_assessment.KIND:
        spec.update(protected_input_id=str(uuid.uuid4()), assessment_sha256='d' * 64)
    return spec


def prepare(w, spec, entry):
    NativeJob.objects.filter(pk=w.job.pk).update(
        state='queued' if entry == 'claim' else 'running', attempts=0 if entry == 'claim' else 1,
        specification=models.Value(copy.deepcopy(spec), output_field=models.JSONField()))
    return row(w.job)


def invoke(w, entry):
    if entry == 'claim':
        return service.claim(w.job.pk)
    if entry == 'checkpoint':
        return service.checkpoint(w.job.pk, w.job.lease_token, time.monotonic() + 120)
    return service.finish(w.job.pk, w.job.lease_token, 'succeeded', result={'candidate': 'new result'})


def assert_denial(w, before, entry, code):
    if entry == 'checkpoint':
        assert row(w.job) == before and not JobEvent.objects.filter(job=w.job).exists()
        return
    after = row(w.job)
    assert after['state'] == 'blocked' and after['reason_code'] == code
    assert after['revision'] == before['revision'] + 1 and after['attempts'] == before['attempts']
    assert after['lease_token'] is after['lease_until'] is None
    assert {k for k in before if after[k] != before[k]} <= {
        'state', 'reason_code', 'finished_at', 'revision', 'lease_token', 'lease_until'}
    event = JobEvent.objects.get(job=w.job)
    assert event.event_type == 'blocked' and event.detail == {'reason_code': code}
    assert service.claim(w.job.pk) is None and row(w.job) == after
    assert JobEvent.objects.filter(job=w.job).count() == 1


def deny(w, before, entry, code, monkeypatch, *, projection=True):
    if entry == 'checkpoint':
        if projection:
            with checkpoint_reads(monkeypatch) as (materialized, queries):
                with pytest.raises(service.JobConflict) as caught:
                    invoke(w, entry)
            assert_projection(materialized, queries, refreshed=False)
        else:
            with pytest.raises(service.JobConflict) as caught:
                invoke(w, entry)
        assert caught.value.code == code
    else:
        assert invoke(w, entry) is None
    assert_denial(w, before, entry, code)


@pytest.mark.parametrize('spec', INVALID, ids=[f'shape-{n}' for n in range(len(INVALID))])
@pytest.mark.parametrize('entry', ['checkpoint', 'finish'])
def test_malformed_envelope_cannot_checkpoint_or_publish(worker, monkeypatch, spec, entry):  # noqa: F811
    before = prepare(worker, spec, entry)
    monkeypatch.setattr(projects, 'recheck', lambda *a: pytest.fail('malformed envelope reached live scope'))
    monkeypatch.setattr(service, 'lock_authority', lambda *a: pytest.fail('malformed envelope reached actor locking'))
    deny(worker, before, entry, 'job_specification_invalid', monkeypatch)


@pytest.mark.parametrize('fault', FAULTS)
@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('entry', ['claim', 'checkpoint', 'finish'])
def test_malformed_reference_blocks_before_orm_conversion_or_protected_evidence(worker, monkeypatch, fault, kind, entry):  # noqa: F811
    spec = specification(worker, kind)
    key = ('training_job_id' if kind == service.training_scoring.KIND else 'protected_input_id') if fault.endswith('id') else (
        'training_result_sha256' if kind == service.training_scoring.KIND else 'assessment_sha256')
    if fault.startswith('missing'):
        del spec[key]
    else:
        spec[key] = None if fault.startswith('null') else [] if fault.startswith('list') else 'invalid'
    before = prepare(worker, spec, entry)
    monkeypatch.setattr(service.native_assessment, 'recheck', lambda *a: pytest.fail('bad reference reached protected evidence'))
    deny(worker, before, entry, 'job_specification_invalid', monkeypatch)


@pytest.mark.parametrize('saved_spec', [None, [], {'kind': []}])
@pytest.mark.parametrize('entry', ['claim', 'checkpoint', 'finish'])
def test_malformed_referenced_training_metadata_is_an_integrity_conflict(worker, monkeypatch, saved_spec, entry):  # noqa: F811
    spec = specification(worker, service.training_scoring.KIND)
    NativeJob.objects.filter(pk=worker.trained.pk).update(specification=models.Value(saved_spec, output_field=models.JSONField()))
    reference_before = row(worker.trained)
    before = prepare(worker, spec, entry)
    deny(worker, before, entry, 'job_training_result_changed', monkeypatch, projection=False)
    assert row(worker.trained) == reference_before


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('entry', ['claim', 'checkpoint', 'finish'])
def test_valid_reference_syntax_preserves_existing_execution_and_authority(worker, monkeypatch, kind, entry):  # noqa: F811
    spec = specification(worker, kind)
    checked = []
    if kind == service.native_assessment.KIND:
        # Existing protected-assessment integration tests exercise the actual plan;
        # this control proves its hook receives the unchanged valid reference.
        monkeypatch.setattr(service.native_assessment, 'recheck', lambda job: checked.append(job.specification))
    before = prepare(worker, spec, entry)
    with patch.object(projects, 'recheck', wraps=projects.recheck) as live:
        selected = invoke(worker, entry)
    assert live.call_args_list and live.call_args_list[-1].args == (before['authority'],)
    after = row(worker.job)
    if kind == service.native_assessment.KIND:
        assert checked == [spec]
    if entry == 'claim':
        assert selected[0].pk == worker.job.pk and after['state'] == 'running'
        assert after['attempts'] == 1 and after['result'] == before['result']
    elif entry == 'checkpoint':
        assert selected is None and after == before
    else:
        assert after['state'] == 'succeeded' and after['result'] == {'candidate': 'new result'}
        assert after['result_sha256'] == service.digest(after['result'])


@pytest.mark.parametrize('kind', ['', 'UNKNOWN'])
@pytest.mark.parametrize('entry', ['checkpoint', 'finish'])
def test_unknown_kind_retains_live_authority_then_blocks_with_runtime_reason(worker, monkeypatch, kind, entry):  # noqa: F811
    before = prepare(worker, {'kind': kind}, entry)
    with patch.object(projects, 'recheck', wraps=projects.recheck) as live:
        deny(worker, before, entry, 'job_runtime_changed', monkeypatch)
    assert live.call_args_list[0].args == (before['authority'],)


@pytest.mark.parametrize('fault', ['envelope', 'reference'])
def test_invalid_publication_receipt_failure_rolls_back_without_repair(worker, fault):  # noqa: F811
    spec = None if fault == 'envelope' else {'kind': service.training_scoring.KIND, 'training_job_id': []}
    before = prepare(worker, spec, 'finish')
    with patch.object(JobEvent.objects, 'create', side_effect=DatabaseError('owned receipt failure')):
        with pytest.raises(DatabaseError, match='owned receipt failure'):
            invoke(worker, 'finish')
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize('entry', ['claim', 'checkpoint', 'finish'])
def test_real_authority_storage_errors_are_not_reclassified(worker, monkeypatch, entry):  # noqa: F811
    spec = specification(worker, service.training_scoring.KIND)
    before = prepare(worker, spec, entry)
    def unavailable(*a):
        raise DatabaseError('owned live authority failure')
    monkeypatch.setattr(projects, 'recheck', unavailable)
    with pytest.raises(DatabaseError, match='owned live authority failure'):
        invoke(worker, entry)
    assert row(worker.job) == before and not JobEvent.objects.filter(job=worker.job).exists()
