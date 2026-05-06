from ninja import Schema, Field
from typing import List, Dict, Optional, Literal, Annotated
from uuid import UUID
from datetime import datetime

# --- Input Schemas ---

class SymptomInput(Schema):
    """32 binary symptom features from patient form"""
    genital_discharge: bool = False
    painful_urination: bool = False
    genital_sores: bool = False
    pelvic_pain: bool = False
    testicular_pain: bool = False
    abnormal_bleeding: bool = False
    itching: bool = False
    fever: bool = False
    rash: bool = False
    swollen_lymph_nodes: bool = False
    # ... (remaining 22 symptoms)
    # Additional symptoms as needed
    other_symptoms: Dict[str, bool] = Field(default_factory=dict)

class RiskBehaviourInput(Schema):
    partner_count_12m: int = Field(default=0, ge=0, le=50)
    condom_use_frequency: Literal["never", "sometimes", "often", "always"] = "never"
    prior_testing_history: bool = False
    substance_use: bool = False
    sex_work_exposure: bool = False
    msm_msw_indicator: Optional[Literal["msm", "msw", "none"]] = "none"

class DemographicsInput(Schema):
    age: Annotated[int, Field(ge=13, le=100)]
    sex: Literal["male", "female", "other"]
    geographic_region: str = Field(..., min_length=1, max_length=50)
    sub_county: Optional[str] = None

class RawPatientRecord(Schema):
    """Raw input from patient form or API"""
    source: Literal["who_api", "moh_db", "patient_form", "geolocation"]
    symptoms: SymptomInput
    risk_behaviours: RiskBehaviourInput
    demographics: DemographicsInput
    prior_sti_history: List[str] = Field(default_factory=list)
    sti_diagnoses: Optional[List[str]] = Field(None, description="Confirmed STI labels for training")

# --- Processing Config Schemas ---

def _default_deduplication_keys() -> List[str]:
    return ["age", "sex", "geographic_region"]

def _default_target_classes() -> List[str]:
    return ["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "none"]

class PreprocessingConfig(Schema):
    """Configuration for a preprocessing run"""
    apply_deduplication: bool = True
    deduplication_keys: List[str] = Field(default_factory=_default_deduplication_keys)
    imputation_strategy: Literal["mean", "median", "mode", "knn"] = "median"
    apply_smote: bool = True
    smote_sampling_strategy: Literal["auto", "minority", "not majority"] = "auto"
    apply_differential_privacy: bool = True
    dp_epsilon: float = Field(default=0.1, gt=0, le=1.0)
    k_anonymity: int = Field(default=10, ge=5, le=50)
    target_classes: List[str] = Field(default_factory=_default_target_classes)

class BatchProcessRequest(Schema):
    """Request to start a preprocessing batch job"""
    source: Literal["who_api", "moh_db", "patient_form", "geolocation"]
    records: List[RawPatientRecord]
    config: PreprocessingConfig

class SingleProcessRequest(Schema):
    """Request to process a single record (real-time)"""
    record: RawPatientRecord
    config: Optional[PreprocessingConfig] = Field(default_factory=PreprocessingConfig)

# --- Output Schemas ---

class ProcessedFeatures(Schema):
    """Engineered feature output"""
    symptom_vector: List[int] = Field(..., min_length=32, max_length=32)
    composite_risk_score: float = Field(..., ge=0.0, le=1.0)
    age_encoded: float
    sex_encoded: int
    region_encoded: int
    temporal_features: Dict[str, float]
    behavioural_embedding: List[float]

class ProcessedRecordOut(Schema):
    """Output schema for a processed record"""
    anonymous_id: str
    features: ProcessedFeatures
    sti_probabilities: Optional[Dict[str, float]] = None
    risk_level: Literal["low", "moderate", "high", "critical"]
    geographic_region: str
    k_anonymity_group: Optional[int] = None
    privacy_applied: bool

class PreprocessingJobOut(Schema):
    """Job status response"""
    job_id: UUID
    source: str
    status: str
    raw_record_count: int
    processed_record_count: int
    duplicate_count: int
    stages: Dict[str, Optional[datetime]]
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_log: Optional[str] = None

class HealthCheckOut(Schema):
    """Service health status"""
    status: str
    pipeline_ready: bool
    active_jobs: int
    last_completion: Optional[datetime] = None