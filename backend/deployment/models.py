from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class PackageReview(models.Model):
    """Discussion of one exact package; never model or production approval."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey('access_control.Project', on_delete=models.PROTECT)
    dataset = models.ForeignKey('declaration.Declaration', on_delete=models.PROTECT)
    bundle_id = models.UUIDField()
    execution_id = models.UUIDField()
    assessment_id = models.UUIDField()
    manifest_sha256 = models.CharField(max_length=64)
    context_sha256 = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['dataset', 'bundle_id'], name='review_dataset_bundle_unique')]


class PackageReviewEvent(models.Model):
    """Append-only API receipts with actor and authority snapshots."""
    id = models.UUIDField(primary_key=True, editable=False)
    review = models.ForeignKey(PackageReview, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_snapshot = models.JSONField()
    authority_snapshot = models.JSONField()
    request_sha256 = models.CharField(max_length=64)
    revision = models.PositiveIntegerField()
    event_type = models.CharField(max_length=24)
    finding_id = models.UUIDField(null=True)
    severity = models.CharField(max_length=16, blank=True)
    text = models.TextField(blank=True)
    evidence_job = models.ForeignKey('execution_jobs.NativeJob', null=True, on_delete=models.PROTECT)
    evidence = models.JSONField(null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['revision']
        constraints = [models.UniqueConstraint(fields=['review', 'revision'], name='review_event_revision_unique'),
                       models.CheckConstraint(condition=(models.Q(evidence_job__isnull=True, evidence__isnull=True)
                                                         | models.Q(evidence_job__isnull=False, evidence__isnull=False)),
                                              name='review_event_evidence_pair')]
