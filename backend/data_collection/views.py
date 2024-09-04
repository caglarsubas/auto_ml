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
                    pass #'float'
            else:
                data_type = column_data.dtype.name

            unique_count = column_data.nunique(dropna=False)
            level_of_measurement = determine_level_of_measurement(column_data, data_type, unique_count)

            data_dict.append({
                'Feature_Name': column,
                'Data_Type': data_type,
                '#_of_Unique_Value': unique_count,
                'Level_of_Measurement': level_of_measurement
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

        return Response(data_dict)