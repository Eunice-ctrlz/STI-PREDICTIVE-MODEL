from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .models import RiskPrediction
from patients.models import Patient
from .serializers import PredictionSerializer
import random
import uuid

@api_view(['POST'])
def predict(request):
    try:
        patient_id = request.data.get('patient_id')
        sti_type = request.data.get('sti_type', 'general')
        
        patient = Patient.objects.get(patient_id=patient_id)
        
        # Mock prediction logic based on risk factors
        risk_score = 0.1
        top_factors = {}
        
        if patient.number_of_partners_12m > 3:
            risk_score += 0.3
            top_factors['num_partners_12m'] = 0.35
            
        if patient.prior_sti_history:
            risk_score += 0.2
            top_factors['prior_sti_history'] = 0.28
            
        if patient.condom_use_frequency < 0.5:
            risk_score += 0.15
            top_factors['condom_use_freq'] = 0.15
            
        if patient.substance_use:
            risk_score += 0.1
            top_factors['substance_use'] = 0.12
            
        if not patient.hiv_status_known:
            risk_score += 0.05
            top_factors['hiv_unknown'] = 0.10
            
        risk_score = min(risk_score + random.uniform(-0.05, 0.05), 0.99)
        risk_score = max(risk_score, 0.01)
        
        if risk_score > 0.6:
            risk_level = 'high'
            tests = ['HIV', 'Syphilis', 'Gonorrhea', 'Chlamydia']
            actions = 'Immediate comprehensive STI screening recommended. Provide risk reduction counseling.'
        elif risk_score > 0.3:
            risk_level = 'moderate'
            tests = ['HIV', 'Syphilis']
            actions = 'Routine STI screening recommended. Provide condom counseling.'
        else:
            risk_level = 'low'
            tests = []
            actions = 'Continue routine screening per guidelines.'

        prediction = RiskPrediction.objects.create(
            patient=patient,
            sti_type=sti_type,
            risk_score=risk_score,
            risk_level=risk_level,
            confidence_interval_lower=max(0, risk_score - 0.1),
            confidence_interval_upper=min(1, risk_score + 0.1),
            top_risk_factors=top_factors,
            recommended_tests=tests,
            recommended_actions=actions,
            model_version='sti_risk_v1',
            model_name='Random Forest'
        )
        
        return Response(PredictionSerializer(prediction).data, status=status.HTTP_201_CREATED)
    except Patient.DoesNotExist:
        return Response({'detail': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def history(request, patient_id):
    try:
        patient = Patient.objects.get(patient_id=patient_id)
        predictions = RiskPrediction.objects.filter(patient=patient).order_by('-created_at')
        serializer = PredictionSerializer(predictions, many=True)
        return Response(serializer.data)
    except Patient.DoesNotExist:
        return Response({'detail': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
def stats(request):
    days = int(request.query_params.get('days', 30))
    # Mock stats
    return Response({
        'total_predictions': 1200,
        'high_risk_predictions': 342,
        'accuracy': 0.89
    })
