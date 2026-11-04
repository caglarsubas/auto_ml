"""Versioned raw inputs and train-fitted, row-preserving purifier replay.

Row deduplication is an explicit pre-split population operation. It is never
reapplied to validation or scoring batches. Learned decisions use only fit rows.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pandas as pd
from django.conf import settings

from modeling.execution_artifacts import digest_file
from preprocessing.purifier_catalog import PURIFIER_OPTIONS

VERSION = 2


def validate_options(options):
    allowed = {item['id'] for item in PURIFIER_OPTIONS}
    if not isinstance(options, (list, set)) or any(type(value) is not int or value not in allowed for value in options):
        raise ValueError('Purifier options must be catalog identifiers from 1 through 34.')


def save_recipe(processed_path, file_id, eligible, options, dictionary, preserve, split, original_rows):
    validate_options(options)
    root = Path(settings.MEDIA_ROOT).resolve()
    processed = Path(processed_path).resolve()
    if not processed.is_relative_to(root):
        raise ValueError('Purifier outputs must be in managed artifact storage.')
    raw_path = processed.with_suffix('.raw.csv')
    with raw_path.open('x', encoding='utf-8', newline='') as stream:
        eligible.to_csv(stream, index=False)
    recipe = {'schema_version': VERSION, 'recipe_id': str(uuid.uuid4()), 'file_id': int(file_id),
              'options': sorted(options), 'data_dictionary': dictionary or [], 'preserve': sorted(preserve),
              'outer_split': split, 'eligible_source_rows': list(map(int, original_rows)),
              'population_operation': 'Exact row deduplication before partitioning' if 2 in options else 'No row filtering',
              'raw_input': {'path': str(raw_path.relative_to(root)), 'sha256': digest_file(raw_path)},
              'processed_input': {'path': str(processed.relative_to(root)), 'sha256': digest_file(processed)}}
    with processed.with_suffix('.purifier.json').open('x', encoding='utf-8') as stream:
        json.dump(recipe, stream, indent=2, allow_nan=False)
    return recipe


def load_recipe_input(processed_path, file_id):
    processed = Path(processed_path).resolve()
    sidecar = processed.with_suffix('.purifier.json')
    if not sidecar.is_file():
        if re.fullmatch(r'processed_\d+_[a-f0-9]{32}', processed.stem):
            raise ValueError('The raw-input purifier recipe is missing. Re-run preprocessing; legacy fallback is prohibited for this version.')
        return None, None
    with sidecar.open(encoding='utf-8') as stream:
        recipe = json.load(stream)
    root = Path(settings.MEDIA_ROOT).resolve()
    if recipe.get('schema_version') != VERSION or recipe.get('file_id') != int(file_id):
        raise ValueError('Purifier recipe version or dataset identity does not match.')
    validate_options(recipe.get('options'))
    expected = recipe.get('processed_input') or {}
    if str(processed.relative_to(root)) != expected.get('path') or digest_file(processed) != expected.get('sha256'):
        raise ValueError('Processed input failed purifier recipe integrity verification.')
    raw = recipe.get('raw_input') or {}
    path = (root / raw.get('path', '')).resolve()
    if not path.is_relative_to(root) or not path.is_file() or digest_file(path) != raw.get('sha256'):
        raise ValueError('Raw input failed purifier recipe integrity verification.')
    frame = pd.read_csv(path)
    split = recipe.get('outer_split') or {}
    train, test = pd.Index(split.get('train_idx', [])), pd.Index(split.get('test_idx', []))
    if not train.is_unique or not test.is_unique or len(train) < 5 or len(test) < 1 or not train.intersection(test).empty:
        raise ValueError('Purifier recipe has invalid outer partition membership.')
    if set(train).union(test) != set(frame.index) or len(recipe.get('eligible_source_rows', [])) != len(frame):
        raise ValueError('Purifier recipe membership does not cover the eligible raw input exactly.')
    return frame, recipe


def fit_purifier(frame, recipe, train, preserve=()):
    """Use the existing catalog engine on fit rows only, then freeze its state."""
    from preprocessing.views import PreprocessingRunView
    validate_options(recipe.get('options'))
    train = pd.Index(train)
    if not train.is_unique or len(train) < 2 or not train.isin(frame.index).all():
        raise ValueError('Purifier fit rows are missing, duplicated or insufficient.')
    view = PreprocessingRunView()
    options = set(recipe['options']) - {2}
    fitted, _, _, _ = view._apply_options(frame.loc[train], options,
        preserve=set(recipe.get('preserve') or []).union(preserve),
        data_dictionary=recipe.get('data_dictionary'), train_idx=train, collect_stats=False)
    if not fitted.index.equals(train):
        raise ValueError('Learned purifier replay must preserve fit-row alignment.')
    state = {**view._last_purifier_artifact, 'schema_version': VERSION,
             'recipe_id': recipe['recipe_id'], 'raw_input_sha256': recipe['raw_input']['sha256'],
             'fit_scope': 'training_partition', 'fit_rows': train.tolist(),
             'retained_columns': list(fitted.columns),
             'row_policy': 'preserve_all_input_rows', 'population_operation': recipe['population_operation']}
    # JSON round-trip is the same representation frozen into the scoring bundle.
    return json.loads(json.dumps(state, allow_nan=False))


def apply_purifier(frame, state):
    if state.get('schema_version') != VERSION or state.get('row_policy') != 'preserve_all_input_rows':
        raise ValueError('Unsupported fitted purifier state; row-preserving replay is required.')
    columns = state.get('retained_columns')
    if not isinstance(columns, list) or not columns or len(set(columns)) != len(columns):
        raise ValueError('Fitted purifier has no valid retained feature schema.')
    missing = [column for column in columns if column not in frame]
    if missing:
        raise ValueError(f'Missing required raw features: {missing}')
    work = frame.loc[:, columns].copy()
    for column, bounds in state.get('clip_bounds', {}).items():
        if column in work:
            try:
                work[column] = pd.to_numeric(work[column], errors='raise').clip(bounds['lo'], bounds['hi'])
            except (ValueError, TypeError) as error:
                raise ValueError(f'Raw feature {column!r} does not match the fitted numeric purifier schema.') from error
    for column, entries in state.get('category_replacements', {}).items():
        if column in work:
            mapping = {entry['from']: entry['to'] for entry in entries}
            if isinstance(work[column].dtype, pd.CategoricalDtype):
                work[column] = work[column].astype(object)
            work[column] = work[column].map(lambda value: mapping.get(value, value) if pd.notna(value) else value)
    if not work.index.equals(frame.index):
        raise ValueError('Purifier replay changed input row alignment.')
    return work


def subset_purifier(state, features, encoding_report):
    """Keep only raw dependencies of an adopted model's feature subset."""
    required = set(features)
    for report in encoding_report:
        outputs = (report.get('mapping') or {}).get('columns') or [report['feature']]
        if required.intersection(outputs):
            required.add(report['feature'])
    columns = [column for column in state['retained_columns'] if column in required]
    return {**state, 'retained_columns': columns,
            'clip_bounds': {key: value for key, value in state.get('clip_bounds', {}).items() if key in columns},
            'category_replacements': {key: value for key, value in state.get('category_replacements', {}).items() if key in columns}}
