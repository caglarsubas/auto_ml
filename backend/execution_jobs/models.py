"""Durable native requests and append-only receipts, never Celery result state."""

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class QueueLock(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)


class NativeJob(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    project = models.ForeignKey("access_control.Project", on_delete=models.PROTECT)
    dataset = models.ForeignKey("declaration.Declaration", on_delete=models.PROTECT)
    source_dataset = models.ForeignKey("declaration.Declaration", null=True, on_delete=models.PROTECT, related_name="scoring_jobs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_snapshot = models.JSONField()
    authority = models.JSONField()
    specification = models.JSONField()
    request_sha256 = models.CharField(max_length=64)
    state = models.CharField(max_length=24, default="queued")
    revision = models.PositiveIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    next_dispatch = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    result = models.JSONField(null=True)
    result_sha256 = models.CharField(max_length=64, blank=True)
    reason_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=["state", "next_dispatch"])]


class JobEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(NativeJob, on_delete=models.PROTECT, related_name="events")
    revision = models.PositiveIntegerField()
    event_type = models.CharField(max_length=32)
    actor_snapshot = models.JSONField(default=dict)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["revision"]
        constraints = [models.UniqueConstraint(fields=["job", "revision"], name="job_event_revision_unique")]
