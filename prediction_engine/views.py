from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import RiskPrediction
from patients.models import Patient
from .serializers import PredictionSerializer
from .ml_model import get_predictor


@api_view(['POST'])
def predict(request):
    """
    Run an STI risk prediction for a given patient using the trained ML model.
    Falls back to a calibrated heuristic model if no trained artifact is found.
    """
    try:
        patient_id = request.data.get('patient_id')
        sti_type = request.data.get('sti_type', 'general')
        model_version = request.data.get('model_version', 'sti_risk_v1')

        if not patient_id:
            return Response(
                {'detail': 'patient_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        patient = Patient.objects.get(patient_id=patient_id, is_active=True)

        # Run the actual ML model (Random Forest or heuristic fallback)
        predictor = get_predictor(model_name=model_version, sti_type=sti_type)
        result = predictor.predict(patient)

        # Persist the prediction record
        prediction = RiskPrediction.objects.create(
            patient=patient,
            sti_type=sti_type,
            risk_score=result['risk_score'],
            risk_level=result['risk_level'],
            confidence_interval_lower=result.get('confidence_interval_lower'),
            confidence_interval_upper=result.get('confidence_interval_upper'),
            top_risk_factors=result['top_risk_factors'],
            recommended_tests=result['recommended_tests'],
            recommended_actions=result['recommended_actions'],
            likely_stis=result.get('likely_stis', []),
            model_version=result['model_version'],
            model_name=result['model_name'],
        )

        return Response(
            PredictionSerializer(prediction).data,
            status=status.HTTP_201_CREATED,
        )

    except Patient.DoesNotExist:
        return Response(
            {'detail': 'Patient not found or inactive'},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {'detail': str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(['GET'])
def prediction_detail(request, prediction_id):
    """
    Retrieve a saved prediction by its primary key.
    Called by PredictionResult.jsx on the result page.
    """
    prediction = get_object_or_404(RiskPrediction, id=prediction_id)
    return Response(PredictionSerializer(prediction).data)


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
    from django.db.models import Count, Avg
    from datetime import datetime, timedelta

    days = int(request.query_params.get('days', 30))
    since = datetime.now() - timedelta(days=days)

    qs = RiskPrediction.objects.filter(created_at__gte=since)
    total = qs.count()
    distribution = dict(
        qs.values('risk_level')
          .annotate(count=Count('id'))
          .values_list('risk_level', 'count')
    )
    avg_score = qs.aggregate(avg=Avg('risk_score'))['avg'] or 0.0

    # Ensure all levels are present
    for level in ['low', 'moderate', 'high', 'very_high']:
        distribution.setdefault(level, 0)

    return Response({
        'total_predictions': total,
        'risk_distribution': distribution,
        'avg_risk_score': round(avg_score, 4),
        'model_version': 'sti_risk_v1',
        'period': f'Last {days} days',
    })
