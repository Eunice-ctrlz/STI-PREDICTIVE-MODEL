from ninja import Router
from django.db.models import Count, Avg, Q
from datetime import datetime, timedelta
from typing import Optional
from patients.models import Patient
from prediction_engine.models import RiskPrediction
from .models import ReportTemplate, GeneratedReport

router = Router(tags=["MOH Reporting"])


@router.get("/dashboard")
def get_dashboard_metrics(request, county: Optional[str] = None, days: int = 30):
    """
    Main dashboard metrics for MOH reporting.
    """
    since = datetime.now() - timedelta(days=days)
    
    # Base querysets
    patient_qs = Patient.objects.filter(is_active=True)
    prediction_qs = RiskPrediction.objects.filter(created_at__gte=since)
    
    if county:
        patient_qs = patient_qs.filter(county__iexact=county)
        prediction_qs = prediction_qs.filter(patient__county__iexact=county)
    
    total_patients = patient_qs.count()
    total_predictions = prediction_qs.count()
    
    # Risk distribution
    risk_dist = dict(prediction_qs.values('risk_level').annotate(
        count=Count('id')
    ).values_list('risk_level', 'count'))
    
    for level in ['low', 'moderate', 'high', 'very_high']:
        if level not in risk_dist:
            risk_dist[level] = 0
    
    # Age distribution
    age_groups = ['<15', '15-19', '20-24', '25-29', '30-34', '35-39', '40-49', '50+']
    age_dist = {}
    for patient in patient_qs:
        ag = patient.age_group
        age_dist[ag] = age_dist.get(ag, 0) + 1
    
    # Gender distribution
    gender_dist = dict(patient_qs.values('gender').annotate(
        count=Count('id')
    ).values_list('gender', 'count'))
    
    # County breakdown (top 10)
    county_breakdown = list(patient_qs.values('county').annotate(
        patients=Count('id'),
        avg_risk=Avg('predictions__risk_score'),
        high_risk=Count('predictions', filter=Q(predictions__risk_level__in=['high', 'very_high']))
    ).order_by('-patients')[:10])
    
    # Screening trend (daily counts)
    from django.db.models.functions import TruncDate
    daily_trend = list(prediction_qs.annotate(
        date=TruncDate('created_at')
    ).values('date').annotate(
        count=Count('id'),
        avg_risk=Avg('risk_score')
    ).order_by('date')[:30])
    
    return {
        'period': f'Last {days} days',
        'county_filter': county,
        'summary': {
            'total_patients': total_patients,
            'total_screenings': total_predictions,
            'avg_risk_score': round(prediction_qs.aggregate(avg=Avg('risk_score'))['avg'] or 0, 3),
            'high_risk_patients': risk_dist.get('high', 0) + risk_dist.get('very_high', 0),
        },
        'risk_distribution': risk_dist,
        'age_distribution': age_dist,
        'gender_distribution': gender_dist,
        'county_breakdown': county_breakdown,
        'daily_trend': daily_trend,
    }


@router.get("/templates")
def list_report_templates(request):
    return list(ReportTemplate.objects.filter(is_active=True).values())


@router.get("/reports")
def list_generated_reports(request, status: str = None):
    qs = GeneratedReport.objects.all()
    if status:
        qs = qs.filter(status=status)
    return list(qs.values().order_by('-generated_at')[:20])