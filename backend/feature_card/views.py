from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializers import FeatureCardSerializer
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats
import logging
import os
from django.conf import settings
from declaration.models import Declaration, DataDictionary  # Make sure to import DataDictionary if you haven't
from django.http import JsonResponse
from django.db import models
import json
import math
logger = logging.getLogger(__name__)

        
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, np.ndarray):
            return [self.default(x) for x in obj.tolist()]
        if pd.isna(obj):
            return None
        return super(NumpyEncoder, self).default(obj)
    
class FeatureCardViewSet(viewsets.ViewSet):
    def _resolve_file_path(self, request, file_id):
        """Resolve the file path, respecting optional file_override query param."""
        file_override = request.query_params.get('file_override', None)
        if file_override:
            override_path = os.path.join(settings.MEDIA_ROOT, file_override) if not os.path.isabs(file_override) else file_override
            if os.path.exists(override_path):
                logger.info(f"Using file override: {override_path}")
                return override_path, None
            else:
                return None, Response({"error": f"Override file not found: {file_override}"}, status=status.HTTP_404_NOT_FOUND)

        try:
            data_file = Declaration.objects.get(id=file_id)
        except Declaration.DoesNotExist:
            return None, Response({"error": f"File not found for ID: {file_id}"}, status=status.HTTP_404_NOT_FOUND)

        file_path = data_file.get_file_path()
        if not file_path:
            return None, Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        if not os.path.exists(file_path):
            data_files_dir = os.path.join(settings.MEDIA_ROOT, 'data_files')
            for filename in os.listdir(data_files_dir):
                if filename.startswith('processed_') and filename.endswith(data_file.original_name):
                    file_path = os.path.join(data_files_dir, filename)
                    data_file.file.name = os.path.join('data_files', filename)
                    data_file.save()
                    break
            else:
                return None, Response({"error": "Processed file not found"}, status=status.HTTP_404_NOT_FOUND)

        return file_path, None

    @action(detail=True, methods=['get'])
    def get_feature_info(self, request, pk=None):
        file_id = pk
        column_name = request.query_params.get('column', None)
        
        logger.info(f"Received request for file_id: {file_id}, column: {column_name}")

        if not column_name:
            logger.error("Column name is missing in the request")
            return Response({"error": "Column name is required"}, status=status.HTTP_400_BAD_REQUEST)

        file_path, err_resp = self._resolve_file_path(request, file_id)
        if err_resp:
            return err_resp
        logger.info(f"Resolved file path: {file_path}")

        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            logger.error(f"Error reading file: {str(e)}")
            return Response({"error": f"Error reading file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if column_name not in df.columns:
            logger.error(f"Column '{column_name}' not found in the dataset")
            return Response({"error": f"Column '{column_name}' not found in the dataset"}, status=status.HTTP_404_NOT_FOUND)

        column_data = df[column_name]
        
        # Determine the level of measurement
        level_of_measurement = self.determine_level_of_measurement(column_data)
        try:
            # Calculate descriptive statistics
            stats = self.calculate_descriptive_stats(column_data, level_of_measurement)

            # Get the description from DataDictionary
            try:
                data_dict = DataDictionary.objects.get(data_file_id=file_id, column_name=column_name)
                feature_description = data_dict.description
            except DataDictionary.DoesNotExist:
                feature_description = None

            feature_data = {
                "Feature_Name": column_name,
                "Feature_Description": feature_description if feature_description else "No description available.",
                "Level_of_Measurement": level_of_measurement,
                "Descriptive_Stats": stats,
            }
            #serializer = FeatureCardSerializer(feature_data)
            #return Response(serializer.data)  # Replace with actual data
            # Use custom JSON encoder
            try:
                try:
                    # Use standard JSON encoder
                    json_data = json.dumps(feature_data)
                    return Response(json.loads(json_data))
                except:
                    json_data = json.dumps(feature_data, cls=NumpyEncoder)
                    return Response(json.loads(json_data))
            except ValueError as ve:
                logger.error(f"JSON encoding error: {str(ve)}")
                # If JSON encoding fails, try to remove problematic values
                if "histogram_data" in feature_data["Descriptive_Stats"]:
                    feature_data["Descriptive_Stats"]["histogram_data"] = [
                        x for x in feature_data["Descriptive_Stats"]["histogram_data"] 
                        if x is not None
                    ]
                # Try encoding again
                try:
                    try:
                        # Use standard JSON encoder
                        json_data = json.dumps(feature_data)
                        return Response(json.loads(json_data))
                    except:
                        json_data = json.dumps(feature_data, cls=NumpyEncoder)
                        return Response(json.loads(json_data))
                except ValueError:
                    # If it still fails, return an error response
                    return Response({"error": "Unable to serialize data"}, status=500)
        except Exception as e:
            logger.error(f"Error in get_feature_info: {str(e)}", exc_info=True)
            return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)
    
    def determine_level_of_measurement(self, column_data):
        if pd.api.types.is_numeric_dtype(column_data):
            if column_data.nunique() > 10:  # arbitrary threshold
                return 'continuous'
            else:
                return 'cardinal'
        else:
            return 'nominal'  # or 'ordinal' if you can determine it's ordered

    @staticmethod
    def safe_float(value):
        if pd.isna(value) or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
            return None
        try:
            float_value = float(value)
            return float_value if math.isfinite(float_value) else None
        except (ValueError, TypeError):
            return None

    def calculate_descriptive_stats(self, column_data, level_of_measurement):
        if level_of_measurement in ['continuous', 'cardinal']:
            numeric_data = pd.to_numeric(column_data, errors='coerce')
            non_nan_data = numeric_data.dropna()
            
            stats = {
                'Mean': round(self.safe_float(non_nan_data.mean()), 2),
                'Min': round(self.safe_float(non_nan_data.min()), 2),
                '1st_Quantile': round(self.safe_float(non_nan_data.quantile(0.01)), 2),
                '5th_Quantile': round(self.safe_float(non_nan_data.quantile(0.05)), 2),
                '25th_Q1': round(self.safe_float(non_nan_data.quantile(0.25)), 2),
                '50th_Median': round(self.safe_float(non_nan_data.median()), 2),
                '75th_Q3': round(self.safe_float(non_nan_data.quantile(0.75)), 2),
                '95th_Quantile': round(self.safe_float(non_nan_data.quantile(0.95)), 2),
                '99th_Quantile': round(self.safe_float(non_nan_data.quantile(0.99)), 2),
                'Max': round(self.safe_float(non_nan_data.max()), 2),
                'Std': round(self.safe_float(non_nan_data.std()), 2),
                'Skewness': round((self.safe_float(scipy_stats.skew(non_nan_data)) if len(non_nan_data) > 0 else None), 2),
                'Kurtosis': round((self.safe_float(scipy_stats.kurtosis(non_nan_data)) if len(non_nan_data) > 0 else None), 2),
                'histogram_data': [self.safe_float(x) for x in non_nan_data.tolist() if self.safe_float(x) is not None]
            }
        else:
            value_counts = column_data.value_counts(dropna=False)
            total_count = len(column_data)
            stats = {
                '#_of_Categories': int(len(value_counts)),
                'Mode_Value': str(value_counts.index[0]) if len(value_counts) > 0 else None,
                'Mode_Ratio': round((self.safe_float((value_counts.iloc[0] / total_count) * 100) if len(value_counts) > 0 else None), 2),
                'Missing_Ratio': round(self.safe_float((column_data.isnull().sum() / total_count) * 100), 2),
                '#_of_Outlier_Categories': int(sum((value_counts / total_count) < 0.005)),
                'value_counts': {str(k): int(v) for k, v in value_counts.items()}
            }
        return stats

    def json_default(value):
        if isinstance(value, (np.integer, np.floating)):
            return float(value) if not np.isnan(value) else None
        elif isinstance(value, np.ndarray):
            return [json_default(v) for v in value]  # noqa: F821 - known latent bug (method lacks self); only reachable for ndarray payloads, tracked separately
        elif pd.isna(value):
            return None
        raise TypeError(f"Unserializable value: {value}")

    @action(detail=True, methods=['get'])
    def get_stacked_feature_data(self, request, pk=None):
        file_id = pk
        column_name = request.query_params.get('column', None)
        
        if not column_name:
            return Response({"error": "Column name is required"}, status=400)

        try:
            file_path, err_resp = self._resolve_file_path(request, file_id)
            if err_resp:
                return err_resp
            df = pd.read_csv(file_path)
            
            target_column = 'Target'
            
            if column_name not in df.columns:
                return Response({"error": f"Column '{column_name}' not found in the dataset"}, status=404)
            if target_column not in df.columns:
                return Response({"error": "Target column not found in the dataset"}, status=404)
            
            feature_data = df[column_name]
            target_data = df[target_column]
            
            stacked_data = {}
            feat_nunique = feature_data.nunique(dropna=False)
            # Low-cardinality numeric features (e.g. encoded categoricals) get
            # value_counts format so the frontend renders grouped bar charts.
            use_value_counts = (not pd.api.types.is_numeric_dtype(feature_data)) or feat_nunique <= 20
            for target_class in target_data.unique():
                if use_value_counts:
                    class_data = feature_data[target_data == target_class].fillna('NaN')
                    value_counts = class_data.value_counts(dropna=False)
                    stacked_data[str(target_class)] = {str(k): int(v) for k, v in value_counts.items()}
                else:
                    class_data = feature_data[target_data == target_class].tolist()
                    stacked_data[str(target_class)] = [x if not pd.isna(x) else None for x in class_data]

            # Compute target averages per category (for features with <= 20 unique values)
            nunique = feature_data.nunique(dropna=False)
            target_averages = None
            if nunique <= 20:
                filled = feature_data.fillna('__NULL__')
                grouped = df.assign(__feat__=filled).groupby('__feat__')[target_column]
                ta_mean = grouped.mean()
                ta_count = grouped.count()
                total = len(df)
                target_averages = []
                for cat in ta_mean.index:
                    cnt = int(ta_count.get(cat, 0))
                    target_averages.append({
                        'category': str(cat) if str(cat) != '__NULL__' else '(null)',
                        'count': cnt,
                        'volume_share': round(cnt / total * 100, 2) if total > 0 else 0,
                        'target_average': round(float(ta_mean.get(cat, 0)), 6),
                    })
                # Sort by target_average descending
                target_averages.sort(key=lambda x: x['target_average'], reverse=True)

            response_payload = {
                'stacked_data': stacked_data,
                'target_averages': target_averages,
            }
            json_data = json.dumps(response_payload, default=self.json_default)
            return JsonResponse(json.loads(json_data), safe=False)

        except Exception as e:
            logger.error(f"Error in get_stacked_feature_data: {str(e)}", exc_info=True)
            return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)