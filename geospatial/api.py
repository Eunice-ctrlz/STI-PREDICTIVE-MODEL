from ninja import Router
from typing import List, Optional
from django.db.models import Count, Avg
from patients.models import Patient
from prediction_engine.models import RiskPrediction
from .models import GeographicRiskZone
from .schemas import GeoRiskZoneSchema, HeatmapPointSchema


router = Router(tags=["Geospatial"])


@router.get("/risk-zones", response=List[GeoRiskZoneSchema])
def list_risk_zones(request, county: Optional[str] = None, risk_level: Optional[str] = None):
    qs = GeographicRiskZone.objects.all()
    if county:
        qs = qs.filter(county__iexact=county)
    if risk_level:
        qs = qs.filter(risk_level=risk_level)
    return qs.order_by('-risk_score')[:100]


@router.get("/heatmap")
def get_heatmap_data(request, county: Optional[str] = None, days: int = 90):
    """
    Return aggregated risk data by location for heatmap visualization.
    """
    from django.db.models import Avg, Count, Q
    from datetime import datetime, timedelta
    
    since = datetime.now() - timedelta(days=days)
    
    # Aggregate predictions by patient county
    qs = RiskPrediction.objects.filter(
        created_at__gte=since
    ).values(
        'patient__county',
        'patient__sub_county'
    ).annotate(
        avg_risk=Avg('risk_score'),
        patient_count=Count('patient', distinct=True),
        high_risk_count=Count('id', filter=Q(risk_level__in=['high', 'very_high']))
    ).order_by('-avg_risk')
    
    if county:
        qs = qs.filter(patient__county__iexact=county)
    
    # Mock coordinates for counties (in production, use actual GIS data)
    county_coords = {
        'Nairobi': (-1.2921, 36.8219),
        'Mombasa': (-4.0435, 39.6682),
        'Kisumu': (-0.0917, 34.7680),
        'Nakuru': (-0.3031, 36.0800),
    }
    
    results = []
    for item in qs[:50]:
        county_name = item['patient__county'] or 'Unknown'
        lat, lng = county_coords.get(county_name, (-0.5, 37.0))
        
        results.append({
            'lat': lat + (hash(county_name) % 1000) / 10000,  # slight jitter
            'lng': lng + (hash(item['patient__sub_county'] or '') % 1000) / 10000,
            'intensity': round(float(item['avg_risk']), 3),
            'county': county_name,
            'sub_county': item['patient__sub_county'] or '',
            'patient_count': item['patient_count'],
            'high_risk_count': item['high_risk_count'],
        })
    
    return results


@router.get("/county-summary")
def get_county_summary(request):
    """
    Summary statistics per county for the dashboard.
    """
    from django.db.models import Avg, Count, Q
    from datetime import datetime, timedelta
    
    since = datetime.now() - timedelta(days=30)
    
    data = Patient.objects.filter(
        predictions__created_at__gte=since
    ).values('county').annotate(
        total_patients=Count('id', distinct=True),
        avg_risk=Avg('predictions__risk_score'),
        high_risk=Count('predictions', filter=Q(predictions__risk_level__in=['high', 'very_high'])),
        moderate_risk=Count('predictions', filter=Q(predictions__risk_level='moderate')),
        low_risk=Count('predictions', filter=Q(predictions__risk_level='low')),
    ).order_by('-avg_risk')
    
    return list(data)