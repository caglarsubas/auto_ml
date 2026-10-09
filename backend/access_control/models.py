"""Local MCP authority. REST project roles remain a separate release requirement."""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class MCPDatasetGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    dataset = models.ForeignKey('declaration.Declaration', on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=[('read', 'Read'), ('prepare', 'Read and propose')])
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revision = models.UUIDField(default=uuid.uuid4, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor', 'dataset'], name='mcp_actor_dataset_unique')]

    def save(self, *args, **kwargs):
        self.revision = uuid.uuid4()
        self.updated_at = timezone.now()
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'revision', 'updated_at'}
        super().save(*args, **kwargs)


class MCPAccessEvent(models.Model):
    """Reserved before access; actor/grant snapshots survive deletion/revocation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    grant = models.ForeignKey(MCPDatasetGrant, null=True, on_delete=models.SET_NULL)
    actor_snapshot = models.JSONField(default=dict)
    grant_snapshot = models.JSONField(default=dict)
    authority_source = models.CharField(max_length=32, default='stdio_installation_actor')
    file_id = models.PositiveBigIntegerField(null=True)
    operation = models.CharField(max_length=32)
    tool_name = models.CharField(max_length=200)
    required_scope = models.CharField(max_length=100, blank=True)
    arguments_sha256 = models.CharField(max_length=64, blank=True)
    outcome = models.CharField(max_length=32, default='started')
    reason_code = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [models.Index(fields=['actor', 'file_id', 'started_at'], name='mcp_access_actor_file_idx')]
