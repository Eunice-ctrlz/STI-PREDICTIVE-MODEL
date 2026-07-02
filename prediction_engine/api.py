from ninja import Router
from django.shortcuts import get_object_or_404
from django.db.models import Count, Avg, Q
from typing import List, Optional
from datetime import datetime, timedelta
from patients.models import Patient
from clinicians.models import Clinician
from .models import RiskPrediction, ModelPerformanceMetric
from .schemas import (
    PredictionRequestSchema, PredictionResultSchema,
    BatchPredictionSchema, RiskStatsSchema
)
from .ml_model import get_predictor

router = Router(tags=["Predictions"])


@router.post("/predict", response=PredictionResultSchema)
def predict_risk(request, payload: PredictionRequestSchema):
    patient = get_object_or_404(Patient, patient_id=payload.patient_id, is_active=True)
    
    # Get predictor
    predictor = get_predictor(
        model_name=payload.model_version or "sti_risk_v1",
        sti_type=payload.sti_type or "general"
    )
    
    # Run prediction
    result = predictor.predict(patient)
    
    # Get clinician from request user if authenticated
    clinician = None
    if request.user.is_authenticated:
        try:
            clinician = Clinician.objects.get(user=request.user)
        except Clinician.DoesNotExist:
            pass
    
    # Save prediction
    prediction = RiskPrediction.objects.create(
        patient=patient,
        clinician=clinician,
        sti_type=payload.sti_type or "general",
        risk_score=result['risk_score'],
        risk_level=result['risk_level'],
        confidence_interval_lower=result.get('confidence_interval_lower'),
        confidence_interval_upper=result.get('confidence_interval_upper'),
        top_risk_factors=result['top_risk_factors'],
        input_features=result.get('input_features', {}),
        model_version=result['model_version'],
        model_name=result['model_name'],
        recommended_tests=result['recommended_tests'],
        recommended_actions=result['recommended_actions'],
    )
    
    return {
        'id': prediction.id,
        'patient_id': patient.patient_id,
        'patient_name': patient.full_name,
        'sti_type': prediction.sti_type,
        'risk_score': prediction.risk_score,
        'risk_level': prediction.risk_level,
        'confidence_interval_lower': prediction.confidence_interval_lower,
        'confidence_interval_upper': prediction.confidence_interval_upper,
        'top_risk_factors': prediction.top_risk_factors,
        'recommended_tests': prediction.recommended_tests,
        'recommended_actions': prediction.recommended_actions,
        'model_version': prediction.model_version,
        'model_name': prediction.model_name,
        'validated_by_clinician': prediction.validated_by_clinician,
        'created_at': prediction.created_at,
    }


@router.post("/predict/batch", response=List[PredictionResultSchema])
def batch_predict(request, payload: BatchPredictionSchema):
    results = []
    for pid in payload.patient_ids:
        try:
            patient = Patient.objects.get(patient_id=pid, is_active=True)
            req = PredictionRequestSchema(
                patient_id=pid,
                sti_type=payload.sti_type
            )
            # Reuse single predict logic
            result = predict_risk(request, req)
            results.append(result)
        except Patient.DoesNotExist:
            continue
    return results


@router.get("/history/{patient_id}", response=List[PredictionResultSchema])
def get_prediction_history(request, patient_id: str, sti_type: Optional[str] = None):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    qs = patient.predictions.all()
    if sti_type:
        qs = qs.filter(sti_type=sti_type)
    return qs.order_by('-created_at')[:20]


@router.get("/stats", response=RiskStatsSchema)
def get_prediction_stats(
    request,
    days: int = 30,
    county: Optional[str] = None,
    facility_id: Optional[int] = None
):
    since = datetime.now() - timedelta(days=days)
    qs = RiskPrediction.objects.filter(created_at__gte=since)
    
    if county:
        qs = qs.filter(patient__county__iexact=county)
    if facility_id:
        qs = qs.filter(clinician__facility_id=facility_id)
    
    total = qs.count()
    distribution = dict(qs.values('risk_level').annotate(count=Count('id')).values_list('risk_level', 'count'))
    avg_score = qs.aggregate(avg=Avg('risk_score'))['avg'] or 0.0
    
    # Fill missing levels with 0
    for level in ['low', 'moderate', 'high', 'very_high']:
        if level not in distribution:
            distribution[level] = 0
    
    return {
        'total_predictions': total,
        'risk_distribution': distribution,
        'avg_risk_score': round(avg_score, 4),
        'model_version': 'sti_risk_v1',
        'period': f'Last {days} days',
    }


@router.post("/validate/{prediction_id}")
def validate_prediction(request, prediction_id: int, notes: str = "", actual_outcome: str = ""):
    prediction = get_object_or_404(RiskPrediction, id=prediction_id)
    prediction.validated_by_clinician = True
    prediction.clinician_notes = notes
    if actual_outcome:
        prediction.actual_outcome = actual_outcome
    prediction.save()
    return {"success": True, "message": "Prediction validated"}


@router.get("/performance", response=List[dict])
def get_model_performance(request, model_version: Optional[str] = None):
    qs = ModelPerformanceMetric.objects.all()
    if model_version:
        qs = qs.filter(model_version=model_version)
    return list(qs.values().order_by('-evaluated_on')[:10])