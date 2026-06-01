from ninja import Router, NinjaAPI
from typing import List, Optional
from datetime import date
import uuid
from datetime import timezone
from .models import WHODataExport , AggregatedIncident
from .schemas import (
    ReportRequest, ReportOut, WeeklyReportDetail,
    DashboardFilter, PolicyMetricOut, PolicyDashboardOut,
    AlertConfigCreate, AlertConfigOut, AlertHistoryOut,
    WHOExportRequest, WHOExportOut, SurveillanceDataPoint
)
from .services.report_generator import WeeklyReportGenerator
from .services.policy_dashboard import PolicyDashboardService
from .services.outbreak_alerts import OutbreakAlertService
from .models import SurveillanceReport, PolicyDashboardMetric, OutbreakNotificationConfig, OutbreakAlertHistory

api = NinjaAPI(title="STI MOH/WHO Reporting API", version="1.0")
router = Router()

# --- Report Generation ---

@router.post("/reports/generate", response=ReportOut, tags=["Reports"])
def generate_report(request, payload: ReportRequest):
    """
    Generate surveillance report.
    Spec Section 7.4: Weekly automated summary reports aligned to WHO reporting standards.
    """
    generator = WeeklyReportGenerator(payload.period_start, payload.period_end)
    
    report = generator.generate(
        scope_national=payload.scope_national,
        counties=payload.counties
    )
    
    return ReportOut(
        report_id=report.report_id,
        report_type=report.report_type,
        period=f"{report.period_start} to {report.period_end}",
        status=report.status,
        generated_at=report.generated_at,
        file_format=report.file_format,
        file_size_mb=round(report.file_size_bytes / 1024 / 1024, 2) if report.file_size_bytes else None,
        download_url=f"/api/v1/reporting/reports/{report.report_id}/download" if report.status == "ready" else None
    )

@router.get("/reports", response=List[ReportOut], tags=["Reports"])
def list_reports(request, 
                 report_type: Optional[str] = None,
                 limit: int = 20):
    """List generated reports"""
    queryset = SurveillanceReport.objects.all()
    if report_type:
        queryset = queryset.filter(report_type=report_type)
    
    return [
        ReportOut(
            report_id=r.report_id,
            report_type=r.report_type,
            period=f"{r.period_start} to {r.period_end}",
            status=r.status,
            generated_at=r.generated_at,
            file_format=r.file_format,
            file_size_mb=round(r.file_size_bytes / 1024 / 1024, 2) if r.file_size_bytes else None,
            download_url=f"/api/v1/reporting/reports/{r.report_id}/download" if r.status == "ready" else None
        )
        for r in queryset.order_by("-generated_at")[:limit]
    ]

@router.get("/reports/{report_id}", response=WeeklyReportDetail, tags=["Reports"])
def get_report_detail(request, report_id: str):
    """Get detailed weekly report content"""
    report = SurveillanceReport.objects.get(report_id=report_id)
    
    return WeeklyReportDetail(
        report_id=report.report_id,
        reporting_period=f"{report.period_start} to {report.period_end}",
        total_assessments=report.total_assessments,
        total_confirmed_cases=report.total_confirmed_cases,
        sti_breakdown=report.sti_breakdown,
        risk_distribution=report.risk_distribution,
        age_distribution=report.age_distribution,
        sex_distribution=report.sex_distribution,
        geographic_distribution=report.geographic_distribution,
        testing_metrics={
            "tests_conducted": report.tests_conducted,
            "tests_positive": report.tests_positive,
            "treatment_initiated": report.treatment_initiated,
            "treatment_completed": report.treatment_completed
        },
        coverage_gaps=report.facility_gaps,
        who_aligned=report.who_submission_ready
    )

# --- Policy Dashboard ---

@router.get("/dashboard", response=PolicyDashboardOut, tags=["Dashboard"])
def get_policy_dashboard(request, 
                         county: Optional[str] = None,
                         category: Optional[str] = None,
                         period_days: int = 30):
    """
    Policy dashboard for MOH decision makers.
    Spec Section 7.4: Policy dashboard with STI burden estimates, testing coverage gaps, treatment uptake rates.
    """
    service = PolicyDashboardService()
    metrics = service.generate_metrics(county=county, period_days=period_days)
    
    if category:
        metrics = [m for m in metrics if m.category == category]
    
    # Priority alerts
    alerts = []
    for m in metrics:
        if m.category == "burden" and m.current_value > (m.target_value or 100):
            alerts.append(f"STI burden in {m.county or 'national'} exceeds target: {m.current_value}%")
        elif m.category == "coverage" and m.current_value < (m.target_value or 0):
            alerts.append(f"Testing coverage in {m.county or 'national'} below target: {m.current_value}%")
    
    # Recommended actions
    actions = []
    if any(m.trend_direction == "worsening" for m in metrics):
        actions.append("Investigate worsening trends in high-burden counties")
    if any(m.category == "inequity" and m.current_value > 2.0 for m in metrics):
        actions.append("Address urban-rural testing inequities through mobile clinics")
    
    return PolicyDashboardOut(
        generated_at=timezone.now(),
        filters_applied=DashboardFilter(county=county, category=category, period_days=period_days),
        metrics=[
            PolicyMetricOut(
                metric_id=m.metric_id,
                category=m.category,
                indicator_name=m.indicator_name,
                county=m.county or None,
                current_value=m.current_value,
                previous_value=m.previous_value,
                target_value=m.target_value,
                unit=m.unit,
                trend_direction=m.trend_direction,
                trend_percentage=m.trend_percentage,
                period=f"{m.period_start} to {m.period_end}",
                data_quality=m.data_quality_score
            )
            for m in metrics
        ],
        priority_alerts=alerts,
        recommended_actions=actions
    )

# --- Outbreak Alerts ---

@router.post("/alerts/config", response=AlertConfigOut, tags=["Outbreak Alerts"])
def create_alert_config(request, payload: AlertConfigCreate):
    """
    Create outbreak alert configuration.
    Spec Section 7.4: Configurable alert thresholds for outbreak notification triggers.
    """
    config = OutbreakNotificationConfig.objects.create(
        sti_type=payload.sti_type,
        county=payload.county or "",
        threshold_type=payload.threshold_type,
        threshold_value=payload.threshold_value,
        notify_moh=payload.notify_moh,
        notify_who=payload.notify_who,
        notify_county_officers=payload.notify_county_officers,
        email_recipients=payload.email_recipients,
        created_by="MOH Officer"  # Would be authenticated user
    )
    
    return AlertConfigOut(
        config_id=config.config_id,
        sti_type=config.sti_type,
        county=config.county or None,
        threshold_type=config.threshold_type,
        threshold_value=config.threshold_value,
        is_active=config.is_active
    )

@router.get("/alerts/configs", response=List[AlertConfigOut], tags=["Outbreak Alerts"])
def list_alert_configs(request, sti_type: Optional[str] = None):
    """List outbreak alert configurations"""
    queryset = OutbreakNotificationConfig.objects.filter(is_active=True)
    if sti_type:
        queryset = queryset.filter(sti_type=sti_type)
    
    return [
        AlertConfigOut(
            config_id=c.config_id,
            sti_type=c.sti_type,
            county=c.county or None,
            threshold_type=c.threshold_type,
            threshold_value=c.threshold_value,
            is_active=c.is_active
        )
        for c in queryset
    ]

@router.get("/alerts/history", response=List[AlertHistoryOut], tags=["Outbreak Alerts"])
def get_alert_history(request, county: Optional[str] = None, limit: int = 50):
    """Get historical outbreak alerts"""
    queryset = OutbreakAlertHistory.objects.all()
    if county:
        queryset = queryset.filter(county=county)
    
    return [
        AlertHistoryOut(
            alert_id=a.alert_id,
            sti_type=a.sti_type,
            county=a.county,
            actual_value=a.actual_value,
            threshold_value=a.threshold_value,
            triggered_at=a.notification_timestamp,
            acknowledged=bool(a.acknowledged_by)
        )
        for a in queryset.order_by("-notification_timestamp")[:limit]
    ]

# --- WHO Data Export ---

@router.post("/who/export", response=WHOExportOut, tags=["WHO Export"])
def export_who_data(request, payload: WHOExportRequest):
    """
    Export WHO-aligned surveillance data.
    Spec Section 7.4: CSV and JSON export of aggregated non-identifiable surveillance data.
    """
    # Generate export
    export = WHODataExport.objects.create(
        export_format=payload.export_format,
        data_period_start=payload.data_period_start,
        data_period_end=payload.data_period_end,
        record_count=0,  # Would count actual records
        counties_covered=payload.counties or ["all"],
        sti_types_included=payload.sti_types or ["all"],
        file_path=f"who_exports/who_{uuid.uuid4()}.{payload.export_format}",
        file_size_bytes=0
    )
    
    return WHOExportOut(
        export_id=export.export_id,
        export_format=export.export_format,
        data_period=f"{export.data_period_start} to {export.data_period_end}",
        record_count=export.record_count,
        file_size_mb=0.0,
        generated_at=export.generated_at,
        who_ready=True,
        download_url=f"/api/v1/reporting/who/{export.export_id}/download"
    )

@router.get("/who/exports", response=List[WHOExportOut], tags=["WHO Export"])
def list_who_exports(request, limit: int = 20):
    """List WHO data exports"""
    exports = WHODataExport.objects.order_by("-generated_at")[:limit]
    
    return [
        WHOExportOut(
            export_id=e.export_id,
            export_format=e.export_format,
            data_period=f"{e.data_period_start} to {e.data_period_end}",
            record_count=e.record_count,
            file_size_mb=round(e.file_size_bytes / 1024 / 1024, 2),
            generated_at=e.generated_at,
            who_ready=not e.transmitted_to_who,
            download_url=f"/api/v1/reporting/who/{e.export_id}/download"
        )
        for e in exports
    ]

@router.get("/surveillance/data", response=List[SurveillanceDataPoint], tags=["Data Access"])
def get_surveillance_data(request,
                          period_start: date,
                          period_end: date,
                          county: Optional[str] = None,
                          sti_type: Optional[str] = None):
    """
    Access aggregated non-identifiable surveillance data.
    For public health research and international reporting.
    """
    # Query aggregated incident data
    queryset = AggregatedIncident.objects.filter(
        period_start__gte=period_start,
        period_end__lte=period_end
    ).select_related('grid_cell')
    
    if county:
        queryset = queryset.filter(grid_cell__county=county)
    if sti_type:
        queryset = queryset.filter(sti_type=sti_type)
    
    return [
        SurveillanceDataPoint(
            reporting_period=f"{inc.period_start} to {inc.period_end}",
            county=inc.grid_cell.county,
            sub_county=inc.grid_cell.sub_county,
            sti_type=inc.sti_type,
            age_group="all",  # Would be age-aggregated
            sex="all",
            case_count=inc.incident_count,
            incidence_rate=round(inc.incident_count / max(inc.grid_cell.population_estimate, 1) * 100000, 2),
            tests_conducted=0,  # Would integrate testing data
            tests_positive=0,
            treatment_initiated=0
        )
        for inc in queryset[:1000]
    ]

api.add_router("/reporting/", router)