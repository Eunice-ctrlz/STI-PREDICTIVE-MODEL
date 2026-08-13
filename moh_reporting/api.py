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
    now = datetime.now()
    since = now - timedelta(days=days)
    # The equally-sized window immediately before `since`, used for the
    # period-over-period deltas shown on the dashboard stat cards.
    prev_since = since - timedelta(days=days)

    # Base querysets
    patient_qs = Patient.objects.filter(is_active=True)
    prediction_qs = RiskPrediction.objects.filter(created_at__gte=since)
    prev_patient_qs = Patient.objects.filter(is_active=True, created_at__lt=since)
    prev_prediction_qs = RiskPrediction.objects.filter(
        created_at__gte=prev_since, created_at__lt=since
    )

    if county:
        patient_qs = patient_qs.filter(county__iexact=county)
        prediction_qs = prediction_qs.filter(patient__county__iexact=county)
        prev_patient_qs = prev_patient_qs.filter(county__iexact=county)
        prev_prediction_qs = prev_prediction_qs.filter(patient__county__iexact=county)

    total_patients = patient_qs.count()
    total_predictions = prediction_qs.count()
    
    # Risk distribution
    risk_dist = dict(prediction_qs.values('risk_level').annotate(
        count=Count('id')
    ).values_list('risk_level', 'count'))
    
    for level in ['low', 'moderate', 'high', 'very_high']:
        if level not in risk_dist:
            risk_dist[level] = 0
    
    # Age distribution, keyed by Patient.age_group and kept in ascending age
    # order so the chart's x-axis reads left-to-right.
    AGE_GROUP_ORDER = ['under_15', '15_24', '25_34', '35_44', '45_plus']
    age_counts = {}
    for patient in patient_qs:
        ag = patient.age_group
        age_counts[ag] = age_counts.get(ag, 0) + 1
    age_dist = {g: age_counts.get(g, 0) for g in AGE_GROUP_ORDER}
    
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
    
    avg_risk_score = round(prediction_qs.aggregate(avg=Avg('risk_score'))['avg'] or 0, 3)
    high_risk_patients = risk_dist.get('high', 0) + risk_dist.get('very_high', 0)

    # Same four measures over the preceding window, so the frontend can show a
    # real change instead of a hardcoded one. `None` means "no prior data to
    # compare against" and the UI hides the delta entirely.
    prev_high_risk = prev_prediction_qs.filter(
        risk_level__in=['high', 'very_high']
    ).count()
    previous = {
        'total_patients': prev_patient_qs.count(),
        'total_screenings': prev_prediction_qs.count(),
        'avg_risk_score': round(prev_prediction_qs.aggregate(avg=Avg('risk_score'))['avg'] or 0, 3),
        'high_risk_patients': prev_high_risk,
    }

    def pct_change(current, before):
        if not before:
            return None
        return round((current - before) / before * 100, 1)

    return {
        'period': f'Last {days} days',
        'period_days': days,
        'county_filter': county,
        'summary': {
            'total_patients': total_patients,
            'total_screenings': total_predictions,
            'avg_risk_score': avg_risk_score,
            'high_risk_patients': high_risk_patients,
        },
        'previous_summary': previous,
        'change_pct': {
            'total_patients': pct_change(total_patients, previous['total_patients']),
            'total_screenings': pct_change(total_predictions, previous['total_screenings']),
            'avg_risk_score': pct_change(avg_risk_score, previous['avg_risk_score']),
            'high_risk_patients': pct_change(high_risk_patients, previous['high_risk_patients']),
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