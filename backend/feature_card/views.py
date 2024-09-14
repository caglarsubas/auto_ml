from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializers import FeatureCardSerializer
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats
import logging
import os
from django.conf import settings
from data_collection.models import DataFile
from django.http import JsonResponse
from django.db.models import F
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
    @action(detail=True, methods=['get'])
    def get_feature_info(self, request, pk=None):
        file_id = pk
        column_name = request.query_params.get('column', None)
        
        logger.info(f"Received request for file_id: {file_id}, column: {column_name}")

        if not column_name:
            logger.error("Column name is missing in the request")
            return Response({"error": "Column name is required"}, status=400)

        try:
            data_file = DataFile.objects.get(id=file_id)
        except DataFile.DoesNotExist:
            logger.error(f"DataFile with id {file_id} not found")
            return Response({"error": f"File not found for ID: {file_id}"}, status=404)

        # Assuming your files are stored in a 'data_files' directory in your project
        file_path = os.path.join(settings.MEDIA_ROOT, 'data_files', data_file.original_name)
        logger.info(f"Attempting to access file at: {os.path.abspath(file_path)}")

        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return Response({"error": f"File not found for ID: {file_id}"}, status=404)

        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            logger.error(f"Error reading file: {str(e)}")
            return Response({"error": f"Error reading file: {str(e)}"}, status=500)

        if column_name not in df.columns:
            logger.error(f"Column '{column_name}' not found in the dataset")
            return Response({"error": f"Column '{column_name}' not found in the dataset"}, status=404)

        column_data = df[column_name]
        
        # Determine the level of measurement
        level_of_measurement = self.determine_level_of_measurement(column_data)
        try:
            # Calculate descriptive statistics
            stats = self.calculate_descriptive_stats(column_data, level_of_measurement)
            
            feature_data = {
                "Feature_Name": column_name,
                "Feature_Description": "",  # You might want to store and retrieve this separately
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
                'Mean': self.safe_float(non_nan_data.mean()),
                'Min': self.safe_float(non_nan_data.min()),
                '1st_Quantile': self.safe_float(non_nan_data.quantile(0.01)),
                '5th_Quantile': self.safe_float(non_nan_data.quantile(0.05)),
                '25th_Q1': self.safe_float(non_nan_data.quantile(0.25)),
                '50th_Median': self.safe_float(non_nan_data.median()),
                '75th_Q3': self.safe_float(non_nan_data.quantile(0.75)),
                '95th_Quantile': self.safe_float(non_nan_data.quantile(0.95)),
                '99th_Quantile': self.safe_float(non_nan_data.quantile(0.99)),
                'Max': self.safe_float(non_nan_data.max()),
                'Std': self.safe_float(non_nan_data.std()),
                'Skewness': self.safe_float(scipy_stats.skew(non_nan_data)) if len(non_nan_data) > 0 else None,
                'Kurtosis': self.safe_float(scipy_stats.kurtosis(non_nan_data)) if len(non_nan_data) > 0 else None,
                'histogram_data': [self.safe_float(x) for x in non_nan_data.tolist() if self.safe_float(x) is not None]
            }
        else:
            value_counts = column_data.value_counts(dropna=False)
            total_count = len(column_data)
            stats = {
                '#_of_Categories': int(len(value_counts)),
                'Mode_Value': str(value_counts.index[0]) if len(value_counts) > 0 else None,
                'Mode_Ratio': self.safe_float((value_counts.iloc[0] / total_count) * 100) if len(value_counts) > 0 else None,
                'Missing_Ratio': self.safe_float((column_data.isnull().sum() / total_count) * 100),
                '#_of_Outlier_Categories': int(sum((value_counts / total_count) < 0.005)),
                'value_counts': {str(k): int(v) for k, v in value_counts.items()}
            }
        return stats

    def json_default(value):
        if isinstance(value, (np.integer, np.floating)):
            return float(value) if not np.isnan(value) else None
        elif isinstance(value, np.ndarray):
            return [json_default(v) for v in value]
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
            data_file = DataFile.objects.get(id=file_id)
            file_path = data_file.file.path
            df = pd.read_csv(file_path)
            
            target_column = 'Target'
            
            if column_name not in df.columns:
                return Response({"error": f"Column '{column_name}' not found in the dataset"}, status=404)
            if target_column not in df.columns:
                return Response({"error": "Target column not found in the dataset"}, status=404)
            
            feature_data = df[column_name]
            target_data = df[target_column]
            
            stacked_data = {}
            for target_class in target_data.unique():
                if pd.api.types.is_numeric_dtype(feature_data):
                    class_data = feature_data[target_data == target_class].tolist()
                    stacked_data[str(target_class)] = [x if not pd.isna(x) else None for x in class_data]
                else:
                    # For object (categorical) type, include NaN as a category
                    class_data = feature_data[target_data == target_class].fillna('NaN')
                    value_counts = feature_data[target_data == target_class].value_counts()
                    stacked_data[str(target_class)] = value_counts.to_dict()

            json_data = json.dumps(stacked_data, default=self.json_default)
            return JsonResponse(json.loads(json_data), safe=False)

        except Exception as e:
            logger.error(f"Error in get_stacked_feature_data: {str(e)}", exc_info=True)
            return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)