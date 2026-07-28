"""Unit tests for Feature Store SQL collections."""

import os

import pandas as pd
import pytest


@pytest.mark.unit
class TestSqlValidation:
    def test_rejects_empty(self):
        from feature_store.sql_engine import SqlValidationError, validate_readonly_select

        with pytest.raises(SqlValidationError):
            validate_readonly_select('')

    def test_rejects_drop(self):
        from feature_store.sql_engine import SqlValidationError, validate_readonly_select

        with pytest.raises(SqlValidationError):
            validate_readonly_select('DROP TABLE users')

    def test_rejects_insert(self):
        from feature_store.sql_engine import SqlValidationError, validate_readonly_select

        with pytest.raises(SqlValidationError):
            validate_readonly_select('INSERT INTO t VALUES (1)')

    def test_rejects_multi_statement(self):
        from feature_store.sql_engine import SqlValidationError, validate_readonly_select

        with pytest.raises(SqlValidationError):
            validate_readonly_select('SELECT 1; SELECT 2')

    def test_allows_select(self):
        from feature_store.sql_engine import validate_readonly_select

        assert validate_readonly_select('SELECT 1 AS x') == 'SELECT 1 AS x'

    def test_allows_with_cte(self):
        from feature_store.sql_engine import validate_readonly_select

        sql = 'WITH a AS (SELECT 1 AS x) SELECT * FROM a'
        assert validate_readonly_select(sql) == sql

    def test_strips_trailing_semicolon(self):
        from feature_store.sql_engine import validate_readonly_select

        assert validate_readonly_select('SELECT 1;') == 'SELECT 1'


@pytest.mark.unit
@pytest.mark.django_db
class TestFeatureStoreModels:
    def test_project_to_business_understanding(self):
        from feature_store.models import Project

        project = Project.objects.create(
            name='Credit Risk',
            objective='Predict default within 12 months',
            population='New applicants',
            target_contract={
                'event_definition': 'default',
                'good_bad_window': '12m',
                'target_column': 'Target',
            },
        )
        bu = project.to_business_understanding()
        assert bu['objective'] == 'Predict default within 12 months'
        assert bu['completed'] is True
        assert bu['target_contract']['target_column'] == 'Target'

    def test_collection_unique_per_project(self):
        from django.db import IntegrityError
        from feature_store.models import DataConnection, FeatureCollection, Project

        project = Project.objects.create(name='P1')
        conn = DataConnection.objects.create(
            name='lake',
            engine='duckdb',
            config={'base_path': '/tmp'},
        )
        FeatureCollection.objects.create(
            project=project, connection=conn, name='apps'
        )
        with pytest.raises(IntegrityError):
            FeatureCollection.objects.create(
                project=project, connection=conn, name='apps'
            )


@pytest.mark.unit
@pytest.mark.django_db
class TestDuckDBMaterialize:
    def _lake_setup(self, tmp_path, settings):
        from feature_store.models import DataConnection, FeatureCollection, Project

        settings.MEDIA_ROOT = str(tmp_path)
        os.makedirs(tmp_path / 'data_files', exist_ok=True)

        apps = pd.DataFrame({
            'application_id': [1, 2, 3],
            'customer_id': [10, 20, 30],
            'Target': [0, 1, 0],
        })
        cust = pd.DataFrame({
            'customer_id': [10, 20, 30],
            'income': [50000, 80000, 45000],
            'segment': ['A', 'B', 'A'],
        })
        lake = tmp_path / 'lake'
        lake.mkdir()
        apps.to_csv(lake / 'applications.csv', index=False)
        cust.to_csv(lake / 'customers.csv', index=False)

        project = Project.objects.create(
            name='Default Project',
            objective='Score applications',
        )
        conn = DataConnection.objects.create(
            name='Local Lake',
            engine='duckdb',
            config={'base_path': str(lake)},
        )
        sql = """
        SELECT a.application_id, a.Target, c.income, c.segment
        FROM read_csv_auto('applications.csv') a
        JOIN read_csv_auto('customers.csv') c
          ON a.customer_id = c.customer_id
        """
        collection = FeatureCollection.objects.create(
            project=project,
            connection=conn,
            name='app_features',
            sql_text=sql,
            normalization_level='denormalized',
            grain='application_id',
            entity_keys=['application_id'],
        )
        return project, conn, collection

    def test_duckdb_query_and_materialize(self, tmp_path, settings):
        pytest.importorskip('duckdb')
        from declaration.models import DataDictionary
        from feature_store.materialize import build_dictionary_payload, materialize_collection
        from feature_store.sql_engine import execute_query, test_connection

        project, conn, collection = self._lake_setup(tmp_path, settings)

        ping = test_connection(conn.engine, conn.config, conn.secret_ref)
        assert ping['ok'] is True

        preview = execute_query(
            conn.engine, conn.config, collection.sql_text, limit=10
        )
        assert 'application_id' in preview.columns
        assert preview.row_count == 3

        result = materialize_collection(collection)
        collection.refresh_from_db()
        assert collection.status == 'materialized'
        assert result['declaration_id'] == collection.materialized_declaration_id
        assert DataDictionary.objects.filter(
            data_file_id=result['declaration_id']
        ).count() >= 4

        dictionary = build_dictionary_payload(collection)
        assert any(d['Feature_Name'] == 'income' for d in dictionary)
        bu = project.to_business_understanding()
        assert bu['objective'] == 'Score applications'

    def test_rejects_destructive_sql_at_engine(self, tmp_path, settings):
        pytest.importorskip('duckdb')
        from feature_store.sql_engine import SqlValidationError, execute_query

        _, conn, _ = self._lake_setup(tmp_path, settings)
        with pytest.raises(SqlValidationError):
            execute_query(conn.engine, conn.config, 'DROP TABLE t')


@pytest.mark.unit
@pytest.mark.django_db
class TestFeatureStoreCRUD:
    def test_create_project_connection_collection(self, tmp_path):
        from feature_store.models import DataConnection, FeatureCollection, Project
        from feature_store.serializers import (
            DataConnectionSerializer,
            FeatureCollectionSerializer,
            ProjectSerializer,
        )

        ps = ProjectSerializer(data={'name': 'Proj', 'objective': 'Goal'})
        assert ps.is_valid(), ps.errors
        project = ps.save()
        assert project.to_business_understanding()['objective'] == 'Goal'

        cs = DataConnectionSerializer(data={
            'name': 'Duck',
            'engine': 'duckdb',
            'config': {'base_path': str(tmp_path)},
        })
        assert cs.is_valid(), cs.errors
        conn = cs.save()

        fcs = FeatureCollectionSerializer(data={
            'project': project.id,
            'connection': conn.id,
            'name': 'fc1',
            'sql_text': 'SELECT 1 AS x',
            'normalization_level': 'normalized',
        })
        assert fcs.is_valid(), fcs.errors
        collection = fcs.save()
        assert collection.status == 'draft'
        assert FeatureCollection.objects.filter(pk=collection.pk).exists()
        assert DataConnection.objects.filter(pk=conn.pk).exists()
