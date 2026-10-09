# data_collection/serializers.py
from rest_framework import serializers
from .models import Declaration

class DeclarationSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(source='project_binding.project_id', read_only=True, default=None)

    class Meta:
        model = Declaration
        fields = ['id', 'file', 'name', 'original_name', 'uploaded_at', 'has_header', 'project_id']
