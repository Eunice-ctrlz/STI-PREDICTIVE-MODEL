from rest_framework import serializers
from .models import RiskPrediction

class PredictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskPrediction
        fields = '__all__'
