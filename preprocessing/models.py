from django.db import models

# Create your models here.
import json

class RawDataSource(models.TextChoices):
    WHO_API = "who_api", "WHO Global API"
    MOH_DB = "moh_db", "MOH Kenya Database"
    PATIENT_FORM = "patient_form", "Patient Input Form"
    GEOLOCATION = "geolocation", "Geolocation Layer"

class ProcessingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"

class PreprocessingJob(models.Model):
    """Tracks a preprocessing batch job"""
    job_id = models.UUIDField(primary_key=True, editable=False)
    source = models.CharField(max_length=20, choices=RawDataSource.choices)
    raw_record_count = models.PositiveIntegerField(default=0)
    processed_record_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.PENDING)
    config = models.JSONField(default=dict, help_text="Preprocessing parameters")
    error_log = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Pipeline stages tracking
    deduplication_completed = models.DateTimeField(null=True, blank=True)
    imputation_completed = models.DateTimeField(null=True, blank=True)
    encoding_completed = models.DateTimeField(null=True, blank=True)
    smote_completed = models.DateTimeField(null=True, blank=True)
    anonymisation_completed = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

class ProcessedRecord(models.Model):
    """Individual processed patient record (anonymised)"""
    anonymous_id = models.CharField(max_length=64, unique=True, db_index=True)
    job = models.ForeignKey(PreprocessingJob, on_delete=models.CASCADE, related_name="records")
    
    # Features (stored as JSON for flexibility)
    symptoms = models.JSONField(default=dict, help_text="32 binary symptom features")
    risk_behaviours = models.JSONField(default=dict)
    demographics = models.JSONField(default=dict)  # age, sex, region
    geographic_region = models.CharField(max_length=50)
    prior_sti_history = models.JSONField(default=list)
    
    # Engineered features
    composite_risk_score = models.FloatField(null=True)
    temporal_features = models.JSONField(default=dict)
    
    # Labels (for training data)
    sti_labels = models.JSONField(default=dict, help_text="One-hot encoded STI classes")
    risk_level = models.CharField(
        max_length=20,
        choices=[("low", "Low"), ("moderate", "Moderate"), ("high", "High"), ("critical", "Critical")],
        null=True
    )
    
    # Privacy & audit
    differential_privacy_applied = models.BooleanField(default=False)
    k_anonymity_group = models.PositiveIntegerField(null=True, help_text="k-anonymity group ID")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["geographic_region", "risk_level"]),
            models.Index(fields=["anonymous_id"]),
        ]

class FeatureEncoderConfig(models.Model):
    """Stores encoding configurations for reproducibility"""
    name = models.CharField(max_length=100, unique=True)
    feature_type = models.CharField(max_length=50)  # categorical, numerical, binary
    encoding_method = models.CharField(max_length=50)  # one_hot, label, target, standard_scale
    categories = models.JSONField(default=list, null=True)
    fitted_params = models.JSONField(default=dict, null=True)  # mean, std for scaling
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)