from django.db import models
from django.utils import timezone
import uuid


class PipelineRun(models.Model):
    """Persistent pipeline run with checkpoint state for resume capability."""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
    ]

    STEP_CHOICES = [
        ('declaration', 'Declaration'),
        ('preprocessing', 'Preprocessing'),
        ('data_quality', 'Data Quality'),
        ('modeling', 'Modeling'),
        ('sfs', 'SFS'),
        ('evaluation', 'Evaluation'),
        ('deployment', 'Deployment'),
    ]

    name = models.CharField(max_length=255)
    pipeline_type = models.CharField(max_length=50, default='boosting')
    file_id = models.IntegerField(null=True, blank=True)
    current_step = models.CharField(max_length=50, choices=STEP_CHOICES, default='declaration')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.pipeline_type}) - {self.current_step} [{self.status}]"


class HoldoutAccess(models.Model):
    """An access receipt, including failed assessments, never a review approval."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution_id = models.UUIDField(null=True)
    file_id = models.IntegerField()
    dataset_sha256 = models.CharField(max_length=64, blank=True)
    parameters = models.JSONField(default=dict)
    actor = models.ForeignKey('auth.User', null=True, on_delete=models.SET_NULL)
    accessed_at = models.DateTimeField(default=timezone.now)
    evidence_status = models.CharField(max_length=24, default='exploratory')

    class Meta:
        ordering = ['accessed_at']
        indexes = [models.Index(fields=['file_id', 'dataset_sha256'], name='holdout_dataset_idx')]
