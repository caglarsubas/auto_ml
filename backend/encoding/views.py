"""
Encoding step API views.

POST /api/encoding/analyze/  – identify categorical features & return encoding plan
POST /api/encoding/apply/    – apply encoding, save encoded file, return report
"""

from access_control import projects
from access_control.storage import invalid_reference, managed_path, positive_file_id

import errno
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from modeling.execution_artifacts import projection_lock
from modeling.sfs_evidence import _sync_directory

from .encoding_utils import analyze_categorical_features, apply_encoding

logger = logging.getLogger(__name__)


def _publish_encoding(request, file_id, frame, categorical_columns):
    version = uuid.uuid4().hex
    root = Path(settings.MEDIA_ROOT).resolve()
    versions = root / 'encoded_files'
    if versions.is_symlink():
        invalid_reference('The encoding output directory must be inside managed artifact storage.')
    destination = versions / version
    path = destination / f'encoded_{file_id}_{version}.csv'
    meta_path = path.with_suffix('.meta.json')
    managed_path(str(path), table=True)
    versions.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.staging-', dir=versions) as staging:
        staged = Path(staging)
        with (staged / path.name).open('x', encoding='utf-8', newline='') as stream:
            frame.to_csv(stream, index=False)
            stream.flush()
            os.fsync(stream.fileno())
        with (staged / meta_path.name).open('x', encoding='utf-8') as stream:
            json.dump({'categorical_columns': categorical_columns}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(staged)

        with projection_lock(file_id), transaction.atomic():
            if os.path.lexists(destination):
                raise FileExistsError('Encoding version already exists.')
            if projects.governed():
                from deployment.reviews import lock_authority

                lock_authority(request.user, file_id, 'developer')
                for scope in getattr(request._request, '_project_scopes', []):
                    projects.recheck(scope)
                projects.register_artifact(path, file_id=file_id)
                projects.register_artifact(meta_path, file_id=file_id)
            try:
                staged.rename(destination)
            except OSError as exc:
                if exc.errno in (errno.EEXIST, errno.ENOTEMPTY):
                    raise FileExistsError('Encoding version already exists.') from exc
                raise
            _sync_directory(versions)
    return path.relative_to(root).as_posix()


class EncodingAnalyzeView(APIView):
    """Return an encoding plan for all categorical features in the processed file."""

    def post(self, request):
        try:
            file_id = request.data.get('file_id')
            processed_file = request.data.get('processed_file')
            data_dict_raw = request.data.get('data_dictionary', [])
            excluded_variables = request.data.get('excluded_variables', [])

            if not processed_file:
                return Response({'error': 'processed_file is required'}, status=400)

            # Resolve path
            csv_path = managed_path(processed_file, table=True)
            if not os.path.exists(csv_path):
                return Response({'error': f'Processed file not found: {processed_file}'}, status=404)

            df = pd.read_csv(csv_path)

            # Parse data_dictionary (may arrive as JSON string)
            if isinstance(data_dict_raw, str):
                try:
                    data_dict_raw = json.loads(data_dict_raw)
                except Exception:
                    data_dict_raw = []

            data_dict = data_dict_raw if isinstance(data_dict_raw, list) else []

            plan = analyze_categorical_features(
                df,
                data_dict,
                target_col='Target',
                excluded_cols=excluded_variables,
            )

            return Response({
                'plan': plan,
                'total_features': len(df.columns),
                'categorical_count': len(plan),
                'numeric_count': len(df.columns) - len(plan) - 1,  # minus Target
            })

        except ValidationError:
            raise
        except Exception as exc:
            logger.exception('EncodingAnalyzeView error')
            return Response({'error': str(exc)}, status=500)


class EncodingApplyView(APIView):
    """Apply encoding based on the (possibly user-adjusted) plan."""

    def post(self, request):
        try:
            file_id = request.data.get('file_id')
            processed_file = request.data.get('processed_file')
            plan_raw = request.data.get('plan', [])
            use_native = request.data.get('use_native', True)

            if not processed_file:
                return Response({'error': 'processed_file is required'}, status=400)

            csv_path = managed_path(processed_file, table=True)
            if not os.path.exists(csv_path):
                return Response({'error': f'Processed file not found: {processed_file}'}, status=404)
            file_id = positive_file_id(file_id)

            df = pd.read_csv(csv_path)

            # Parse plan
            if isinstance(plan_raw, str):
                try:
                    plan_raw = json.loads(plan_raw)
                except Exception:
                    plan_raw = []
            plan = plan_raw if isinstance(plan_raw, list) else []

            # Apply encoding
            encoded_df, report = apply_encoding(df, plan, target_col='Target', use_native=use_native)

            # Save sidecar metadata so the modeling step knows which columns
            # are categorical (CSV serialization loses pd.Categorical dtype).
            cat_meta = [
                {
                    'feature': r.get('feature', ''),
                    'strategy': r.get('strategy_applied', ''),
                    'categories': (r.get('mapping') or {}).get('categories', []),
                }
                for r in report
            ]
            encoded_rel = _publish_encoding(request, file_id, encoded_df, cat_meta)

            # Build summary
            strategy_counts = {}
            for r in report:
                s = r.get('strategy_applied', 'unknown')
                strategy_counts[s] = strategy_counts.get(s, 0) + 1

            return Response({
                'encoded_file': encoded_rel,
                'report': report,
                'summary': {
                    'total_encoded': len(report),
                    'strategy_counts': strategy_counts,
                    'original_shape': list(df.shape),
                    'encoded_shape': list(encoded_df.shape),
                },
            })

        except FileExistsError:
            return Response({'error': 'A new file could not be published. Retry.',
                'error_code': 'file_publication_conflict'}, status=409)
        except ValidationError:
            raise
        except projects.ProjectDenied as exc:
            return Response({'error_code': exc.code}, status=403)
        except Exception as exc:
            logger.exception('EncodingApplyView error')
            return Response({'error': str(exc)}, status=500)
