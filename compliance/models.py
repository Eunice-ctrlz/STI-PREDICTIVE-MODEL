from django.db import models
import uuid

class AuditActionType(models.TextChoices):
    PREDICTION_MADE = "prediction_made", "Prediction Made"
    GUIDANCE_ACCESSED = "guidance_accessed", "Guidance Accessed"
    GUIDANCE_APPROVED = "guidance_approved", "Guidance Approved"
    GUIDANCE_DEPLOYED = "guidance_deployed", "Guidance Deployed"
    THRESHOLD_OVERRIDE = "threshold_override", "Threshold Override"
    ALERT_ACKNOWLEDGED = "alert_acknowledged", "Alert Acknowledged"
    ALERT_RESOLVED = "alert_resolved", "Alert Resolved"
    PATIENT_REFERRED = "patient_referred", "Patient Referred"
    TEST_ORDERED = "test_ordered", "Test Ordered"
    MODEL_DEPLOYED = "model_deployed", "Model Deployed"
    MODEL_RETRAINED = "model_retrained", "Model Retrained"
    DRIFT_DETECTED = "drift_detected", "Drift Detected"
    BIAS_VIOLATION = "bias_violation", "Bias Violation Detected"
    DATA_DELETED = "data_deleted", "Data Deleted per Retention Policy"
    COMPLIANCE_REVIEW = "compliance_review", "Compliance Review Conducted"

class ImmutableAuditLog(models.Model):
    """
    Immutable audit log of all predictions, inputs, and guidance outputs.
    Spec Section 3.1: Required for regulatory review.
    Section 8.2: Version-controlled approval with clinician name recorded.
    """
    log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Action classification
    action_type = models.CharField(max_length=30, choices=AuditActionType.choices)
    action_timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # Actor (nullable for system actions)
    actor_type = models.CharField(max_length=20, choices=[
        ("clinician", "Clinician"),
        ("system", "System"),
        ("admin", "Administrator"),
        ("patient", "Patient (Anonymous)")
    ])
    actor_id = models.CharField(max_length=100, blank=True, db_index=True)
    actor_credentials = models.CharField(max_length=200, blank=True)
    
    # Subject (patient or model)
    anonymous_id = models.CharField(max_length=64, blank=True, db_index=True)
    model_version = models.CharField(max_length=50, blank=True)
    
    # Data accessed or produced
    risk_score = models.FloatField(null=True)
    risk_level = models.CharField(max_length=20, blank=True)
    sti_probabilities = models.JSONField(default=dict)
    guidance_version = models.PositiveIntegerField(null=True)
    guidance_id = models.UUIDField(null=True)
    
    # Context
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    session_id = models.UUIDField(null=True)
    
    # Immutable hash chain for tamper detection
    previous_log_hash = models.CharField(max_length=64, blank=True)
    current_log_hash = models.CharField(max_length=64)
    
    # Raw payload (encrypted at rest in production)
    payload_summary = models.JSONField(default=dict)
    
    class Meta:
        ordering = ["-action_timestamp"]
        indexes = [
            models.Index(fields=["anonymous_id", "action_timestamp"]),
            models.Index(fields=["actor_id", "action_type"]),
            models.Index(fields=["action_type", "action_timestamp"]),
        ]

class BiasAuditReport(models.Model):
    """
    Quarterly bias audit report.
    Spec Section 8.3: Demographic parity checks, calibration testing.
    """
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Reporting period
    period_start = models.DateField()
    period_end = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    
    # Model evaluated
    model_version = models.CharField(max_length=50)
    model_type = models.CharField(max_length=20, choices=[
        ("classifier", "STI Risk Classifier"),
        ("forecaster", "Outbreak Forecaster")
    ])
    
    # Subgroup performance
    subgroup_results = models.JSONField(default=dict, help_text="""
    {
        "age_13_17": {"auc_roc": 0.87, "f1": 0.78, "sample_count": 450},
        "age_18_24": {"auc_roc": 0.91, "f1": 0.84, "sample_count": 3200},
        "age_25_34": {"auc_roc": 0.89, "f1": 0.81, "sample_count": 2800},
        ...
    }
    """)
    
    # Threshold violations
    violations_found = models.JSONField(default=list, help_text="""
    [
        {"subgroup": "age_65_plus", "metric": "auc_roc", "value": 0.78, "threshold": 0.80}
    ]
    """)
    
    # Calibration results
    calibration_by_subgroup = models.JSONField(default=dict)
    
    # Overall assessment
    passes_bias_audit = models.BooleanField(default=True)
    recommended_actions = models.JSONField(default=list)
    
    # Reviewed by
    reviewed_by = models.CharField(max_length=100, blank=True)
    review_date = models.DateField(null=True)
    
    class Meta:
        ordering = ["-generated_at"]

class DriftDetectionResult(models.Model):
    """
    Population Stability Index tracking.
    Spec Section 4.3: PSI computed weekly, threshold 0.2 triggers retraining.
    """
    detection_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Model reference
    model_version = models.CharField(max_length=50)
    feature_name = models.CharField(max_length=100)
    
    # PSI metrics
    psi_score = models.FloatField()
    psi_threshold = models.FloatField(default=0.2)
    is_drift_detected = models.BooleanField(default=False)
    
    # Distribution comparison
    training_distribution = models.JSONField(default=dict)
    current_distribution = models.JSONField(default=dict)
    
    # Impact assessment
    severity = models.CharField(max_length=20, choices=[
        ("low", "Low"),
        ("moderate", "Moderate"),
        ("high", "High"),
        ("critical", "Critical")
    ])
    
    # Action taken
    retraining_triggered = models.BooleanField(default=False)
    retraining_job_id = models.UUIDField(null=True)
    alert_sent = models.BooleanField(default=False)
    
    detected_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-detected_at"]
        indexes = [
            models.Index(fields=["model_version", "feature_name"]),
            models.Index(fields=["is_drift_detected", "severity"]),
        ]

class ClinicalValidationGate(models.Model):
    """
    Hard validation gate for all guidance content.
    Spec Section 8.2: No ML-generated advice surfaced without completing this gate.
    """
    gate_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Content being validated
    content_type = models.CharField(max_length=30, choices=[
        ("patient_guidance", "Patient Guidance"),
        ("clinician_guidance", "Clinician Guidance"),
        ("treatment_protocol", "Treatment Protocol"),
        ("differential_diagnosis", "Differential Diagnosis")
    ])
    content_id = models.UUIDField()
    
    # Validation stages
    stage_drafted = models.DateTimeField(auto_now_add=True)
    stage_clinician_1_review = models.DateTimeField(null=True)
    stage_clinician_2_review = models.DateTimeField(null=True)
    stage_id_specialist_review = models.DateTimeField(null=True)
    stage_moh_review = models.DateTimeField(null=True)
    
    # Reviewers
    clinician_1_name = models.CharField(max_length=100, blank=True)
    clinician_1_credentials = models.CharField(max_length=200, blank=True)
    clinician_2_name = models.CharField(max_length=100, blank=True)
    clinician_2_credentials = models.CharField(max_length=200, blank=True)
    id_specialist_name = models.CharField(max_length=100, blank=True)
    id_specialist_credentials = models.CharField(max_length=200, blank=True)
    moh_signatory_name = models.CharField(max_length=100, blank=True)
    moh_signatory_credentials = models.CharField(max_length=200, blank=True)
    
    # Status
    status = models.CharField(max_length=30, choices=[
        ("draft", "Draft"),
        ("under_clinical_review", "Under Clinical Review"),
        ("clinician_approved", "Clinician Approved"),
        ("id_specialist_approved", "ID Specialist Approved"),
        ("moh_approved", "MOH Approved"),
        ("deployed", "Deployed"),
        ("deprecated", "Deprecated")
    ], default="draft")
    
    # Hard gate enforcement
    deployment_blocked = models.BooleanField(default=True)
    block_reason = models.TextField(blank=True)
    
    # Version control
    version = models.PositiveIntegerField(default=1)
    previous_version = models.ForeignKey('self', on_delete=models.SET_NULL, null=True)
    
    # Annual re-review
    annual_review_due = models.DateField()
    last_reviewed_at = models.DateTimeField(null=True)
    
    class Meta:
        ordering = ["-stage_drafted"]

class DataRetentionPolicy(models.Model):
    """
    Data retention configuration and execution log.
    Spec Section 5.2: Patient inputs deleted after 90 days. Aggregated data 5 years.
    """
    policy_name = models.CharField(max_length=100, unique=True)
    data_type = models.CharField(max_length=50, choices=[
        ("patient_input", "Patient Input Forms"),
        ("processed_record", "Processed Anonymised Records"),
        ("audit_log", "Audit Logs"),
        ("model_training_data", "Model Training Data"),
        ("geospatial_grid", "Geospatial Grid Data")
    ])
    retention_days = models.PositiveIntegerField()
    auto_delete_enabled = models.BooleanField(default=True)
    
    # Execution tracking
    last_execution = models.DateTimeField(null=True)
    records_deleted_last_run = models.PositiveIntegerField(default=0)
    execution_log = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ComplianceViolation(models.Model):
    """
    Tracked compliance violations requiring remediation.
    """
    violation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    severity = models.CharField(max_length=20, choices=[
        ("low", "Low"),
        ("moderate", "Moderate"),
        ("high", "High"),
        ("critical", "Critical")
    ])
    
    category = models.CharField(max_length=50, choices=[
        ("privacy", "Privacy Violation"),
        ("bias", "Bias/Fairness Violation"),
        ("validation", "Clinical Validation Failure"),
        ("data_retention", "Data Retention Non-Compliance"),
        ("security", "Security Incident"),
        ("audit_gap", "Missing Audit Trail")
    ])
    
    description = models.TextField()
    affected_system_component = models.CharField(max_length=100)
    
    # Detection
    detected_by = models.CharField(max_length=100)
    detected_at = models.DateTimeField(auto_now_add=True)
    related_audit_log = models.ForeignKey(ImmutableAuditLog, on_delete=models.SET_NULL, null=True)
    
    # Remediation
    remediation_plan = models.TextField(blank=True)
    remediation_deadline = models.DateField()
    remediation_completed = models.BooleanField(default=False)
    remediation_completed_at = models.DateTimeField(null=True)
    remediated_by = models.CharField(max_length=100, blank=True)
    
    # Escalation
    escalated_to = models.CharField(max_length=100, blank=True)
    escalation_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ["-detected_at"]