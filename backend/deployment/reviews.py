"""Review of exact evidence with attributable findings and decisions."""
import hashlib
import json
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from access_control import projects
from access_control.authority import actor_snapshot
from access_control.models import ProjectDataset, ProjectMembership
from deployment.deploy_utils import bundle_dir, bundle_summary
from deployment.evidence import current_selection, verify_bundle
from deployment.models import PackageReview, PackageReviewEvent
from modeling.execution_artifacts import digest_file, projection_lock
from modeling.models import PipelineRun


class ReviewConflict(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def context_digest(file_id):
    """Pin mutable development context; frozen package originals stay unchanged."""
    from declaration.models import Declaration
    dataset = Declaration.objects.get(pk=file_id)
    source = dataset.get_file_path()
    if not source:
        raise ReviewConflict('review_source_unavailable')
    root = Path(settings.MEDIA_ROOT)
    projections = [root / folder / f'{file_id}_{suffix}.json'
                   for folder, suffix in [('modeling', 'status'), ('evaluation', 'evaluation')]]
    return digest({'source': digest_file(source), 'source_path': dataset.file.name,
                   'has_header': dataset.has_header,
                   'projections': [digest_file(p) if p.is_file() else None for p in projections],
                   'pipelines': list(PipelineRun.objects.filter(file_id=file_id).order_by('pk')
                                     .values('pk', 'state', 'current_step', 'status'))})


def package_identity(file_id, bundle_id):
    manifest, sha = verify_bundle(bundle_dir(file_id, bundle_id), file_id, str(bundle_id))
    if manifest.get('handoff_schema_version') != 1 or not manifest.get('execution_id') or not manifest.get('assessment_id'):
        raise ReviewConflict('review_requires_verified_execution_and_assessment')
    for key in ('bundle_id', 'execution_id', 'assessment_id'):
        if str(uuid.UUID(str(manifest[key]))) != manifest[key]:
            raise ReviewConflict('review_package_identity_invalid')
    # Prevent historical cross-project outcome history from entering a new review.
    out = Path(bundle_dir(file_id, bundle_id))
    for name in ('evaluation.json', 'model_card.json'):
        projects.assert_evidence_scope(json.loads((out / name).read_text()), file_id)
    return {key: manifest[key] for key in ('bundle_id', 'execution_id', 'assessment_id')} | {'manifest_sha256': sha}


def current_identity(file_id):
    try:
        summary = bundle_summary(file_id)
        return package_identity(file_id, summary['bundle_id'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def subject_identity(review):
    identity = {'manifest_sha256': review.manifest_sha256}
    for key in ('bundle_id', 'execution_id', 'assessment_id'):
        value = getattr(review, key)
        identity[key] = str(value) if value is not None else None
    if review.native_assessment_id is not None:
        identity.update(assessment_job_id=str(review.native_assessment_id),
                        assessment_result_sha256=review.assessment_result_sha256)
    return identity


def native_subject(file_id, project_id, identifier, expected):
    from deployment.native_candidate import sha
    from execution_jobs import reproduction, service
    from execution_jobs.models import NativeJob

    job = NativeJob.objects.get(pk=identifier, dataset_id=file_id, project_id=project_id)
    try:
        manifest, raw = reproduction.verified_manifest(job, expected)
    except service.JobConflict as error:
        raise ReviewConflict(error.code) from None
    return manifest, sha(raw)


def subject_state(review):
    if review.native_assessment_id is not None:
        try:
            manifest, sha = native_subject(review.dataset_id, review.project_id, review.native_assessment_id,
                                           review.assessment_result_sha256)
            if (sha != review.manifest_sha256
                    or manifest['assessment']['specification']['assessment_sha256'] != review.context_sha256):
                return 'integrity_unavailable', None
            return 'current', manifest
        except (ReviewConflict, projects.ProjectDenied):
            return 'historical', None
        except (ObjectDoesNotExist, OSError, ValueError, KeyError, TypeError):
            return 'integrity_unavailable', None
    try:
        exact = package_identity(review.dataset_id, review.bundle_id)
        expected = subject_identity(review)
        if exact != expected:
            return 'integrity_unavailable', None
        selected = current_selection(review.dataset_id)
        if selected != (str(review.execution_id), str(review.execution_id), str(review.assessment_id)):
            return 'historical', None
        current = current_identity(review.dataset_id)
        if current != expected or context_digest(review.dataset_id) != review.context_sha256:
            return 'historical', None
        return 'current', None
    except (OSError, ValueError, KeyError, TypeError, projects.ProjectDenied):
        return 'integrity_unavailable', None


def freshness(review):
    return subject_state(review)[0]


def require_current(review):
    status, manifest = subject_state(review)
    if status != 'current':
        raise ReviewConflict('package_review_stale')
    return manifest


def require_independent_reviewer(actor, manifest, events):
    from execution_jobs.reproduction import development_actors

    if (actor.pk in development_actors(manifest)
            or any(e.event_type == 'response' and e.actor_snapshot.get('id') == actor.pk for e in events)):
        raise projects.ProjectDenied('review_requires_independent_reviewer')


def serialize(review, actor, *, replayed=False, manifest=None):
    from deployment import review_decisions
    from deployment.review_evidence import validate_events

    events = list(review.events.all())
    validate_events(actor, review, events)
    status, manifest = ('current', manifest) if manifest is not None else subject_state(review)
    decision = review_decisions.state(review, events, status, manifest)
    return {'id': str(review.pk), 'file_id': review.dataset_id, 'project_id': str(review.project_id),
            **subject_identity(review), 'context_sha256': review.context_sha256,
            'revision': review.revision, 'created_at': review.created_at.isoformat(),
            'freshness': status, 'production_use_approved': False, 'review_approved': decision['status'] == 'approved',
            'decision': decision,
            'findings': review_decisions.findings(events), 'replayed': replayed,
            'events': [{'id': str(e.pk), 'revision': e.revision, 'event_type': e.event_type,
                        'finding_id': str(e.finding_id) if e.finding_id else None,
                        'severity': e.severity, 'text': e.text, 'actor': e.actor_snapshot,
                        'authority': e.authority_snapshot, 'created_at': e.created_at.isoformat(),
                        'evidence': e.evidence, **({'details': e.details} if e.details is not None else {})}
                       for e in events]}


@contextmanager
def review_transaction(file_id, *, native, write=False):
    from execution_jobs import service

    # Native assessment uses the queue lock before project or dataset locks.
    queue = service.locked(write=write) if native else nullcontext()
    with queue, projection_lock(file_id), transaction.atomic():
        yield


def actor_scope(actor, file_id, role=None):
    if not projects.governed():
        raise projects.ProjectDenied('review_requires_project_governance')
    scope = projects.dataset_authority(actor.pk, file_id, 'read')
    if role and scope['role'] != role:
        raise projects.ProjectDenied('review_role_required')
    return scope


def lock_authority(actor, file_id, role):
    # Serialize membership changes with review publication, using admin_change's
    # project lock and the membership row as additional defense.
    from access_control.models import Project
    binding = ProjectDataset.objects.select_for_update().get(dataset_id=file_id)
    Project.objects.select_for_update().get(pk=binding.project_id)
    ProjectMembership.objects.select_for_update().get(actor=actor, project_id=binding.project_id)
    return actor_scope(actor, file_id, role)


def checked_request(data, fields):
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError('Supply exactly the displayed review action fields.')
    return uuid.UUID(str(data['request_id']))


def replay(identifier, request_sha):
    previous = PackageReviewEvent.objects.filter(pk=identifier).select_related('review').first()
    if previous:
        if previous.request_sha256 != request_sha:
            raise ReviewConflict('review_request_reused')
        return previous.review
    return None


def append_record(review, actor, scope, identifier, sha, kind, text='', finding_id=None, severity='',
                  evidence_job=None, evidence=None, details=None):
    review.revision += 1
    PackageReviewEvent.objects.create(id=identifier, review=review, actor=actor, actor_snapshot=actor_snapshot(actor),
                                     authority_snapshot=scope, request_sha256=sha, revision=review.revision,
                                     event_type=kind, text=text, finding_id=finding_id, severity=severity,
                                     evidence_job=evidence_job, evidence=evidence, details=details)
    review.save(update_fields=['revision'])


def start(actor, file_id, data):
    from deployment.scoring_receipts import require_digest

    native = isinstance(data, dict) and 'assessment_job_id' in data
    subject_fields = {'assessment_job_id', 'assessment_result_sha256'} if native else {'bundle_id'}
    identifier = checked_request(data, {'request_id', 'manifest_sha256'} | subject_fields)
    subject_id = uuid.UUID(str(data['assessment_job_id' if native else 'bundle_id']))
    manifest_sha256 = require_digest(data['manifest_sha256']) if native else data['manifest_sha256']
    result_sha256 = require_digest(data['assessment_result_sha256']) if native else None
    actor_scope(actor, file_id, 'reviewer')
    sha = digest({'actor_id': actor.pk, 'file_id': file_id, 'create': data})
    with review_transaction(file_id, native=native, write=True):
        scope = lock_authority(actor, file_id, 'reviewer')
        previous = replay(identifier, sha)
        if previous:
            if str(previous.project_id) != scope['project_id']:
                raise projects.ProjectDenied('review_project_mismatch')
            return serialize(previous, actor, replayed=True)
        if native:
            manifest, current_sha = native_subject(file_id, scope['project_id'], subject_id, result_sha256)
            if manifest_sha256 != current_sha:
                raise ReviewConflict('review_manifest_changed')
            require_independent_reviewer(actor, manifest, ())
            if PackageReview.objects.filter(native_assessment_id=subject_id).exists():
                raise ReviewConflict('package_review_already_exists')
            subject = {'native_assessment_id': subject_id, 'assessment_result_sha256': result_sha256,
                       'manifest_sha256': current_sha,
                       'context_sha256': manifest['assessment']['specification']['assessment_sha256']}
        else:
            subject = package_identity(file_id, subject_id)
            if manifest_sha256 != subject['manifest_sha256']:
                raise ReviewConflict('review_manifest_changed')
            if PackageReview.objects.filter(dataset_id=file_id, bundle_id=subject_id).exists():
                raise ReviewConflict('package_review_already_exists')
            subject['context_sha256'] = context_digest(file_id)
        review = PackageReview.objects.create(project_id=scope['project_id'], dataset_id=file_id, **subject)
        if not native:
            require_current(review)
        append_record(review, actor, scope, identifier, sha, 'opened')
        projects.recheck(scope)
        return serialize(review, actor, manifest=require_current(review))


def append(actor, review_id, data):
    from deployment import review_decisions

    kind = data.get('event_type') if isinstance(data, dict) else None
    fields = {'request_id', 'expected_revision', 'event_type', 'text'}
    if kind == 'finding':
        fields.add('severity')
    elif kind in {'response', 'resolve', 'reopen'}:
        fields.add('finding_id')
    elif kind == 'exception':
        fields.update({'finding_id', 'expires_at'})
    elif kind == 'approve':
        fields.add('report')
    elif kind != 'revoke':
        raise ValueError('Select a supported review action.')
    if isinstance(data, dict) and 'evidence' in data:
        fields.add('evidence')
        from deployment.review_evidence import checked_reference
        checked_reference(data['evidence'])
    identifier = checked_request(data, fields)
    if not isinstance(data['text'], str) or not 1 <= len(data['text'].strip()) <= 10000:
        raise ValueError('Supply a finding, response or disposition between 1 and 10000 characters.')
    if type(data['expected_revision']) is not int or data['expected_revision'] < 1:
        raise ValueError('Supply the last observed review revision.')
    role = 'developer' if kind == 'response' else 'reviewer'
    review = PackageReview.objects.get(pk=review_id)
    actor_scope(actor, review.dataset_id, role)
    sha = digest({'actor_id': actor.pk, 'review_id': str(review.pk), 'action': data})
    native = review.native_assessment_id is not None
    decision_action = kind in {'exception', 'approve', 'revoke'}
    if (decision_action and not native) or (native and 'evidence' in data):
        raise ReviewConflict('review_action_unsupported_for_subject')
    with review_transaction(review.dataset_id, native=native, write=True):
        scope = lock_authority(actor, review.dataset_id, role)
        review = PackageReview.objects.select_for_update().get(pk=review_id)
        if str(review.project_id) != scope['project_id']:
            raise projects.ProjectDenied('review_project_mismatch')
        previous = replay(identifier, sha)
        if previous:
            return serialize(previous, actor, replayed=True)
        manifest = require_current(review)
        if data['expected_revision'] != review.revision:
            raise ReviewConflict('review_revision_changed')
        events = list(review.events.all())
        if native and role == 'reviewer':
            require_independent_reviewer(actor, manifest, events)
        finding_id, severity = None, ''
        if kind == 'finding':
            severity = data['severity']
            if severity not in {'critical', 'major', 'minor', 'observation'}:
                raise ValueError('Select critical, major, minor or observation.')
        elif kind in {'response', 'resolve', 'reopen', 'exception'}:
            finding_id = uuid.UUID(str(data['finding_id']))
            selected = next((f for f in review_decisions.findings(events) if f['id'] == str(finding_id)), None)
            allowed_state = {'resolved', 'excepted'} if kind == 'reopen' else {'open'}
            if not selected or selected['state'] not in allowed_state:
                raise ReviewConflict('finding_state_changed')
            if kind == 'resolve' and review.events.filter(finding_id=finding_id, event_type='response',
                                                         actor_snapshot__id=actor.pk).exists():
                raise projects.ProjectDenied('reviewer_cannot_resolve_own_response')
        evidence_job, evidence = None, None
        if 'evidence' in data:
            from deployment.review_evidence import capture
            evidence_job, evidence = capture(actor, review, data['evidence'])
        details = review_decisions.prepare(review, kind, data, events, manifest) if decision_action else None
        append_record(review, actor, scope, identifier, sha, kind, data['text'], finding_id, severity,
                      evidence_job, evidence, details)
        projects.recheck(scope)
        return serialize(review, actor, manifest=require_current(review))
