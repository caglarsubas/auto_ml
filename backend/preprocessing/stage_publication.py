"""Publish and verify self-contained preprocessing stage versions."""

import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction

from access_control import projects
from modeling.execution_artifacts import digest_file, projection_lock, replace_projection
from modeling.split_contract import SPLIT_VERSION, split_path
from preprocessing.purifier_contract import PURIFIER_VERSION, purifier_path
from preprocessing.replay import save_recipe


STAGE_DIRECTORY = Path('data_files/preprocessing')
SUFFIXES = {
    'raw': '.raw.csv', 'recipe': '.purifier.json', 'split': '.split.json',
    'purifier': '.purifier-fit.json', 'datq': '.datq.json', 'result': '.result.json',
    'receipt': '.stage.json',
}


class StageConflict(ValueError):
    pass


def stage_path(file_id, identifier):
    version = uuid.UUID(str(identifier)).hex
    return Path(settings.MEDIA_ROOT) / STAGE_DIRECTORY / str(int(file_id)) / version / f'processed_{int(file_id)}_{version}.csv'


def stage_paths(processed_path):
    path = Path(processed_path)
    return {'processed': path, **{name: path.with_suffix(suffix) for name, suffix in SUFFIXES.items()}}


def is_versioned_stage(processed_path):
    root = Path(settings.MEDIA_ROOT).resolve() / STAGE_DIRECTORY
    return Path(processed_path).resolve().is_relative_to(root)


def request_digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False,
                                     separators=(',', ':')).encode()).hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()


def result_path(file_id):
    return Path(settings.MEDIA_ROOT) / 'preprocessing_results' / f'{int(file_id)}_result.json'


def _read_json(path):
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


def _read_current(file_id):
    try:
        result = _read_json(result_path(file_id))
        if not isinstance(result, dict):
            raise ValueError('Expected a preprocessing result object.')
        return result
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise StageConflict('The current preprocessing result is unreadable.') from error


def read_result(file_id, processed_path=None):
    if processed_path is not None and is_versioned_stage(processed_path):
        return load_stage(processed_path, file_id)[1]
    result = _read_current(file_id)
    if result is None:
        return None
    saved = result.get('processed_file')
    if processed_path is not None and (not saved or relative(processed_path) != saved):
        return None
    if saved:
        selected = Path(settings.MEDIA_ROOT) / saved
        if is_versioned_stage(selected):
            return load_stage(selected, file_id)[1]
    return {**result, 'preprocessing_provenance': 'historical_unverified'}


def read_datq(file_id, processed_path=None):
    if processed_path is None:
        if saved := (_read_current(file_id) or {}).get('processed_file'):
            selected = Path(settings.MEDIA_ROOT) / saved
            if is_versioned_stage(selected):
                processed_path = selected
    if processed_path is not None:
        if is_versioned_stage(processed_path):
            load_stage(processed_path, file_id, include_result=False)
            return _read_json(stage_paths(processed_path)['datq'])
        result = read_result(file_id, processed_path)
        return (result or {}).get('datq_summary') or []
    legacy = Path(settings.MEDIA_ROOT) / 'data_quality' / f'{int(file_id)}_datq_summary.json'
    return _read_json(legacy) if legacy.exists() else []


def read_split(file_id, processed_path):
    if load_stage(processed_path, file_id, include_result=False) is not None:
        return _read_json(stage_paths(processed_path)['split'])
    return None


def _write_json(path, payload):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(payload, allow_nan=False, default=str, separators=(',', ':')))


def _file_record(path):
    return {'bytes': path.stat().st_size, 'sha256': digest_file(path)}


def load_stage(processed_path, file_id, *, include_result=True):
    """Verify a stage against its publication receipt, or recognize historical storage."""
    path = Path(processed_path).resolve()
    if not is_versioned_stage(path):
        return None
    version = path.parent.name
    if not re.fullmatch('[a-f0-9]{32}', version) or path != stage_path(file_id, version).resolve():
        raise StageConflict('Select a preprocessing version from the requested dataset.')
    paths = stage_paths(path)
    try:
        if paths['receipt'].is_symlink():
            raise StageConflict('Preprocessing publication identity is invalid.')
        receipt = _read_json(paths['receipt'])
        identity = (receipt['schema_version'], receipt['file_id'], receipt['version_id'], receipt['processed_file'])
        if identity != (1, int(file_id), version, relative(path)) or set(receipt['files']) != set(paths) - {'receipt'}:
            raise StageConflict('Preprocessing publication identity is invalid.')
        for name, member in paths.items():
            if name == 'receipt' or (name == 'result' and not include_result):
                continue
            if member.is_symlink() or _file_record(member) != receipt['files'][name]:
                raise StageConflict(f'Preprocessing artifact failed verification: {name}.')
        recipe, split = _read_json(paths['recipe']), _read_json(paths['split'])
        if (recipe['file_id'] != int(file_id) or split['file_id'] != int(file_id)
                or recipe['recipe_id'] != receipt['recipe_id']
                or any(recipe['outer_split'][key] != split[key]
                       for key in ('strategy', 'split_config', 'train_idx', 'test_idx'))
                or recipe['raw_input'] != {'path': relative(paths['raw']), 'sha256': receipt['files']['raw']['sha256']}
                or recipe['processed_input'] != {'path': relative(path), 'sha256': receipt['files']['processed']['sha256']}):
            raise StageConflict('Preprocessing recipe does not match the published inputs and split.')
        purifier = _read_json(paths['purifier'])
        if purifier['file_id'] != int(file_id) or purifier['path'] != relative(paths['purifier']):
            raise StageConflict('Purifier state does not match the published version.')
        result = _read_json(paths['result']) if include_result else None
        if result is not None and (result['processed_file'], result['preprocessing_version_id']) != (relative(path), version):
            raise StageConflict('Preprocessing result does not match the published version.')
        return receipt, result, purifier
    except StageConflict:
        raise
    except (KeyError, TypeError, OSError, ValueError) as error:
        raise StageConflict('Preprocessing version is unavailable or incomplete.') from error


def _projection_record(path):
    return digest_file(path) if path.exists() else None


def _register(request, paths, file_id):
    if projects.governed():
        from deployment.reviews import lock_authority

        lock_authority(request.user, file_id, 'developer')
        for scope in getattr(request._request, '_project_scopes', []):
            projects.recheck(scope)
        for path in paths.values():
            projects.register_artifact(path, file_id=file_id)


def _advance(paths, receipt, file_id):
    current = result_path(file_id)
    current_sha256 = _projection_record(current)
    if current_sha256 == receipt['previous_result_sha256']:
        replace_projection(paths['result'], current)
    elif current_sha256 != receipt['files']['result']['sha256']:
        # A newer publication owns the current view. Retrying an older request
        # can return its own result without adopting it over that newer stage.
        return
    # The canonical view resolves through the verified version. A retry can
    # restore compatibility files if their refresh was interrupted afterward.
    aliases = {'split': Path(split_path(file_id)), 'purifier': Path(purifier_path(file_id)),
               'datq': Path(settings.MEDIA_ROOT) / 'data_quality' / f'{file_id}_datq_summary.json'}
    for name, alias in aliases.items():
        if _projection_record(alias) != receipt['files'][name]['sha256']:
            replace_projection(paths[name], alias)


def _replay(request, path, file_id, request_sha256):
    receipt, result, _ = load_stage(path, file_id)
    if receipt['request_sha256'] != request_sha256:
        raise StageConflict('This preprocessing request ID is already bound to different inputs.')
    paths = stage_paths(path)
    with transaction.atomic():
        _register(request, paths, file_id)
    _advance(paths, receipt, file_id)
    return result


def replay_stage(request, path, file_id, request_sha256):
    if not path.parent.exists():
        return None
    with projection_lock(file_id):
        return _replay(request, path, file_id, request_sha256)


def publish_stage(request, path, file_id, request_sha256, source_sha256,
                  processed, eligible, recipe_inputs, split, purifier, result):
    """Expose a complete version, then advance the existing compatibility outputs."""
    path.parent.parent.mkdir(parents=True, exist_ok=True)
    paths = stage_paths(path)
    staging_root = Path(settings.MEDIA_ROOT) / '.preprocessing-staging'
    staging_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stage-', dir=staging_root) as staging:
        work = stage_paths(Path(staging) / path.name)
        processed.to_csv(work['processed'], index=False, mode='x')
        recipe = save_recipe(work['processed'], file_id, eligible, *recipe_inputs, published_path=path)
        split = {'version': SPLIT_VERSION, 'file_id': file_id, 'source': 'preprocessing', **split,
                 'n_train': len(split['train_idx']), 'n_test': len(split['test_idx']),
                 'frame_index': list(range(len(processed)))}
        purifier = {'version': PURIFIER_VERSION, 'file_id': file_id, 'path': relative(paths['purifier']), **purifier}
        result.update(processed_file=relative(path), preprocessing_version_id=path.parent.name,
                      preprocessing_provenance='verified_stage', purifier_recipe_id=recipe['recipe_id'],
                      split_artifact=relative(paths['split']), purifier_artifact=relative(paths['purifier']))
        for name, payload in [('split', split), ('purifier', purifier), ('datq', result.get('datq_summary') or []),
                              ('result', result)]:
            _write_json(work[name], payload)
        files = {name: _file_record(member) for name, member in work.items() if name != 'receipt'}
        with projection_lock(file_id):
            if path.parent.exists():
                return _replay(request, path, file_id, request_sha256)
            receipt = {'schema_version': 1, 'file_id': file_id, 'version_id': path.parent.name,
                       'processed_file': relative(path), 'recipe_id': recipe['recipe_id'], 'files': files,
                       'source_sha256': source_sha256, 'request_sha256': request_sha256,
                       'previous_result_sha256': _projection_record(result_path(file_id))}
            _write_json(work['receipt'], receipt)
            with transaction.atomic():
                _register(request, paths, file_id)
                os.rename(staging, path.parent)
            _advance(paths, receipt, file_id)
    return result
