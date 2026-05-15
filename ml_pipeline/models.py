from django.db import models
import uuid


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class ModelType(models.TextChoices):
    RISK_CLASSIFIER = "risk_classifier", "STI Risk Classifier (XGBoost + RF)"
    PATTERN_PREDICTOR = "pattern_predictor", "Pattern Predictor (LSTM + Prophet)"
    HOTSPOT_ENGINE = "hotspot_engine", "Geospatial Hotspot Engine (DBSCAN + KDE)"


class TrainingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    DRIFT_TRIGGERED = "drift_triggered", "Triggered by Drift Alert"


class RiskLevel(models.TextChoices):
    LOW = "low", "Low"
    MODERATE = "moderate", "Moderate"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class STIClass(models.TextChoices):
    HIV = "hiv", "HIV"
    CHLAMYDIA = "chlamydia", "Chlamydia"
    SYPHILIS = "syphilis", "Syphilis"
    GONORRHOEA = "gonorrhoea", "Gonorrhoea"
    HPV = "hpv", "HPV"
    HSV2 = "hsv2", "HSV-2"
    NONE = "none", "None / Indeterminate"


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

class MLModel(models.Model):
    """
    Versioned registry entry for every trained model artefact.
    All predictions reference a model_version for full audit traceability.
    Integrates with MLflow: mlflow_run_id links to the external experiment store.
    """
    model_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_type = models.CharField(max_length=30, choices=ModelType.choices, db_index=True)
    version = models.CharField(
        max_length=20,
        help_text="Semantic version string, e.g. '1.0.0'",
    )
    mlflow_run_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="MLflow run ID for experiment tracking cross-reference",
    )
    artefact_path = models.CharField(
        max_length=500,
        help_text="Path to serialised model artefact (joblib / .pt / Prophet JSON)",
    )
    feature_schema_version = models.CharField(
        max_length=20,
        default="1.0",
        help_text="Version of the feature engineering schema used at training time",
    )

    # Evaluation metrics (stored as JSON for flexibility across model types)
    evaluation_metrics = models.JSONField(
        default=dict,
        help_text="AUC-ROC, F1, MAPE etc. per class/horizon at validation time",
    )
    meets_deployment_threshold = models.BooleanField(
        default=False,
        help_text="True when AUC-ROC ≥ 0.85 (classifier) or MAPE ≤ 15% (predictor)",
    )

    # Drift monitoring
    psi_score = models.FloatField(
        null=True,
        help_text="Population Stability Index computed weekly. >0.2 triggers retraining alert.",
    )
    last_psi_check = models.DateTimeField(null=True, blank=True)
    drift_alert_active = models.BooleanField(default=False)

    # Lifecycle
    is_active = models.BooleanField(
        default=False,
        help_text="Only one model per type may be active at a time.",
    )
    clinical_validation_completed = models.BooleanField(
        default=False,
        help_text="Hard gate — model may not serve patient/clinician outputs until True.",
    )
    validated_by = models.CharField(max_length=200, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [["model_type", "version"]]
        indexes = [
            models.Index(fields=["model_type", "is_active"]),
            models.Index(fields=["drift_alert_active"]),
        ]

    def __str__(self):
        return f"{self.get_model_type_display()} v{self.version} ({'active' if self.is_active else 'inactive'})"


# ---------------------------------------------------------------------------
# Training Jobs
# ---------------------------------------------------------------------------

class TrainingJob(models.Model):
    """
    Tracks a single model training run, including data source, config, and outcome.
    Created automatically by the quarterly scheduler or drift-triggered pipeline.
    """
    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_type = models.CharField(max_length=30, choices=ModelType.choices)
    status = models.CharField(
        max_length=20, choices=TrainingStatus.choices, default=TrainingStatus.PENDING
    )
    trigger = models.CharField(
        max_length=50,
        default="scheduled",
        help_text="'scheduled', 'drift_alert', 'manual', or 'data_update'",
    )

    # Data window
    training_data_start = models.DateField()
    training_data_end = models.DateField()
    record_count = models.PositiveIntegerField(default=0)
    class_distribution = models.JSONField(
        default=dict,
        help_text="Record count per STI class label before SMOTE",
    )

    # Hyperparameters used
    hyperparameters = models.JSONField(default=dict)

    # Outcome
    resulting_model = models.OneToOneField(
        MLModel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="training_job",
    )
    error_log = models.TextField(blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["model_type", "status"])]


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

class RiskPrediction(models.Model):
    """
    Individual STI risk prediction produced by the ensemble classifier.

    Linked to the anonymous_id from preprocessing — never to a patient name or PII.
    The clinical_review_required flag is set when any class probability ≥ 0.7;
    this prediction must not be surfaced to the patient until a clinician has reviewed it.
    """
    prediction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_version = models.ForeignKey(
        MLModel, on_delete=models.PROTECT, related_name="risk_predictions"
    )

    # Identity (anonymised)
    anonymous_id = models.CharField(max_length=64, db_index=True)

    # Input snapshot (for audit — no PII)
    input_feature_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 of the normalised feature vector for audit reproducibility",
    )
    input_features = models.JSONField(
        help_text="Full feature vector at inference time. Stored for SHAP audit trail."
    )

    # Outputs
    sti_probabilities = models.JSONField(
        help_text="Dict of {sti_class: probability_score} for all 7 classes"
    )
    predicted_class = models.CharField(
        max_length=20,
        choices=STIClass.choices,
        help_text="Highest-probability STI class",
    )
    overall_risk_level = models.CharField(max_length=20, choices=RiskLevel.choices)
    overall_risk_score = models.FloatField(help_text="Max probability across all STI classes")

    # Explainability
    shap_values = models.JSONField(
        null=True,
        help_text="SHAP value dict for the top contributing features",
    )
    top_features = models.JSONField(
        default=list,
        help_text="Top 3 features driving this prediction [{feature, shap_value, direction}]",
    )
    confidence_lower = models.FloatField(null=True, help_text="95% CI lower bound")
    confidence_upper = models.FloatField(null=True, help_text="95% CI upper bound")

    # Clinical gate
    clinical_review_required = models.BooleanField(
        default=False,
        help_text="True when any class probability ≥ 0.7. Hard block on patient display.",
    )
    clinical_review_completed = models.BooleanField(default=False)
    reviewed_by = models.CharField(max_length=100, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["anonymous_id", "created_at"]),
            models.Index(fields=["overall_risk_level"]),
            models.Index(fields=["clinical_review_required", "clinical_review_completed"]),
        ]


class OutbreakForecast(models.Model):
    """
    Regional 30/60/90-day outbreak incidence forecasts produced by the
    LSTM + Prophet ensemble. One record per county × STI type × forecast run.
    """
    forecast_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_version = models.ForeignKey(
        MLModel, on_delete=models.PROTECT, related_name="outbreak_forecasts"
    )

    county = models.CharField(max_length=50, db_index=True)
    sti_type = models.CharField(max_length=20, choices=STIClass.choices, db_index=True)
    forecast_generated_on = models.DateField()

    # Historical baseline used
    baseline_start = models.DateField()
    baseline_end = models.DateField()
    baseline_incidence_rate = models.FloatField(
        help_text="Incidence rate per 100,000 in the baseline period"
    )

    # 30-day forecast
    forecast_30d_rate = models.FloatField()
    forecast_30d_lower = models.FloatField(help_text="95% CI lower")
    forecast_30d_upper = models.FloatField(help_text="95% CI upper")

    # 60-day forecast
    forecast_60d_rate = models.FloatField()
    forecast_60d_lower = models.FloatField()
    forecast_60d_upper = models.FloatField()

    # 90-day forecast
    forecast_90d_rate = models.FloatField()
    forecast_90d_lower = models.FloatField()
    forecast_90d_upper = models.FloatField()

    # Trend
    year_over_year_delta_pct = models.FloatField(
        null=True,
        help_text="% change vs same period last year. Positive = worsening trend.",
    )
    trend_direction = models.CharField(
        max_length=20,
        choices=[("rising", "Rising"), ("stable", "Stable"), ("declining", "Declining")],
        default="stable",
    )

    # Model diagnostics
    lstm_mape = models.FloatField(null=True, help_text="LSTM walk-forward MAPE on validation set")
    prophet_mape = models.FloatField(null=True)
    ensemble_weight_lstm = models.FloatField(default=0.6)
    ensemble_weight_prophet = models.FloatField(default=0.4)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-forecast_generated_on"]
        unique_together = [["county", "sti_type", "forecast_generated_on"]]
        indexes = [
            models.Index(fields=["county", "sti_type"]),
            models.Index(fields=["forecast_generated_on"]),
        ]


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class PredictionAuditLog(models.Model):
    """
    Immutable append-only audit log for every prediction event.
    Required for regulatory review under Kenya Data Protection Act 2019.
    Records must never be updated or deleted.
    """
    log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(
        max_length=50,
        help_text=(
            "'prediction_created', 'clinical_review_completed', "
            "'guidance_surfaced', 'model_activated', 'drift_alert'"
        ),
    )
    prediction = models.ForeignKey(
        RiskPrediction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    model_version = models.ForeignKey(
        MLModel, null=True, blank=True, on_delete=models.SET_NULL
    )
    anonymous_id = models.CharField(max_length=64, blank=True)
    actor = models.CharField(
        max_length=100,
        blank=True,
        help_text="System component or clinician identifier (anonymised)",
    )
    payload = models.JSONField(
        default=dict,
        help_text="Event-specific metadata. No PII stored.",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        # No update/delete permissions — enforced at DB level via policy
        indexes = [
            models.Index(fields=["event_type", "timestamp"]),
            models.Index(fields=["anonymous_id"]),
        ]

    def save(self, *args, **kwargs):
        # Prevent updates — audit records are write-once
        if self.pk and PredictionAuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("Audit log records are immutable and cannot be updated.")
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Drift Monitoring
# ---------------------------------------------------------------------------

class DriftReport(models.Model):
    """
    Weekly PSI drift report per model. Auto-generated by the monitoring scheduler.
    A PSI score > 0.2 sets drift_alert_active on the linked MLModel and
    queues a TrainingJob with trigger='drift_alert'.
    """
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_version = models.ForeignKey(
        MLModel, on_delete=models.CASCADE, related_name="drift_reports"
    )
    report_date = models.DateField()
    psi_score = models.FloatField(help_text="Overall Population Stability Index")
    feature_psi = models.JSONField(
        default=dict,
        help_text="Per-feature PSI scores. Used to identify which inputs are drifting.",
    )
    alert_triggered = models.BooleanField(default=False)
    subgroup_auc = models.JSONField(
        default=dict,
        help_text="AUC-ROC per demographic subgroup. <0.80 flags bias review.",
    )
    bias_flag = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-report_date"]
        unique_together = [["model_version", "report_date"]]