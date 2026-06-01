from ninja import Schema, Field
from typing import List, Dict, Optional, Literal, Any
from uuid import UUID
from datetime import date, datetime
from typing import Annotated
from pydantic import Field

# --- Report Generation Schemas ---

class ReportRequest(Schema):
    """Request generation of a surveillance report"""
    report_type: Literal["weekly", "monthly", "outbreak", "annual", "ad_hoc"]
    period_start: date
    period_end: date
    scope_national: bool = True
    counties: List[str] = Field(default_factory=list)
    file_format: Literal["csv", "json", "pdf", "xlsx"] = "csv"

class ReportOut(Schema):
    """Generated report metadata"""
    report_id: UUID
    report_type: str
    period: str
    status: str
    generated_at: datetime
    file_format: str
    file_size_mb: Optional[float]
    download_url: Optional[str]

class WeeklyReportDetail(Schema):
    """Detailed weekly report content"""
    report_id: UUID
    reporting_period: str
    total_assessments: int
    total_confirmed_cases: int
    sti_breakdown: Dict[str, int]
    risk_distribution: Dict[str, int]
    age_distribution: Dict[str, int]
    sex_distribution: Dict[str, float]
    geographic_distribution: Dict[str, int]
    testing_metrics: Dict[str, Any]
    coverage_gaps: List[Dict[str, Any]]
    who_aligned: bool

# --- Policy Dashboard Schemas ---

class DashboardFilter(Schema):
    """Filter for policy dashboard metrics"""
    county: Optional[str] = None
    category: Optional[Literal["burden", "coverage", "treatment", "forecast", "inequity"]] = None
    period_days: Annotated[int, Field(gt=0, ge=7, le=365)] = 30

class PolicyMetricOut(Schema):
    """Single policy dashboard metric"""
    metric_id: UUID
    category: str
    indicator_name: str
    county: Optional[str]
    current_value: float
    previous_value: Optional[float]
    target_value: Optional[float]
    unit: str
    trend_direction: str
    trend_percentage: Optional[float]
    period: str
    data_quality: float

class PolicyDashboardOut(Schema):
    """Complete policy dashboard"""
    generated_at: datetime
    filters_applied: DashboardFilter
    metrics: List[PolicyMetricOut]
    priority_alerts: List[str]
    recommended_actions: List[str]

# --- Outbreak Alert Schemas ---

class AlertConfigCreate(Schema):
    """Create outbreak alert configuration"""
    sti_type: str
    county: Optional[str] = None
    threshold_type: Literal["incidence_rate", "case_count", "percentage_increase", "forecast_exceedance"]
    threshold_value: float
    notify_moh: bool = True
    notify_who: bool = False
    notify_county_officers: bool = True
    email_recipients: List[str] = Field(default_factory=list)

class AlertConfigOut(Schema):
    """Alert configuration output"""
    config_id: UUID
    sti_type: str
    county: Optional[str]
    threshold_type: str
    threshold_value: float
    is_active: bool

class AlertHistoryOut(Schema):
    """Historical outbreak alert"""
    alert_id: UUID
    sti_type: str
    county: str
    actual_value: float
    threshold_value: float
    triggered_at: datetime
    acknowledged: bool

# --- WHO Export Schemas ---

class WHOExportRequest(Schema):
    """Request WHO-aligned data export"""
    data_period_start: date
    data_period_end: date
    export_format: Literal["csv", "json", "hl7"] = "csv"
    sti_types: List[str] = Field(default_factory=list)
    counties: List[str] = Field(default_factory=list)

class WHOExportOut(Schema):
    """WHO export metadata"""
    export_id: UUID
    export_format: str
    data_period: str
    record_count: int
    file_size_mb: float
    generated_at: datetime
    who_ready: bool
    download_url: str

class SurveillanceDataPoint(Schema):
    """Individual non-identifiable surveillance data point"""
    reporting_period: str
    county: str
    sub_county: Optional[str]
    sti_type: str
    age_group: str
    sex: str
    case_count: int
    incidence_rate: Optional[float]
    tests_conducted: int
    tests_positive: int
    treatment_initiated: int