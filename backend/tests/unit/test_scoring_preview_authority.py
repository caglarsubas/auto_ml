"""A complete native scoring preview retains both accepted dataset scopes."""
import uuid

import pytest
from django.db import DatabaseError

from access_control import projects
from access_control.models import ProjectDataset, ProjectMembership
from execution_jobs import service, training_scoring
from execution_jobs.models import JobEvent, NativeAdoption, NativeAdoptionEvent, NativeJob, NativeProtectedInput
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import post, world  # noqa: F401
from tests.unit.test_native_training_scoring import candidate  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def snapshot():
    return [list(model.objects.order_by('pk').values()) for model in
            [NativeJob, JobEvent, NativeAdoption, NativeAdoptionEvent, NativeProtectedInput, HoldoutAccess]]


def late(monkeypatch, boundary, callback):
    prepared, observed = [], []
    original_prepare = training_scoring.prepare

    def prepare(*args, **kwargs):
        value = original_prepare(*args, **kwargs)
        prepared.append(True)
        return value

    monkeypatch.setattr(training_scoring, 'prepare', prepare)
    if boundary == 'json':
        original = training_scoring.json.loads

        def loads(*args, **kwargs):
            result = original(*args, **kwargs)
            if prepared and not observed and isinstance(result, dict) and 'training_job_id' in result and 'result' in result:
                observed.append(True)
                callback()
            return result

        monkeypatch.setattr(training_scoring.json, 'loads', loads)
    else:
        original = training_scoring.digest

        def digest(value):
            result = original(value)
            if prepared and not observed and isinstance(value, dict) and value.get('kind') == training_scoring.KIND:
                observed.append(True)
                callback()
            return result

        monkeypatch.setattr(training_scoring, 'digest', digest)
    return observed


def invoke(w, entry):
    data = {'input_file_id': w.input_id, 'training_result_sha256': w.trained.result_sha256}
    if entry == 'service':
        return training_scoring.preview(w.users['developer'], w.trained.pk, data)
    return post(w.clients['developer'], f'/api/jobs/{w.trained.pk}/scoring-input/', data)


@pytest.mark.parametrize('entry', ['service', 'http'])
@pytest.mark.parametrize('boundary', ['json', 'digest'])
@pytest.mark.parametrize('guard', ['actor', 'membership', 'training_binding', 'input_binding'])
def test_late_revocation_withholds_the_complete_scoring_preview(candidate, monkeypatch, entry, boundary, guard):
    w = candidate
    before, inputs = snapshot(), (w.path.read_bytes(), w.scoring_path.read_bytes())

    def revoke():
        actor = w.users['developer']
        if guard == 'actor':
            type(actor).objects.filter(pk=actor.pk).update(is_active=False)
        elif guard == 'membership':
            ProjectMembership.objects.filter(project=w.project, actor=actor).update(revision=uuid.uuid4())
        else:
            ProjectDataset.objects.filter(dataset_id=w.file_id if guard == 'training_binding' else w.input_id).update(revision=uuid.uuid4())

    observed = late(monkeypatch, boundary, revoke)
    if entry == 'service':
        with pytest.raises(projects.ProjectDenied):
            invoke(w, entry)
    else:
        response = invoke(w, entry)
        assert response.status_code == 403, response.content
        assert b'scoring_sha256' not in response.content and b'prediction_contract' not in response.content
    assert observed == [True] and snapshot() == before
    assert (w.path.read_bytes(), w.scoring_path.read_bytes()) == inputs


@pytest.mark.parametrize('entry', ['service', 'http'])
@pytest.mark.parametrize('boundary', ['json', 'digest'])
@pytest.mark.parametrize('scope', ['training', 'input'])
def test_late_authority_outage_never_returns_success_or_private_diagnostics(candidate, monkeypatch, entry, boundary, scope):
    w = candidate
    before = snapshot()
    original = projects.recheck
    observed = late(monkeypatch, boundary, lambda: None)

    def unavailable(authority, **kwargs):
        if observed and authority.get('file_id') == (w.file_id if scope == 'training' else w.input_id):
            raise DatabaseError('private SQL must remain private')
        return original(authority, **kwargs)

    monkeypatch.setattr(projects, 'recheck', unavailable)
    if entry == 'service':
        with pytest.raises(DatabaseError):
            invoke(w, entry)
    else:
        response = invoke(w, entry)
        assert response.status_code == 503, response.content
        assert b'private SQL' not in response.content and b'scoring_sha256' not in response.content
    assert observed == [True] and snapshot() == before


@pytest.mark.parametrize('entry', ['service', 'http'])
def test_valid_scoring_previews_preserve_exact_plans_payloads_and_read_only_state(candidate, entry):
    w = candidate
    before, inputs = snapshot(), (w.path.read_bytes(), w.scoring_path.read_bytes())
    values = []
    for _ in range(2):
        value = invoke(w, entry)
        if entry == 'http':
            assert value.status_code == 200, value.content
            value = value.json()
        values.append(value)
    plan, raw_export, _ = training_scoring.prepare(w.users['developer'], w.file_id, w.trained.pk, w.trained.result_sha256, w.input_id)
    exported = training_scoring.json.loads(raw_export)
    assert values[0] == values[1]
    assert values[0]['scoring_sha256'] == training_scoring.digest(plan)
    assert values[0]['features'] == exported['result']['features']
    assert values[0]['prediction_contract'] == exported['result']['prediction_contract']
    assert snapshot() == before and (w.path.read_bytes(), w.scoring_path.read_bytes()) == inputs
