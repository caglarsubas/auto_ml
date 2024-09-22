# data_collection/serializers.py
from rest_framework import serializers
from .models import Declaration

class DeclarationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Declaration
        fields = ['id', 'file', 'name', 'original_name', 'uploaded_at']