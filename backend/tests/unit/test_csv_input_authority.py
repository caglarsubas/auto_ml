"""Late authority changes withhold the complete native CSV input and receipt."""
import uuid

import pytest
from django.db import DatabaseError

from access_control import projects
from access_control.models import ProjectDataset, ProjectMembership
from declaration.models import Declaration
from execution_jobs import csv_scoring
from execution_jobs.models import JobEvent, NativeAdoption, NativeAdoptionEvent, NativeJob, NativeProtectedInput
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def snapshot():
    return [list(model.objects.order_by('pk').values()) for model in
            [NativeJob, JobEvent, NativeAdoption, NativeAdoptionEvent, NativeProtectedInput, HoldoutAccess]]


def late_fingerprint(monkeypatch, callback):
    observed = []
    original = csv_scoring.csv_input

    def fingerprint(raw):
        result = original(raw)
        observed.append(True)
        callback()
        return result

    monkeypatch.setattr(csv_scoring, 'csv_input', fingerprint)
    return observed


def invoke(w, entry):
    if entry == 'bytes':
        return csv_scoring.input_bytes(w.users['developer'].pk, w.file_id)
    if entry == 'preview':
        return csv_scoring.prepare(w.users['developer'], w.file_id)
    return w.clients['developer'].get(f'/api/jobs/datasets/{w.file_id}/input/')


@pytest.mark.parametrize('entry', ['bytes', 'preview', 'http'])
@pytest.mark.parametrize('guard', ['actor', 'membership', 'binding'])
def test_revocation_during_real_fingerprinting_withholds_input_and_receipt(world, monkeypatch, entry, guard):
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

    observed = late_fingerprint(monkeypatch, revoke)
    if entry == 'http':
        response = invoke(w, entry)
        assert response.status_code == 403, response.content
        assert b'sha256' not in response.content and b'relative_path' not in response.content
    else:
        with pytest.raises(projects.ProjectDenied):
            invoke(w, entry)
    assert observed == [True] and snapshot() == before and w.path.read_bytes() == source


@pytest.mark.parametrize('entry', ['bytes', 'preview', 'http'])
def test_late_authority_outage_withholds_input_and_private_diagnostics(world, monkeypatch, entry):
    w = world
    before, source = snapshot(), w.path.read_bytes()
    observed = late_fingerprint(monkeypatch, lambda: None)
    original = projects.recheck

    def unavailable(authority, **kwargs):
        if observed:
            raise DatabaseError('private SQL must remain private')
        return original(authority, **kwargs)

    monkeypatch.setattr(projects, 'recheck', unavailable)
    if entry == 'http':
        response = invoke(w, entry)
        assert response.status_code == 503, response.content
        assert b'private SQL' not in response.content and b'sha256' not in response.content
    else:
        with pytest.raises(DatabaseError):
            invoke(w, entry)
    assert observed == [True] and snapshot() == before and w.path.read_bytes() == source


@pytest.mark.parametrize('entry', ['bytes', 'preview', 'http'])
def test_valid_input_preserves_exact_bytes_receipts_and_read_only_state(world, entry):
    w = world
    before, source = snapshot(), w.path.read_bytes()
    fingerprint = csv_scoring.csv_input(source)
    dataset = Declaration.objects.get(pk=w.file_id)
    expected = {'file_id': w.file_id, 'name': dataset.original_name, **fingerprint, 'budget': csv_scoring.BUDGET}
    values = []
    for _ in range(2):
        value = invoke(w, entry)
        if entry == 'bytes':
            raw, receipt, authority = value
            assert raw == source
            assert receipt == {k: v for k, v in expected.items() if k != 'budget'} | {'relative_path': dataset.file.name}
            assert authority == projects.dataset_authority(w.users['developer'].pk, w.file_id, 'read')
        else:
            if entry == 'http':
                assert value.status_code == 200, value.content
                value = value.json()
            assert value == expected
        values.append(value)
    assert values[0] == values[1] and snapshot() == before and w.path.read_bytes() == source
