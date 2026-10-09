"""Real HTTP roles, exact-package binding, retries, races and retained evidence."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
import numpy as np
import pandas as pd
from django.db import DatabaseError, connections
from django.db.models.deletion import ProtectedError
from django.test import Client
from rest_framework.test import APIRequestFactory, force_authenticate

from access_control import projects
from access_control.models import Project, ProjectPolicy, ProjectMembership
from declaration.models import Declaration
from deployment import reviews
from deployment.deploy_utils import build_score_bundle, bundle_dir
from deployment.models import PackageReview, PackageReviewEvent
from modeling.models import PipelineRun
from tests.unit.test_governed_foundation import declaration

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def packaged(_use_tmp_media, django_user_model, settings):
    from modeling.views import ModelingStartView
    from evaluation.views import EvaluationRunView
    actor = django_user_model.objects.create_user(username='native-builder')
    frame = pd.DataFrame({'x': np.linspace(-2, 2, 160), 'other': np.random.normal(size=160),
                          'outcome': ['bad', 'good'] * 80})
    relative = 'data_files/review.csv'
    frame.to_csv(Path(settings.MEDIA_ROOT) / relative, index=False)
    dataset = Declaration.objects.create(name='review', original_name='review.csv', file=relative)
    request = APIRequestFactory().post('/api/modeling/start/', {'file_id': dataset.pk,
        'processed_file': relative, 'algorithm': 'logistic_regression', 'business_understanding': declaration()}, format='json')
    force_authenticate(request, actor)
    response = ModelingStartView.as_view()(request)
    assert response.status_code == 200, response.data
    execution_id = response.data['execution_id']
    request = APIRequestFactory().post('/api/evaluation/run/', {'file_id': dataset.pk, 'execution_id': execution_id}, format='json')
    force_authenticate(request, actor)
    response = EvaluationRunView.as_view()(request)
    assert response.status_code == 200, response.data
    return dataset.pk, execution_id, response.data['evaluation']['holdout_access_id'], build_score_bundle(dataset.pk)


@pytest.fixture
def world(packaged, django_user_model):
    file_id, _, _, bundle = packaged
    ProjectPolicy.objects.create()
    project = Project.objects.create(name='Review fixture')
    projects.bind_dataset(Declaration.objects.get(pk=file_id), project.pk)
    users, clients = {}, {}
    for role in ['developer', 'reviewer', 'admin', 'outsider']:
        actor = django_user_model.objects.create_user(username=role, password='synthetic-review-fixture')
        if role != 'outsider':
            ProjectMembership.objects.create(actor=actor, project=project, role=role)
        client = Client()
        client.force_login(actor)
        users[role], clients[role] = actor, client
    return file_id, project, bundle, users, clients


def post(client, url, data):
    return client.post(url, json.dumps(data), content_type='application/json')


def create(world, role='reviewer', **overrides):
    file_id, _, bundle, _, clients = world
    payload = {'request_id': str(uuid.uuid4()), 'bundle_id': bundle['bundle_id'], 'manifest_sha256': bundle['manifest_sha256'], **overrides}
    return post(clients[role], f'/api/reviews/datasets/{file_id}/', payload), payload


def action(case, kind='finding', **overrides):
    return {'request_id': str(uuid.uuid4()), 'expected_revision': case['revision'],
            'event_type': kind, 'text': 'Synthetic review text',
            **({'severity': 'major'} if kind == 'finding' else {}), **overrides}


def append(world, case, kind='finding', role='reviewer', **overrides):
    return post(world[4][role], f'/api/reviews/{case["id"]}/', action(case, kind, **overrides))


def test_findings_response_disposition_reopen_and_receipt_history(world):
    file_id, project, bundle, users, clients = world
    original = (Path(bundle_dir(file_id, bundle['bundle_id'])) / 'manifest.json').read_bytes()
    response, payload = create(world)
    assert response.status_code == 200, response.content
    case = response.json()
    assert case['freshness'] == 'current' and case['revision'] == 1
    assert case['manifest_sha256'] == bundle['manifest_sha256']
    assert case['project_id'] == str(project.pk)
    assert not case['review_approved'] and not case['production_use_approved']
    retry = post(clients['reviewer'], f'/api/reviews/datasets/{file_id}/', payload)
    assert retry.json()['replayed'] and retry.json()['id'] == case['id']
    result = append(world, case, text='<script>untrusted finding</script>')
    assert result.status_code == 200, result.content
    case = result.json()
    finding = case['findings'][0]['id']
    payload = action(case, 'response', finding_id=finding, text='Developer evidence response')
    url = f'/api/reviews/{case["id"]}/'
    result = post(clients['developer'], url, payload)
    assert result.status_code == 200, result.content
    case = result.json()
    assert case['findings'][0]['responses'] == 1
    assert post(clients['developer'], url, payload).json()['replayed']
    case = append(world, case, 'resolve', finding_id=finding, text='Reviewer verified response').json()
    assert case['findings'][0]['state'] == 'resolved'
    assert append(world, case, 'response', role='developer', finding_id=finding).status_code == 409
    case = append(world, case, 'reopen', finding_id=finding, text='Additional evidence needed').json()
    assert case['findings'][0]['state'] == 'open'
    assert [e['event_type'] for e in case['events']] == ['opened', 'finding', 'response', 'resolve', 'reopen']
    assert [e['revision'] for e in case['events']] == list(range(1, 6))
    assert case['events'][2]['actor'] == {'id': users['developer'].pk, 'username': 'developer'}
    assert case['events'][2]['authority']['role'] == 'developer'
    assert (Path(bundle_dir(file_id, bundle['bundle_id'])) / 'manifest.json').read_bytes() == original
    assert clients['admin'].get(url).status_code == 200
    directory = clients['developer'].get(f'/api/reviews/datasets/{file_id}/').json()
    assert directory['reviews'][0]['id'] == case['id'] and directory['total'] == 1
    assert create(world)[0].status_code == 409
    assert clients['reviewer'].put(url, '{}', content_type='application/json').status_code == 405
    assert clients['reviewer'].delete(url).status_code == 405
    with pytest.raises(ProtectedError):
        Declaration.objects.get(pk=file_id).delete()
    assert clients['developer'].delete(f'/api/declaration/{file_id}/').json()['error_code'] == 'dataset_retained_for_review'


@pytest.mark.parametrize('role', ['developer', 'admin', 'outsider'])
def test_only_project_reviewer_can_open(world, role):
    assert create(world, role)[0].status_code == 403
    assert not PackageReview.objects.exists()


@pytest.mark.parametrize('role,kind', [('developer', 'finding'), ('developer', 'resolve'),
                                      ('reviewer', 'response'), ('admin', 'finding'), ('admin', 'response')])
def test_action_roles_enforced_on_server(world, role, kind):
    case = create(world)[0].json()
    result = append(world, case, kind, role=role, **({'finding_id': str(uuid.uuid4())} if kind != 'finding' else {}))
    assert result.status_code == 403
    assert PackageReviewEvent.objects.count() == 1


def test_scope_and_explicit_project_cannot_leak_discussions(world):
    file_id, _, _, users, clients = world
    case = create(world)[0].json()
    url = f'/api/reviews/{case["id"]}/'
    assert clients['outsider'].get(url).status_code == 403
    assert clients['outsider'].get(f'/api/reviews/datasets/{file_id}/').status_code == 403
    other = Project.objects.create(name='Another project')
    ProjectMembership.objects.create(actor=users['reviewer'], project=other, role='reviewer')
    assert clients['reviewer'].get(url + f'?project_id={other.pk}').status_code == 403
    assert clients['reviewer'].get(url + '?file_id=999999').status_code == 403
    assert clients['reviewer'].get('/api/reviews/' + str(uuid.uuid4()) + '/').status_code == 403


def test_optimistic_revision_and_exact_request_binding(world):
    case = create(world)[0].json()
    payload = action(case)
    url = f'/api/reviews/{case["id"]}/'
    assert post(world[4]['reviewer'], url, payload).status_code == 200
    assert append(world, case).json()['error_code'] == 'review_revision_changed'
    assert post(world[4]['reviewer'], url, {**payload, 'text': 'altered request'}).json()['error_code'] == 'review_request_reused'
    assert PackageReviewEvent.objects.count() == 2
    assert PackageReview.objects.get(pk=case['id']).revision == 2


@pytest.mark.parametrize('change', ['source', 'modeling', 'assessment', 'pipeline', 'replacement', 'tamper', 'missing'])
def test_changed_evidence_blocks_edits_but_keeps_history(world, settings, change):
    file_id, _, bundle, _, clients = world
    case = create(world)[0].json()
    root = Path(settings.MEDIA_ROOT)
    if change == 'source':
        source = Declaration.objects.get(pk=file_id).get_file_path()
        with open(source, 'a') as stream:
            stream.write('999,999,bad\n')
    elif change in {'modeling', 'assessment'}:
        path = root / ('modeling' if change == 'modeling' else 'evaluation') / f'{file_id}_{"status" if change == "modeling" else "evaluation"}.json'
        value = json.loads(path.read_text())
        value['changed'] = 'new development intent'
        path.write_text(json.dumps(value))
    elif change == 'pipeline':
        PipelineRun.objects.create(file_id=file_id, name='new experiment', state={'business_understanding': {'objective': 'changed'}})
    elif change == 'replacement':
        new = build_score_bundle(file_id)
        assert new['bundle_id'] != bundle['bundle_id']
    else:
        path = Path(bundle_dir(file_id, bundle['bundle_id'])) / 'model_card.json'
        if change == 'tamper':
            path.write_text('{}')
        else:
            path.unlink()
    result = append(world, case)
    assert result.status_code == 409 and result.json()['error_code'] == 'package_review_stale'
    current = clients['reviewer'].get(f'/api/reviews/{case["id"]}/').json()
    assert current['freshness'] == ('integrity_unavailable' if change in {'tamper', 'missing'} else 'historical')
    assert current['events'] == case['events'] and current['revision'] == 1
    assert not current['review_approved']


def test_changed_manifest_and_unverified_legacy_are_rejected(world):
    response, _ = create(world, manifest_sha256='0' * 64)
    assert response.status_code == 409 and not PackageReview.objects.exists()
    with patch('deployment.reviews.verify_bundle', return_value=({'file_id': world[0]}, '0' * 64)):
        assert create(world)[0].json()['error_code'] == 'review_requires_verified_execution_and_assessment'


def test_revoked_authority_and_storage_failures_do_not_publish(world):
    case = create(world)[0].json()
    with patch('deployment.reviews.append_record', side_effect=DatabaseError('synthetic')):
        assert append(world, case).status_code == 503
    assert PackageReviewEvent.objects.count() == 1
    member = ProjectMembership.objects.get(actor=world[3]['reviewer'])
    member.active = False
    member.save()
    assert append(world, case).status_code == 403
    assert world[4]['reviewer'].get(f'/api/reviews/{case["id"]}/').status_code == 403


def test_mid_publication_change_rolls_back_event_and_revision(world):
    case = create(world)[0].json()
    original = reviews.require_current
    calls = []
    def check(review):
        calls.append(review.pk)
        if len(calls) == 2:
            raise reviews.ReviewConflict('package_review_stale')
        original(review)
    with patch('deployment.reviews.require_current', side_effect=check):
        assert append(world, case).status_code == 409
    assert len(calls) == 2 and PackageReviewEvent.objects.count() == 1
    assert PackageReview.objects.get(pk=case['id']).revision == 1


def test_actor_snapshot_survives_deletion_and_role_change_cannot_self_resolve(world):
    case = append(world, create(world)[0].json()).json()
    finding_id = case['findings'][0]['id']
    case = append(world, case, 'response', role='developer', finding_id=finding_id).json()
    member = ProjectMembership.objects.get(actor=world[3]['developer'])
    member.role = 'reviewer'
    member.save()
    response = append(world, case, 'resolve', role='developer', finding_id=finding_id)
    assert response.status_code == 403 and response.json()['error_code'] == 'reviewer_cannot_resolve_own_response'
    actor_id = world[3]['developer'].pk
    world[3]['developer'].delete()
    event = PackageReviewEvent.objects.get(event_type='response')
    assert event.actor is None and event.actor_snapshot == {'id': actor_id, 'username': 'developer'}


def test_concurrent_same_revision_serializes_without_lost_updates(world):
    case = create(world)[0].json()
    actor_id = world[3]['reviewer'].pk
    def write(index):
        from django.contrib.auth import get_user_model
        try:
            actor = get_user_model().objects.get(pk=actor_id)
            try:
                return reviews.append(actor, case['id'], action(case, text=f'Concurrent {index}'))['revision']
            except reviews.ReviewConflict as exc:
                return exc.code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, range(2)))
    assert sorted(results, key=str) == [2, 'review_revision_changed']
    assert PackageReviewEvent.objects.count() == 2


@pytest.mark.parametrize('overrides', [{'text': ''}, {'text': 'x' * 10001}, {'expected_revision': True},
                                       {'severity': 'blanket-statistical-gate'}, {'event_type': 'approve'},
                                       {'actor_id': 1}, {'request_id': 'invalid'}])
def test_malformed_or_spoofed_actions_never_append(world, overrides):
    case = create(world)[0].json()
    assert append(world, case, **overrides).status_code == 400
    assert PackageReviewEvent.objects.count() == 1


def test_legacy_development_has_no_attributable_review_authority(world):
    ProjectPolicy.objects.all().delete()
    assert create(world)[0].status_code == 403


def test_review_writes_require_real_csrf(world):
    client = Client(enforce_csrf_checks=True)
    client.force_login(world[3]['reviewer'])
    _, payload = create(world, role='admin')
    assert post(client, f'/api/reviews/datasets/{world[0]}/', payload).status_code == 403
    assert not PackageReview.objects.exists()
