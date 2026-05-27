from ninja import Schema, Field
from typing import List, Dict, Optional, Literal, Annotated, Any
from uuid import UUID
from datetime import date, datetime
from pydantic import confloat, conint

# --- Clinician Profile Schemas ---

class ClinicianRegistration(Schema):
    """Registration for new clinician"""
    username: str = Field(..., min_length=3, max_length=150)
    email: str
    password: str = Field(..., min_length=8)
    first_name: str
    last_name: str
    license_number: str = Field(..., min_length=5, max_length=50)
    license_issuing_body: str
    license_expiry_date: date
    role: Literal["gp", "ids", "pho", "lab", "moh"]
    facility_name: str
    facility_county: str
    facility_sub_county: str
    specialization: Optional[str] = None

class ClinicianProfileOut(Schema):
    clinician_id: UUID
    full_name: str
    role: str
    role_display: str
    license_number: str
    verification_status: str
    facility_name: str
    facility_county: str
    can_view_population_data: bool
    can_approve_guidance: bool
    can_override_threshold: bool

class ClinicianVerification(Schema):
    """MOH verification of clinician"""
    license_number: str
    verification_status: Literal["verified", "suspended", "expired"]
    verified_by: str
    notes: Optional[str] = None

# --- Clinical Guidance Schemas ---

class GuidanceDraft(Schema):
    """Draft new clinical guidance"""
    title: str = Field(..., min_length=10, max_length=200)
    sti_type: Literal["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "general"]
    risk_level: Literal["low", "moderate", "high", "critical"]
    symptom_pattern: Dict[str, List[str]]
    differential_diagnosis: List[Dict[str, Any]]
    recommended_tests: List[str]
    treatment_protocol: Dict
    referral_criteria: List[str]
    patient_counseling_points: List[str]

class GuidanceReview(Schema):
    """Review existing guidance"""
    guidance_id: UUID
    review_action: Literal["approve", "reject", "request_changes"]
    reviewer_name: str
    reviewer_credentials: str
    comments: Optional[str] = None

class GuidanceOut(Schema):
    guidance_id: UUID
    title: str
    sti_type: str
    risk_level: str
    differential_diagnosis: List[Dict]
    recommended_tests: List[str]
    treatment_protocol: Dict
    referral_criteria: List[str]
    patient_counseling_points: List[str]
    validation_status: str
    version: int
    moh_approved: bool
    deployed_at: Optional[datetime]

# --- Patient Risk Alert Schemas ---

class RiskAlertOut(Schema):
    alert_id: UUID
    anonymous_id: str
    risk_score: Annotated[float, Field(ge=0.0, le=1.0)]
    risk_level: str
    sti_probabilities: Dict[str, float]
    top_features: List[Dict[str, Any]]
    status: str
    triggered_at: datetime
    clinician_notes: Optional[str]
    recommended_action: Optional[str]

class AlertAction(Schema):
    """Action on a risk alert"""
    alert_id: UUID
    action: Literal["acknowledge", "review", "escalate", "resolve", "override"]
    clinician_notes: Optional[str] = None
    recommended_action: Optional[str] = None
    test_orders: Optional[List[str]] = None
    referral_destination: Optional[str] = None
    override_reason: Optional[str] = None  # Required for threshold_override

class AlertSummary(Schema):
    """Summary of alerts for clinician dashboard"""
    total_new: int
    total_acknowledged: int
    total_under_review: int
    total_critical_unacknowledged: int
    avg_risk_score: Optional[float]
    alerts: List[RiskAlertOut]

# --- Population Dashboard Schemas ---

class PopulationSummaryOut(Schema):
    summary_id: UUID
    reporting_period: str
    total_patients_assessed: int
    risk_distribution: Dict[str, int]
    sti_distribution: Dict[str, int]
    new_alerts: int
    resolved_alerts: int
    week_over_week_delta: Optional[float]
    trend_direction: Literal["improving", "stable", "worsening", "unknown"]

class SymptomDifferentialRequest(Schema):
    """Request symptom-driven differential diagnosis"""
    symptoms: List[str] = Field(..., min_length=1)
    demographics: Dict[str, Any]
    geographic_region: str

class SymptomDifferentialOut(Schema):
    """Ranked STI differentials with probability scores"""
    ranked_differentials: List[Dict[str, Any]]
    recommended_guidance_id: Optional[UUID]
    recommended_tests: List[str]
    urgency_level: Literal["routine", "urgent", "emergency"]

# --- Audit & Compliance Schemas ---

class AuditEntryOut(Schema):
    log_id: UUID
    action_type: str
    timestamp: datetime
    anonymous_id: Optional[str]
    risk_score: Optional[float]
    model_version: Optional[str]

class WeeklyReportOut(Schema):
    """Weekly regional incidence summary report"""
    report_period: str
    county: str
    total_assessments: int
    new_cases_suspected: int
    confirmed_cases: int
    testing_coverage: float
    treatment_initiation_rate: float
    alert_response_time_avg_hours: float
    guidance_utilization_rate: float