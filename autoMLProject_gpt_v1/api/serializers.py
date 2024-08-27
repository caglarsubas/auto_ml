from rest_framework import serializers
from .models import IrisData

class IrisDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = IrisData
        fields = '__all__'
