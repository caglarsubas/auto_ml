"""Bind known ordinary input admissions to protected assessment reuse checks."""

from django.db.models import Q

from access_control import projects
from access_control.models import ProjectAuthorityEvent
from execution_jobs import csv_scoring, training_scoring, training_search
from execution_jobs.models import NativeJob
from modeling.holdout_evidence import prospective_payload


def admit_generic_input(actor, scopes, input_sha256, source):
    """Record the exact uploaded bytes before parsing under the custody lock."""
    from execution_jobs import service

    with service.locked(write=True):
        for scope in scopes:
            projects.recheck(scope)
        if prospective_payload(input_sha256):
            return False
        projects.audit(actor, 'development_input_admitted', {'input_sha256': input_sha256},
                       scopes[0]['project_id'], source=source)
    return True


def prior_development_use(input_sha256, project_id, *, sealed_at=None):
    """Return one exact-input admission receipt, with project-scoped attribution."""
    # The native training and candidate scoring APIs parse input at admission.
    # A plain CSV scoring job parses only after a worker claims it.
    csv_claim = Q(specification__kind=csv_scoring.KIND, specification__source__sha256=input_sha256, attempts__gt=0)
    if sealed_at is not None:
        csv_claim &= Q(events__event_type='started', events__created_at__lt=sealed_at)
    job = NativeJob.objects.filter(
        Q(specification__kind=training_search.KIND, specification__training__source__sha256=input_sha256)
        | Q(specification__kind=training_scoring.KIND, specification__source__sha256=input_sha256)
        | csv_claim
    ).order_by('created_at', 'pk').values('id', 'project_id', 'actor_snapshot', 'created_at').first()
    if job:
        return _receipt('native_job', job, project_id, 'created_at')
    admission = ProjectAuthorityEvent.objects.filter(
        operation='development_input_admitted', outcome='completed', resource__input_sha256=input_sha256,
    ).order_by('recorded_at', 'pk').values('id', 'project_id', 'actor_snapshot', 'recorded_at').first()
    return _receipt('generic_input_admission', admission, project_id, 'recorded_at') if admission else None


def _receipt(kind, row, project_id, timestamp):
    if str(row['project_id']) != str(project_id):
        return {'kind': kind, 'visibility': 'outside_project'}
    return {'kind': kind, 'visibility': 'same_project', 'id': str(row['id']),
            'actor': row['actor_snapshot'], 'recorded_at': row[timestamp].isoformat()}
