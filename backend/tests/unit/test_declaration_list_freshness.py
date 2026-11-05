"""Cached view declarations cannot hide new uploads or retain revoked access."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

import pytest

from access_control import projects
from access_control.models import Project, ProjectMembership, ProjectPolicy
from declaration.models import Declaration
from declaration.views import DeclarationViewSet

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db]


def test_list_uses_fresh_rows_and_current_project_authority_after_cached_empty_query(
        _use_tmp_media, django_user_model, monkeypatch, settings):
    settings.DECLARAI_RUNTIME_PROFILE = "development"
    actor = django_user_model.objects.create(username="fresh-list-actor")
    client = Client()
    client.force_login(actor)
    cached = Declaration.objects.all()
    assert list(cached) == []
    monkeypatch.setattr(DeclarationViewSet, "queryset", cached)
    response = client.get('/api/declaration/')
    assert response.status_code == 200 and response.json() == []
    response = client.post('/api/declaration/', {
        'file': SimpleUploadedFile('fresh-list.csv', b'x,y\n1,0\n2,1\n', content_type='text/csv'),
        'column_separator': 'comma',
    })
    assert response.status_code == 201, response.content
    identifier = response.json()['id']
    response = client.get('/api/declaration/')
    assert response.status_code == 200 and identifier in [row['id'] for row in response.json()]
    assert cached._result_cache == []

    ProjectPolicy.objects.create()
    own, other = Project.objects.create(name='Owned'), Project.objects.create(name='Other')
    member = ProjectMembership.objects.create(actor=actor, project=own, role='developer')
    projects.bind_dataset(Declaration.objects.get(pk=identifier), own.pk)
    foreign = Declaration.objects.create(name='Foreign', file='data_files/foreign.csv')
    projects.bind_dataset(foreign, other.pk)
    response = client.get('/api/declaration/')
    assert response.status_code == 200 and [row['id'] for row in response.json()] == [identifier]
    member.active = False
    member.save(update_fields=['active'])
    response = client.get('/api/declaration/')
    assert response.status_code == 200 and response.json() == []
    assert cached._result_cache == []
