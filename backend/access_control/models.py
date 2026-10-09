"""Attributable session, MCP and project authority records."""
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


class AssistantActionApproval(models.Model):
    """One expiring typed dispatch; not review, job or expert-code authority."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_snapshot = models.JSONField(default=dict)
    file_id = models.PositiveBigIntegerField()
    action_type = models.CharField(max_length=64)
    payload = models.JSONField()
    source = models.CharField(max_length=16, default='panel')
    parent_span_id = models.CharField(max_length=256, blank=True)
    context = models.JSONField()
    environment = models.JSONField()
    budget = models.JSONField()
    proposal_sha256 = models.CharField(max_length=64)
    state = models.CharField(max_length=24, default='prepared')
    result = models.JSONField(null=True)
    reason_code = models.CharField(max_length=64, blank=True)
    prepared_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    approved_at = models.DateTimeField(null=True)
    dispatched_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['-prepared_at']
        indexes = [models.Index(fields=['actor', 'file_id', 'prepared_at'], name='assistant_actor_file_idx')]


class SessionAuthority(models.Model):
    """Current browser authority; changing its revision invalidates prior sessions."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, primary_key=True, on_delete=models.CASCADE)
    revision = models.UUIDField(default=uuid.uuid4, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)


class LoginThrottleBucket(models.Model):
    """Shared admission counters, keyed by secret-key HMAC rather than raw inputs."""
    key = models.CharField(max_length=64, primary_key=True)
    window_started_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveIntegerField(default=0)
    blocked_attempts = models.PositiveBigIntegerField(default=0)
    denial_recorded = models.BooleanField(default=False)


class AuthenticationEvent(models.Model):
    """Credential/session/operator evidence; never passwords, cookies or raw IPs."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_snapshot = models.JSONField(default=dict)
    subject_snapshot = models.JSONField(default=dict)
    authority_source = models.CharField(max_length=32)
    event_type = models.CharField(max_length=32)
    outcome = models.CharField(max_length=24, default='pending')
    reason_code = models.CharField(max_length=64, blank=True)
    source_key = models.CharField(max_length=64, blank=True)
    principal_key = models.CharField(max_length=64, blank=True)
    session_revision = models.UUIDField(null=True)
    operator_label = models.CharField(max_length=100, blank=True)
    request_sha256 = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [models.Index(fields=['actor', 'started_at'], name='auth_event_actor_time_idx'),
                   models.Index(fields=['event_type', 'started_at'], name='auth_event_type_time_idx')]


class ProjectPolicy(models.Model):
    """Durable installation activation; no supported downgrade to legacy access."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    activated_at = models.DateTimeField(default=timezone.now)


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(default=timezone.now)


class ProjectMembership(models.Model):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name='memberships')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=[('developer', 'Developer'), ('reviewer', 'Reviewer'), ('admin', 'Project administrator')])
    active = models.BooleanField(default=True)
    revision = models.UUIDField(default=uuid.uuid4, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['project', 'actor'], name='project_actor_unique')]


    def save(self, *args, **kwargs):
        self.revision = uuid.uuid4()
        self.updated_at = timezone.now()
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'revision', 'updated_at'}
        super().save(*args, **kwargs)


class ProjectDataset(models.Model):
    dataset = models.OneToOneField('declaration.Declaration', on_delete=models.CASCADE, primary_key=True, related_name='project_binding')
    project = models.ForeignKey(Project, on_delete=models.PROTECT)
    revision = models.UUIDField(default=uuid.uuid4, editable=False)
    assigned_at = models.DateTimeField(default=timezone.now)


class ProjectPipeline(models.Model):
    pipeline = models.OneToOneField('modeling.PipelineRun', on_delete=models.CASCADE, primary_key=True, related_name='project_binding')
    project = models.ForeignKey(Project, on_delete=models.PROTECT)
    revision = models.UUIDField(default=uuid.uuid4, editable=False)
    assigned_at = models.DateTimeField(default=timezone.now)


class ProjectArtifact(models.Model):
    path_sha256 = models.CharField(max_length=64, primary_key=True)
    relative_path = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.PROTECT)
    dataset = models.ForeignKey('declaration.Declaration', on_delete=models.CASCADE, null=True)
    registered_at = models.DateTimeField(default=timezone.now)


class ProjectAuthorityEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, null=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    actor_snapshot = models.JSONField(default=dict)
    authority_source = models.CharField(max_length=40)
    operator_label = models.CharField(max_length=100, blank=True)
    operation = models.CharField(max_length=40)
    resource = models.JSONField(default=dict)
    outcome = models.CharField(max_length=24)
    reason_code = models.CharField(max_length=64, blank=True)
    request_sha256 = models.CharField(max_length=64, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)
