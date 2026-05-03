"""
Encoding step API views.

POST /api/encoding/analyze/  – identify categorical features & return encoding plan
POST /api/encoding/apply/    – apply encoding, save encoded file, return report
"""

import json
import logging
import os
from datetime import datetime

import pandas as pd
from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView

from .encoding_utils import analyze_categorical_features, apply_encoding

logger = logging.getLogger(__name__)


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
            csv_path = os.path.join(settings.MEDIA_ROOT, processed_file) if not os.path.isabs(processed_file) else processed_file
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

            csv_path = os.path.join(settings.MEDIA_ROOT, processed_file) if not os.path.isabs(processed_file) else processed_file
            if not os.path.exists(csv_path):
                return Response({'error': f'Processed file not found: {processed_file}'}, status=404)

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

            # Save encoded CSV
            ts = datetime.now().strftime('%Y%m%d%H%M%S')
            encoded_dir = os.path.join(settings.MEDIA_ROOT, 'encoded_files')
            os.makedirs(encoded_dir, exist_ok=True)
            encoded_filename = f'encoded_{file_id}_{ts}.csv'
            encoded_path = os.path.join(encoded_dir, encoded_filename)
            encoded_df.to_csv(encoded_path, index=False)
            encoded_rel = os.path.relpath(encoded_path, settings.MEDIA_ROOT)

            # Save sidecar metadata so the modeling step knows which columns
            # are categorical (CSV serialization loses pd.Categorical dtype).
            cat_meta = []
            for r in report:
                cat_meta.append({
                    'feature': r.get('feature', ''),
                    'strategy': r.get('strategy_applied', ''),
                    'categories': (r.get('mapping') or {}).get('categories', []),
                })
            meta_path = encoded_path.replace('.csv', '.meta.json')
            try:
                with open(meta_path, 'w', encoding='utf-8') as mf:
                    json.dump({'categorical_columns': cat_meta}, mf)
                logger.info('Saved encoding metadata to %s (%d categorical cols)', meta_path, len(cat_meta))
            except Exception as me:
                logger.warning('Failed to save encoding metadata: %s', me)

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

        except Exception as exc:
            logger.exception('EncodingApplyView error')
            return Response({'error': str(exc)}, status=500)
