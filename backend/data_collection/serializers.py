# data_collection/serializers.py
from rest_framework import serializers
from .models import DataFile

class DataFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataFile
        fields = ['id', 'file', 'name', 'original_name', 'uploaded_at']