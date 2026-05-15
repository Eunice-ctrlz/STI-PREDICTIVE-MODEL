"""
STI Predictive Model — ML Pipeline (L3)
tasks.py

Celery tasks for:
  - Scheduled quarterly retraining (all three models)
  - Drift-triggered retraining
  - Weekly PSI drift monitoring
  - Quarterly bias audit
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import (
    ModelType, TrainingJob, TrainingStatus, TriggerType,
    DriftAlert, MLflowExperiment,
)
from .classifier import STIRiskClassifier
from .forecaster import OutbreakPatternPredictor
from .geospatial import GeospatialHotspotEngine
from .registry import ModelRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: Fetch preprocessed training records from the preprocessing app
# ---------------------------------------------------------------------------

def _fetch_training_records(
    model_type: str,
    training_start,
    training_end,
) -> List[Dict]:
    """
    Pull processed records from the preprocessing layer (L2)
    within the rolling 5-year training window.
    """
    # Import here to avoid circular imports
    from preprocessing.models import ProcessedRecord

    qs = ProcessedRecord.objects.filter(
        created_at__date__gte=training_start,
        created_at__date__lte=training_end,
    )

    if model_type == ModelType.RISK_CLASSIFIER:
        # Labelled records only
        qs = qs.exclude(sti_labels={})

    records = []
    for rec in qs.iterator(chunk_size=500):
        row = {
            "symptom_vector": rec.symptoms.get("vector", [0] * 32),
            "composite_risk_score": rec.composite_risk_score or 0.0,
            "age_encoded": rec.demographics.get("age_encoded", 0),
            "sex_encoded": rec.demographics.get("sex_encoded", 0),
            "region_encoded": rec.demographics.get("region_encoded", 0),
            "temporal_features": rec.temporal_features or {},
            "prior_sti_history": rec.prior_sti_history or [],
            "geographic_region": rec.geographic_region,
        }
        if rec.sti_labels:
            # Take the highest-confidence label
            row["sti_label"] = max(rec.sti_labels, key=rec.sti_labels.get)
        records.append(row)
    return records


def _fetch_timeseries_records(training_start, training_end) -> List[Dict]:
    """Pull monthly incidence aggregates for the forecaster."""
    from ingestion.models import RawRecord, DataSourceType
    qs = RawRecord.objects.filter(
        source__in=[DataSourceType.WHO_API, DataSourceType.MOH_DB],
        record_date__gte=training_start,
        record_date__lte=training_end,
        status="raw",
    )
    records = []
    for rec in qs.iterator(chunk_size=500):
        payload = rec.raw_payload
        records.append({
            "date": str(rec.record_date),
            "county": rec.geographic_region,
            "sti_type": payload.get("sti_type", "all"),
            "incidence_rate": payload.get("incidence_rate", 0.0),
            "population_density": payload.get("population_density", 0.0),
            "healthcare_access_index": payload.get("healthcare_access_index", 0.5),
        })
    return records


def _fetch_geo_records(training_start, training_end) -> List[Dict]:
    """Pull geo grid records for the hotspot engine."""
    from ingestion.models import GeoRecord
    qs = GeoRecord.objects.filter(
        week_start__gte=training_start,
        week_start__lte=training_end,
        suppressed=False,
    )
    records = []
    for rec in qs.iterator(chunk_size=500):
        records.append({
            "latitude_grid": rec.latitude_grid,
            "longitude_grid": rec.longitude_grid,
            "county": rec.county,
            "sub_county": rec.sub_county,
            "sti_counts": rec.sti_counts,
            "total_cases": rec.total_cases,
            "suppressed": rec.suppressed,
            "week_start": str(rec.week_start),
        })
    return records


# ---------------------------------------------------------------------------
# Task: Train STI Risk Classifier
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def train_risk_classifier_task(
    self,
    job_id: str,
    xgb_params: Optional[Dict] = None,
    rf_params: Optional[Dict] = None,
):
    """
    Train the STI Risk Classifier (XGBoost + RF ensemble).
    Updates TrainingJob status and registers the resulting ModelVersion.
    """
    try:
        job = TrainingJob.objects.get(job_id=job_id)
        job.status = TrainingStatus.RUNNING
        job.started_at = timezone.now()
        job.save()

        registry = ModelRegistry()
        experiment_id = registry.get_experiment_id(ModelType.RISK_CLASSIFIER)

        records = _fetch_training_records(
            ModelType.RISK_CLASSIFIER,
            job.training_data_start,
            job.training_data_end,
        )
        job.training_record_count = len(records)
        job.save(update_fields=["training_record_count"])

        if len(records) < 100:
            raise ValueError(
                f"Only {len(records)} labelled records available. "
                "Minimum 100 required; 10,000 recommended (§4.1.1)."
            )

        classifier = STIRiskClassifier(
            xgb_params=xgb_params,
            rf_params=rf_params,
            mlflow_experiment_id=experiment_id,
        )
        metrics = classifier.train(records, run_name=f"job_{job_id[:8]}")

        job.status = TrainingStatus.EVALUATING
        job.mlflow_run_id = classifier.mlflow_run_id
        job.metrics = metrics
        job.passed_thresholds = metrics.get("passed_thresholds", False)
        job.save()

        if not metrics.get("passed_thresholds", False):
            job.status = TrainingStatus.REJECTED
            job.error_log = (
                f"Did not meet deployment thresholds — "
                f"AUC={metrics.get('auc_roc_mean', 0):.4f} "
                f"(threshold {0.85}), F1={metrics.get('f1_mean', 0):.4f} "
                f"(threshold {0.75})"
            )
            job.completed_at = timezone.now()
            job.save()
            logger.warning("Risk classifier job %s REJECTED: %s", job_id, job.error_log)
            return {"job_id": job_id, "status": "rejected", "metrics": metrics}

        # Register model version
        artifact_uri = f"runs:/{classifier.mlflow_run_id}/sti_risk_classifier"
        model_version = registry.register_model(job, metrics, artifact_uri)

        job.status = TrainingStatus.COMPLETED
        job.completed_at = timezone.now()
        job.save()

        logger.info(
            "Risk classifier training completed: job=%s, version=%s, AUC=%.4f",
            job_id, model_version.version_id, metrics.get("auc_roc_mean", 0),
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "version_id": str(model_version.version_id),
            "metrics": metrics,
        }

    except Exception as exc:
        _mark_job_failed(job_id, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Task: Train Pattern Predictor
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def train_pattern_predictor_task(
    self,
    job_id: str,
    lstm_params: Optional[Dict] = None,
    prophet_params: Optional[Dict] = None,
):
    """Train LSTM + Prophet outbreak forecaster."""
    try:
        job = TrainingJob.objects.get(job_id=job_id)
        job.status = TrainingStatus.RUNNING
        job.started_at = timezone.now()
        job.save()

        registry = ModelRegistry()
        experiment_id = registry.get_experiment_id(ModelType.PATTERN_PREDICTOR)

        records = _fetch_timeseries_records(
            job.training_data_start,
            job.training_data_end,
        )
        job.training_record_count = len(records)
        job.save(update_fields=["training_record_count"])

        forecaster = OutbreakPatternPredictor(
            lstm_params=lstm_params,
            prophet_params=prophet_params,
            mlflow_experiment_id=experiment_id,
        )
        metrics = forecaster.train(records, run_name=f"job_{job_id[:8]}")

        job.status = TrainingStatus.EVALUATING
        job.mlflow_run_id = forecaster.mlflow_run_id
        job.metrics = metrics
        job.passed_thresholds = metrics.get("passed_thresholds", False)
        job.save()

        if not metrics.get("passed_thresholds", False):
            job.status = TrainingStatus.REJECTED
            job.error_log = (
                f"MAPE={metrics.get('mape_mean', 999):.2f}% exceeds threshold "
                f"of {15.0}%"
            )
            job.completed_at = timezone.now()
            job.save()
            return {"job_id": job_id, "status": "rejected", "metrics": metrics}

        artifact_uri = f"runs:/{forecaster.mlflow_run_id}/outbreak_pattern_predictor"
        model_version = registry.register_model(job, metrics, artifact_uri)

        job.status = TrainingStatus.COMPLETED
        job.completed_at = timezone.now()
        job.save()

        logger.info(
            "Pattern predictor training completed: job=%s, MAPE=%.2f%%",
            job_id, metrics.get("mape_mean", 0),
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "version_id": str(model_version.version_id),
            "metrics": metrics,
        }

    except Exception as exc:
        _mark_job_failed(job_id, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Task: Train Geospatial Engine
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def train_geospatial_engine_task(self, job_id: str, dbscan_params: Optional[Dict] = None):
    """Run a geospatial hotspot analysis run (DBSCAN + KDE)."""
    try:
        job = TrainingJob.objects.get(job_id=job_id)
        job.status = TrainingStatus.RUNNING
        job.started_at = timezone.now()
        job.save()

        registry = ModelRegistry()
        experiment_id = registry.get_experiment_id(ModelType.GEOSPATIAL_ENGINE)

        geo_records = _fetch_geo_records(
            job.training_data_start,
            job.training_data_end,
        )
        job.training_record_count = len(geo_records)
        job.save(update_fields=["training_record_count"])

        engine = GeospatialHotspotEngine(
            dbscan_params=dbscan_params,
            mlflow_experiment_id=experiment_id,
        )
        result = engine.run(geo_records, sti_type="all", run_name=f"job_{job_id[:8]}")

        metrics = {
            "sti_types_processed": len(result.get("results", {})),
            "passed_thresholds": len(result.get("results", {})) > 0,
        }
        for stype, data in result.get("results", {}).items():
            metrics[f"{stype}_n_clusters"] = data.get("n_clusters", 0)
            metrics[f"{stype}_morans_i"] = data.get("morans_i", {}).get("moran_i", 0.0)

        job.status = TrainingStatus.EVALUATING
        job.mlflow_run_id = engine.mlflow_run_id
        job.metrics = metrics
        job.passed_thresholds = metrics["passed_thresholds"]
        job.save()

        artifact_uri = f"runs:/{engine.mlflow_run_id}/geospatial_hotspot_engine"
        model_version = registry.register_model(job, metrics, artifact_uri)

        job.status = TrainingStatus.COMPLETED
        job.completed_at = timezone.now()
        job.save()

        logger.info(
            "Geospatial engine run completed: job=%s, types=%d",
            job_id, metrics["sti_types_processed"],
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "version_id": str(model_version.version_id),
            "metrics": metrics,
        }

    except Exception as exc:
        _mark_job_failed(job_id, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Task: Quarterly Retraining (all models)
# ---------------------------------------------------------------------------

@shared_task
def quarterly_retraining_task():
    """
    Scheduled quarterly retraining for all three models.
    Uses a rolling 5-year window ending today.
    """
    today = timezone.now().date()
    window_start = today - timedelta(days=5 * 365)

    model_tasks = {
        ModelType.RISK_CLASSIFIER: train_risk_classifier_task,
        ModelType.PATTERN_PREDICTOR: train_pattern_predictor_task,
        ModelType.GEOSPATIAL_ENGINE: train_geospatial_engine_task,
    }

    job_ids = []
    for model_type, task_fn in model_tasks.items():
        job = TrainingJob.objects.create(
            model_type=model_type,
            trigger=TriggerType.SCHEDULED,
            training_data_start=window_start,
            training_data_end=today,
            hyperparameters={},
        )
        task_fn.delay(str(job.job_id))
        job_ids.append(str(job.job_id))
        logger.info(
            "Quarterly retraining queued for %s: job=%s", model_type, job.job_id
        )

    return {"queued_jobs": job_ids, "window_start": str(window_start)}


# ---------------------------------------------------------------------------
# Task: Weekly Drift Monitoring (§4.3)
# ---------------------------------------------------------------------------

@shared_task
def weekly_drift_check_task():
    """
    Weekly PSI drift check for the risk classifier.
    Compares last 4 weeks of production traffic against training distribution.
    Triggers retraining if PSI > 0.2.
    """
    from preprocessing.models import ProcessedRecord

    today = timezone.now().date()
    reference_start = today - timedelta(days=5 * 365)
    reference_end = today - timedelta(days=28)
    current_start = today - timedelta(days=28)

    def _load_records(start, end):
        qs = ProcessedRecord.objects.filter(
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
        rows = []
        for rec in qs.iterator(chunk_size=500):
            rows.append({
                "symptom_vector": rec.symptoms.get("vector", [0] * 32),
                "composite_risk_score": rec.composite_risk_score or 0.0,
                "age_encoded": rec.demographics.get("age_encoded", 0),
                "sex_encoded": rec.demographics.get("sex_encoded", 0),
                "region_encoded": rec.demographics.get("region_encoded", 0),
                "temporal_features": rec.temporal_features or {},
                "prior_sti_history": rec.prior_sti_history or [],
            })
        return rows

    registry = ModelRegistry()
    reference_records = _load_records(reference_start, reference_end)
    current_records = _load_records(current_start, today)

    if len(reference_records) < 100 or len(current_records) < 10:
        logger.info("Insufficient data for drift check — skipping")
        return {"status": "skipped", "reason": "insufficient_data"}

    alert = registry.check_drift(
        ModelType.RISK_CLASSIFIER,
        reference_records,
        current_records,
    )

    if alert:
        # Trigger drift-based retraining
        job = TrainingJob.objects.create(
            model_type=ModelType.RISK_CLASSIFIER,
            trigger=TriggerType.DRIFT,
            training_data_start=reference_start,
            training_data_end=today,
            hyperparameters={},
        )
        train_risk_classifier_task.delay(str(job.job_id))

        alert.retraining_triggered = True
        alert.triggered_job = job
        alert.save(update_fields=["retraining_triggered", "triggered_job"])

        logger.warning(
            "Drift-triggered retraining scheduled: PSI=%.4f, job=%s",
            alert.psi_score, job.job_id,
        )
        return {
            "status": "drift_detected",
            "psi_score": alert.psi_score,
            "retraining_job_id": str(job.job_id),
        }

    return {"status": "no_drift"}


# ---------------------------------------------------------------------------
# Task: Quarterly Bias Audit (§8.3)
# ---------------------------------------------------------------------------

@shared_task
def quarterly_bias_audit_task():
    """
    Quarterly automated bias audit for the production risk classifier.
    Flags any demographic subgroup with AUC < 0.80.
    """
    from prediction_engine.models import PredictionAuditLog  # L4

    today = timezone.now()
    period_start = today - timedelta(days=90)

    logs = list(
        PredictionAuditLog.objects.filter(
            model_type=ModelType.RISK_CLASSIFIER,
            created_at__gte=period_start,
        ).values(
            "predicted_label",
            "true_label",
            "predicted_probabilities",
            "age_encoded",
            "sex_encoded",
            "region_encoded",
        )
    )

    if len(logs) < 50:
        logger.info("Insufficient inference logs for bias audit — skipping")
        return {"status": "skipped", "reason": "insufficient_logs"}

    registry = ModelRegistry()
    audit = registry.run_bias_audit(
        ModelType.RISK_CLASSIFIER,
        logs,
        period_start,
        today,
    )

    return {
        "status": "completed",
        "audit_id": str(audit.audit_id),
        "flagged_subgroups": audit.flagged_subgroups,
        "retraining_recommended": audit.retraining_recommended,
    }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _mark_job_failed(job_id: str, exc: Exception) -> None:
    try:
        job = TrainingJob.objects.get(job_id=job_id)
        job.status = TrainingStatus.FAILED
        job.error_log = str(exc)
        job.completed_at = timezone.now()
        job.save()
    except TrainingJob.DoesNotExist:
        logger.error("Cannot mark unknown job %s as failed", job_id)