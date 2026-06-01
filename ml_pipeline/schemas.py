from ninja import Schema, Field
from typing import List, Dict, Optional, Literal, Any,Annotated
from uuid import UUID
from datetime import date, datetime
from pydantic import confloat, conint


# ---------------------------------------------------------------------------
# Training schemas
# ---------------------------------------------------------------------------

class ClassifierHyperparameters(Schema):
    """XGBoost + Random Forest ensemble hyperparameters"""
    # XGBoost
    xgb_n_estimators: Annotated[int, Field(ge=100, le=2000)] = 500
    xgb_max_depth: Annotated[int, Field(ge=2, le=12)] = 6
    xgb_learning_rate: Annotated[float, Field(gt=0.0, le=0.5)] = 0.05
    xgb_subsample: Annotated[float, Field(ge=0.5, le=1.0)] = 0.8
    xgb_colsample_bytree: Annotated[float, Field(ge=0.5, le=1.0)] = 0.8
    xgb_scale_pos_weight: Optional[Annotated[float, Field(ge=0.0)]] = None  # Auto-computed from class dist if None

    # Random Forest
    rf_n_estimators: Annotated[int, Field(ge=50, le=1000)] = 200
    rf_max_depth: Optional[Annotated[int, Field(ge=1, le=10)]] = None  # None = unlimited
    rf_min_samples_split: Annotated[int, Field(ge=2, le=20)] = 4

    # Voting ensemble weights
    ensemble_weight_xgb: Annotated[float, Field(ge=0.0, le=1.0)] = 0.6
    ensemble_weight_rf: Annotated[float, Field(ge=0.0, le=1.0)] = 0.4

    # Threshold tuning
    decision_threshold: Annotated[float, Field(ge=0.1, le=0.9)] = 0.5
    clinical_alert_threshold: Annotated[float, Field(ge=0.5, le=0.95)] = 0.7


class LSTMHyperparameters(Schema):
    """LSTM pattern predictor hyperparameters"""
    hidden_size: Annotated[int, Field(ge=32, le=512)] = 128
    num_layers: Annotated[int, Field(ge=1, le=4)] = 2
    dropout: Annotated[float, Field(ge=0.0, le=0.5)] = 0.2
    learning_rate: Annotated[float, Field(gt=0.0, le=0.1)] = 0.001
    batch_size: Annotated[int, Field(ge=8, le=256)] = 32
    epochs: Annotated[int, Field(ge=10, le=500)] = 100
    sequence_length: Annotated[int, Field(ge=6, le=60)] = 24  # months of look-back
    early_stopping_patience: Annotated[int, Field(ge=3, le=30)] = 10


class TrainingJobRequest(Schema):
    """Request to start a training job"""
    model_type: Literal["risk_classifier", "pattern_predictor", "hotspot_engine"]
    training_data_start: date
    training_data_end: date
    trigger: Literal["scheduled", "drift_alert", "manual", "data_update"] = "manual"
    classifier_params: Optional[ClassifierHyperparameters] = None
    lstm_params: Optional[LSTMHyperparameters] = None
    # Geospatial engine uses config from geospatial app — no extra params needed here


class TrainingJobOut(Schema):
    job_id: UUID
    model_type: str
    status: str
    trigger: str
    training_data_start: date
    training_data_end: date
    record_count: int
    class_distribution: Dict[str, int]
    hyperparameters: Dict[str, Any]
    resulting_model_id: Optional[UUID] = None
    error_log: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Model registry schemas
# ---------------------------------------------------------------------------

class MLModelOut(Schema):
    model_id: UUID
    model_type: str
    version: str
    mlflow_run_id: str
    artefact_path: str
    feature_schema_version: str
    evaluation_metrics: Dict[str, Any]
    meets_deployment_threshold: bool
    psi_score: Optional[float]
    drift_alert_active: bool
    is_active: bool
    clinical_validation_completed: bool
    validated_by: str
    validated_at: Optional[datetime]
    created_at: datetime


class ActivateModelRequest(Schema):
    """Promote a model version to active. Requires clinical validation."""
    model_id: UUID
    validated_by: str = Field(..., min_length=3, max_length=200)
    validation_notes: str = Field(default="", max_length=2000)


# ---------------------------------------------------------------------------
# Inference — risk classifier
# ---------------------------------------------------------------------------

class SHAPFeatureContribution(Schema):
    feature: str
    shap_value: float
    direction: Literal["increases_risk", "decreases_risk"]
    display_label: str


class STIProbabilityOut(Schema):
    """Per-class probability scores from the classifier ensemble"""
    hiv: float
    chlamydia: float
    syphilis: float
    gonorrhoea: float
    hpv: float
    hsv2: float
    none: float


class RiskPredictionOut(Schema):
    prediction_id: UUID
    anonymous_id: str
    model_version_id: UUID
    model_version: str

    sti_probabilities: STIProbabilityOut
    predicted_class: str
    overall_risk_level: Literal["low", "moderate", "high", "critical"]
    overall_risk_score: float = Field(..., ge=0.0, le=1.0)

    # Explainability — top 3 features
    top_features: List[SHAPFeatureContribution]
    confidence_lower: Optional[float]
    confidence_upper: Optional[float]

    # Clinical gate status
    clinical_review_required: bool
    clinical_review_completed: bool

    created_at: datetime


class InferenceRequest(Schema):
    """
    Submit a preprocessed anonymous record for risk scoring.
    Must supply the anonymous_id from the preprocessing pipeline.
    """
    anonymous_id: str = Field(..., min_length=32, max_length=64)
    # Feature vector as produced by PreprocessingPipeline.process_single_record()
    symptom_vector: List[int] = Field(..., min_length=32, max_length=32)
    composite_risk_score: Annotated[float, Field(ge=0.0, le=1.0)] = Field(..., ge=0.0, le=1.0)  # (ge=0.0, le=1.0)
    age_encoded: Annotated[int, Field(ge=13, le=100)]
    sex_encoded: Annotated[int, Field(ge=0, le=2)]
    region_encoded: Annotated[int, Field(ge=0, le=10)]
    temporal_features: Dict[str, Annotated[float, Field(ge=0.0, le=1.0)]]
    behavioural_embedding: List[Annotated[float, Field(ge=0.0, le=1.0)]]
    prior_sti_history: List[str] = Field(default_factory=list)
    compute_shap: bool = True


# ---------------------------------------------------------------------------
# Inference — outbreak forecasting
# ---------------------------------------------------------------------------

class ForecastRequest(Schema):
    county: str = Field(..., min_length=1, max_length=50)
    sti_type: Literal["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "all"] = "all"
    baseline_months: Annotated[int, Field(ge=12, le=60)] = 60  # months of historical data to use


class HorizonForecast(Schema):
    rate_per_100k: float
    lower_95: float
    upper_95: float
    delta_vs_baseline_pct: Optional[float]


class OutbreakForecastOut(Schema):
    forecast_id: UUID
    county: str
    sti_type: str
    forecast_generated_on: date
    baseline_incidence_rate: float
    forecast_30d: HorizonForecast
    forecast_60d: HorizonForecast
    forecast_90d: HorizonForecast
    year_over_year_delta_pct: Optional[float]
    trend_direction: Literal["rising", "stable", "declining"]
    lstm_mape: Optional[float]
    prophet_mape: Optional[float]
    model_version_id: UUID


# ---------------------------------------------------------------------------
# Drift & monitoring
# ---------------------------------------------------------------------------

class DriftReportOut(Schema):
    report_id: UUID
    model_version_id: UUID
    model_version: str
    report_date: date
    psi_score: float
    feature_psi: Dict[str, float]
    alert_triggered: bool
    subgroup_auc: Dict[str, float]
    bias_flag: bool
    notes: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditLogOut(Schema):
    log_id: UUID
    event_type: str
    prediction_id: Optional[UUID]
    model_version_id: Optional[UUID]
    anonymous_id: str
    actor: str
    payload: Dict[str, Any]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Clinical review
# ---------------------------------------------------------------------------

class ClinicalReviewRequest(Schema):
    prediction_id: UUID
    reviewed_by: str = Field(..., min_length=3, max_length=100)
    approved: bool
    clinical_notes: str = Field(default="", max_length=2000)


class ClinicalReviewOut(Schema):
    prediction_id: UUID
    clinical_review_completed: bool
    reviewed_by: str
    reviewed_at: datetime
    approved: bool