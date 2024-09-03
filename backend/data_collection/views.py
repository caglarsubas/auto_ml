# data_collection/views.py
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import DataFile
from .serializers import DataFileSerializer
import pandas as pd
import numpy as np

class DataFileViewSet(viewsets.ModelViewSet):
    queryset = DataFile.objects.all()
    serializer_class = DataFileSerializer

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
        
        # Replace NaN values with None (which will be serialized to null in JSON)
        df = df.replace({np.nan: None})
        
        preview = {
            "top_rows": df.head().to_dict(orient='records'),
            "bottom_rows": df.tail().to_dict(orient='records'),
            "columns": df.columns.tolist()
        }
        return Response(preview)