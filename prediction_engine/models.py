"""
STI Predictive Model — ML Pipeline (L3)
models.py

Tracks training jobs, model versions, experiment runs, and drift alerts
for all three models: STI Risk Classifier, Pattern Predictor, Geospatial Engine.
All model versioning is mirrored to MLflow; these tables are the Django
source of truth for the prediction engine (L4) to resolve active model versions.
"""

import uuid
from django.db import models


class ModelType(models.TextChoices):
    RISK_CLASSIFIER = "risk_classifier", "STI Risk Classifier"
    PATTERN_PREDICTOR = "pattern_predictor", "Outbreak Pattern Predictor"
    GEOSPATIAL_ENGINE = "geospatial_engine", "Geospatial Hotspot Engine"


class TrainingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    EVALUATING = "evaluating", "Evaluating"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    REJECTED = "rejected", "Rejected — Did Not Meet Performance Thresholds"


class ModelStage(models.TextChoices):
    STAGING = "staging", "Staging"
    PRODUCTION = "production", "Production"
    ARCHIVED = "archived", "Archived"
    PENDING_CLINICAL = "pending_clinical", "Pending Clinical Validation"


class TriggerType(models.TextChoices):
    SCHEDULED = "scheduled", "Quarterly Scheduled Retraining"
    DRIFT = "drift", "Drift Detection Alert"
    MANUAL = "manual", "Manual Trigger"
    INITIAL = "initial", "Initial Training"


# ---------------------------------------------------------------------------
# MLflow Experiment Registry
# ---------------------------------------------------------------------------

class MLflowExperiment(models.Model):
    """
    Maps a Django model type to its MLflow experiment.
    One experiment per model type, referenced by all training runs.
    """
    model_type = models.CharField(
        max_length=30,
        choices=ModelType.choices,
        unique=True,
    )
    mlflow_experiment_id = models.CharField(max_length=100, unique=True)
    mlflow_experiment_name = models.CharField(max_length=200)
    artifact_location = models.CharField(
        max_length=500,
        help_text="MLflow artifact store URI (S3/GCS/local)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_model_type_display()} → {self.mlflow_experiment_name}"


# ---------------------------------------------------------------------------
# Training Job
# ---------------------------------------------------------------------------

class TrainingJob(models.Model):
    """
    One row per training run. Tracks dataset window, hyperparameters,
    evaluation metrics, and the resulting model version.
    """
    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_type = models.CharField(max_length=30, choices=ModelType.choices)
    trigger = models.CharField(max_length=20, choices=TriggerType.choices)
    status = models.CharField(
        max_length=20,
        choices=TrainingStatus.choices,
        default=TrainingStatus.PENDING,
    )

    # Dataset window used for this training run
    training_data_start = models.DateField(null=True, blank=True)
    training_data_end = models.DateField(null=True, blank=True)
    training_record_count = models.PositiveIntegerField(default=0)

    # MLflow references
    mlflow_run_id = models.CharField(max_length=100, blank=True)
    mlflow_experiment = models.ForeignKey(
        MLflowExperiment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="training_jobs",
    )

    # Hyperparameters logged as JSON
    hyperparameters = models.JSONField(default=dict)

    # Evaluation metrics (populated after training)
    metrics = models.JSONField(
        default=dict,
        help_text="AUC-ROC, F1, precision, recall per class; MAPE for forecaster",
    )
    passed_thresholds = models.BooleanField(
        null=True,
        help_text="True if all performance thresholds (AUC≥0.85, F1≥0.75) passed",
    )

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    error_log = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model_type", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"TrainingJob({self.model_type}, {self.status}, {self.created_at:%Y-%m-%d})"


# ---------------------------------------------------------------------------
# Model Version
# ---------------------------------------------------------------------------

class ModelVersion(models.Model):
    """
    A validated, deployable model artifact.
    Linked 1-to-1 with a completed TrainingJob.
    The prediction engine (L4) queries this table to resolve
    which model version to use for inference.
    """
    version_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_type = models.CharField(max_length=30, choices=ModelType.choices)
    stage = models.CharField(
        max_length=20,
        choices=ModelStage.choices,
        default=ModelStage.STAGING,
    )
    training_job = models.OneToOneField(
        TrainingJob,
        on_delete=models.PROTECT,
        related_name="model_version",
    )

    # MLflow model registry reference
    mlflow_model_name = models.CharField(max_length=200)
    mlflow_model_version = models.CharField(max_length=20)
    mlflow_run_id = models.CharField(max_length=100)

    # Artifact hash for integrity verification
    model_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 of serialised model artifact",
    )
    artifact_uri = models.CharField(max_length=500)

    # Performance summary (denormalised from TrainingJob for fast L4 queries)
    auc_roc_mean = models.FloatField(null=True)
    f1_mean = models.FloatField(null=True)
    mape = models.FloatField(null=True, help_text="For pattern predictor only")

    # Clinical validation
    clinical_validation_passed = models.BooleanField(default=False)
    clinical_validated_by = models.CharField(max_length=200, blank=True)
    clinical_validated_at = models.DateTimeField(null=True, blank=True)

    promoted_to_production_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model_type", "stage"]),
        ]

    def __str__(self):
        return (
            f"ModelVersion({self.model_type}, v{self.mlflow_model_version}, "
            f"{self.stage})"
        )


# ---------------------------------------------------------------------------
# Drift Alert
# ---------------------------------------------------------------------------

class DriftAlert(models.Model):
    """
    Raised when the Population Stability Index (PSI) exceeds 0.2
    for any active production model. Triggers retraining review.
    """
    alert_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.CASCADE,
        related_name="drift_alerts",
    )
    model_type = models.CharField(max_length=30, choices=ModelType.choices)
    psi_score = models.FloatField(help_text="Population Stability Index score")
    psi_threshold = models.FloatField(default=0.2)
    features_drifted = models.JSONField(
        default=list,
        help_text="List of feature names with PSI > threshold",
    )
    retraining_triggered = models.BooleanField(default=False)
    triggered_job = models.ForeignKey(
        TrainingJob,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="triggered_by_drift",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"DriftAlert({self.model_type}, PSI={self.psi_score:.3f})"


# ---------------------------------------------------------------------------
# Bias Audit Record
# ---------------------------------------------------------------------------

class BiasAuditRecord(models.Model):
    """
    Quarterly bias audit results per model version.
    Tracks AUC-ROC per demographic subgroup (age, sex, region).
    Flags if any subgroup drops below 0.80 threshold.
    """
    audit_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.CASCADE,
        related_name="bias_audits",
    )
    audit_period_start = models.DateField()
    audit_period_end = models.DateField()

    # Per-subgroup AUC scores
    auc_by_age_group = models.JSONField(default=dict)
    auc_by_sex = models.JSONField(default=dict)
    auc_by_region = models.JSONField(default=dict)

    # Overall flag
    any_subgroup_below_threshold = models.BooleanField(default=False)
    flagged_subgroups = models.JSONField(
        default=list,
        help_text="Subgroup keys where AUC < 0.80",
    )
    retraining_recommended = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-audit_period_end"]