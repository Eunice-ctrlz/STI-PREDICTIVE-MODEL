from ninja import Schema, Field
from typing import List, Dict, Optional, Literal,Annotated
from uuid import UUID
from datetime import date, datetime

# --- Feature Input Schemas ---

class SymptomFeatures(Schema):
    """32 binary symptom features"""
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
    rectal_pain: bool = False
    rectal_bleeding: bool = False
    sore_throat: bool = False
    joint_pain: bool = False
    hair_loss: bool = False
    weight_loss: bool = False
    night_sweats: bool = False
    fatigue: bool = False
    nausea: bool = False
    vomiting: bool = False
    diarrhoea: bool = False
    abdominal_pain: bool = False
    back_pain: bool = False
    dysuria: bool = False
    dyspareunia: bool = False
    menorrhagia: bool = False
    metrorrhagia: bool = False
    urethral_discharge: bool = False
    vaginal_odour: bool = False
    dysmenorrhoea: bool = False
    proctitis: bool = False
    lymphadenopathy: bool = False

class BehaviourFeatures(Schema):
    """Behavioural risk features"""
    partner_count_12m: Annotated[int, Field(ge=0, le=50)] = 0
    new_partners_3m: Annotated[int, Field(ge=0, le=20)] = 0
    condom_use_frequency: Literal["never", "sometimes", "often", "always"] = "never"
    prior_sti_test_12m: bool = False
    prior_sti_diagnosis_count: Annotated[int, Field(ge=0, le=10)] = 0
    substance_use: bool = False
    sex_work_exposure: bool = False

class DemographicFeatures(Schema):
    """Demographic features"""
    age: Annotated[int, Field(ge=13, le=100)]
    sex: Literal["male", "female", "other"]
    geographic_region: str

class ModelInputFeatures(Schema):
    """Complete feature vector for model inference"""
    symptoms: SymptomFeatures
    behaviours: BehaviourFeatures
    demographics: DemographicFeatures
    temporal_features: Optional[Dict[str, float]] = None

# --- Classification Output ---

class STIProbability(Schema):
    """Probability for a single STI class"""
    sti_type: Literal["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "none"]
    probability: Annotated[float, Field(ge=0.0, le=1.0)]
    confidence_interval_lower: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = None
    confidence_interval_upper: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = None

class ClassificationResult(Schema):
    """STI risk classifier output"""
    model_id: Optional[UUID]
    model_version: str
    overall_risk_level: Literal["low", "moderate", "high", "critical"]
    overall_risk_score: Annotated[float, Field(ge=0.0, le=1.0)]
    sti_probabilities: List[STIProbability]
    top_features: List[Dict[str, any]]
    clinical_review_required: bool = False

# --- Forecasting Output ---

class ForecastPoint(Schema):
    """Single forecast data point"""
    date: date
    predicted_incidence: float
    confidence_lower: float
    confidence_upper: float

class OutbreakForecast(Schema):
    """Outbreak forecast for a region"""
    model_id: Optional[UUID]
    model_version: str
    county: str
    sti_type: str
    forecast_horizon_days: Annotated[int, Field(ge=30, le=90)]
    forecast_points: List[ForecastPoint]
    peak_predicted_date: Optional[date] = None
    trend_direction: Literal["increasing", "decreasing", "stable"]

# --- Training Schemas ---

class TrainingConfig(Schema):
    """Configuration for model training"""
    model_type: Literal["classifier", "forecaster"]
    training_data_start: date
    training_data_end: date
    hyperparameters: Optional[Dict] = None
    
    # Classifier specific
    smote_sampling: Literal["auto", "minority", "not_majority"] = "auto"
    class_weight: Literal["balanced", "balanced_subsample"] = "balanced"
    
    # Forecaster specific
    forecast_horizon: Literal[30, 60, 90] = 30
    lstm_units: Annotated[int, Field(ge=32, le=256)] = 128
    prophet_seasonality: bool = True

class TrainingJobOut(Schema):
    """Training job status"""
    job_id: UUID
    model_type: str
    status: str
    epochs_completed: int
    current_loss: Optional[float]
    created_at: datetime
    completed_at: Optional[datetime]

class ModelEvaluation(Schema):
    """Model evaluation metrics"""
    model_id: UUID
    model_version: str
    auc_roc: Dict[str, float]
    f1_score: Dict[str, float]
    precision: Dict[str, float]
    recall: Dict[str, float]
    calibration_error: float
    meets_deployment_threshold: bool

# --- Drift Detection ---

class DriftReport(Schema):
    """Population drift detection report"""
    log_id: UUID
    model_version: str
    psi_score: float
    threshold: float
    features_drifted: List[str]
    retraining_triggered: bool
    detected_at: datetime