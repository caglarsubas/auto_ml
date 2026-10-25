"""Admission/replay receipts must authorize after materializing private output.

Only expensive preparation is stubbed. Identity, scopes, transactions, job/event
writes, request hashes, replay selection and response serialization are real.
Existing integration/private tests retain full scientific preparation coverage.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import DatabaseError
from rest_framework.test import APIClient

from access_control import projects
from access_control.models import Project, ProjectDataset, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from execution_jobs import service, training_search, training_scoring, native_assessment
from execution_jobs.models import NativeJob, JobEvent
from tests.unit.test_governed_foundation import declaration

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
KINDS = [service.KIND, service.csv_scoring.KIND, training_search.KIND, training_scoring.KIND, native_assessment.KIND]
SCORING = [service.csv_scoring.KIND, training_scoring.KIND]


@pytest.fixture
def world(settings, django_user_model, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.DECLARAI_RUNTIME_PROFILE = 'development'
    settings.DECLARAI_JOBS_ENABLED = True
    ProjectPolicy.objects.create()
    actor = django_user_model.objects.create_user(username='private-receipt-actor')
    project = Project.objects.create(name='Receipt authority fixture')
    membership = ProjectMembership.objects.create(project=project, actor=actor, role='developer')
    primary = Declaration.objects.create(name='Receipt primary')
    source = Declaration.objects.create(name='Receipt source')
    for item in [primary, source]:
        projects.bind_dataset(item, project.pk)
    return SimpleNamespace(actor=actor, project=project, member=membership, primary=primary, source=source)


def admission(w, monkeypatch, kind, mode):
    role = 'reviewer' if kind == native_assessment.KIND else 'developer'
    ProjectMembership.objects.filter(pk=w.member.pk).update(role=role)
    source_scope = projects.dataset_authority(w.actor.pk, w.source.pk)
    bundle, protected = str(uuid.uuid4()), str(uuid.uuid4())
    body = {'request_id': str(uuid.uuid4()), 'kind': kind}
    if kind in [service.KIND, service.csv_scoring.KIND]:
        identity = dict(file_id=w.primary.pk, bundle_id=bundle, execution_id=str(uuid.uuid4()), assessment_id=str(uuid.uuid4()))
        monkeypatch.setattr(service, 'header', lambda *a: ({'algorithm': 'xgboost'}, identity))
        body.update(bundle_id=bundle, manifest_sha256='a' * 64)
        if kind == service.csv_scoring.KIND:
            monkeypatch.setattr(service.csv_scoring, 'input_bytes', lambda *a: (b'x\n1\n', {'sha256': 'b' * 64}, source_scope))
            body.update(input_file_id=w.source.pk, input_sha256='b' * 64)
    elif kind == training_search.KIND:
        plan = {'source': {'sha256': 'b' * 64}, 'profile': {'runtime': service.runtime(kind), 'limits': service.limits(kind)}}
        monkeypatch.setattr(training_search, 'prepare', lambda *a: (plan, {}))
        body.update(data_role='development_only', business_understanding=declaration(), features=['x'],
                    validation={'strategy': 'random', 'n_splits': 3}, input_sha256='b' * 64, training_sha256=service.digest(plan))
    elif kind == training_scoring.KIND:
        plan = {'source': {'sha256': 'b' * 64}, 'source_authority': source_scope}
        monkeypatch.setattr(training_scoring, 'prepare', lambda *a: (plan, b'{}', b'x\n1\n'))
        body.update(training_job_id=str(uuid.uuid4()), training_result_sha256='c' * 64,
                    input_file_id=w.source.pk, input_sha256='b' * 64, scoring_sha256=service.digest(plan))
    else:
        prepared = {'schema_version': 1, 'kind': kind, 'protected_input_id': protected,
                    'runtime': service.runtime(kind), 'limits': service.limits(kind)}
        sealed = SimpleNamespace(adoption=SimpleNamespace(training_job=SimpleNamespace(dataset_id=w.primary.pk)))
        monkeypatch.setattr(native_assessment, 'plan', lambda *a: (prepared, sealed, b'{}', projects.dataset_authority(w.actor.pk, w.primary.pk)))
        body.update(protected_input_id=protected, assessment_sha256=service.digest(prepared))
    w.body = body
    if mode == 'replay':
        created = service.submit(w.actor, w.primary.pk, body)
        result = {'private': 'retained-private-result'}
        NativeJob.objects.filter(pk=created['id']).update(state='succeeded', result=result, result_sha256=service.digest(result))
    return list(NativeJob.objects.values()), list(JobEvent.objects.values())


def invoke(w, entry):
    if entry == 'service':
        return service.submit(w.actor, w.primary.pk, w.body)
    c = APIClient()
    c.force_authenticate(w.actor)
    c.raise_request_exception = False
    return c.post(f'/api/jobs/datasets/{w.primary.pk}/', w.body, format='json')


def assert_preserved(before):
    assert list(NativeJob.objects.values()) == before[0]
    assert list(JobEvent.objects.values()) == before[1]


def revoke_after_serialization(w, monkeypatch, guard):
    original = service.serialize
    def changed(job, **kw):
        response = original(job, **kw)
        if guard == 'actor':
            type(w.actor).objects.filter(pk=w.actor.pk).update(is_active=False)
        else:
            item = w.source if guard == 'source' else w.primary
            ProjectDataset.objects.filter(dataset=item).update(revision=uuid.uuid4())
        return response
    monkeypatch.setattr(service, 'serialize', changed)


def denied(w, before, entry):
    if entry == 'service':
        with pytest.raises(projects.ProjectDenied):
            invoke(w, entry)
    else:
        response = invoke(w, entry)
        assert response.status_code == 403
        assert b'private-receipt-actor' not in response.content and b'retained-private-result' not in response.content
    assert_preserved(before)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('mode', ['new', 'replay'])
@pytest.mark.parametrize('entry', ['service', 'http'])
@pytest.mark.parametrize('guard', ['primary', 'actor'])
def test_all_native_admission_and_replay_receipts_recheck_final_authority(world, monkeypatch, kind, mode, entry, guard):
    before = admission(world, monkeypatch, kind, mode)
    revoke_after_serialization(world, monkeypatch, guard)
    denied(world, before, entry)


@pytest.mark.parametrize('kind', SCORING)
@pytest.mark.parametrize('mode', ['new', 'replay'])
@pytest.mark.parametrize('entry', ['service', 'http'])
def test_scoring_receipt_fence_includes_source_dataset(world, monkeypatch, kind, mode, entry):
    before = admission(world, monkeypatch, kind, mode)
    revoke_after_serialization(world, monkeypatch, 'source')
    denied(world, before, entry)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('mode', ['new', 'replay'])
@pytest.mark.parametrize('entry', ['service', 'http'])
def test_valid_receipts_keep_status_raw_evidence_and_single_submission(world, monkeypatch, kind, mode, entry):
    before = admission(world, monkeypatch, kind, mode)
    response = invoke(world, entry)
    body = response if entry == 'service' else response.json()
    if entry == 'http':
        assert response.status_code == (200 if mode == 'replay' else 202)
    assert body['replayed'] is (mode == 'replay')
    assert body['review_approved'] is body['production_use_approved'] is False
    assert NativeJob.objects.count() == JobEvent.objects.count() == 1
    if mode == 'replay':
        assert body['result'] == before[0][0]['result'] and body['result_sha256'] == before[0][0]['result_sha256']
        assert_preserved(before)
    else:
        assert body['state'] == 'queued' and body['events'][0]['event_type'] == 'submitted'
        assert body['result'] is None and body['attempts'] == 0


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('mode', ['new', 'replay'])
def test_final_authority_storage_failure_propagates_and_rolls_back(world, monkeypatch, kind, mode):
    before = admission(world, monkeypatch, kind, mode)
    original = service.serialize
    def prepared(job, **kw):
        response = original(job, **kw)
        def unavailable(*a, **k):
            raise DatabaseError('owned final authority failure')
        monkeypatch.setattr(projects, 'recheck', unavailable)
        return response
    monkeypatch.setattr(service, 'serialize', prepared)
    with pytest.raises(DatabaseError, match='owned final authority failure'):
        invoke(world, 'service')
    assert_preserved(before)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('mode', ['new', 'replay'])
def test_receipt_serialization_failure_never_partially_admits_or_replays(world, monkeypatch, kind, mode):
    before = admission(world, monkeypatch, kind, mode)
    with patch.object(service, 'serialize', side_effect=DatabaseError('owned receipt failure')):
        with pytest.raises(DatabaseError, match='owned receipt failure'):
            invoke(world, 'service')
    assert_preserved(before)
