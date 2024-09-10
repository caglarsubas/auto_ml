# data_collection/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import DataFile
from .serializers import DataFileSerializer
import os
from django.conf import settings
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


class DataFileViewSet(viewsets.ModelViewSet):
    queryset = DataFile.objects.all()
    serializer_class = DataFileSerializer

    def create(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if a file with the same name already exists
        file_path = os.path.join(settings.MEDIA_ROOT, 'data_files', file.name)
        if os.path.exists(file_path):
            return Response(
                {"error": f"A file named '{file.name}' already exists. Please choose a different name or use the existing file."},
                status=status.HTTP_409_CONFLICT
            )

        # If the file doesn't exist, proceed with the creation
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['get'], url_path='by-name/(?P<file_name>.+)')
    def get_by_name(self, request, file_name=None):
        try:
            data_file = DataFile.objects.get(file__endswith=file_name)
            serializer = self.get_serializer(data_file)
            return Response(serializer.data)
        except DataFile.DoesNotExist:
            return Response({"error": f"File '{file_name}' not found."}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        data_file = self.get_object()
        file_path = data_file.file.path
        
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file_path)
        else:
            return Response({"error": "Unsupported file format"}, status=400)
        
        df = df.replace({np.nan: None})
        
        preview = {
            "top_rows": df.head().to_dict(orient='records'),
            "bottom_rows": df.tail().to_dict(orient='records'),
            "columns": df.columns.tolist()
        }
        return Response(preview)

    def calculate_descriptive_stats(self, column_data, data_type, level_of_measurement):
        desc_stats = {}
        if level_of_measurement in ['continuous', 'cardinal']:
            numeric_data = pd.to_numeric(column_data, errors='coerce')
            desc_stats = {
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
                'Kurtosis': round(scipy_stats.kurtosis(numeric_data.dropna()), 2)
            }
        elif level_of_measurement in ['nominal', 'ordinal']:
            value_counts = column_data.value_counts(dropna=False)
            total_count = len(column_data)
            desc_stats = {
                '#_of_Categories': len(value_counts),
                'Mode_Value': value_counts.index[0] if len(value_counts) > 0 else None,
                'Mode_Ratio': round((value_counts.iloc[0] / total_count) * 100, 2) if len(value_counts) > 0 else 0,
                'Missing_Ratio': round((column_data.isnull().sum() / total_count) * 100, 2),
                '#_of_Outlier_Categories': sum((value_counts / total_count) < 0.005)
            }
        return desc_stats

    # to json serialization of NaNs
    def replace_nan_with_none(self, obj):
        if isinstance(obj, dict):
            return {key: self.replace_nan_with_none(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.replace_nan_with_none(item) for item in obj]
        elif isinstance(obj, float) and np.isnan(obj):
            return None
        return obj
        
    @action(detail=True, methods=['post'])
    def data_dictionary(self, request, pk=None):
        data_file = self.get_object()
        file_path = data_file.file.path
        dictionary_file = request.FILES.get('dictionary')

        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file_path)
        else:
            return Response({"error": "Unsupported file format"}, status=400)

        def determine_level_of_measurement(column_data, data_type, unique_count):
            if unique_count == len(column_data):
                return 'id'
            elif (data_type == 'float64')&(unique_count>1000):
                return 'continuous'
            elif (data_type == 'float64')&(unique_count<=1000):
                return 'cardinal'
            elif data_type == 'integer':
                if unique_count > 1000 or unique_count / len(column_data) > 0.1:
                    return 'continuous'
                else:
                    if unique_count>5:
                        return 'cardinal'
                    else:
                        return 'nominal'
            elif data_type == 'object':
                try:
                    pd.to_datetime(column_data, errors='raise', format='%d/%m/%Y %I:%M:%S %p')
                    return 'datetime'
                except:
                    return 'nominal'
            else:
                return 'unknown'

        data_dict = []
        for column in df.columns:
            column_data = df[column]
            numeric_data = pd.to_numeric(column_data, errors='coerce')
            
            if numeric_data.notna().all():
                if all(numeric_data.astype(float) == numeric_data.astype(int)):
                    data_type = 'integer'
                else:
                    data_type = 'float'
            else:
                data_type = column_data.dtype.name

            unique_count = column_data.nunique(dropna=False)
            level_of_measurement = determine_level_of_measurement(column_data, data_type, unique_count)

            # Calculate Missing_Ratio and Mode_Ratio
            missing_ratio = (column_data.isnull().sum() / len(column_data)) * 100
            mode_count = column_data.value_counts().iloc[0] if len(column_data) > 0 else 0
            mode_ratio = (mode_count / len(column_data)) * 100

            # Determine Model_Usage_YN
            model_usage_yn = ('No' if level_of_measurement in ['id', 'date', 'datetime', 'timestamp'] or 
                              column in ['Target'] or 'date' in data_type.lower() or 
                              (unique_count/len(column_data))>0.90 
                              else 'Yes')

            # Calculate descriptive statistics
            descriptive_stats = self.calculate_descriptive_stats(column_data, data_type, level_of_measurement)

            data_dict.append({
                'Feature_Name': column,
                'Data_Type': data_type,
                '#_of_Unique_Value': unique_count,
                'Level_of_Measurement': level_of_measurement,
                'Missing_Ratio': round(missing_ratio, 2),
                'Mode_Ratio': round(mode_ratio, 2),
                'Model_Usage_YN': model_usage_yn,
                'Descriptive_Stats': descriptive_stats
            })

        # Process dictionary file if provided
        if dictionary_file:
            if dictionary_file.name.endswith('.csv'):
                dict_df = pd.read_csv(dictionary_file)
            elif dictionary_file.name.endswith(('.xls', '.xlsx')):
                dict_df = pd.read_excel(dictionary_file)
            else:
                return Response({"error": "Unsupported dictionary file format"}, status=400)

            dict_df = dict_df.set_index(dict_df.columns[0])
            for item in data_dict:
                if item['Feature_Name'] in dict_df.index:
                    item['Feature_Description'] = dict_df.loc[item['Feature_Name'], dict_df.columns[0]]
                    if 'Level_of_Measurement' in dict_df.columns:
                        item['Level_of_Measurement'] = dict_df.loc[item['Feature_Name'], 'Level_of_Measurement']

        data_dict = self.replace_nan_with_none(data_dict)
        return Response(data_dict)