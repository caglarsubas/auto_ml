from django.contrib import admin
from django.db import transaction
from django.utils import timezone

from access_control.authority import actor_snapshot, grant_snapshot
from access_control.models import MCPAccessEvent, MCPDatasetGrant


@admin.register(MCPDatasetGrant)
class MCPDatasetGrantAdmin(admin.ModelAdmin):
    list_display = ['actor', 'dataset', 'role', 'active', 'expires_at', 'updated_at']
    readonly_fields = ['revision', 'updated_at']

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            MCPAccessEvent.objects.create(actor=request.user, grant=obj,
                actor_snapshot=actor_snapshot(request.user), grant_snapshot=grant_snapshot(obj),
                file_id=obj.dataset_id, operation='grant_changed', tool_name='django_admin',
                authority_source='authenticated_admin', outcome='completed', finished_at=timezone.now())


@admin.register(MCPAccessEvent)
class MCPAccessEventAdmin(admin.ModelAdmin):
    list_display = ['started_at', 'actor', 'file_id', 'operation', 'outcome', 'reason_code']
    readonly_fields = [field.name for field in MCPAccessEvent._meta.fields]

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
