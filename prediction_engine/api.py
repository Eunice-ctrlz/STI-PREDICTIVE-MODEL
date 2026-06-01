from ninja import Router, NinjaAPI
from typing import List, Optional
from datetime import date

from .schemas import (
    ModelInputFeatures, ClassificationResult, OutbreakForecast,
    TrainingConfig, TrainingJobOut, ModelEvaluation, DriftReport
)
from .classifier import STIRiskClassifier
from .forecaster import OutbreakForecaster
from .models import MLModelRegistry, TrainingJob, DriftDetectionLog

api = NinjaAPI(
    title="STI Prediction Engine API",
    version="1.0",
    urls_namespace="prediction_engine"
)
router = Router()

# Active model instances (in production, use singleton/registry)
_active_classifier = None
_active_forecaster = None

def get_classifier():
    global _active_classifier
    if _active_classifier is None:
        _active_classifier = STIRiskClassifier()
        # Load latest deployed model
        latest = MLModelRegistry.objects.filter(
            model_type="classifier",
            is_active=True
        ).first()
        if latest:
            _active_classifier.load(latest.artifact_path)
    return _active_classifier

@router.post("/predict/risk", response=ClassificationResult, tags=["Classification"])
def predict_risk(request, payload: ModelInputFeatures):
    """
    Predict STI risk from symptom and behavioural inputs.
    Spec Section 4.1.1: Outputs probability score 0-1 per class.
    """
    classifier = get_classifier()
    
    result = classifier.predict(
        symptoms=payload.symptoms.dict(),
        behaviours=payload.behaviours.dict(),
        demographics=payload.demographics.dict()
    )
    
    # Get active model metadata
    model = MLModelRegistry.objects.filter(
        model_type="classifier", is_active=True
    ).first()
    
    return ClassificationResult(
        model_id=model.model_id if model else None,
        model_version=model.version if model else "unknown",
        overall_risk_level=result["overall_risk_level"],
        overall_risk_score=result["overall_risk_score"],
        sti_probabilities=result["sti_probabilities"],
        top_features=result["top_features"],
        clinical_review_required=result["clinical_review_required"]
    )

@router.post("/forecast", response=OutbreakForecast, tags=["Forecasting"])
def forecast_outbreak(request, 
                      county: str,
                      sti_type: str,
                      horizon_days: int = 30):
    """
    Forecast outbreak trends for a county.
    Spec Section 4.1.2: 30/60/90-day incidence rate forecasts.
    """
    # In production, fetch recent data from database
    # For now, return placeholder
    return OutbreakForecast(
        model_id=None,
        model_version="v1.0",
        county=county,
        sti_type=sti_type,
        forecast_horizon_days=horizon_days,
        forecast_points=[],
        trend_direction="stable"
    )

@router.post("/train", response=TrainingJobOut, tags=["Training"])
def start_training(request, payload: TrainingConfig):
    """
    Start asynchronous model training job.
    """
    job = TrainingJob.objects.create(
        model_type=payload.model_type,
        status="queued",
        hyperparameters=payload.dict()
    )
    
    # Queue Celery task
    from .tasks import train_model_task
    train_model_task.delay(str(job.job_id), payload.dict())
    
    return TrainingJobOut(
        job_id=job.job_id,
        model_type=job.model_type,
        status=job.status,
        epochs_completed=0,
        current_loss=None,
        created_at=job.created_at,
        completed_at=None
    )

@router.get("/models", response=List[ModelEvaluation], tags=["Model Registry"])
def list_models(request, model_type: Optional[str] = None):
    """List registered models with performance metrics"""
    queryset = MLModelRegistry.objects.all()
    if model_type:
        queryset = queryset.filter(model_type=model_type)
    
    return [
        ModelEvaluation(
            model_id=m.model_id,
            model_version=m.version,
            auc_roc=m.auc_roc,
            f1_score=m.f1_score,
            precision=m.precision,
            recall=m.recall,
            calibration_error=0.0,
            meets_deployment_threshold=m.validation_status == "deployed"
        )
        for m in queryset.order_by("-created_at")[:20]
    ]

@router.get("/drift", response=List[DriftReport], tags=["Monitoring"])
def get_drift_reports(request, model_version: Optional[str] = None):
    """
    Get population drift detection reports.
    Spec Section 4.3: PSI computed weekly, threshold 0.2.
    """
    queryset = DriftDetectionLog.objects.all()
    if model_version:
        queryset = queryset.filter(model__version=model_version)
    
    return [
        DriftReport(
            log_id=d.log_id,
            model_version=d.model.version,
            psi_score=d.psi_score,
            threshold=d.psi_threshold,
            features_drifted=d.features_drifted,
            retraining_triggered=d.retraining_triggered,
            detected_at=d.detected_at
        )
        for d in queryset.order_by("-detected_at")[:50]
    ]

api.add_router("/prediction/", router)