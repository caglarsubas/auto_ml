"""Owned metadata history fixture; never a queue execution or recovery fixture."""
import os
import uuid
from datetime import timedelta


def seed_native_history_e2e(username):
    if os.environ.get('DECLARAI_TEST_INSTALLATION') != '1':
        raise RuntimeError('History seed requires disposable installation.')
    from access_control.authority import actor_snapshot
    from access_control.models import ProjectMembership
    from access_control.projects import bind_dataset
    from declaration.models import Declaration
    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile
    from django.utils import timezone
    from execution_jobs.models import NativeJob, JobEvent
    from deployment.reviews import digest

    actor = get_user_model().objects.get(username=username + '-training')
    project = ProjectMembership.objects.get(actor=actor).project_id
    dataset = Declaration.objects.create(name='Queue history.csv', original_name='Queue history.csv')
    dataset.file.save('history-ui-' + uuid.uuid4().hex + '.csv', ContentFile(b'x,outcome\n1,good\n2,bad\n'))
    bind_dataset(dataset, project, source='disposable-history-e2e')
    now = timezone.now()
    for i in range(123):
        state = ['failed', 'cancelled', 'blocked'][i % 3]
        spec = {'kind': ['package_integrity_v1', 'native_csv_scoring_v1', 'native_numeric_training_search_v1'][i % 3]}
        job = NativeJob.objects.create(id=uuid.uuid4(), dataset=dataset, project_id=project, actor=actor,
                                       actor_snapshot=actor_snapshot(actor), authority={}, specification=spec,
                                       request_sha256=digest({'disposable_history': i}), state=state, revision=1,
                                       reason_code='disposable_metadata_example', attempts=1,
                                       expires_at=now + timedelta(hours=1), finished_at=now,
                                       created_at=now - timedelta(seconds=123-i))
        JobEvent.objects.create(job=job, revision=1, event_type=state, actor_snapshot=actor_snapshot(actor), detail={})
