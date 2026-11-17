from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class PackageReview(models.Model):
    """Independent review of one exact assessment or historical package."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey('access_control.Project', on_delete=models.PROTECT)
    dataset = models.ForeignKey('declaration.Declaration', on_delete=models.PROTECT)
    bundle_id = models.UUIDField(null=True)
    execution_id = models.UUIDField(null=True)
    assessment_id = models.UUIDField(null=True)
    native_assessment = models.ForeignKey('execution_jobs.NativeJob', null=True, on_delete=models.PROTECT)
    assessment_result_sha256 = models.CharField(max_length=64, blank=True, default='')
    manifest_sha256 = models.CharField(max_length=64)
    context_sha256 = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['dataset', 'bundle_id'], name='review_dataset_bundle_unique'),
            models.UniqueConstraint(fields=['native_assessment'], name='review_native_assessment_unique'),
            models.CheckConstraint(condition=(
                models.Q(native_assessment__isnull=True, bundle_id__isnull=False, execution_id__isnull=False,
                         assessment_id__isnull=False, assessment_result_sha256='')
                | (models.Q(native_assessment__isnull=False, bundle_id__isnull=True, execution_id__isnull=True,
                            assessment_id__isnull=True) & ~models.Q(assessment_result_sha256=''))
            ), name='review_subject_present'),
        ]


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
    details = models.JSONField(null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['revision']
        constraints = [models.UniqueConstraint(fields=['review', 'revision'], name='review_event_revision_unique'),
                       models.CheckConstraint(condition=(models.Q(evidence_job__isnull=True, evidence__isnull=True)
                                                         | models.Q(evidence_job__isnull=False, evidence__isnull=False)),
                                              name='review_event_evidence_pair')]
