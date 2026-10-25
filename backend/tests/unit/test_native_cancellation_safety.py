"""Cancellation must retain evidence and authorize the final response."""
import copy
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection, models
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from access_control import projects
from access_control.models import Project, ProjectDataset, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
BAD_AUTHORITY = [None, [], 'private-authority', {}, {'actor_id': None}, {'actor_id': True},
                 {'actor_id': 1.0}, {'actor_id': '1'}, {'actor_id': []}, {'actor_id': {}},
                 {'actor_id': 0}, {'actor_id': 2}]
PAYLOADS = ['spec_null', 'actor_null', 'both_null', 'spec_list', 'actor_list', 'ordinary']


@pytest.fixture
def world(settings, django_user_model, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.DECLARAI_RUNTIME_PROFILE = 'development'
    settings.DECLARAI_JOBS_ENABLED = True
    ProjectPolicy.objects.create()
    project = Project.objects.create(name='Cancellation safety fixture')
    # Fixed identity makes True/1.0 coercion regressions deterministic on both DBs.
    actor = django_user_model.objects.create_user(pk=1, username='cancellation-owner')
    ProjectMembership.objects.create(project=project, actor=actor, role='reviewer')
    dataset = Declaration.objects.create(name='Cancellation primary')
    source = Declaration.objects.create(name='Cancellation source')
    for item in [dataset, source]:
        projects.bind_dataset(item, project.pk)
    result = {'private': 'private-payload', 'scores': [1, 2]}
    job = NativeJob.objects.create(
        id=uuid.uuid4(), project=project, dataset=dataset, source_dataset=source, actor=actor,
        authority=projects.dataset_authority(actor.pk, dataset.pk), actor_snapshot={'private': 'saved actor'},
        specification={'kind': service.KIND}, request_sha256='a' * 64, revision=5,
        expires_at=timezone.now() + timedelta(hours=1), result=result, result_sha256=service.digest(result))
    return SimpleNamespace(job=job, actor=actor, project=project, source=source)


def row(w):
    return NativeJob.objects.values().get(pk=w.job.pk)


def prepare(w, state='queued', payload='ordinary'):
    spec = None if payload in {'spec_null', 'both_null'} else [] if payload == 'spec_list' else {'kind': service.KIND}
    actor = None if payload in {'actor_null', 'both_null'} else [] if payload == 'actor_list' else {'private': 'saved actor'}
    running = state in {'running', 'cancel_requested'}
    NativeJob.objects.filter(pk=w.job.pk).update(
        state=state, attempts=1 if running else 0,
        specification=models.Value(spec, output_field=models.JSONField()),
        actor_snapshot=models.Value(actor, output_field=models.JSONField()),
        lease_token=uuid.uuid4() if running else None,
        lease_until=timezone.now() + timedelta(seconds=180) if running else None,
        finished_at=timezone.now() if state in service.TERMINAL else None)
    return row(w)


def invoke(w, entry):
    if entry == 'service':
        return service.cancel(w.actor, w.job.pk, {'action': 'cancel'})
    c = APIClient()
    c.force_authenticate(w.actor)
    c.raise_request_exception = False
    return c.post(f'/api/jobs/{w.job.pk}/', {'action': 'cancel'}, format='json')


@pytest.mark.parametrize('authority', BAD_AUTHORITY, ids=[f'authority-{i}' for i in range(len(BAD_AUTHORITY))])
@pytest.mark.parametrize('entry', ['service', 'http'])
def test_malformed_or_coercible_submitter_is_denied_without_mutation(world, authority, entry):
    prepare(world)
    NativeJob.objects.filter(pk=world.job.pk).update(authority=models.Value(copy.deepcopy(authority), output_field=models.JSONField()))
    before = row(world)
    if entry == 'service':
        with pytest.raises(projects.ProjectDenied) as caught:
            invoke(world, entry)
        assert caught.value.code == 'job_cancel_submitter_required'
    else:
        response = invoke(world, entry)
        assert response.status_code == 403 and response.json() == {'error_code': 'job_cancel_submitter_required'}
        assert b'private-payload' not in response.content
    assert row(world) == before and not JobEvent.objects.filter(job=world.job).exists()


@pytest.mark.parametrize('payload', PAYLOADS)
@pytest.mark.parametrize('state', ['queued', 'running'])
@pytest.mark.parametrize('entry', ['service', 'http'])
def test_cancellation_writes_only_transition_fields_and_keeps_opaque_payloads(world, payload, state, entry):
    before = prepare(world, state, payload)
    with CaptureQueriesContext(connection) as queries:
        response = invoke(world, entry)
    body = response if entry == 'service' else response.json()
    if entry == 'http':
        assert response.status_code == 200
    after = row(world)
    expected = 'cancel_requested' if state == 'running' else 'cancelled'
    assert after['state'] == body['state'] == expected and after['reason_code'] == 'actor_cancelled'
    assert after['revision'] == before['revision'] + 1
    assert {k for k in before if after[k] != before[k]} <= {'state', 'reason_code', 'finished_at', 'revision'}
    assert after['lease_token'] == before['lease_token'] and after['lease_until'] == before['lease_until']
    assert body['specification'] == before['specification'] and body['submitted_by'] == before['actor_snapshot']
    assert body['result'] == before['result'] and body['result_sha256'] == before['result_sha256']
    updates = [q['sql'] for q in queries if q['sql'].lstrip().startswith('UPDATE') and '"execution_jobs_nativejob"' in q['sql']]
    assert len(updates) == 1 and all('"'+field+'"' not in updates[0] for field in
        ['specification', 'authority', 'actor_snapshot', 'result', 'result_sha256', 'request_sha256', 'attempts'])
    event = JobEvent.objects.get(job=world.job)
    assert event.event_type == expected and event.actor_snapshot['id'] == world.actor.pk
    invoke(world, entry)
    assert row(world) == after and JobEvent.objects.filter(job=world.job).count() == 1


@pytest.mark.parametrize('guard', ['primary', 'source', 'actor'])
@pytest.mark.parametrize('state', ['queued', 'running', 'succeeded'])
def test_authority_changed_during_serialization_denies_response_and_rolls_back(world, monkeypatch, guard, state):
    before = prepare(world, state)
    original = service.serialize
    def revoked(job, **kwargs):
        value = original(job, **kwargs)
        if guard == 'actor':
            type(world.actor).objects.filter(pk=world.actor.pk).update(is_active=False)
        else:
            file_id = world.job.dataset_id if guard == 'primary' else world.source.pk
            ProjectDataset.objects.filter(dataset_id=file_id).update(revision=uuid.uuid4())
        return value
    monkeypatch.setattr(service, 'serialize', revoked)
    entry = 'service' if state == 'running' else 'http'
    if entry == 'service':
        with pytest.raises(projects.ProjectDenied):
            invoke(world, entry)
    else:
        response = invoke(world, entry)
        assert response.status_code == 403 and b'private-payload' not in response.content
    assert row(world) == before and not JobEvent.objects.filter(job=world.job).exists()


@pytest.mark.parametrize('state', ['succeeded', 'blocked', 'failed', 'cancelled', 'cancel_requested'])
@pytest.mark.parametrize('entry', ['service', 'http'])
def test_repeated_or_terminal_cancellation_keeps_raw_metadata_and_history(world, state, entry):
    before = prepare(world, state, 'both_null')
    response = invoke(world, entry)
    body = response if entry == 'service' else response.json()
    if entry == 'http':
        assert response.status_code == 200
    assert body['state'] == state and body['specification'] is body['submitted_by'] is None
    assert row(world) == before and not JobEvent.objects.filter(job=world.job).exists()


@pytest.mark.parametrize('state', ['queued', 'running'])
def test_receipt_failure_rolls_back_entire_cancellation(world, state):
    before = prepare(world, state, 'both_null')
    with patch.object(JobEvent.objects, 'create', side_effect=DatabaseError('owned receipt failure')):
        with pytest.raises(DatabaseError, match='owned receipt failure'):
            invoke(world, 'service')
    assert row(world) == before and not JobEvent.objects.filter(job=world.job).exists()


@pytest.mark.parametrize('entry', ['service', 'http'])
def test_live_authority_storage_failure_is_not_reported_as_invalid_submitter(world, monkeypatch, entry):
    before = prepare(world)
    original = projects.recheck
    def unavailable(*a, **kw):
        if 'allow_deleted' in kw:
            return original(*a, **kw)
        raise DatabaseError('owned authority storage failure')
    monkeypatch.setattr(projects, 'recheck', unavailable)
    if entry == 'service':
        with pytest.raises(DatabaseError, match='owned authority storage failure'):
            invoke(world, entry)
    else:
        response = invoke(world, entry)
        assert response.status_code == 503 and response.json() == {'error_code': 'job_storage_unavailable'}
    assert row(world) == before and not JobEvent.objects.filter(job=world.job).exists()


@pytest.mark.parametrize('guard', ['project', 'source', 'digest'])
def test_existing_project_source_and_result_guards_still_prevent_cancellation(world, guard):
    prepare(world)
    if guard == 'project':
        other = Project.objects.create(name='Other cancellation project')
        NativeJob.objects.filter(pk=world.job.pk).update(project=other)
    elif guard == 'source':
        other = Project.objects.create(name='Foreign cancellation source')
        ProjectDataset.objects.filter(dataset=world.source).update(project=other)
    else:
        NativeJob.objects.filter(pk=world.job.pk).update(result_sha256='0' * 64)
    before = row(world)
    response = invoke(world, 'http')
    assert response.status_code == (409 if guard == 'digest' else 403)
    assert b'private-payload' not in response.content
    assert row(world) == before and not JobEvent.objects.filter(job=world.job).exists()
