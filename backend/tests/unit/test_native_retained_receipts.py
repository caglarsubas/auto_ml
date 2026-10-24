"""Authorized inspection preserves irregular saved receipts without inventing scores."""
import copy

import pytest
from django.db import models
from rest_framework.test import APIClient

from access_control.models import ProjectMembership
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob
from tests.unit.test_native_claim_attempt_budget import worker, row  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
BAD_SPECS = [None, [], 'private-spec', 0, False, {}, {'kind': []}, {'kind': {}}, {'kind': None}]
BAD_RESULTS = [['private-result'], 'private-result', True, {'scores': None}, {'scores': 3},
               {'scores': 'x' * 600}, {'scores': {str(i): i for i in range(501)}}]


def saved(w, spec, result):
    NativeJob.objects.filter(pk=w.job.pk).update(
        specification=models.Value(copy.deepcopy(spec), output_field=models.JSONField()),
        result=models.Value(copy.deepcopy(result), output_field=models.JSONField()),
        result_sha256=service.digest(result) if result is not None else '', attempts=0)
    w.job.refresh_from_db()
    return row(w.job)


def client(actor):
    c = APIClient()
    c.force_authenticate(actor)
    c.raise_request_exception = False
    return c


@pytest.mark.parametrize('spec', BAD_SPECS, ids=[f'spec-{i}' for i in range(len(BAD_SPECS))])
def test_blocked_malformed_claim_remains_inspectable_without_repair(worker, spec):  # noqa: F811
    result = {'private': 'retained-output'}
    saved(worker, spec, result)
    assert service.claim(worker.job.pk) is None
    before = row(worker.job)
    events = list(JobEvent.objects.filter(job=worker.job).values())
    response = client(worker.actor).get(f'/api/jobs/{worker.job.pk}/')
    assert response.status_code == 200 and response['Cache-Control'] == 'no-store'
    body = response.json()
    assert body['state'] == 'blocked' and body['reason_code'] == 'job_specification_invalid'
    assert body['specification'] == spec and body['result'] == result and body['result_sha256'] == service.digest(result)
    assert body['review_approved'] is body['production_use_approved'] is False
    assert row(worker.job) == before and list(JobEvent.objects.filter(job=worker.job).values()) == events


@pytest.mark.parametrize('result', BAD_RESULTS, ids=[f'result-{i}' for i in range(len(BAD_RESULTS))])
def test_irregular_result_is_visible_verbatim_but_cannot_export_as_scores(worker, result):  # noqa: F811
    before = saved(worker, {'kind': service.csv_scoring.KIND}, result)
    NativeJob.objects.filter(pk=worker.job.pk).update(state='succeeded')
    before = row(worker.job)
    c = client(worker.actor)
    response = c.get(f'/api/jobs/{worker.job.pk}/')
    assert response.status_code == 200 and response['Cache-Control'] == 'no-store'
    assert response.json()['result'] == result and response.json()['result_sha256'] == before['result_sha256']
    response = c.get(f'/api/jobs/{worker.job.pk}/scores/', {'sha256': before['result_sha256']})
    assert response.status_code == 409 and response.json() == {'error_code': 'job_scoring_result_unavailable'}
    assert response['Cache-Control'] == 'no-store' and row(worker.job) == before
    assert not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize('spec', BAD_SPECS, ids=[f'export-spec-{i}' for i in range(len(BAD_SPECS))])
def test_unknown_saved_kind_never_authorizes_score_download(worker, spec):  # noqa: F811
    saved(worker, spec, {'scores': [1, 2]})
    NativeJob.objects.filter(pk=worker.job.pk).update(state='succeeded')
    before = row(worker.job)
    response = client(worker.actor).get(f'/api/jobs/{worker.job.pk}/scores/', {'sha256': before['result_sha256']})
    assert response.status_code == 409 and response.json() == {'error_code': 'job_scoring_result_unavailable'}
    assert response['Cache-Control'] == 'no-store' and row(worker.job) == before


@pytest.mark.parametrize('spec', [None, {'kind': []}])
@pytest.mark.parametrize('guard', ['outsider', 'revoked', 'tampered'])
def test_project_authority_and_digest_checks_still_precede_receipt_inspection(worker, django_user_model, spec, guard):  # noqa: F811
    saved(worker, spec, {'private': 'retained-output'})
    actor = worker.actor
    if guard == 'outsider':
        actor = django_user_model.objects.create_user(username='retained-outsider')
    elif guard == 'revoked':
        ProjectMembership.objects.filter(actor=actor).update(active=False)
    else:
        NativeJob.objects.filter(pk=worker.job.pk).update(result_sha256='0' * 64)
    before = row(worker.job)
    response = client(actor).get(f'/api/jobs/{worker.job.pk}/')
    assert response.status_code == (409 if guard == 'tampered' else 403)
    assert response['Cache-Control'] == 'no-store'
    assert 'retained-output' not in response.content.decode() and row(worker.job) == before


@pytest.mark.parametrize('kind', [service.csv_scoring.KIND, service.training_scoring.KIND])
@pytest.mark.parametrize('size', [0, 500, 501])
def test_valid_score_previews_and_canonical_downloads_remain_unchanged(worker, kind, size):  # noqa: F811
    result = {'scores': [{'row': i, 'prediction': i / 1000} for i in range(size)], 'rows': size}
    saved(worker, {'kind': kind}, result)
    NativeJob.objects.filter(pk=worker.job.pk).update(state='succeeded')
    before = row(worker.job)
    c = client(worker.actor)
    response = c.get(f'/api/jobs/{worker.job.pk}/')
    assert response.status_code == 200
    value = response.json()['result']
    expected = {'rows': size, 'scores_preview': result['scores'][:500], 'scores_truncated': True} if size > 500 else result
    assert value == expected and response.json()['result_sha256'] == service.digest(result)
    response = c.get(f'/api/jobs/{worker.job.pk}/scores/', {'sha256': before['result_sha256']})
    assert response.status_code == 200 and response.content == service.csv_scoring.canonical_bytes(result)
    assert response['Cache-Control'] == 'no-store' and row(worker.job) == before


@pytest.mark.parametrize('spec,result', [(None, {'private': 'retained'}), ({'kind': service.csv_scoring.KIND}, ['bad'])])
def test_head_receipts_retain_private_cache_policy_without_changing_saved_data(worker, spec, result):  # noqa: F811
    before = saved(worker, spec, result)
    response = client(worker.actor).head(f'/api/jobs/{worker.job.pk}/')
    assert response.status_code == 200 and response.content == b'' and response['Cache-Control'] == 'no-store'
    assert row(worker.job) == before
