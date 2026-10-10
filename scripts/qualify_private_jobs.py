#!/usr/bin/env python3
"""Synthetic private TLS jobs: quiescent snapshot and empty-broker recovery.

The owning PostgreSQL fixture supplies external state, metadata and artifacts.
Only this script's worker/dispatcher process groups are stopped. No model state
is loaded. A real 180-second orphan lease expires without a clock injection.
"""
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get('DECLARAI_TEST_INSTALLATION') != '1':
        raise RuntimeError('Use only a disposable synthetic installation.')
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import connection
    from access_control import projects
    from access_control.models import Project, ProjectMembership, ProjectPolicy
    from declaration.models import Declaration
    from deployment.deploy_utils import bundle_dir
    from execution_jobs import service
    from execution_jobs.models import NativeJob
    from execution_jobs.preflight import check_runtime
    from execution_jobs.tasks import run_native_job

    if (settings.DECLARAI_RUNTIME_PROFILE != 'private' or connection.vendor != 'postgresql'
            or not connection.settings_dict['NAME'].startswith('declarai_fixture')):
        raise RuntimeError('Private jobs require the disposable TLS PostgreSQL fixture.')
    state_file = Path(os.environ['DECLARAI_JOB_FIXTURE_STATE'])
    if not state_file.is_absolute():
        raise RuntimeError('State belongs outside the checkout in the disposable fixture.')
    phase = sys.argv[1:]
    processes = []

    def start(role, log):
        process = subprocess.Popen(['sh', str(ROOT / 'docker/private-job-entrypoint.sh'), role],
                                   cwd=ROOT / 'backend', env=os.environ.copy(), stdout=log, stderr=log,
                                   start_new_session=True)
        processes.append(process)
        return process

    def stop():
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)

    def wait(identifier, states, seconds=45):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            job = NativeJob.objects.get(pk=identifier)
            if job.state in states:
                return job
            if any(p.poll() is not None for p in processes):
                raise RuntimeError('An owned private job process exited unexpectedly.')
            time.sleep(0.1)
        raise RuntimeError('Private job did not reach its expected state.')

    def snapshot(identifiers):
        result = {}
        for label, identifier in identifiers.items():
            job = NativeJob.objects.get(pk=identifier)
            result[label] = {
                'receipt': service.serialize(job), 'authority': job.authority,
                'request_sha256': job.request_sha256,
                'lease_token': str(job.lease_token) if job.lease_token else None,
                'lease_until': job.lease_until.isoformat() if job.lease_until else None,
                'next_dispatch': job.next_dispatch.isoformat(),
            }
        return result

    if phase == ['seed']:
        assert not state_file.exists()
        check_runtime()
        token = uuid.uuid4().hex
        actor = get_user_model().objects.create_user(username='private-job-fixture-' + token)
        ProjectPolicy.objects.get_or_create(pk=1)
        project = Project.objects.create(name='Synthetic private job fixture ' + token)
        ProjectMembership.objects.create(project=project, actor=actor, role='reviewer')
        dataset = Declaration.objects.create(name='Private hash-only fixture', original_name='synthetic.csv',
                                             file='data_files/private-job-' + token + '.csv')
        projects.bind_dataset(dataset, project.pk, actor)
        bundle_id, execution_id, assessment_id = (str(uuid.uuid4()) for _ in range(3))
        out = Path(bundle_dir(dataset.pk, bundle_id))
        out.mkdir(parents=True)
        names = ['synthetic.model', 'lineage.json', 'business_understanding.json', 'success_criteria.json',
                 'monitoring_plan.json', 'modeling_status.json', 'execution_manifest.json',
                 'assessment_manifest.json', 'evaluation.json', 'model_card.json']
        for name in names:
            (out / name).write_bytes(b'{}')
        (out / 'synthetic.model').write_bytes(b'not-deserializable-model-state' * 1024)
        files = {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
                 for p in out.iterdir()}
        identity = {'file_id': dataset.pk, 'bundle_id': bundle_id, 'execution_id': execution_id,
                    'assessment_id': assessment_id}
        manifest = {**identity, 'handoff_schema_version': 1, 'schema_version': 4,
                    'model_file': 'synthetic.model', 'artifact_integrity': files}
        raw = json.dumps(manifest).encode()
        (out / 'manifest.json').write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        (out / 'publication.json').write_text(json.dumps({**identity, 'manifest_sha256': sha}))
        def submit():
            return service.submit(actor, dataset.pk, {'request_id': str(uuid.uuid4()), 'kind': service.KIND,
                                                      'bundle_id': bundle_id, 'manifest_sha256': sha})['id']
        identifiers = {label: submit() for label in ['queued', 'orphan', 'completed', 'cancelled']}
        _, old_token = service.claim(identifiers['orphan'])
        service.cancel(actor, identifiers['cancelled'], {'action': 'cancel'})
        with state_file.with_suffix('.worker.log').open('wb') as log:
            try:
                start('worker', log)
                run_native_job.apply_async(args=[identifiers['completed']], retry=False)
                completed = wait(identifiers['completed'], {'succeeded', 'failed', 'blocked'})
                assert completed.state == 'succeeded' and completed.attempts == 1
            finally:
                stop()
        artifact_hashes = {p.relative_to(settings.MEDIA_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in out.iterdir()}
        # Tokens are fixture-private: never copy this state into release evidence.
        with open(state_file, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            json.dump({'ids': identifiers, 'old_token': str(old_token), 'artifact_hashes': artifact_hashes,
                       'jobs': snapshot(identifiers)}, stream)
        print(json.dumps({'private_jobs': 'seed', 'actual_private_worker_completion': 'passed',
                          'quiescent_states': ['queued', 'running', 'succeeded', 'cancelled']}))
        return

    state = json.loads(state_file.read_text())
    ids = state['ids']
    if phase == ['broker-down']:
        assert snapshot(ids) == state['jobs']
        result = service.dispatch_once()
        assert result == {'delivered': 0, 'broker_unavailable': 1}
        assert snapshot(ids) == state['jobs']
        print(json.dumps({'private_jobs': 'broker-down', 'real_broker_loss_retains_requests': 'passed'}))
        return
    if phase not in [['verify'], ['recover']]:
        raise RuntimeError('Use seed, broker-down, verify or recover.')
    check_runtime()
    assert snapshot(ids) == state['jobs']
    for relative, sha in state['artifact_hashes'].items():
        path = Path(settings.MEDIA_ROOT) / relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    if phase == ['verify']:
        print(json.dumps({'private_jobs': 'verify', 'exact_database_artifact_restore': 'passed'}))
        return
    with state_file.with_suffix('.recovery.log').open('wb') as log:
        try:
            start('dispatcher', log)
            orphan = wait(ids['orphan'], {'queued', 'failed', 'blocked'}, seconds=200)
            assert orphan.state == 'queued' and orphan.attempts == 1
            service.finish(orphan.pk, uuid.UUID(state['old_token']), 'succeeded', result={'stale': True})
            orphan.refresh_from_db()
            assert orphan.state == 'queued' and orphan.result is None
            start('worker', log)
            for label, attempts in [('queued', 1), ('orphan', 2)]:
                job = wait(ids[label], {'succeeded', 'blocked', 'failed'})
                assert job.state == 'succeeded' and job.attempts == attempts
                assert job.events.filter(event_type='succeeded').count() == 1
                receipt = service.serialize(job)
                original_events = state['jobs'][label]['receipt']['events']
                assert receipt['events'][:len(original_events)] == original_events
                assert job.authority == state['jobs'][label]['authority']
                assert job.request_sha256 == state['jobs'][label]['request_sha256']
                assert receipt['result_sha256'] == service.digest(receipt['result'])
            current = snapshot(ids)
            for label in ['completed', 'cancelled']:
                assert current[label] == state['jobs'][label]
            # Duplicate messages after restore must not adopt or rerun terminal results.
            for identifier in ids.values():
                run_native_job.apply_async(args=[identifier], retry=False)
            time.sleep(1)
            assert snapshot(ids) == current
            print(json.dumps({'private_jobs': 'recover', 'private_tls_prefork_and_dispatcher': 'passed',
                              'empty_broker_database_artifact_restore': 'passed',
                              'natural_180_second_lease_recovery': 'passed', 'stale_token_fenced': 'passed',
                              'duplicate_single_publication': 'passed', 'terminal_history_preserved': 'passed',
                              'native_state_loaded': False, 'production_recovery': 'not_qualified'}))
        finally:
            stop()


if __name__ == '__main__':
    main()
