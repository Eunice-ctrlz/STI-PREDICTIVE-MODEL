from celery import shared_task
from datetime import date, timedelta

from .services import SpatialAnalyzer
from .models import AggregatedIncident, HotspotAlert

@shared_task
def generate_weekly_heatmaps():
    """
    Weekly scheduled task to regenerate all heatmaps.
    Spec Section 4.1.3: GeoJSON heatmap layers updated weekly.
    """
    sti_types = ["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "all"]
    
    # Get all counties with data
    counties = AggregatedIncident.objects.values_list(
        'grid_cell__county', flat=True
    ).distinct()
    
    period_end = date.today()
    period_start = period_end - timedelta(days=30)
    
    for county in counties:
        for sti_type in sti_types:
            try:
                analyzer = SpatialAnalyzer({
                    "dp_epsilon": 0.1,
                    "kde_bandwidth_km": 15.0,
                    "dbscan_eps_km": 10.0
                })
                analyzer.analyze_region(county, sti_type, period_start, period_end)
            except Exception as e:
                continue
    
    return {"status": "completed", "counties_processed": len(counties)}

@shared_task
def detect_outbreaks():
    """
    Daily outbreak detection task.
    Creates alerts when critical hotspot thresholds are exceeded.
    """
    # Implementation in SpatialAnalyzer._create_hotspot_alert
    # Triggered automatically during analyze_region
    pass