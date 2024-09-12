from rest_framework import serializers

class FeatureCardSerializer(serializers.Serializer):
    Feature_Name = serializers.CharField()
    Feature_Description = serializers.CharField(allow_blank=True, allow_null=True)
    Level_of_Measurement = serializers.CharField()
    Descriptive_Stats = serializers.DictField()