"""The complete training preview retains its initially accepted dataset scope."""
import uuid

import pytest
from django.db import DatabaseError

from access_control import projects
from access_control.models import ProjectDataset, ProjectMembership
from execution_jobs import training_search
from execution_jobs.models import JobEvent, NativeAdoption, NativeAdoptionEvent, NativeJob, NativeProtectedInput
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import post, world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def snapshot():
    return [list(model.objects.order_by('pk').values()) for model in
            [NativeJob, JobEvent, NativeAdoption, NativeAdoptionEvent, NativeProtectedInput, HoldoutAccess]]


def late(monkeypatch, boundary, callback):
    prepared, observed = [], []
    original_prepare, original_digest = training_search.prepare, training_search.digest

    def observe():
        if not observed:
            observed.append(True)
            callback()

    def prepare(*args, **kwargs):
        result = original_prepare(*args, **kwargs)
        prepared.append(True)
        if boundary == 'prepared':
            observe()
        return result

    def digest(value):
        result = original_digest(value)
        if prepared and boundary == 'digest':
            observe()
        return result

    monkeypatch.setattr(training_search, 'prepare', prepare)
    monkeypatch.setattr(training_search, 'digest', digest)
    return observed


def invoke(w, entry):
    if entry == 'service':
        return training_search.preview(w.users['developer'], w.file_id, w.options)
    return post(w.clients['developer'], f'/api/jobs/datasets/{w.file_id}/training-input/', w.options)


@pytest.mark.parametrize('entry', ['service', 'http'])
@pytest.mark.parametrize('boundary', ['prepared', 'digest'])
@pytest.mark.parametrize('guard', ['actor', 'membership', 'binding'])
def test_late_revocation_withholds_the_complete_training_preview(world, monkeypatch, entry, boundary, guard):
    w = world
    before, source = snapshot(), w.path.read_bytes()

    def revoke():
        actor = w.users['developer']
        if guard == 'actor':
            type(actor).objects.filter(pk=actor.pk).update(is_active=False)
        elif guard == 'membership':
            ProjectMembership.objects.filter(project=w.project, actor=actor).update(revision=uuid.uuid4())
        else:
            ProjectDataset.objects.filter(dataset_id=w.file_id).update(revision=uuid.uuid4())

    observed = late(monkeypatch, boundary, revoke)
    if entry == 'service':
        with pytest.raises(projects.ProjectDenied):
            invoke(w, entry)
    else:
        response = invoke(w, entry)
        assert response.status_code == 403, response.content
        assert b'training_sha256' not in response.content and b'prediction_contract' not in response.content
    assert observed == [True] and snapshot() == before
    assert w.path.read_bytes() == source


@pytest.mark.parametrize('entry', ['service', 'http'])
@pytest.mark.parametrize('boundary', ['prepared', 'digest'])
def test_late_authority_outage_withholds_the_preview_and_private_errors(world, monkeypatch, entry, boundary):
    w = world
    before, source = snapshot(), w.path.read_bytes()
    observed = late(monkeypatch, boundary, lambda: None)
    original = projects.recheck

    def unavailable(authority, **kwargs):
        if observed:
            raise DatabaseError('private SQL must remain private')
        return original(authority, **kwargs)

    monkeypatch.setattr(projects, 'recheck', unavailable)
    if entry == 'service':
        with pytest.raises(DatabaseError):
            invoke(w, entry)
    else:
        response = invoke(w, entry)
        assert response.status_code == 503, response.content
        assert b'private SQL' not in response.content and b'training_sha256' not in response.content
    assert observed == [True] and snapshot() == before
    assert w.path.read_bytes() == source


@pytest.mark.parametrize('entry', ['service', 'http'])
def test_valid_previews_preserve_plans_and_read_only_state(world, entry):
    w = world
    before, source = snapshot(), w.path.read_bytes()
    values = []
    for _ in range(2):
        value = invoke(w, entry)
        if entry == 'http':
            assert value.status_code == 200, value.content
            value = value.json()
        values.append(value)
    plan, _ = training_search.prepare(w.users['developer'].pk, w.file_id, w.options)
    assert values[0] == values[1]
    assert values[0]['training_sha256'] == training_search.digest(plan)
    assert values[0]['input_sha256'] == plan['source']['sha256']
    assert values[0]['prediction_contract'] == plan['prediction_contract']
    assert values[0]['folds'] == plan['folds']
    assert values[0]['budget'] == plan['profile']['limits'] and values[0]['runtime'] == plan['profile']['runtime']
    assert snapshot() == before and w.path.read_bytes() == source
