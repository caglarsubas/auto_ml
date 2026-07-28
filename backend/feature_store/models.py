from django.db import models


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


class Project(models.Model):
    name = models.CharField(max_length=255)
    objective = models.TextField(blank=True, default='')
    decision_use_case = models.TextField(blank=True, default='')
    prediction_horizon = models.CharField(max_length=255, blank=True, default='')
    population = models.TextField(blank=True, default='')
    exclusions = models.TextField(blank=True, default='')
    target_contract = models.JSONField(default=default_target_contract, blank=True)
    success_criteria = models.JSONField(default=default_success_criteria, blank=True)
    assumptions = models.TextField(blank=True, default='')
    regulatory_notes = models.TextField(blank=True, default='')
    forbidden_features = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.name

    def to_business_understanding(self) -> dict:
        """Shape compatible with modeling.crisp_dm.empty_business_understanding()."""
        return {
            'objective': self.objective or '',
            'decision_use_case': self.decision_use_case or '',
            'prediction_horizon': self.prediction_horizon or '',
            'population': self.population or '',
            'exclusions': self.exclusions or '',
            'target_contract': dict(self.target_contract or default_target_contract()),
            'assumptions': self.assumptions or '',
            'regulatory_notes': self.regulatory_notes or '',
            'forbidden_features': list(self.forbidden_features or []),
            'success_criteria': dict(self.success_criteria or default_success_criteria()),
            'hard_block_modeling_without_criteria': False,
            'completed': bool(str(self.objective or '').strip()),
        }


class DataConnection(models.Model):
    ENGINE_POSTGRES = 'postgres'
    ENGINE_DUCKDB = 'duckdb'
    ENGINE_CHOICES = [
        (ENGINE_POSTGRES, 'PostgreSQL'),
        (ENGINE_DUCKDB, 'DuckDB (Parquet/CSV lakehouse)'),
    ]

    name = models.CharField(max_length=255)
    engine = models.CharField(max_length=32, choices=ENGINE_CHOICES)
    config = models.JSONField(default=dict, blank=True)
    secret_ref = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Environment variable name holding the password (Postgres). Never store raw secrets.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.engine})'


class FeatureCollection(models.Model):
    NORM_NORMALIZED = 'normalized'
    NORM_PARTIAL = 'partially_denormalized'
    NORM_DENORMALIZED = 'denormalized'
    NORMALIZATION_CHOICES = [
        (NORM_NORMALIZED, 'Normalized'),
        (NORM_PARTIAL, 'Partially denormalized'),
        (NORM_DENORMALIZED, 'Denormalized'),
    ]

    STATUS_DRAFT = 'draft'
    STATUS_PREVIEWED = 'previewed'
    STATUS_MATERIALIZED = 'materialized'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PREVIEWED, 'Previewed'),
        (STATUS_MATERIALIZED, 'Materialized'),
        (STATUS_FAILED, 'Failed'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='collections')
    connection = models.ForeignKey(
        DataConnection, on_delete=models.PROTECT, related_name='collections'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    sql_text = models.TextField(blank=True, default='')
    normalization_level = models.CharField(
        max_length=32, choices=NORMALIZATION_CHOICES, default=NORM_DENORMALIZED
    )
    grain = models.CharField(max_length=255, blank=True, default='')
    entity_keys = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    materialized_declaration = models.ForeignKey(
        'declaration.Declaration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feature_collections',
    )
    row_count = models.PositiveIntegerField(null=True, blank=True)
    column_schema = models.JSONField(default=list, blank=True)
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('project', 'name')

    def __str__(self):
        return f'{self.project.name} / {self.name}'


class FeatureDefinition(models.Model):
    collection = models.ForeignKey(
        FeatureCollection, on_delete=models.CASCADE, related_name='definitions'
    )
    column_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    level_of_measurement = models.CharField(max_length=64, blank=True, default='unknown')
    model_usage_yn = models.CharField(max_length=8, default='Yes')

    class Meta:
        unique_together = ('collection', 'column_name')
        ordering = ['column_name']

    def __str__(self):
        return f'{self.collection.name}.{self.column_name}'
