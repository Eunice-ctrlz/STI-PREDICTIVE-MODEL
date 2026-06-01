from celery import shared_task
from datetime import date, timedelta
from django.utils import timezone
from .services.report_generator import WeeklyReportGenerator
from .services.outbreak_alerts import OutbreakAlertService

@shared_task
def generate_weekly_surveillance_report():
    """
    Weekly automated report generation.
    Spec Section 7.4: Weekly automated summary reports.
    """
    period_end = date.today()
    period_start = period_end - timedelta(days=7)
    
    generator = WeeklyReportGenerator(period_start, period_end)
    report = generator.generate(scope_national=True)
    
    # Auto-send to MOH
    report.sent_to_moh = True
    report.sent_at = timezone.now()
    report.save()
    
    return {
        "report_id": str(report.report_id),
        "status": "generated_and_sent",
        "who_aligned": report.who_submission_ready
    }

@shared_task
def evaluate_outbreak_triggers():
    """
    Evaluate outbreak alert triggers.
    """
    service = OutbreakAlertService()
    
    # Check recent hotspot alerts
    from geospatial.models import HotspotAlert
    recent_alerts = HotspotAlert.objects.filter(
        is_active=True,
        created_at__gte=timezone.now() - timedelta(days=1)
    )
    
    triggered = []
    for alert in recent_alerts:
        # Convert alert to incidence rate
        incidence = alert.total_incidents / max(alert.population_at_risk, 1) * 100000
        
        result = service.evaluate_triggers(
            county=alert.primary_county,
            sti_type=alert.sti_type,
            current_value=incidence,
            value_type="incidence_rate"
        )
        triggered.extend(result)
    
    return {"triggers_evaluated": len(recent_alerts), "alerts_triggered": len(triggered)}