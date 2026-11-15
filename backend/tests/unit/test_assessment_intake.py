"""Protected first-use evidence accounts for exact bytes seen in ordinary intake."""

import hashlib
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from access_control import projects
from access_control.models import ProjectAuthorityEvent
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.assessment_intake import prior_development_use
from execution_jobs.models import NativeJob
from tests.unit.test_durable_training_search import post, world  # noqa: F401
from tests.unit.test_native_protected_assessment import queued
from tests.unit.test_prospective_assessment import prospective, seal  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def test_imported_outcomes_remain_exploratory_and_cannot_be_scored_after_seal(prospective, monkeypatch):
    w = prospective
    raw = w.outcomes.to_csv(index=False).encode()
    upload = w.clients['developer'].post('/api/declaration/', {
        'file': SimpleUploadedFile('earlier.csv', raw), 'column_separator': 'comma',
    })
    assert upload.status_code == 201, upload.content
    digest = hashlib.sha256(raw).hexdigest()
    intake = ProjectAuthorityEvent.objects.get(operation='development_input_admitted', resource__input_sha256=digest)
    expected = prior_development_use(digest, w.project.pk)
    assert expected['id'] == str(intake.pk)
    assert expected['actor']['id'] == w.users['developer'].pk
    assert prior_development_use(digest, uuid.uuid4()) == {
        'kind': 'generic_input_admission', 'visibility': 'outside_project',
    }

    sealed, _, identifier = seal(w, w.outcomes)
    assert sealed.status_code == 200, sealed.content
    job_id = queued(w, {'id': identifier})
    service.execute(job_id)
    result = NativeJob.objects.get(pk=job_id).result
    assert result['evidence_status'] == 'exploratory'
    assert result['confirmation_reason'] == 'prior_development_input_access'
    assert result['reuse_adjudication']['prior_development'] == expected

    def reject_bundle_access(*args, **kwargs):
        pytest.fail('Protected bytes reached ordinary scoring')

    monkeypatch.setattr('deployment.views.bundle_dir', reject_bundle_access)
    denied = w.clients['developer'].post('/api/deployment/score/', {
        'file_id': w.file_id, 'file': SimpleUploadedFile('protected.csv', raw),
    })
    assert denied.status_code == 409 and denied.json()['error_code'] == 'prospective_outcomes_protected'
    assert ProjectAuthorityEvent.objects.filter(operation='development_input_admitted', resource__input_sha256=digest).count() == 1


def test_native_preview_alone_records_outcome_exposure(prospective):
    w = prospective
    path = w.path.with_name('preview-alias.csv')
    w.outcomes.to_csv(path, index=False)
    alias = Declaration.objects.create(file=str(path.relative_to(w.root)), name='fixture alias', original_name=path.name)
    projects.bind_dataset(alias, w.project.pk)
    response = post(w.clients['developer'], f'/api/jobs/datasets/{alias.pk}/training-input/', w.options)
    assert response.status_code == 200, response.content
    assert not NativeJob.objects.filter(dataset=alias).exists()

    sealed, _, identifier = seal(w, w.outcomes)
    assert sealed.status_code == 200, sealed.content
    job_id = queued(w, {'id': identifier})
    service.execute(job_id)
    result = NativeJob.objects.get(pk=job_id).result
    intake = ProjectAuthorityEvent.objects.get(operation='development_input_admitted', authority_source='native_training_preview',
                                               resource__input_sha256=result['input_sha256'])
    assert result['evidence_status'] == 'exploratory'
    assert result['confirmation_reason'] == 'prior_development_input_access'
    assert result['reuse_adjudication']['prior_development']['id'] == str(intake.pk)
