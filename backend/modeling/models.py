from django.db import models
from django.utils import timezone


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
