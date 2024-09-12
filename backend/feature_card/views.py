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

logger = logging.getLogger(__name__)
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

        # Calculate descriptive statistics
        stats = self.calculate_descriptive_stats(column_data, level_of_measurement)

        feature_data = {
            "Feature_Name": column_name,
            "Feature_Description": "",  # You might want to store and retrieve this separately
            "Level_of_Measurement": level_of_measurement,
            "Descriptive_Stats": stats
        }

        serializer = FeatureCardSerializer(feature_data)
        return Response(serializer.data)  # Replace with actual data

    def determine_level_of_measurement(self, column_data):
        if pd.api.types.is_numeric_dtype(column_data):
            if column_data.nunique() > 10:  # arbitrary threshold
                return 'continuous'
            else:
                return 'cardinal'
        else:
            return 'nominal'  # or 'ordinal' if you can determine it's ordered

    def calculate_descriptive_stats(self, column_data, level_of_measurement):
        if level_of_measurement in ['continuous', 'cardinal']:
            numeric_data = pd.to_numeric(column_data, errors='coerce')
            stats = {
                'Mean': round(numeric_data.mean(), 2),
                'Min': round(numeric_data.min(), 2),
                '1st_Quantile': round(numeric_data.quantile(0.01), 2),
                '5th_Quantile': round(numeric_data.quantile(0.05), 2),
                '25th_Q1': round(numeric_data.quantile(0.25), 2),
                '50th_Median': round(numeric_data.median(), 2),
                '75th_Q3': round(numeric_data.quantile(0.75), 2),
                '95th_Quantile': round(numeric_data.quantile(0.95), 2),
                '99th_Quantile': round(numeric_data.quantile(0.99), 2),
                'Max': round(numeric_data.max(), 2),
                'Std': round(numeric_data.std(), 2),
                'Skewness': round(scipy_stats.skew(numeric_data.dropna()), 2),
                'Kurtosis': round(scipy_stats.kurtosis(numeric_data.dropna()), 2),
                'histogram_data': numeric_data.dropna().tolist()
            }
        else:  # nominal or ordinal
            value_counts = column_data.value_counts(dropna=False)
            total_count = len(column_data)
            stats = {
                '#_of_Categories': len(value_counts),
                'Mode_Value': value_counts.index[0] if len(value_counts) > 0 else None,
                'Mode_Ratio': round((value_counts.iloc[0] / total_count) * 100, 2) if len(value_counts) > 0 else 0,
                'Missing_Ratio': round((column_data.isnull().sum() / total_count) * 100, 2),
                '#_of_Outlier_Categories': sum((value_counts / total_count) < 0.005),
                'value_counts': value_counts.to_dict()
            }
        return stats