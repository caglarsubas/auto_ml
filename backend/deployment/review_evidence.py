"""Digest-bound successful native checks cited by exact-package review events.

Never load model state or rerun a job. Terminal job results are immutable through
the native API. Do not acquire the queue lock while holding a review/project lock.
"""

import uuid

from access_control import projects
from deployment.reviews import ReviewConflict, digest
from deployment.scoring_receipts import require_digest
from execution_jobs import service, csv_scoring
from execution_jobs.models import NativeJob


def checked_reference(reference):
    if not isinstance(reference, dict) or set(reference) != {'job_id', 'result_sha256'}:
        raise ValueError('Supply exactly the selected job ID and result SHA-256.')
    return uuid.UUID(str(reference['job_id'])), require_digest(reference['result_sha256'])


def source_scopes(actor, review, reference=None):
    """Include cited input authority in the HTTP response's final rechecks."""
    ids = set(review.events.exclude(evidence_job=None).values_list('evidence_job_id', flat=True))
    if reference is not None:
        try:
            ids.add(checked_reference(reference)[0])
        except ValueError:
            # The action validator reports malformed optional references as 400.
            pass
    scopes = {}
    for job in NativeJob.objects.filter(pk__in=ids):
        if job.source_dataset_id is not None:
            scope = service.scope(actor, job.source_dataset_id)
            if scope['project_id'] != str(review.project_id):
                raise projects.ProjectDenied('review_evidence_input_project_mismatch')
            scopes[job.source_dataset_id] = scope
    return list(scopes.values())


def capture(actor, review, reference):
    identifier, expected_sha = checked_reference(reference)
    job = NativeJob.objects.get(pk=identifier)
    try:
        scopes = service.read_authority(actor, job)
    except service.JobConflict as exc:
        raise ReviewConflict(exc.code) from None
    if job.dataset_id != review.dataset_id or job.project_id != review.project_id:
        raise ReviewConflict('review_evidence_package_mismatch')
    exact = {k: str(getattr(review, k)) for k in ('bundle_id', 'execution_id', 'assessment_id', 'manifest_sha256')}
    if any(job.specification.get(k) != value for k, value in exact.items()):
        raise ReviewConflict('review_evidence_package_mismatch')
    if (job.state != 'succeeded' or job.specification.get('kind') not in {service.KIND, csv_scoring.KIND}
            or not isinstance(job.result, dict) or not job.result or not job.finished_at):
        raise ReviewConflict('review_evidence_success_required')
    if job.result_sha256 != expected_sha:
        raise ReviewConflict('review_evidence_result_changed')
    if any(job.result.get(k) != value for k, value in exact.items()) or job.result.get('file_id') != review.dataset_id:
        raise ReviewConflict('review_evidence_package_mismatch')
    facts = {k: job.result[k] for k in ('artifact_count', 'verified_bytes', 'model_state_loaded',
             'score_parity_verified', 'refit_verified', 'n_scored', 'score_semantics', 'scores_calibrated',
             'offline_verification_scope') if k in job.result}
    snapshot = {'schema_version': 1, 'job_id': str(job.pk), 'kind': job.specification['kind'],
                'result_sha256': expected_sha, 'specification_sha256': digest(job.specification),
                'job_revision': job.revision, 'finished_at': job.finished_at.isoformat(),
                'submitted_by': job.actor_snapshot, 'package': exact, 'facts': facts,
                'source_dataset_id': job.source_dataset_id,
                'input_sha256': job.specification.get('source', {}).get('sha256'),
                'independent_reproduction_verified': False}
    for scope in scopes:
        projects.recheck(scope)
    return job, snapshot


def validate_events(actor, review, events):
    # One full digest check per distinct job, even when many events cite it.
    checked = {}
    for event in events:
        if event.evidence_job_id is None and event.evidence is None:
            continue
        if not isinstance(event.evidence, dict) or str(event.evidence_job_id) != event.evidence.get('job_id'):
            raise ReviewConflict('review_evidence_reference_changed')
        identifier = event.evidence_job_id
        if identifier not in checked:
            _, checked[identifier] = capture(actor, review, {'job_id': str(identifier),
                                                           'result_sha256': event.evidence.get('result_sha256')})
        if checked[identifier] != event.evidence:
            raise ReviewConflict('review_evidence_reference_changed')


def receipt(actor, review, event):
    validate_events(actor, review, [event])
    if event.evidence_job_id is None:
        raise ReviewConflict('review_evidence_reference_required')
    job, snapshot = capture(actor, review, {'job_id': str(event.evidence_job_id),
                                           'result_sha256': event.evidence['result_sha256']})
    # A scoring preview is not the cited full result. Retain all rows for replay.
    result = service.serialize(job) | {'result': job.result}
    return {'schema_version': 1, 'review_id': str(review.pk), 'event_id': str(event.pk),
            'evidence': snapshot, 'job': result, 'review_approved': False, 'production_use_approved': False}
