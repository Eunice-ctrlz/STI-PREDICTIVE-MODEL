from rest_framework import serializers
from .models import CountyRiskData

class CountyRiskDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = CountyRiskData
        fields = '__all__'
