"""A current snapshot for another resource cannot authorize native work."""
import copy
import time
from unittest.mock import patch

import pytest
from django.db import DatabaseError, models

from access_control import projects
from access_control.models import Project, ProjectMembership
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob
from tests.unit.test_native_checkpoint_payloads import worker, row, checkpoint_reads, assert_projection  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
FAULTS = ['primary_dataset', 'primary_project', 'primary_membership', 'primary_write',
          'source_dataset', 'source_project', 'source_actor', 'source_missing',
          'primary_null', 'primary_list', 'source_null', 'source_list', 'primary_bool_actor']


@pytest.fixture
def bound(worker, django_user_model):  # noqa: F811
    w = worker
    ProjectMembership.objects.filter(actor=w.actor).update(role='developer')
    w.other = Declaration.objects.create(name='Other dataset')
    projects.bind_dataset(w.other, w.project.pk)
    w.foreign_project = Project.objects.create(name='Other project')
    w.foreign = Declaration.objects.create(name='Foreign dataset')
    projects.bind_dataset(w.foreign, w.foreign_project.pk)
    ProjectMembership.objects.create(actor=w.actor, project=w.foreign_project, role='developer')
    w.other_actor = django_user_model.objects.create_user(username='other-valid-scope-actor')
    ProjectMembership.objects.create(actor=w.other_actor, project=w.project, role='developer')
    NativeJob.objects.filter(pk=w.job.pk).update(authority=projects.dataset_authority(w.actor.pk, w.job.dataset_id))
    w.job.refresh_from_db()
    return w


def prepare(w, fault=None, entry='checkpoint', with_source=False):
    authority = copy.deepcopy(w.job.authority)
    spec = copy.deepcopy(w.job.specification)
    has_source = with_source or bool(fault and fault.startswith('source_'))
    if has_source:
        spec['source_authority'] = projects.dataset_authority(w.actor.pk, w.source.pk)
    if fault == 'primary_dataset':
        authority = projects.dataset_authority(w.actor.pk, w.other.pk)
    elif fault == 'primary_project':
        authority = projects.dataset_authority(w.actor.pk, w.foreign.pk)
    elif fault == 'primary_membership':
        authority = projects.membership(w.actor.pk, w.project.pk)
    elif fault == 'primary_write':
        authority = projects.dataset_authority(w.actor.pk, w.job.dataset_id, 'write')
    elif fault == 'source_dataset':
        spec['source_authority'] = projects.dataset_authority(w.actor.pk, w.other.pk)
    elif fault == 'source_project':
        spec['source_authority'] = projects.dataset_authority(w.actor.pk, w.foreign.pk)
    elif fault == 'source_actor':
        spec['source_authority'] = projects.dataset_authority(w.other_actor.pk, w.source.pk)
    elif fault == 'source_missing':
        del spec['source_authority']
    elif fault == 'primary_null':
        authority = None
    elif fault == 'primary_list':
        authority = []
    elif fault == 'source_null':
        spec['source_authority'] = None
    elif fault == 'source_list':
        spec['source_authority'] = []
    elif fault == 'primary_bool_actor':
        authority['actor_id'] = True
    # These borrowed scopes are genuinely current and accepted by the generic
    # project checker; only their relationship to this job is wrong.
    if fault in FAULTS[:7]:
        projects.recheck(spec['source_authority'] if fault.startswith('source_') else authority)
    NativeJob.objects.filter(pk=w.job.pk).update(
        state='queued' if entry == 'claim' else 'running', attempts=0 if entry == 'claim' else 1,
        authority=models.Value(authority, output_field=models.JSONField()), specification=spec,
        source_dataset_id=w.source.pk if has_source else None)
    return row(w.job)


def invoke(w, entry):
    if entry == 'claim':
        return service.claim(w.job.pk)
    if entry == 'checkpoint':
        return service.checkpoint(w.job.pk, w.job.lease_token, time.monotonic() + 120)
    return service.finish(w.job.pk, w.job.lease_token, 'succeeded', result={'candidate': 'must not publish'})


@pytest.mark.parametrize('fault', FAULTS)
@pytest.mark.parametrize('entry', ['claim', 'checkpoint', 'finish'])
def test_invalid_binding_cannot_claim_checkpoint_or_publish(bound, monkeypatch, fault, entry):
    w = bound
    before = prepare(w, fault, entry)
    if entry == 'checkpoint':
        with checkpoint_reads(monkeypatch) as (materialized, queries):
            with pytest.raises(projects.ProjectDenied) as error:
                invoke(w, entry)
        assert error.value.code == 'job_authority_binding_changed'
        assert_projection(materialized, queries, refreshed=False)
        assert row(w.job) == before and not JobEvent.objects.filter(job=w.job).exists()
    else:
        assert invoke(w, entry) is None
        after = row(w.job)
        assert after['state'] == 'blocked' and after['reason_code'] == 'job_authority_changed'
        assert after['result'] == before['result'] and after['result_sha256'] == before['result_sha256']
        assert after['authority'] == before['authority'] and after['specification'] == before['specification']
        assert after['attempts'] == before['attempts'] and after['revision'] == before['revision'] + 1
        assert after['lease_token'] is after['lease_until'] is None
        event = JobEvent.objects.get(job=w.job)
        assert event.event_type == 'blocked' and event.detail == {'reason_code': 'job_authority_changed'}
        closed = row(w.job)
        assert service.claim(w.job.pk) is None and row(w.job) == closed
        assert JobEvent.objects.filter(job=w.job).count() == 1


@pytest.mark.parametrize('kind', [service.KIND, service.csv_scoring.KIND, service.training_search.KIND,
                                  service.training_scoring.KIND, service.native_assessment.KIND])
def test_binding_denial_precedes_kind_specific_evidence_work(bound, monkeypatch, kind):
    w = bound
    prepare(w, 'primary_dataset')
    spec = row(w.job)['specification']
    spec['kind'] = kind
    NativeJob.objects.filter(pk=w.job.pk).update(specification=spec)
    monkeypatch.setattr(service.native_assessment, 'recheck', lambda *a: pytest.fail('protected evidence reached'))
    monkeypatch.setattr(projects, 'recheck', lambda *a: pytest.fail('borrowed scope reached live authority check'))
    with pytest.raises(projects.ProjectDenied) as error:
        service.recheck_execution(NativeJob.objects.get(pk=w.job.pk))
    assert error.value.code == 'job_authority_binding_changed'


@pytest.mark.parametrize('has_source', [False, True])
@pytest.mark.parametrize('entry', ['claim', 'checkpoint', 'finish'])
def test_real_matching_scopes_keep_valid_execution_behavior(bound, has_source, entry):
    w = bound
    before = prepare(w, entry=entry, with_source=has_source)
    result = invoke(w, entry)
    after = row(w.job)
    if entry == 'claim':
        assert result[0].pk == w.job.pk and result[1] == after['lease_token']
        assert after['state'] == 'running' and after['attempts'] == 1
        assert after['authority'] == before['authority'] and after['result'] == before['result']
    elif entry == 'checkpoint':
        assert result is None and after == before and not JobEvent.objects.filter(job=w.job).exists()
    else:
        assert after['state'] == 'succeeded' and after['result'] == {'candidate': 'must not publish'}
        assert after['result_sha256'] == service.digest(after['result'])


@pytest.mark.parametrize('entry', ['claim', 'finish'])
def test_invalid_binding_receipt_failure_rolls_back_without_repair(bound, entry):
    before = prepare(bound, 'primary_null', entry)
    with patch.object(JobEvent.objects, 'create', side_effect=DatabaseError('owned receipt failure')):
        with pytest.raises(DatabaseError, match='owned receipt failure'):
            invoke(bound, entry)
    assert row(bound.job) == before and not JobEvent.objects.filter(job=bound.job).exists()


@pytest.mark.parametrize('entry', ['claim', 'checkpoint', 'finish'])
def test_real_authority_storage_errors_are_not_reclassified_as_binding_denials(bound, monkeypatch, entry):
    before = prepare(bound, entry=entry)
    def unavailable(*a):
        raise DatabaseError('owned live authority failure')
    monkeypatch.setattr(projects, 'recheck', unavailable)
    with pytest.raises(DatabaseError, match='owned live authority failure'):
        invoke(bound, entry)
    assert row(bound.job) == before and not JobEvent.objects.filter(job=bound.job).exists()
