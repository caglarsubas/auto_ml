from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .materialize import (
    build_dictionary_payload,
    materialize_collection,
    sync_definitions_from_schema,
)
from .models import DataConnection, FeatureCollection, FeatureDefinition, Project
from .serializers import (
    DataConnectionSerializer,
    FeatureCollectionSerializer,
    FeatureDefinitionSerializer,
    ProjectSerializer,
)
from .sql_engine import (
    DEFAULT_PREVIEW_LIMIT,
    SqlExecutionError,
    SqlValidationError,
    execute_query,
    infer_column_schema,
    test_connection,
)


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer


class DataConnectionViewSet(viewsets.ModelViewSet):
    queryset = DataConnection.objects.all()
    serializer_class = DataConnectionSerializer

    @action(detail=True, methods=['post'], url_path='test')
    def test(self, request, pk=None):
        conn = self.get_object()
        try:
            result = test_connection(conn.engine, conn.config or {}, conn.secret_ref or '')
            return Response(result)
        except (SqlExecutionError, SqlValidationError) as exc:
            return Response(
                {'ok': False, 'message': str(exc), 'engine': conn.engine},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=['post'], url_path='test')
    def test_payload(self, request):
        """Test connection settings before save: {engine, config, secret_ref}."""
        engine = request.data.get('engine')
        config = request.data.get('config') or {}
        secret_ref = request.data.get('secret_ref') or ''
        try:
            result = test_connection(engine, config, secret_ref)
            return Response(result)
        except (SqlExecutionError, SqlValidationError) as exc:
            return Response(
                {'ok': False, 'message': str(exc), 'engine': engine},
                status=status.HTTP_400_BAD_REQUEST,
            )


class FeatureCollectionViewSet(viewsets.ModelViewSet):
    queryset = FeatureCollection.objects.select_related(
        'project', 'connection', 'materialized_declaration'
    ).prefetch_related('definitions')
    serializer_class = FeatureCollectionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=['post'], url_path='preview')
    def preview(self, request, pk=None):
        collection = self.get_object()
        # Allow ad-hoc SQL override from request body without saving
        sql = request.data.get('sql_text')
        if sql is not None:
            collection.sql_text = sql
            if request.data.get('save_sql'):
                collection.save(update_fields=['sql_text', 'updated_at'])

        limit = int(request.data.get('limit') or DEFAULT_PREVIEW_LIMIT)
        conn = collection.connection
        try:
            result = execute_query(
                conn.engine,
                conn.config or {},
                collection.sql_text,
                secret_ref=conn.secret_ref or '',
                limit=limit,
            )
        except (SqlValidationError, SqlExecutionError) as exc:
            collection.status = FeatureCollection.STATUS_FAILED
            collection.last_error = str(exc)
            collection.save(update_fields=['status', 'last_error', 'updated_at'])
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        collection.column_schema = infer_column_schema(result.columns, result.rows)
        collection.status = FeatureCollection.STATUS_PREVIEWED
        collection.last_error = ''
        collection.save(update_fields=['column_schema', 'status', 'last_error', 'updated_at'])
        sync_definitions_from_schema(collection, result.columns, preserve_existing=True)

        return Response({
            'columns': result.columns,
            'rows': result.rows,
            'row_count': result.row_count,
            'truncated': result.truncated,
            'column_schema': collection.column_schema,
            'status': collection.status,
            'definitions': FeatureDefinitionSerializer(
                collection.definitions.all(), many=True
            ).data,
        })

    @action(detail=True, methods=['post'], url_path='materialize')
    def materialize(self, request, pk=None):
        collection = self.get_object()
        sql = request.data.get('sql_text')
        if sql is not None:
            collection.sql_text = sql
            collection.save(update_fields=['sql_text', 'updated_at'])
        try:
            result = materialize_collection(collection)
        except (SqlValidationError, SqlExecutionError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        collection.refresh_from_db()
        payload = FeatureCollectionSerializer(collection).data
        payload['materialize'] = result
        payload['dictionary'] = build_dictionary_payload(collection)
        payload['business_understanding'] = collection.project.to_business_understanding()
        return Response(payload)

    @action(detail=True, methods=['post'], url_path='sync-definitions')
    def sync_definitions(self, request, pk=None):
        collection = self.get_object()
        columns = []
        if collection.column_schema:
            for col in collection.column_schema:
                if isinstance(col, dict) and col.get('name'):
                    columns.append(str(col['name']))
                else:
                    columns.append(str(col))
        if not columns:
            return Response(
                {'error': 'No column_schema available. Run preview or materialize first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sync_definitions_from_schema(collection, columns, preserve_existing=True)
        return Response({
            'definitions': FeatureDefinitionSerializer(
                collection.definitions.all(), many=True
            ).data,
        })

    @action(detail=True, methods=['get', 'put', 'patch'], url_path='definitions')
    def definitions(self, request, pk=None):
        collection = self.get_object()
        if request.method == 'GET':
            return Response(
                FeatureDefinitionSerializer(collection.definitions.all(), many=True).data
            )

        items = request.data if isinstance(request.data, list) else request.data.get('definitions')
        if not isinstance(items, list):
            return Response(
                {'error': 'Expected a list of definition objects.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated = []
        for item in items:
            col = item.get('column_name')
            if not col:
                continue
            obj, _ = FeatureDefinition.objects.get_or_create(
                collection=collection, column_name=col
            )
            if 'description' in item:
                obj.description = item.get('description') or ''
            if 'level_of_measurement' in item:
                obj.level_of_measurement = item.get('level_of_measurement') or 'unknown'
            if 'model_usage_yn' in item:
                obj.model_usage_yn = item.get('model_usage_yn') or 'Yes'
            obj.save()
            updated.append(obj)
        return Response(FeatureDefinitionSerializer(updated, many=True).data)

    @action(detail=True, methods=['get'], url_path='for-modeling')
    def for_modeling(self, request, pk=None):
        """Payload for Model Development intake from a materialized collection."""
        collection = self.get_object()
        if collection.status != FeatureCollection.STATUS_MATERIALIZED:
            return Response(
                {'error': 'Collection must be materialized before use in Model Development.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not collection.materialized_declaration_id:
            return Response(
                {'error': 'Materialized declaration missing.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'collection_id': collection.id,
            'collection_name': collection.name,
            'declaration_id': collection.materialized_declaration_id,
            'project_id': collection.project_id,
            'project_name': collection.project.name,
            'business_understanding': collection.project.to_business_understanding(),
            'dictionary': build_dictionary_payload(collection),
            'grain': collection.grain,
            'entity_keys': collection.entity_keys,
            'normalization_level': collection.normalization_level,
        })


class FeatureDefinitionViewSet(viewsets.ModelViewSet):
    queryset = FeatureDefinition.objects.select_related('collection')
    serializer_class = FeatureDefinitionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        collection_id = self.request.query_params.get('collection')
        if collection_id:
            qs = qs.filter(collection_id=collection_id)
        return qs

    def perform_create(self, serializer):
        collection_id = self.request.data.get('collection')
        serializer.save(collection_id=collection_id)
