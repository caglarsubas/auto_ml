"""Add feature-only input to the disposable training browser project."""
import os
import uuid


def seed_native_candidate_e2e(username):
    if os.environ.get('DECLARAI_TEST_INSTALLATION') != '1':
        raise RuntimeError('Candidate seed requires disposable installation.')
    from access_control.models import ProjectMembership
    from access_control.projects import bind_dataset
    from declaration.models import Declaration
    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile

    actor = get_user_model().objects.get(username=username + '-training')
    project = ProjectMembership.objects.get(actor=actor).project_id
    dataset = Declaration.objects.create(name='Candidate features.csv', original_name='Candidate features.csv')
    dataset.file.save('candidate-ui-' + uuid.uuid4().hex + '.csv', ContentFile(b'z,x\n,0.1\n3,0.6\n9,0.9\n'))
    bind_dataset(dataset, project, source='disposable-candidate-e2e')
