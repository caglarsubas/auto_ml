"""Exact-package findings and responses. No review or production approval."""
import hashlib
import json
import uuid
from pathlib import Path

from django.conf import settings
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


def freshness(review):
    try:
        exact = package_identity(review.dataset_id, review.bundle_id)
        expected = {k: str(getattr(review, k)) for k in ('bundle_id', 'execution_id', 'assessment_id', 'manifest_sha256')}
        if exact != expected:
            return 'integrity_unavailable'
        selected = current_selection(review.dataset_id)
        if selected != (str(review.execution_id), str(review.execution_id), str(review.assessment_id)):
            return 'historical'
        current = current_identity(review.dataset_id)
        if current != expected or context_digest(review.dataset_id) != review.context_sha256:
            return 'historical'
        return 'current'
    except (OSError, ValueError, KeyError, TypeError, projects.ProjectDenied):
        return 'integrity_unavailable'


def require_current(review):
    if freshness(review) != 'current':
        raise ReviewConflict('package_review_stale')


def findings(events):
    result = {}
    for event in events:
        if event.event_type == 'finding':
            result[str(event.pk)] = {'id': str(event.pk), 'severity': event.severity, 'text': event.text,
                                     'state': 'open', 'responses': 0, 'evidence': event.evidence}
        elif event.finding_id:
            item = result[str(event.finding_id)]
            if event.event_type == 'response':
                item['responses'] += 1
            elif event.event_type in {'resolve', 'reopen'}:
                item['state'] = 'resolved' if event.event_type == 'resolve' else 'open'
    return list(result.values())


def serialize(review, actor, *, replayed=False):
    from deployment.review_evidence import validate_events
    events = list(review.events.all())
    validate_events(actor, review, events)
    return {'id': str(review.pk), 'file_id': review.dataset_id, 'project_id': str(review.project_id),
            **{k: str(getattr(review, k)) for k in ('bundle_id', 'execution_id', 'assessment_id', 'manifest_sha256', 'context_sha256')},
            'revision': review.revision, 'created_at': review.created_at.isoformat(),
            'freshness': freshness(review), 'production_use_approved': False, 'review_approved': False,
            'findings': findings(events), 'replayed': replayed,
            'events': [{'id': str(e.pk), 'revision': e.revision, 'event_type': e.event_type,
                        'finding_id': str(e.finding_id) if e.finding_id else None,
                        'severity': e.severity, 'text': e.text, 'actor': e.actor_snapshot,
                        'authority': e.authority_snapshot, 'created_at': e.created_at.isoformat(),
                        'evidence': e.evidence} for e in events]}


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


def append_record(review, actor, scope, identifier, sha, kind, text='', finding_id=None, severity='', evidence_job=None, evidence=None):
    review.revision += 1
    PackageReviewEvent.objects.create(id=identifier, review=review, actor=actor, actor_snapshot=actor_snapshot(actor),
                                     authority_snapshot=scope, request_sha256=sha, revision=review.revision,
                                     event_type=kind, text=text, finding_id=finding_id, severity=severity,
                                     evidence_job=evidence_job, evidence=evidence)
    review.save(update_fields=['revision'])


def start(actor, file_id, data):
    identifier = checked_request(data, {'request_id', 'bundle_id', 'manifest_sha256'})
    bundle_id = uuid.UUID(str(data['bundle_id']))
    scope = actor_scope(actor, file_id, 'reviewer')
    sha = digest({'actor_id': actor.pk, 'file_id': file_id, 'create': data})
    with projection_lock(file_id), transaction.atomic():
        scope = lock_authority(actor, file_id, 'reviewer')
        previous = replay(identifier, sha)
        if previous:
            return serialize(previous, actor, replayed=True)
        exact = package_identity(file_id, bundle_id)
        if data['manifest_sha256'] != exact['manifest_sha256']:
            raise ReviewConflict('review_manifest_changed')
        if PackageReview.objects.filter(dataset_id=file_id, bundle_id=bundle_id).exists():
            raise ReviewConflict('package_review_already_exists')
        review = PackageReview.objects.create(project_id=scope['project_id'], dataset_id=file_id,
                                             context_sha256=context_digest(file_id), **exact)
        require_current(review)
        append_record(review, actor, scope, identifier, sha, 'opened')
        projects.recheck(scope)
        require_current(review)
        return serialize(review, actor)


def append(actor, review_id, data):
    kind = data.get('event_type') if isinstance(data, dict) else None
    fields = {'request_id', 'expected_revision', 'event_type', 'text'}
    if kind == 'finding':
        fields.add('severity')
    elif kind in {'response', 'resolve', 'reopen'}:
        fields.add('finding_id')
    else:
        raise ValueError('Select finding, response, resolve or reopen.')
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
    with projection_lock(review.dataset_id), transaction.atomic():
        scope = lock_authority(actor, review.dataset_id, role)
        review = PackageReview.objects.select_for_update().get(pk=review_id)
        if str(review.project_id) != scope['project_id']:
            raise projects.ProjectDenied('review_project_mismatch')
        previous = replay(identifier, sha)
        if previous:
            return serialize(previous, actor, replayed=True)
        require_current(review)
        if data['expected_revision'] != review.revision:
            raise ReviewConflict('review_revision_changed')
        finding_id, severity = None, ''
        if kind == 'finding':
            severity = data['severity']
            if severity not in {'critical', 'major', 'minor', 'observation'}:
                raise ValueError('Select critical, major, minor or observation.')
        else:
            finding_id = uuid.UUID(str(data['finding_id']))
            selected = next((f for f in findings(review.events.all()) if f['id'] == str(finding_id)), None)
            if not selected or (kind == 'reopen') != (selected['state'] == 'resolved'):
                raise ReviewConflict('finding_state_changed')
            if kind == 'resolve' and review.events.filter(finding_id=finding_id, event_type='response',
                                                         actor_snapshot__id=actor.pk).exists():
                raise projects.ProjectDenied('reviewer_cannot_resolve_own_response')
        evidence_job, evidence = None, None
        if 'evidence' in data:
            from deployment.review_evidence import capture
            evidence_job, evidence = capture(actor, review, data['evidence'])
        append_record(review, actor, scope, identifier, sha, kind, data['text'], finding_id, severity, evidence_job, evidence)
        projects.recheck(scope)
        require_current(review)
        return serialize(review, actor)
