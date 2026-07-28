from rest_framework import serializers
from .models import Project, DataConnection, FeatureCollection, FeatureDefinition


class ProjectSerializer(serializers.ModelSerializer):
    business_understanding = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'objective', 'decision_use_case', 'prediction_horizon',
            'population', 'exclusions', 'target_contract', 'success_criteria',
            'assumptions', 'regulatory_notes', 'forbidden_features',
            'business_understanding', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'business_understanding']

    def get_business_understanding(self, obj):
        return obj.to_business_understanding()


class DataConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataConnection
        fields = [
            'id', 'name', 'engine', 'config', 'secret_ref', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_engine(self, value):
        allowed = {DataConnection.ENGINE_POSTGRES, DataConnection.ENGINE_DUCKDB}
        if value not in allowed:
            raise serializers.ValidationError(f'engine must be one of {sorted(allowed)}')
        return value


class FeatureDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureDefinition
        fields = [
            'id', 'collection', 'column_name', 'description',
            'level_of_measurement', 'model_usage_yn',
        ]
        read_only_fields = ['collection']


class FeatureCollectionSerializer(serializers.ModelSerializer):
    definitions = FeatureDefinitionSerializer(many=True, read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    connection_name = serializers.CharField(source='connection.name', read_only=True)

    class Meta:
        model = FeatureCollection
        fields = [
            'id', 'project', 'project_name', 'connection', 'connection_name',
            'name', 'description', 'sql_text', 'normalization_level', 'grain',
            'entity_keys', 'status', 'materialized_declaration',
            'row_count', 'column_schema', 'last_error', 'definitions',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'status', 'materialized_declaration', 'row_count', 'column_schema',
            'last_error', 'created_at', 'updated_at', 'definitions',
            'project_name', 'connection_name',
        ]
