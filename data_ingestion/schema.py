"""
STI Predictive Model — Data Ingestion Layer (L1)
schemas.py

Pydantic/Ninja schemas for all four ingestion sources and job management.
"""

from ninja import Schema, Field
from typing import Optional, List, Dict, Literal, Any
from uuid import UUID
from datetime import datetime, date


# ---------------------------------------------------------------------------
# WHO API Schemas
# ---------------------------------------------------------------------------

class WHOSurveillanceRecord(Schema):
    """
    Single STI surveillance record from the WHO Global REST API.
    Maps to the WHO standard surveillance reporting format.
    """
    record_id: str = Field(..., description="WHO-assigned record identifier")
    country_code: str = Field(..., min_length=2, max_length=3, description="ISO 3166-1 alpha-2/3")
    region_code: str = Field(..., description="WHO regional office code (e.g. AFRO)")
    sti_type: Literal["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "other"]
    incidence_rate: float = Field(..., ge=0, description="Cases per 100,000 population")
    case_count: Optional[int] = Field(None, ge=0)
    reporting_period_start: date
    reporting_period_end: date
    population_denominator: Optional[int] = Field(None, ge=0)
    data_quality_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WHOIngestRequest(Schema):
    """Request to trigger a manual WHO API ingestion run"""
    sync_window_start: Optional[datetime] = None
    sync_window_end: Optional[datetime] = None
    sti_types: Optional[List[str]] = None  # None = all types
    country_codes: Optional[List[str]] = None  # None = all countries


# ---------------------------------------------------------------------------
# MOH HL7 FHIR Schemas
# ---------------------------------------------------------------------------

class MOHFHIRPatient(Schema):
    """
    Anonymised patient-level fields from the MOH HL7 FHIR resource.
    PII is stripped at source; only pseudonymised identifiers and
    clinically relevant fields are ingested.
    """
    fhir_resource_id: str
    pseudo_id: str = Field(..., description="Pseudonymised patient identifier from MOH system")
    age_band: Literal["<18", "18-24", "25-34", "35-44", "45+"]
    sex: Literal["male", "female", "unknown"]
    county: str
    sub_county: Optional[str] = None
    facility_code: str = Field(..., description="MOH facility code — not a geocode")


class MOHFHIRObservation(Schema):
    """
    Confirmed STI diagnosis observation from MOH FHIR Observation resource.
    """
    observation_id: str
    patient_pseudo_id: str
    sti_diagnosis: str = Field(..., description="SNOMED CT or ICD-10 code")
    sti_label: Literal["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "none"]
    confirmed_date: date
    treatment_initiated: Optional[bool] = None
    lab_confirmed: bool = False
    clinical_stage: Optional[str] = None


class MOHFHIRBundle(Schema):
    """
    HL7 FHIR Bundle wrapping patients + observations for a sync window.
    """
    bundle_id: str
    resource_type: Literal["Bundle"] = "Bundle"
    total: int
    patients: List[MOHFHIRPatient] = Field(default_factory=list)
    observations: List[MOHFHIRObservation] = Field(default_factory=list)
    sync_timestamp: datetime


class MOHIngestRequest(Schema):
    """Request to trigger a manual MOH FHIR ingestion run"""
    sync_window_start: Optional[datetime] = None
    sync_window_end: Optional[datetime] = None
    county_filter: Optional[List[str]] = None  # None = all counties


# ---------------------------------------------------------------------------
# Geolocation Schemas
# ---------------------------------------------------------------------------

class GeoGridCell(Schema):
    """
    One aggregated geospatial grid cell (±5km) from the PostGIS layer.
    Individual coordinates are never transmitted — only grid-snapped
    aggregates with differential privacy applied.
    """
    cell_id: str
    latitude_grid: float = Field(..., ge=-90, le=90)
    longitude_grid: float = Field(..., ge=-180, le=180)
    county: str
    sub_county: Optional[str] = None
    sti_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="STI type → case count. Suppressed if total < 100.",
    )
    total_cases: int = Field(..., ge=0)
    suppressed: bool = Field(
        default=False,
        description="True when cell count < minimum threshold (100)",
    )
    week_start: date


class GeoIngestRequest(Schema):
    """Request to trigger a geolocation layer sync"""
    week_start: Optional[date] = None  # None = current week
    county_filter: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Patient Form Schemas
# ---------------------------------------------------------------------------

class PatientFormSubmission(Schema):
    """
    Real-time submission from the patient-facing symptom form.
    Anonymous session ID only — no PII collected at any point.
    """
    session_id: str = Field(
        ...,
        description="Anonymous session identifier. No linkage to personal identity.",
    )
    # Symptom checklist — 32 binary fields (mapped from SymptomInput)
    symptoms: Dict[str, bool] = Field(
        ...,
        description="32-key symptom dict. Keys must match the canonical SYMPTOM_LIST.",
    )
    # Risk behaviour survey
    partner_count_12m: int = Field(default=0, ge=0, le=50)
    condom_use_frequency: Literal["never", "sometimes", "often", "always"] = "never"
    prior_testing_history: bool = False
    substance_use: bool = False
    sex_work_exposure: bool = False
    msm_msw_indicator: Optional[Literal["msm", "msw", "none"]] = "none"
    # Demographics (coarse — no individual geolocation)
    age: int = Field(..., ge=13, le=100)
    sex: Literal["male", "female", "other"]
    geographic_region: str = Field(..., min_length=1, max_length=50)
    sub_county: Optional[str] = None
    prior_sti_history: List[str] = Field(default_factory=list)
    # Consent
    data_consent_given: bool = Field(
        ...,
        description="Patient must explicitly consent before submission",
    )
    submitted_at: datetime


# ---------------------------------------------------------------------------
# Job / Response Schemas
# ---------------------------------------------------------------------------

class IngestionJobOut(Schema):
    """Response schema for any ingestion job"""
    job_id: UUID
    source: str
    status: str
    triggered_by: str
    raw_record_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    forwarded_count: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    error_log: Optional[str] = None
    preprocessing_job_id: Optional[UUID] = None


class IngestionSummaryOut(Schema):
    """Lightweight status summary for the health endpoint"""
    source: str
    last_run_status: Optional[str]
    last_run_at: Optional[datetime]
    total_jobs_today: int
    total_records_today: int


class ConflictResolutionPolicy(Schema):
    """
    Defines how to handle conflicting records between WHO and MOH sources
    (e.g. differing incidence counts for the same period and region).
    """
    strategy: Literal["prefer_moh", "prefer_who", "latest_wins", "flag_for_review"] = "prefer_moh"
    flag_threshold_pct: float = Field(
        default=20.0,
        ge=0,
        le=100,
        description="Flag if WHO and MOH counts diverge by more than this percentage",
    )


class IngestionHealthOut(Schema):
    """Overall ingestion layer health"""
    status: str
    sources: List[IngestionSummaryOut]
    active_jobs: int
    last_completion: Optional[datetime] = None