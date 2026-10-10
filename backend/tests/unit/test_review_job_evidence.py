"""Review adoption of real native receipts, source authority and retained history."""

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from access_control import projects
from access_control.models import Project, ProjectDataset, ProjectMembership
from deployment import reviews
from deployment.deploy_utils import build_score_bundle
from deployment.models import PackageReview, PackageReviewEvent
from execution_jobs import service, csv_scoring
from execution_jobs.models import NativeJob
from declaration.models import Declaration
from tests.unit.test_package_reviews import packaged, world, create, append, action, post

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def job(world, settings, *, scoring=False, rows=24, execute=True):
    settings.DECLARAI_JOBS_ENABLED = True
    file_id, project, bundle, users, _ = world
    payload = {'request_id': str(uuid.uuid4()), 'kind': service.KIND,
               'bundle_id': bundle['bundle_id'], 'manifest_sha256': bundle['manifest_sha256']}
    if scoring:
        relative = 'data_files/review-input.csv'
        pd.DataFrame({'other': [0.5] * rows, 'x': [0.2] * rows}).to_csv(Path(settings.MEDIA_ROOT) / relative, index=False)
        source = Declaration.objects.create(name='input', file=relative, original_name='input.csv')
        projects.bind_dataset(source, project.pk)
        prepared = csv_scoring.prepare(users['developer'], source.pk)
        payload.update(kind=csv_scoring.KIND, input_file_id=source.pk, input_sha256=prepared['sha256'])
    receipt = service.submit(users['developer'], file_id, payload)
    if execute:
        service.execute(receipt['id'])
        receipt = service.read(users['reviewer'], receipt['id'])
        assert receipt['state'] == 'succeeded', receipt
    return receipt


def reference(receipt):
    return {'job_id': receipt['id'], 'result_sha256': receipt['result_sha256']}


def receipt_url(case, event):
    return f'/api/reviews/{case["id"]}/events/{event["id"]}/receipt/'


@pytest.mark.parametrize('scoring', [False, True])
def test_exact_receipt_attaches_downloads_and_preserves_provenance(world, settings, scoring):
    completed = job(world, settings, scoring=scoring, rows=650)
    case = create(world)[0].json()
    with patch('pickle.load', side_effect=AssertionError('Review must not load native state')):
        response = append(world, case, evidence=reference(completed))
        assert response.status_code == 200, response.content
        case = response.json()
        event = case['events'][-1]
        linked = event['evidence']
        assert linked == case['findings'][0]['evidence']
        assert linked['job_id'] == completed['id'] and linked['result_sha256'] == completed['result_sha256']
        assert linked['specification_sha256'] == reviews.digest(completed['specification'])
        assert linked['submitted_by']['id'] == world[3]['developer'].pk
        assert event['actor']['id'] == world[3]['reviewer'].pk
        assert not linked['independent_reproduction_verified']
        saved = PackageReviewEvent.objects.get(pk=event['id'])
        assert str(saved.evidence_job_id) == completed['id']
        for role in ('reviewer', 'developer', 'admin'):
            download = world[4][role].get(receipt_url(case, event))
            assert download.status_code == 200, download.content
            assert download['Cache-Control'] == 'no-store'
            downloaded = download.json()
            assert downloaded['evidence'] == linked
            assert reviews.digest(downloaded['job']['result']) == linked['result_sha256']
            assert not downloaded['review_approved'] and not downloaded['production_use_approved']
            if scoring:
                assert len(downloaded['job']['result']['scores']) == 650
                assert completed['result']['scores_truncated']
            else:
                assert downloaded['job']['result']['model_state_loaded'] is False
    assert world[4]['outsider'].get(receipt_url(case, event)).status_code == 403
    assert world[4]['developer'].post(receipt_url(case, event), '{}', content_type='application/json').status_code == 405
    with pytest.raises(ProtectedError):
        NativeJob.objects.get(pk=completed['id']).delete()


def test_responses_and_dispositions_cite_receipts_and_exact_retries(world, settings):
    completed = job(world, settings)
    case = append(world, create(world)[0].json()).json()
    url = f'/api/reviews/{case["id"]}/'
    payload = action(case, 'response', finding_id=case['findings'][0]['id'], evidence=reference(completed))
    response = post(world[4]['developer'], url, payload)
    assert response.status_code == 200, response.content
    case = response.json()
    again = post(world[4]['developer'], url, payload).json()
    assert again['replayed'] and again['events'] == case['events'] and again['revision'] == case['revision']
    changed = payload | {'evidence': reference(completed) | {'result_sha256': '0' * 64}}
    assert post(world[4]['developer'], url, changed).json()['error_code'] == 'review_request_reused'
    for kind in ['resolve', 'reopen']:
        response = append(world, case, kind, finding_id=case['findings'][0]['id'], evidence=reference(completed))
        assert response.status_code == 200, response.content
        case = response.json()
        assert case['events'][-1]['evidence']['job_id'] == completed['id']
    assert case['events'][1]['evidence'] is None  # Existing prose-only events remain unasserted.


@pytest.mark.parametrize('value', [None, [], {}, {'job_id': 'invalid', 'result_sha256': '0' * 64},
    {'job_id': str(uuid.uuid4()), 'result_sha256': True},
    {'job_id': str(uuid.uuid4()), 'result_sha256': 'A' * 64},
    {'job_id': str(uuid.uuid4()), 'result_sha256': '0' * 64, 'actor_id': 1}])
def test_malformed_or_spoofed_reference_never_appends(world, value):
    case = create(world)[0].json()
    assert append(world, case, evidence=value).status_code == 400
    assert PackageReviewEvent.objects.count() == 1


@pytest.mark.parametrize('state', ['queued', 'running', 'blocked', 'failed', 'cancelled'])
def test_only_successful_execution_results_can_be_cited(world, settings, state):
    pending = job(world, settings, execute=False)
    NativeJob.objects.filter(pk=pending['id']).update(state=state)
    case = create(world)[0].json()
    response = append(world, case, evidence=reference(pending) | {'result_sha256': '0' * 64})
    assert response.status_code == 409 and response.json()['error_code'] == 'review_evidence_success_required'
    assert PackageReviewEvent.objects.count() == 1


def test_wrong_result_missing_job_and_different_frozen_package_are_blocked(world, settings):
    completed = job(world, settings)
    case = create(world)[0].json()
    assert append(world, case, evidence=reference(completed) | {'result_sha256': '0' * 64}).json()['error_code'] == 'review_evidence_result_changed'
    assert append(world, case, evidence={'job_id': str(uuid.uuid4()), 'result_sha256': '0' * 64}).status_code == 404
    file_id, project, _, users, clients = world
    newer = build_score_bundle(file_id)
    new_world = file_id, project, newer, users, clients
    current = create(new_world)[0].json()
    response = append(world, current, evidence=reference(completed))
    assert response.status_code == 409 and response.json()['error_code'] == 'review_evidence_package_mismatch'
    assert len(clients['reviewer'].get(f'/api/reviews/{case["id"]}/').json()['events']) == 1


@pytest.mark.parametrize('change', ['result', 'reference', 'specification'])
def test_tampered_linked_evidence_is_withheld_without_rewriting_history(world, settings, change):
    completed = job(world, settings)
    case = append(world, create(world)[0].json(), evidence=reference(completed)).json()
    event = case['events'][-1]
    if change == 'result':
        NativeJob.objects.filter(pk=completed['id']).update(result={'tampered': True})
    elif change == 'reference':
        PackageReviewEvent.objects.filter(pk=event['id']).update(evidence=event['evidence'] | {'job_revision': 999})
    else:
        NativeJob.objects.filter(pk=completed['id']).update(specification=completed['specification'] | {'limits': {}})
    assert world[4]['reviewer'].get(f'/api/reviews/{case["id"]}/').status_code == 409
    assert world[4]['reviewer'].get(receipt_url(case, event)).status_code == 409
    assert PackageReviewEvent.objects.count() == 2
    assert PackageReview.objects.get(pk=case['id']).revision == 2


def test_input_reassignment_withholds_linked_discussion_receipt_and_retry(world, settings):
    completed = job(world, settings, scoring=True)
    case = append(world, create(world)[0].json(), evidence=reference(completed)).json()
    event = case['events'][-1]
    source_id = event['evidence']['source_dataset_id']
    other = Project.objects.create(name='Different project')
    ProjectMembership.objects.create(project=other, actor=world[3]['reviewer'], role='reviewer')
    # Unsupported privileged mutation is a deliberate threat fixture.
    ProjectDataset.objects.filter(dataset_id=source_id).update(project=other, revision=uuid.uuid4())
    assert world[4]['reviewer'].get(f'/api/jobs/{completed["id"]}/').status_code == 403
    assert world[4]['reviewer'].get(f'/api/reviews/{case["id"]}/').status_code == 403
    assert world[4]['reviewer'].get(receipt_url(case, event)).status_code == 403
    assert append(world, case, evidence=reference(completed)).status_code == 403
    assert PackageReviewEvent.objects.get(pk=event['id']).evidence == event['evidence']


def test_final_http_recheck_withholds_input_changed_after_receipt_read(world, settings):
    from access_control.project_http import ProjectResponseMiddleware
    completed = job(world, settings, scoring=True)
    case = append(world, create(world)[0].json(), evidence=reference(completed)).json()
    event = case['events'][-1]
    original = ProjectResponseMiddleware.checkpoint
    other = Project.objects.create(name='Reassigned after snapshot')
    def checkpoint(request):
        if request.path == receipt_url(case, event):
            ProjectDataset.objects.filter(dataset_id=event['evidence']['source_dataset_id']).update(project=other, revision=uuid.uuid4())
        return original(request)
    with patch.object(ProjectResponseMiddleware, 'checkpoint', side_effect=checkpoint):
        response = world[4]['reviewer'].get(receipt_url(case, event))
    assert response.status_code == 403 and 'job' not in response.json()
    assert PackageReviewEvent.objects.count() == 2


def test_reference_change_during_publication_rolls_back(world, settings):
    from deployment import review_evidence
    completed = job(world, settings)
    case = create(world)[0].json()
    original = review_evidence.capture
    calls = []
    def changed(*args):
        calls.append(1)
        job, snapshot = original(*args)
        if len(calls) == 2:
            snapshot = snapshot | {'job_revision': 999}
        return job, snapshot
    with patch.object(review_evidence, 'capture', side_effect=changed):
        response = append(world, case, evidence=reference(completed))
    assert response.status_code == 409
    assert PackageReviewEvent.objects.count() == 1
    assert PackageReview.objects.get(pk=case['id']).revision == 1


def test_historical_receipt_and_actor_attribution_remain_inspectable(world, settings):
    completed = job(world, settings)
    case = append(world, create(world)[0].json(), evidence=reference(completed)).json()
    event = case['events'][-1]
    build_score_bundle(world[0])
    world[3]['developer'].delete()
    current = world[4]['reviewer'].get(f'/api/reviews/{case["id"]}/').json()
    assert current['freshness'] == 'historical' and current['events'] == case['events']
    downloaded = world[4]['reviewer'].get(receipt_url(case, event)).json()
    assert downloaded['job']['submitted_by'] == completed['submitted_by']
    assert append(world, current, evidence=reference(completed)).json()['error_code'] == 'package_review_stale'


def test_reference_and_retained_job_must_be_paired_in_database(world, settings):
    completed = job(world, settings)
    case = append(world, create(world)[0].json(), evidence=reference(completed)).json()
    with transaction.atomic(), pytest.raises(IntegrityError):
        PackageReviewEvent.objects.filter(pk=case['events'][-1]['id']).update(evidence_job=None)
