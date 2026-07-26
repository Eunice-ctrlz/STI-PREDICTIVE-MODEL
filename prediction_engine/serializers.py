from rest_framework import serializers
from .models import RiskPrediction


class PredictionSerializer(serializers.ModelSerializer):
    """
    Full serializer for RiskPrediction.

    Adds computed string fields that the frontend (PredictionResult.jsx) needs:
      - patient_name  → Patient.full_name
      - patient_id    → Patient.patient_id  (string, not the DB pk)
    """
    patient_name = serializers.SerializerMethodField()
    patient_id = serializers.SerializerMethodField()

    class Meta:
        model = RiskPrediction
        fields = [
            'id',
            'patient_id',
            'patient_name',
            'sti_type',
            'risk_score',
            'risk_level',
            'confidence_interval_lower',
            'confidence_interval_upper',
            'top_risk_factors',
            'recommended_tests',
            'recommended_actions',
            'likely_stis',
            'model_version',
            'model_name',
            'validated_by_clinician',
            'clinician_notes',
            'created_at',
        ]

    def get_patient_name(self, obj):
        return obj.patient.full_name

    def get_patient_id(self, obj):
        return obj.patient.patient_id
