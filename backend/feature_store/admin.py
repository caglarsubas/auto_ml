from django.contrib import admin
from .models import Project, DataConnection, FeatureCollection, FeatureDefinition


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'objective', 'updated_at')
    search_fields = ('name', 'objective')


@admin.register(DataConnection)
class DataConnectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'engine', 'is_active', 'updated_at')
    list_filter = ('engine', 'is_active')
    search_fields = ('name',)


class FeatureDefinitionInline(admin.TabularInline):
    model = FeatureDefinition
    extra = 0


@admin.register(FeatureCollection)
class FeatureCollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'connection', 'status', 'normalization_level', 'updated_at')
    list_filter = ('status', 'normalization_level')
    search_fields = ('name', 'project__name')
    inlines = [FeatureDefinitionInline]


@admin.register(FeatureDefinition)
class FeatureDefinitionAdmin(admin.ModelAdmin):
    list_display = ('column_name', 'collection', 'level_of_measurement', 'model_usage_yn')
    search_fields = ('column_name', 'collection__name')
