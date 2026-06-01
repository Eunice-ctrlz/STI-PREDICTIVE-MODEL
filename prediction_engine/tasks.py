"""
STI Predictive Model — ML Pipeline (L3)
api.py

Django Ninja REST API for the ML pipeline layer.
Endpoints cover:
  - Training job submission (all three models)
  - Inference (classifier + forecaster)
  - Model version management (list, promote, archive)
  - Clinical validation sign-off
  - Drift and bias audit status
"""

import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import UUID

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema, Field
from ninja.errors import HttpError

from .models import (
    ModelType, ModelVersion, ModelStage, TrainingJob, TrainingStatus,
    TriggerType, DriftAlert, BiasAuditRecord,
)
from .tasks import (
    train_risk_classifier_task,
    train_pattern_predictor_task,
    train_geospatial_engine_task,
)
from .regestry import ModelRegistry

router = Router()


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class TrainClassifierRequest(Schema):
    training_data_start: Optional[date] = None   # Default: 5 years ago
    training_data_end: Optional[date] = None     # Default: today
    xgb_params: Optional[dict] = None
    rf_params: Optional[dict] = None


class TrainForecasterRequest(Schema):
    training_data_start: Optional[date] = None
    training_data_end: Optional[date] = None
    lstm_params: Optional[dict] = None
    prophet_params: Optional[dict] = None


class TrainGeoRequest(Schema):
    training_data_start: Optional[date] = None
    training_data_end: Optional[date] = None
    dbscan_params: Optional[dict] = None


class TrainingJobOut(Schema):
    job_id: UUID
    model_type: str
    status: str
    trigger: str
    training_record_count: int
    passed_thresholds: Optional[bool]
    metrics: dict
    mlflow_run_id: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    error_log: Optional[str] = None


class ModelVersionOut(Schema):
    version_id: UUID
    model_type: str
    stage: str
    mlflow_model_name: str
    mlflow_model_version: str
    mlflow_run_id: str
    model_hash: str
    auc_roc_mean: Optional[float]
    f1_mean: Optional[float]
    mape: Optional[float]
    clinical_validation_passed: bool
    clinical_validated_by: str
    clinical_validated_at: Optional[datetime]
    promoted_to_production_at: Optional[datetime]
    created_at: datetime


class ClassifyRequest(Schema):
    """Single-record inference request"""
    symptom_vector: List[int] = Field(..., min_length=32, max_length=32)
    composite_risk_score: float = Field(..., ge=0.0, le=1.0)
    age_encoded: int
    sex_encoded: int
    region_encoded: int
    temporal_features: dict = Field(default_factory=dict)
    prior_sti_history: List[str] = Field(default_factory=list)


class ClassifyResponse(Schema):
    sti_probabilities: dict
    risk_level: str
    clinical_review_required: bool
    top_features: List[dict]
    model_version: str
    model_hash: str


class ForecastRequest(Schema):
    county: str
    sti_type: str
    history: List[dict]  # Monthly incidence records
    horizons: Optional[List[int]] = None  # Default: [30, 60, 90]


class ForecastResponse(Schema):
    county: str
    sti_type: str
    forecast_date: str
    forecasts: dict
    model_version: str


class ClinicalApprovalRequest(Schema):
    clinician_name: str = Field(..., min_length=2)
    clinician_credential: str = Field(..., min_length=3,
                                      description="e.g. 'MD, Infectious Disease Specialist'")


class DriftAlertOut(Schema):
    alert_id: UUID
    model_type: str
    psi_score: float
    features_drifted: List[str]
    retraining_triggered: bool
    created_at: datetime


class BiasAuditOut(Schema):
    audit_id: UUID
    model_type: str
    audit_period_start: date
    audit_period_end: date
    auc_by_age_group: dict
    auc_by_sex: dict
    auc_by_region: dict
    any_subgroup_below_threshold: bool
    flagged_subgroups: List[str]
    retraining_recommended: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Training Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/train/classifier",
    response=TrainingJobOut,
    tags=["Training"],
    summary="Queue STI Risk Classifier training job",
)
def queue_classifier_training(request, payload: TrainClassifierRequest):
    """
    Queue a training job for the XGBoost + Random Forest risk classifier.
    Uses a rolling 5-year window by default.
    The resulting model version enters STAGING until clinical validation is approved.
    """
    today = date.today()
    job = TrainingJob.objects.create(
        model_type=ModelType.RISK_CLASSIFIER,
        trigger=TriggerType.MANUAL,
        training_data_start=payload.training_data_start or (today - timedelta(days=5 * 365)),
        training_data_end=payload.training_data_end or today,
        hyperparameters={
            "xgb_params": payload.xgb_params or {},
            "rf_params": payload.rf_params or {},
        },
    )
    train_risk_classifier_task.delay(
        str(job.job_id),
        xgb_params=payload.xgb_params,
        rf_params=payload.rf_params,
    )
    return _job_to_schema(job)


@router.post(
    "/train/forecaster",
    response=TrainingJobOut,
    tags=["Training"],
    summary="Queue Outbreak Pattern Predictor training job",
)
def queue_forecaster_training(request, payload: TrainForecasterRequest):
    """Queue LSTM + Prophet forecaster training."""
    today = date.today()
    job = TrainingJob.objects.create(
        model_type=ModelType.PATTERN_PREDICTOR,
        trigger=TriggerType.MANUAL,
        training_data_start=payload.training_data_start or (today - timedelta(days=5 * 365)),
        training_data_end=payload.training_data_end or today,
        hyperparameters={
            "lstm_params": payload.lstm_params or {},
            "prophet_params": payload.prophet_params or {},
        },
    )
    train_pattern_predictor_task.delay(
        str(job.job_id),
        lstm_params=payload.lstm_params,
        prophet_params=payload.prophet_params,
    )
    return _job_to_schema(job)


@router.post(
    "/train/geospatial",
    response=TrainingJobOut,
    tags=["Training"],
    summary="Queue Geospatial Hotspot Engine run",
)
def queue_geospatial_run(request, payload: TrainGeoRequest):
    """Queue a DBSCAN + KDE geospatial hotspot analysis run."""
    today = date.today()
    job = TrainingJob.objects.create(
        model_type=ModelType.GEOSPATIAL_ENGINE,
        trigger=TriggerType.MANUAL,
        training_data_start=payload.training_data_start or (today - timedelta(days=90)),
        training_data_end=payload.training_data_end or today,
        hyperparameters={"dbscan_params": payload.dbscan_params or {}},
    )
    train_geospatial_engine_task.delay(str(job.job_id), dbscan_params=payload.dbscan_params)
    return _job_to_schema(job)


@router.get(
    "/train/jobs/{job_id}",
    response=TrainingJobOut,
    tags=["Training"],
    summary="Get training job status",
)
def get_training_job(request, job_id: UUID):
    job = get_object_or_404(TrainingJob, job_id=job_id)
    return _job_to_schema(job)


@router.get(
    "/train/jobs",
    response=List[TrainingJobOut],
    tags=["Training"],
    summary="List training jobs",
)
def list_training_jobs(
    request,
    model_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
):
    qs = TrainingJob.objects.all()
    if model_type:
        qs = qs.filter(model_type=model_type)
    if status:
        qs = qs.filter(status=status)
    return [_job_to_schema(j) for j in qs[:limit]]


# ---------------------------------------------------------------------------
# Inference Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/predict/classify",
    response=ClassifyResponse,
    tags=["Inference"],
    summary="Run STI risk classification on a single record",
)
def classify_record(request, payload: ClassifyRequest):
    """
    Run the production STI risk classifier on a preprocessed record.
    Returns per-class probabilities, risk level, SHAP top features,
    and a flag if clinical review is required (score > 0.7).

    The model version must have passed clinical validation before
    this endpoint will return results (§8.2 compliance gate).
    """
    try:
        registry = ModelRegistry()
        classifier = registry.load_classifier()
    except RuntimeError as exc:
        raise HttpError(503, str(exc))

    record = payload.dict()
    result = classifier.predict(record)

    version = registry.get_active_version(ModelType.RISK_CLASSIFIER)
    return ClassifyResponse(
        sti_probabilities=result["sti_probabilities"],
        risk_level=result["risk_level"],
        clinical_review_required=result["clinical_review_required"],
        top_features=result["top_features"],
        model_version=str(version.mlflow_model_version),
        model_hash=result["model_hash"] or "",
    )


@router.post(
    "/predict/forecast",
    response=ForecastResponse,
    tags=["Inference"],
    summary="Generate outbreak forecast for a county/STI type",
)
def forecast_outbreak(request, payload: ForecastRequest):
    """
    Generate 30/60/90-day incidence rate forecasts for a given county
    and STI type. Requires a production pattern predictor to be available.
    """
    try:
        registry = ModelRegistry()
        forecaster = registry.load_forecaster()
    except RuntimeError as exc:
        raise HttpError(503, str(exc))

    try:
        result = forecaster.forecast(
            county=payload.county,
            sti_type=payload.sti_type,
            history=payload.history,
            horizons=payload.horizons,
        )
    except ValueError as exc:
        raise HttpError(404, str(exc))

    version = registry.get_active_version(ModelType.PATTERN_PREDICTOR)
    return ForecastResponse(
        county=result["county"],
        sti_type=result["sti_type"],
        forecast_date=result["forecast_date"],
        forecasts=result["forecasts"],
        model_version=str(version.mlflow_model_version),
    )


# ---------------------------------------------------------------------------
# Model Version Management
# ---------------------------------------------------------------------------

@router.get(
    "/versions",
    response=List[ModelVersionOut],
    tags=["Model Management"],
    summary="List all model versions",
)
def list_model_versions(
    request,
    model_type: Optional[str] = None,
    stage: Optional[str] = None,
):
    registry = ModelRegistry()
    versions = registry.list_versions(model_type=model_type, stage=stage)
    return [_version_to_schema(v) for v in versions]


@router.get(
    "/versions/{version_id}",
    response=ModelVersionOut,
    tags=["Model Management"],
)
def get_model_version(request, version_id: UUID):
    version = get_object_or_404(ModelVersion, version_id=version_id)
    return _version_to_schema(version)


@router.post(
    "/versions/{version_id}/approve",
    response=ModelVersionOut,
    tags=["Model Management"],
    summary="Record clinical validation approval",
)
def approve_clinical_validation(
    request, version_id: UUID, payload: ClinicalApprovalRequest
):
    """
    Record clinical sign-off for a model version (§8.2 compliance gate).
    The version must be in PENDING_CLINICAL stage.
    After approval, the version can be promoted to production.
    """
    registry = ModelRegistry()
    try:
        version = registry.approve_clinical_validation(
            str(version_id),
            payload.clinician_name,
            payload.clinician_credential,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return _version_to_schema(version)


@router.post(
    "/versions/{version_id}/promote",
    response=ModelVersionOut,
    tags=["Model Management"],
    summary="Promote a clinically validated model version to production",
)
def promote_to_production(request, version_id: UUID):
    """
    Promote a model version to production.
    Blocked if clinical_validation_passed is False (§8.2 hard constraint).
    """
    registry = ModelRegistry()
    try:
        version = registry.promote_to_production(str(version_id))
    except PermissionError as exc:
        raise HttpError(403, str(exc))
    return _version_to_schema(version)


@router.post(
    "/versions/{version_id}/archive",
    response=ModelVersionOut,
    tags=["Model Management"],
    summary="Archive a model version",
)
def archive_version(request, version_id: UUID):
    registry = ModelRegistry()
    version = registry.archive_version(str(version_id))
    return _version_to_schema(version)


# ---------------------------------------------------------------------------
# Drift & Bias Monitoring
# ---------------------------------------------------------------------------

@router.get(
    "/drift/alerts",
    response=List[DriftAlertOut],
    tags=["Monitoring"],
    summary="List drift alerts",
)
def list_drift_alerts(
    request,
    model_type: Optional[str] = None,
    limit: int = 20,
):
    qs = DriftAlert.objects.all()
    if model_type:
        qs = qs.filter(model_type=model_type)
    return [
        DriftAlertOut(
            alert_id=a.alert_id,
            model_type=a.model_type,
            psi_score=a.psi_score,
            features_drifted=a.features_drifted,
            retraining_triggered=a.retraining_triggered,
            created_at=a.created_at,
        )
        for a in qs[:limit]
    ]


@router.get(
    "/bias/audits",
    response=List[BiasAuditOut],
    tags=["Monitoring"],
    summary="List bias audit records",
)
def list_bias_audits(request, limit: int = 10):
    audits = BiasAuditRecord.objects.all()[:limit]
    return [
        BiasAuditOut(
            audit_id=a.audit_id,
            model_type=a.model_version.model_type,
            audit_period_start=a.audit_period_start,
            audit_period_end=a.audit_period_end,
            auc_by_age_group=a.auc_by_age_group,
            auc_by_sex=a.auc_by_sex,
            auc_by_region=a.auc_by_region,
            any_subgroup_below_threshold=a.any_subgroup_below_threshold,
            flagged_subgroups=a.flagged_subgroups,
            retraining_recommended=a.retraining_recommended,
            created_at=a.created_at,
        )
        for a in audits
    ]


@router.get(
    "/health",
    tags=["Health"],
    summary="ML pipeline health check",
)
def ml_pipeline_health(request):
    registry = ModelRegistry()
    health = {}
    for model_type in [
        ModelType.RISK_CLASSIFIER,
        ModelType.PATTERN_PREDICTOR,
        ModelType.GEOSPATIAL_ENGINE,
    ]:
        try:
            version = registry.get_active_version(model_type)
            health[model_type] = {
                "status": "ready",
                "version": version.mlflow_model_version,
                "clinical_validated": version.clinical_validation_passed,
                "promoted_at": version.promoted_to_production_at.isoformat()
                if version.promoted_to_production_at else None,
            }
        except RuntimeError:
            health[model_type] = {"status": "no_production_model"}

    active_jobs = TrainingJob.objects.filter(
        status__in=[TrainingStatus.PENDING, TrainingStatus.RUNNING]
    ).count()

    return {
        "status": "healthy",
        "models": health,
        "active_training_jobs": active_jobs,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_to_schema(job: TrainingJob) -> TrainingJobOut:
    return TrainingJobOut(
        job_id=job.job_id,
        model_type=job.model_type,
        status=job.status,
        trigger=job.trigger,
        training_record_count=job.training_record_count,
        passed_thresholds=job.passed_thresholds,
        metrics=job.metrics or {},
        mlflow_run_id=job.mlflow_run_id or "",
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        error_log=job.error_log or None,
    )


def _version_to_schema(version: ModelVersion) -> ModelVersionOut:
    return ModelVersionOut(
        version_id=version.version_id,
        model_type=version.model_type,
        stage=version.stage,
        mlflow_model_name=version.mlflow_model_name,
        mlflow_model_version=version.mlflow_model_version,
        mlflow_run_id=version.mlflow_run_id,
        model_hash=version.model_hash,
        auc_roc_mean=version.auc_roc_mean,
        f1_mean=version.f1_mean,
        mape=version.mape,
        clinical_validation_passed=version.clinical_validation_passed,
        clinical_validated_by=version.clinical_validated_by or "",
        clinical_validated_at=version.clinical_validated_at,
        promoted_to_production_at=version.promoted_to_production_at,
        created_at=version.created_at,
    )