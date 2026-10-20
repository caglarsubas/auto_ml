"""Additive candidate export/scoring proof on the owned private TLS installation."""
import json
import os
import secrets
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get('DECLARAI_TEST_INSTALLATION') != '1':
        raise RuntimeError('Disposable private installation required.')
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    import django
    django.setup()
    from access_control import projects
    from access_control.models import ProjectMembership
    from declaration.models import Declaration
    from deployment import native_candidate
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile
    from django.db import connection
    from django.test import Client
    from execution_jobs import service, training_scoring, training_search
    from execution_jobs.models import NativeJob
    from execution_jobs.preflight import check_runtime
    if settings.DECLARAI_RUNTIME_PROFILE != 'private' or connection.vendor != 'postgresql' or not connection.settings_dict['NAME'].startswith('declarai_fixture'):
        raise RuntimeError('Owned private PostgreSQL fixture required.')
    with connection.cursor() as cursor:
        cursor.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()')
        assert cursor.fetchone()[0] is True
    check_runtime()
    state = Path(os.environ['DECLARAI_JOB_FIXTURE_STATE'])
    assert state.is_absolute() and not state.is_relative_to(ROOT)
    actor = get_user_model().objects.create_user(username='candidate-' + uuid.uuid4().hex, password=secrets.token_urlsafe(32))
    # Fixture owns this synthetic account; retain password only in process memory.
    password = secrets.token_urlsafe(32)
    actor.set_password(password); actor.save()
    client = Client(enforce_csrf_checks=True)
    request = {'secure': True, 'HTTP_HOST': settings.ALLOWED_HOSTS[0]}

    def post(path, body, status=200):
        csrf = client.get('/api/auth/session/', **request).json()['csrf_token']
        response = client.post(path, json.dumps(body), content_type='application/json', HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN=settings.CSRF_TRUSTED_ORIGINS[0], **request)
        assert response.status_code == status, (path, response.status_code, response.content)
        return response.json()

    post('/api/auth/login/', {'username': actor.username, 'password': password})
    selected = {}
    for job in NativeJob.objects.filter(state='succeeded').order_by('created_at'):
        if job.specification.get('kind') == training_search.KIND:
            selected.setdefault(job.result['prediction_contract']['task'], job)
    assert set(selected) == {'classification', 'regression'}
    processes = []
    proofs = []
    try:
        with state.with_name('candidate-worker.log').open('wb') as log:
            for role in ['worker', 'dispatcher']:
                processes.append(subprocess.Popen(['sh', str(ROOT / 'docker/private-job-entrypoint.sh'), role], cwd=ROOT / 'backend', env=os.environ.copy(), stdout=log, stderr=log, start_new_session=True))
            for task, trained in selected.items():
                ProjectMembership.objects.get_or_create(actor=actor, project_id=trained.project_id, defaults={'role': 'developer'})
                url = f'/api/jobs/{trained.pk}/candidate/?sha256={trained.result_sha256}&project_id={trained.project_id}'
                response = client.get(url, **request); assert response.status_code == 200
                raw_export, export_sha = response.content, response['X-DeclarAI-Export-SHA256']
                assert native_candidate.sha(raw_export) == export_sha
                raw_input = b'z,x\n,0.1\n2,0.8\n9,-0.2\n'
                dataset = Declaration.objects.create(name='Synthetic candidate features', original_name='features.csv')
                dataset.file.save('candidate-private-' + uuid.uuid4().hex + '.csv', ContentFile(raw_input))
                projects.bind_dataset(dataset, trained.project_id)
                p = post(f'/api/jobs/{trained.pk}/scoring-input/?project_id={trained.project_id}', {'input_file_id': dataset.pk, 'training_result_sha256': trained.result_sha256})
                body = {**{key: p[key] for key in training_scoring.FIELDS}, 'kind': training_scoring.KIND, 'request_id': str(uuid.uuid4())}
                queue_url = f'/api/jobs/datasets/{trained.dataset_id}/?project_id={trained.project_id}'
                queued = post(queue_url, body, 202)
                assert post(queue_url, body)['id'] == queued['id']
                until = time.monotonic() + 45
                while True:
                    result = NativeJob.objects.get(pk=queued['id'])
                    if result.state in service.TERMINAL:
                        break
                    assert time.monotonic() < until and all(p.poll() is None for p in processes)
                    time.sleep(.05)
                assert result.state == 'succeeded', result.reason_code
                expected = native_candidate.score(raw_export, export_sha, raw_input, chunk_size=1)
                assert expected == native_candidate.score(raw_export, export_sha, raw_input, chunk_size=10000)
                assert result.result['scores'] == expected['scores']
                assert result.result['export_sha256'] == export_sha and result.result['n_scored'] == 3
                assert all(result.result[key] is False for key in native_candidate.FLAGS)
                scores = client.get(f'/api/jobs/{result.pk}/scores/?sha256={result.result_sha256}', **request)
                assert scores.status_code == 200 and json.loads(scores.content) == result.result
                assert result.result_sha256 == service.digest(result.result) and result.events.filter(event_type='succeeded').count() == 1
                assert post(queue_url, body)['id'] == str(result.pk)
                trained.refresh_from_db(); assert trained.result_sha256 == expected['training_result_sha256']
                proofs.append({'task': task, 'training_result_sha256': trained.result_sha256, 'export_sha256': export_sha, 'scoring_result_sha256': result.result_sha256, 'rows': 3, 'prediction_parity': True, 'chunk_invariance': True})
        print(json.dumps({'schema': 'private_native_candidate_v1', 'private_tls_prefork_and_dispatcher': 'passed', 'real_csrf_export_preview_submit_download': 'passed', 'native_candidate_scoring': proofs, 'duplicate_single_publication': 'passed', 'expert_or_pickle_loaded': False, 'model_adopted': False, 'release_qualified': False, 'customer_installation_modified': False}))
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)


if __name__ == '__main__':
    main()
