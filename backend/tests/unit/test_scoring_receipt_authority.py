"""Exact scoring receipt downloads retain real project read authority."""
import json
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError

from access_control.models import ProjectMembership
from deployment import views
from tests.unit.test_package_reviews import packaged, world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def receipt(world):
    file_id, _, bundle, _, clients = world
    result = clients['developer'].post('/api/deployment/score/', {
        'file_id': file_id, 'bundle_id': bundle['bundle_id'],
        'file': SimpleUploadedFile('approved.csv', b'x,other\n1,2\n2,1\n3,0\n')})
    assert result.status_code == 200, result.content
    data = result.json()
    url = f'/api/deployment/receipts/{file_id}/{data["batch_id"]}/?sha256={data["receipt_sha256"]}'
    return url, data


@pytest.mark.parametrize('role', ['developer', 'reviewer', 'admin'])
def test_all_current_read_roles_can_download_exact_receipt(world, receipt, role):
    result = world[4][role].get(receipt[0])
    assert result.status_code == 200, result.content
    assert json.loads(result.content)['batch_id'] == receipt[1]['batch_id']
    assert result['Cache-Control'] == 'no-store'


def test_outsider_anonymous_and_revoked_access_withheld(world, receipt):
    from django.test import Client
    assert Client().get(receipt[0]).status_code == 403
    assert world[4]['outsider'].get(receipt[0]).status_code == 403
    ProjectMembership.objects.filter(actor=world[3]['reviewer']).update(active=False)
    assert world[4]['reviewer'].get(receipt[0]).status_code == 403


def test_digest_and_receipt_identity_tampering_block(world, receipt, settings):
    from pathlib import Path
    url, data = receipt
    assert world[4]['reviewer'].get(url.split('?')[0]).status_code == 409
    path = Path(settings.MEDIA_ROOT) / data['scores_path']
    path.write_bytes(path.read_bytes() + b' ')
    assert world[4]['reviewer'].get(url).status_code == 409
    altered = json.loads(path.read_text())
    altered['file_id'] += 1
    path.write_text(json.dumps(altered))
    digest = views.byte_digest(path.read_bytes())
    assert world[4]['reviewer'].get(url.split('?')[0] + '?sha256=' + digest).status_code == 409


def test_final_authority_recheck_and_database_outage(world, receipt):
    original = views.byte_digest
    def revoke(raw):
        ProjectMembership.objects.filter(actor=world[3]['reviewer']).update(active=False)
        return original(raw)
    with patch('deployment.views.byte_digest', side_effect=revoke):
        assert world[4]['reviewer'].get(receipt[0]).status_code == 403
    with patch('access_control.projects.dataset_authority', side_effect=DatabaseError('unavailable')):
        assert world[4]['developer'].get(receipt[0]).status_code == 503
