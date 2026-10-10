#!/usr/bin/env python3
"""Explicit synthetic installation: real Celery delivery, failure and DB fencing.

Run only with DECLARAI_TEST_INSTALLATION=1 and a dedicated fixture broker DB.
No real dataset, model state, credentials or installation exports are read.
"""
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')


def main():
    if os.environ.get('DECLARAI_TEST_INSTALLATION') != '1':
        raise RuntimeError('Use only a disposable synthetic installation.')
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from access_control import projects
    from access_control.models import Project, ProjectMembership, ProjectPolicy
    from declaration.models import Declaration
    from deployment.deploy_utils import bundle_dir
    from execution_jobs import service
    from execution_jobs.models import NativeJob
    from backend.celery import app
    from execution_jobs.tasks import run_native_job

    if not settings.DECLARAI_JOBS_ENABLED or settings.DECLARAI_RUNTIME_PROFILE != 'development':
        raise RuntimeError('This fixture qualifies native jobs in development with SQLite or TLS PostgreSQL; private broker qualification is separate.')
    token = uuid.uuid4().hex
    actor = get_user_model().objects.create_user(username='job-fixture-' + token)
    ProjectPolicy.objects.get_or_create(pk=1)
    project = Project.objects.create(name='Synthetic job fixture ' + token)
    ProjectMembership.objects.create(project=project, actor=actor, role='reviewer')
    dataset = Declaration.objects.create(name='Synthetic hash-only fixture', original_name='synthetic-job.csv', file='data_files/job-' + token + '.csv')
    projects.bind_dataset(dataset, project.pk, actor)
    bundle_id, execution_id, assessment_id = (str(uuid.uuid4()) for _ in range(3))
    out = Path(bundle_dir(dataset.pk, bundle_id)); out.mkdir(parents=True)
    # The worker must never deserialize these deliberately non-model bytes.
    names = ['synthetic.model', 'lineage.json', 'business_understanding.json', 'success_criteria.json',
             'monitoring_plan.json', 'modeling_status.json', 'execution_manifest.json',
             'assessment_manifest.json', 'evaluation.json', 'model_card.json']
    for name in names: (out / name).write_bytes(b'{}')
    # Enough bounded read work to observe and kill an actual active worker.
    with (out / 'synthetic.model').open('wb') as stream:
        for _ in range(384): stream.write(b'x' * 1024 ** 2)
    def file_sha(path):
        sha = hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(1024 ** 2): sha.update(chunk)
        return sha.hexdigest()
    files = {p.name: {'sha256': file_sha(p), 'bytes': p.stat().st_size} for p in out.iterdir()}
    identity = {'file_id': dataset.pk, 'bundle_id': bundle_id, 'execution_id': execution_id, 'assessment_id': assessment_id}
    manifest = {**identity, 'handoff_schema_version': 1, 'schema_version': 4,
                'model_file': 'synthetic.model', 'artifact_integrity': files}
    raw = json.dumps(manifest).encode(); (out / 'manifest.json').write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    (out / 'publication.json').write_text(json.dumps({**identity, 'manifest_sha256': sha}))
    def submit():
        return service.submit(actor, dataset.pk, {'request_id':str(uuid.uuid4()), 'kind':service.KIND,
                'bundle_id':bundle_id, 'manifest_sha256':sha})
    def wait(identifier, states, seconds=45):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            job = NativeJob.objects.get(pk=identifier)
            if job.state in states: return job
            time.sleep(0.02)
        raise RuntimeError('Synthetic worker did not reach the expected state.')
    workers = []
    def start(log):
        process = subprocess.Popen([sys.executable,'-m','celery','-A','backend.celery:app','worker',
            '--pool=prefork','--concurrency=2','--without-gossip','--without-mingle','--without-heartbeat',
            '--loglevel=WARNING','--hostname=fixture-' + token + '@%h'],
            cwd=ROOT/'backend', stdout=log, stderr=log, env=os.environ.copy(), start_new_session=True)
        workers.append(process)
        return process
    def kill(process):
        if process.poll() is None:
            # Only process groups created by this fixture, never discovered PIDs.
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
    with tempfile.TemporaryDirectory(prefix='declarai-native-job-worker-') as tmp:
        with (Path(tmp)/'worker.log').open('wb') as log:
            try:
                crashed = submit()
                worker = start(log)
                service.dispatch_once()
                active = wait(crashed['id'], {'running'})
                old_token = active.lease_token
                kill(worker)
                active.refresh_from_db()
                if active.state != 'running' or active.result is not None:
                    raise RuntimeError('Worker failure was not injected before publication.')
                # Controlled clock fault: do not wait 180 seconds or reduce the
                # production lease/hard-timeout budgets for this fixture.
                NativeJob.objects.filter(pk=active.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
                service.reconcile()
                service.finish(active.pk, old_token, 'succeeded', result={'stale_worker':True})
                active.refresh_from_db()
                assert active.state == 'queued' and active.result is None
                worker = start(log)
                service.dispatch_once()
                recovered = wait(active.pk, {'succeeded','blocked','failed'})
                assert recovered.state == 'succeeded' and recovered.attempts == 2
                # Duplicate broker delivery cannot rerun/adopt an existing result.
                run_native_job.apply_async(args=[str(active.pk)], retry=False)
                time.sleep(1)
                recovered.refresh_from_db()
                assert recovered.attempts == 2 and recovered.events.filter(event_type='succeeded').count() == 1

                cancelled = submit(); service.dispatch_once()
                wait(cancelled['id'], {'running'})
                receipt = service.cancel(actor, cancelled['id'], {'action':'cancel'})
                assert receipt['state'] == 'cancel_requested'
                stopped = wait(cancelled['id'], {'cancelled'})
                assert stopped.result is None

                kill(worker)
                pending = submit()
                original_publish = run_native_job.apply_async
                with app.connection_for_write('redis://127.0.0.1:9/15') as dead_connection:
                    with patch('execution_jobs.tasks.run_native_job.apply_async',
                               side_effect=lambda *a, **k: original_publish(*a, connection=dead_connection, **k)):
                        unavailable = service.dispatch_once()
                assert unavailable['broker_unavailable'] == 1
                assert NativeJob.objects.get(pk=pending['id']).state == 'queued'
                # Recovery uses a fresh worker and retained DB request.
                worker = start(log); service.dispatch_once()
                restored = wait(pending['id'], {'succeeded','blocked','failed'})
                assert restored.state == 'succeeded'
                print(json.dumps({'synthetic':True, 'metadata_engine':settings.DATABASES['default']['ENGINE'],
                    'celery_version':service.runtime()['packages']['celery'], 'actual_prefork_redis_delivery':'passed',
                    'actual_worker_failure_then_injected_lease_expiry':'passed', 'stale_publication_fenced':'passed',
                    'duplicate_delivery_single_publication':'passed', 'active_cancellation':'passed',
                    'broker_connection_failure_retained_request':'passed', 'fresh_worker_recovery':'passed',
                    'artifact_bytes_per_attempt':384*1024**2+18, 'private_redis_tls':'not_qualified',
                    'production_recovery':'not_qualified'}))
            finally:
                for process in workers: kill(process)
                # Remove only this qualifier's 10 fixed synthetic files/metadata.
                for name in names + ['manifest.json','publication.json']:
                    (out/name).unlink(missing_ok=True)
                out.rmdir()


if __name__ == '__main__': main()
