"""Materialize a FeatureCollection SQL result into a Declaration + DataDictionary."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from declaration.models import Declaration, DataDictionary

from .models import FeatureCollection, FeatureDefinition
from .sql_engine import (
    DEFAULT_MATERIALIZE_MAX_ROWS,
    SqlExecutionError,
    SqlValidationError,
    execute_to_dataframe,
    infer_column_schema,
)


def sync_definitions_from_schema(
    collection: FeatureCollection,
    columns: List[str],
    *,
    preserve_existing: bool = True,
) -> List[FeatureDefinition]:
    """Ensure FeatureDefinition rows exist for each column; drop obsolete if not preserving extras."""
    existing = {
        d.column_name: d
        for d in FeatureDefinition.objects.filter(collection=collection)
    }
    result = []
    for col in columns:
        name = str(col)
        if name in existing:
            result.append(existing[name])
            continue
        result.append(
            FeatureDefinition.objects.create(
                collection=collection,
                column_name=name,
                description='',
                level_of_measurement='unknown',
                model_usage_yn='Yes',
            )
        )
    if not preserve_existing:
        keep = set(columns)
        FeatureDefinition.objects.filter(collection=collection).exclude(
            column_name__in=keep
        ).delete()
    return result


def seed_data_dictionary(declaration: Declaration, collection: FeatureCollection) -> None:
    """Replace DataDictionary rows for the declaration from FeatureDefinitions."""
    DataDictionary.objects.filter(data_file=declaration).delete()
    defs = list(FeatureDefinition.objects.filter(collection=collection))
    if not defs and collection.column_schema:
        for col in collection.column_schema:
            name = col.get('name') if isinstance(col, dict) else str(col)
            if name:
                DataDictionary.objects.create(
                    data_file=declaration,
                    column_name=name,
                    description='',
                )
        return
    for d in defs:
        DataDictionary.objects.create(
            data_file=declaration,
            column_name=d.column_name,
            description=d.description or '',
        )


def materialize_collection(
    collection: FeatureCollection,
    *,
    max_rows: int = DEFAULT_MATERIALIZE_MAX_ROWS,
) -> Dict[str, Any]:
    """Run collection SQL, write CSV under MEDIA_ROOT, attach Declaration."""
    conn = collection.connection
    if not conn.is_active:
        raise SqlExecutionError('Data connection is inactive.')

    try:
        df, truncated = execute_to_dataframe(
            conn.engine,
            conn.config or {},
            collection.sql_text,
            secret_ref=conn.secret_ref or '',
            max_rows=max_rows,
        )
    except (SqlValidationError, SqlExecutionError) as exc:
        collection.status = FeatureCollection.STATUS_FAILED
        collection.last_error = str(exc)
        collection.save(update_fields=['status', 'last_error', 'updated_at'])
        raise

    if df is None or df.empty:
        collection.status = FeatureCollection.STATUS_FAILED
        collection.last_error = 'Query returned no rows.'
        collection.save(update_fields=['status', 'last_error', 'updated_at'])
        raise SqlExecutionError('Query returned no rows.')

    columns = [str(c) for c in df.columns.tolist()]
    sample = df.head(5).where(df.head(5).notna(), None).to_dict(orient='records')
    # Normalize sample values for schema inference
    sample_rows = []
    for rec in sample:
        sample_rows.append({str(k): v for k, v in rec.items()})

    ts = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f'fc_{collection.id}_{ts}.csv'
    data_files_dir = os.path.join(settings.MEDIA_ROOT, 'data_files')
    os.makedirs(data_files_dir, exist_ok=True)
    csv_bytes = df.to_csv(index=False).encode('utf-8')

    with transaction.atomic():
        sync_definitions_from_schema(collection, columns, preserve_existing=True)

        if collection.materialized_declaration_id:
            declaration = collection.materialized_declaration
            # Replace file content
            if declaration.file:
                try:
                    declaration.file.delete(save=False)
                except Exception:
                    pass
            declaration.file.save(filename, ContentFile(csv_bytes), save=False)
            declaration.name = collection.name
            declaration.original_name = filename
            declaration.has_header = True
            declaration.save()
        else:
            declaration = Declaration(
                name=collection.name,
                original_name=filename,
                has_header=True,
            )
            declaration.file.save(filename, ContentFile(csv_bytes), save=False)
            declaration.save()

        collection.materialized_declaration = declaration
        collection.row_count = int(len(df))
        collection.column_schema = infer_column_schema(columns, sample_rows)
        collection.status = FeatureCollection.STATUS_MATERIALIZED
        collection.last_error = (
            f'Result truncated to {max_rows} rows.' if truncated else ''
        )
        collection.save()
        seed_data_dictionary(declaration, collection)

    return {
        'collection_id': collection.id,
        'declaration_id': declaration.id,
        'row_count': collection.row_count,
        'columns': columns,
        'truncated': truncated,
        'status': collection.status,
    }


def build_dictionary_payload(collection: FeatureCollection) -> List[Dict[str, Any]]:
    """Frontend-shaped dictionary rows for Model Development."""
    rows = []
    for d in FeatureDefinition.objects.filter(collection=collection).order_by('column_name'):
        rows.append({
            'Feature_Name': d.column_name,
            'Feature_Description': d.description or '',
            'Level_of_Measurement': d.level_of_measurement or 'unknown',
            'Model_Usage_YN': d.model_usage_yn or 'Yes',
        })
    return rows
