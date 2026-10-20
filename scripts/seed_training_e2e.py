"""Additive, explicitly disposable browser training fixtures; never customer data."""
import os
import uuid


def seed_training_e2e(username, password):
    if os.environ.get('DECLARAI_TEST_INSTALLATION') != '1':
        raise RuntimeError('Training browser seed requires a disposable installation.')
    from access_control.projects import bind_dataset, operator_change
    from declaration.models import Declaration
    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile
    from django.db import transaction

    with transaction.atomic():
        users = get_user_model().objects
        developer = users.create_user(username=username + '-training', password=password)
        reviewer = users.create_user(username=username + '-training-reviewer', password=password)
        operator = users.create_user(username='training-fixture-admin-' + uuid.uuid4().hex, password=None)
        event, _ = operator_change({'operation': 'create', 'name': 'Training UI fixture', 'user': operator.username},
                                   uuid.uuid4(), 'disposable-training-e2e')
        for actor, role in [(developer, 'developer'), (reviewer, 'reviewer')]:
            operator_change({'operation': 'member', 'project_id': str(event.project_id),
                             'user': actor.username, 'role': role}, uuid.uuid4(), 'disposable-training-e2e')
        for name, regression in [('Training binary.csv', False), ('Training regression.csv', True)]:
            rows = ['x,z,entity,outcome']
            for i in range(80):
                outcome = str(i % 4) if regression else ('bad' if i % 2 else 'good')
                rows.append(f'{i / 80},{i % 7},{i // 4},{outcome}')
            dataset = Declaration.objects.create(name=name, original_name=name)
            dataset.file.save('training-ui-' + uuid.uuid4().hex + '.csv', ContentFile(('\n'.join(rows) + '\n').encode()))
            bind_dataset(dataset, event.project_id, source='disposable-training-e2e')
