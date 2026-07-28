import django.db.models.deletion
from django.db import migrations, models


def default_target_contract():
    return {
        'event_definition': '',
        'good_bad_window': '',
        'target_column': '',
    }


def default_success_criteria():
    return {
        'primary_metric': 'roc_auc',
        'direction': 'maximize',
        'floor': None,
        'cost_matrix': {'fn_cost': 1.0, 'fp_cost': 1.0},
    }


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('declaration', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataConnection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('engine', models.CharField(choices=[('postgres', 'PostgreSQL'), ('duckdb', 'DuckDB (Parquet/CSV lakehouse)')], max_length=32)),
                ('config', models.JSONField(blank=True, default=dict)),
                ('secret_ref', models.CharField(blank=True, default='', help_text='Environment variable name holding the password (Postgres). Never store raw secrets.', max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('objective', models.TextField(blank=True, default='')),
                ('decision_use_case', models.TextField(blank=True, default='')),
                ('prediction_horizon', models.CharField(blank=True, default='', max_length=255)),
                ('population', models.TextField(blank=True, default='')),
                ('exclusions', models.TextField(blank=True, default='')),
                ('target_contract', models.JSONField(blank=True, default=default_target_contract)),
                ('success_criteria', models.JSONField(blank=True, default=default_success_criteria)),
                ('assumptions', models.TextField(blank=True, default='')),
                ('regulatory_notes', models.TextField(blank=True, default='')),
                ('forbidden_features', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='FeatureCollection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('sql_text', models.TextField(blank=True, default='')),
                ('normalization_level', models.CharField(choices=[('normalized', 'Normalized'), ('partially_denormalized', 'Partially denormalized'), ('denormalized', 'Denormalized')], default='denormalized', max_length=32)),
                ('grain', models.CharField(blank=True, default='', max_length=255)),
                ('entity_keys', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('previewed', 'Previewed'), ('materialized', 'Materialized'), ('failed', 'Failed')], default='draft', max_length=32)),
                ('row_count', models.PositiveIntegerField(blank=True, null=True)),
                ('column_schema', models.JSONField(blank=True, default=list)),
                ('last_error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('connection', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='collections', to='feature_store.dataconnection')),
                ('materialized_declaration', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='feature_collections', to='declaration.declaration')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='collections', to='feature_store.project')),
            ],
            options={
                'ordering': ['-updated_at'],
                'unique_together': {('project', 'name')},
            },
        ),
        migrations.CreateModel(
            name='FeatureDefinition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('column_name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('level_of_measurement', models.CharField(blank=True, default='unknown', max_length=64)),
                ('model_usage_yn', models.CharField(default='Yes', max_length=8)),
                ('collection', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='definitions', to='feature_store.featurecollection')),
            ],
            options={
                'ordering': ['column_name'],
                'unique_together': {('collection', 'column_name')},
            },
        ),
    ]
