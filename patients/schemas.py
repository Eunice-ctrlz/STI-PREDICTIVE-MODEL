from ninja import Schema, Field
from typing import List, Dict, Optional, Literal, Annotated, Any
from uuid import UUID
from datetime import date, datetime
from pydantic import confloat, conint

# --- Symptom Checklist Schemas ---

class SymptomQuestion(Schema):
    """Individual symptom question for the 32-item checklist"""
    symptom_id: str
    question_text: str
    category: Literal["genital", "systemic", "urinary", "rectal", "oral", "other"]
    help_text: Optional[str] = None

class SymptomResponse(Schema):
    """Patient response to a symptom question"""
    symptom_id: str
    present: bool
    severity: Optional[Literal["mild", "moderate", "severe"]] = None
    duration_days: Optional[Annotated[int, Field(ge=0, le=365)]] = None

class SymptomChecklist(Schema):
    """Complete 32-item symptom checklist submission"""
    responses: List[SymptomResponse] = Field(..., min_length=1, max_length=32)

# --- Risk Behaviour Schemas ---

class BehaviourAssessment(Schema):
    """Behavioural risk assessment survey"""
    partner_count_12m: Annotated[int, Field(ge=0, le=50)] = 0
    new_partners_3m: Annotated[int, Field(ge=0, le=20)] = 0
    condom_use_frequency: Literal["never", "sometimes", "often", "always"] = "never"
    condom_use_last_time: bool = False
    prior_sti_test_12m: bool = False
    prior_sti_diagnosis: List[str] = Field(default_factory=list)
    substance_use_alcohol_drugs: bool = False
    sex_work_involvement: bool = False
    msm_msw_indicator: Optional[Literal["msm", "msw", "none", "prefer_not_say"]] = "prefer_not_say"
    partner_hiv_positive: Optional[bool] = None
    partner_hiv_status_unknown: bool = True

# --- Demographics Schemas ---

class PatientDemographics(Schema):
    """Minimal demographics — no identifying information"""
    age: Annotated[int, Field(ge=13, le=100)]
    sex: Literal["male", "female", "other", "prefer_not_say"]
    gender_identity: Optional[str] = None  # Free text, optional
    
    # Geographic context (county only for privacy)
    county: str = Field(..., min_length=1, max_length=50)
    sub_county: Optional[str] = None

# --- Assessment Submission ---

class AssessmentRequest(Schema):
    """Complete patient assessment request"""
    symptoms: SymptomChecklist
    behaviours: BehaviourAssessment
    demographics: PatientDemographics
    consent_reminders: bool = False
    consent_tracking: bool = False
    language: Literal["en", "sw"] = "en"

class AssessmentResponse(Schema):
    """Risk assessment result for patient"""
    assessment_id: UUID
    session_id: UUID
    
    # Risk result
    overall_risk_level: Literal["low", "moderate", "high", "critical"]
    overall_risk_score: Annotated[float, Field(ge=0.0, le=1.0)]
    
    # Per-STI probabilities (plain language, not medical jargon)
    sti_risks: List[Dict[str, Any]]
    
    # Top factors (explainability)
    top_factors: List[Dict[str, str]]
    
    # Plain-language explanation
    explanation: str
    what_this_means: str
    what_to_do_next: List[str]
    
    # Disclaimers
    disclaimer: str = "This is a risk assessment, not a diagnosis. Only a licensed clinician can diagnose STIs."
    mandatory_clinical_review: bool = False  # True if score > 0.7
    
    # Resources
    nearest_clinics: List[Dict[str, Any]]
    education_content_id: Optional[UUID] = None

# --- Session Management ---

class SessionCreate(Schema):
    """Create new anonymous session"""
    county: Optional[str] = None
    language: Literal["en", "sw"] = "en"

class SessionOut(Schema):
    session_id: UUID
    created_at: datetime
    expires_at: datetime
    status: str
    assessment_count: int

class SessionResume(Schema):
    """Resume existing session with ID"""
    session_id: UUID

# --- Result Tracking ---

class ResultEntry(Schema):
    """Self-reported test result"""
    test_date: date
    test_type: str
    result: Literal["negative", "positive", "inconclusive", "pending"]
    notes: Optional[str] = None

class ResultTrendOut(Schema):
    """Trend of results over time"""
    tracking_entries: List[Dict[str, Any]]
    risk_trend: Literal["improving", "stable", "worsening", "insufficient_data"]
    recommendation: str

# --- Reminder Schemas ---

class ReminderSchedule(Schema):
    """Schedule a testing reminder"""
    reminder_type: Literal["3_day", "1_week", "2_week", "1_month", "3_month"]

class ReminderOut(Schema):
    reminder_id: UUID
    scheduled_date: date
    reminder_type: str
    status: str

# --- Clinic Finder ---

class ClinicFinderRequest(Schema):
    """Find nearest testing clinics"""
    county: str
    sub_county: Optional[str] = None
    sti_concern: Optional[str] = None  # Filter by STI type
    max_distance_km: Annotated[float, Field(ge=1.0, le=100.0)] = 50.0

class ClinicOut(Schema):
    facility_id: str
    name: str
    county: str
    sub_county: str
    services: List[str]
    distance_km: Optional[float]
    operating_hours: Dict[str, str]
    contact_phone: Optional[str]
    walk_in_accepted: bool
    appointment_required: bool