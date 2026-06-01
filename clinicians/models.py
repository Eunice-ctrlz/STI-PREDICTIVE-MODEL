from django.db import models

# Create your models here.
from django.contrib.auth.models import User
import uuid

class ClinicianRole(models.TextChoices):
    GENERAL_PRACTITIONER = "gp", "General Practitioner"
    INFECTIOUS_DISEASE_SPECIALIST = "ids", "Infectious Disease Specialist"
    PUBLIC_HEALTH_OFFICER = "pho", "Public Health Officer"
    LAB_TECHNICIAN = "lab", "Laboratory Technician"
    MOH_ADMIN = "moh", "MOH Administrator"

class VerificationStatus(models.TextChoices):
    PENDING = "pending", "Pending Verification"
    VERIFIED = "verified", "Verified"
    SUSPENDED = "suspended", "Suspended"
    EXPIRED = "expired", "License Expired"

class ClinicianProfile(models.Model):
    """
    Verified clinician profile with credential checking.
    Spec Section 7.2: Accessible by licensed healthcare providers with verified credentials.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="clinician_profile")
    clinician_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Professional credentials
    role = models.CharField(max_length=20, choices=ClinicianRole.choices)
    license_number = models.CharField(max_length=50, unique=True, db_index=True)
    license_issuing_body = models.CharField(max_length=100)  # e.g., "Kenya Medical Practitioners and Dentists Council"
    license_expiry_date = models.DateField()
    specialization = models.CharField(max_length=100, blank=True)
    
    # Verification
    verification_status = models.CharField(
        max_length=20, 
        choices=VerificationStatus.choices, 
        default=VerificationStatus.PENDING
    )
    verified_by = models.CharField(max_length=100, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Practice information
    facility_name = models.CharField(max_length=200)
    facility_county = models.CharField(max_length=50)
    facility_sub_county = models.CharField(max_length=50)
    
    # Permissions
    can_view_patient_risk = models.BooleanField(default=True)
    can_view_population_data = models.BooleanField(default=False)  # Only PHO/IDS by default
    can_approve_guidance = models.BooleanField(default=False)  # Only IDS/MOH
    can_override_threshold = models.BooleanField(default=False)  # Critical override
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["license_number", "verification_status"]),
            models.Index(fields=["facility_county", "role"]),
        ]

    def is_verified(self) -> bool:
        return self.verification_status == VerificationStatus.VERIFIED and \
               self.license_expiry_date > models.DateField.today()

class ClinicalGuidance(models.Model):
    """
    Clinically validated guidance content.
    Spec Section 8.2: All guidance must pass through mandatory clinical validation.
    """
    guidance_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Content
    title = models.CharField(max_length=200)
    sti_type = models.CharField(max_length=20, choices=[
        ("hiv", "HIV"),
        ("chlamydia", "Chlamydia"),
        ("syphilis", "Syphilis"),
        ("gonorrhoea", "Gonorrhoea"),
        ("hpv", "HPV"),
        ("hsv2", "HSV-2"),
        ("general", "General STI Guidance")
    ])
    symptom_pattern = models.JSONField(default=dict, help_text="Symptom combinations triggering this guidance")
    risk_level = models.CharField(max_length=20, choices=[
        ("low", "Low"),
        ("moderate", "Moderate"),
        ("high", "High"),
        ("critical", "Critical")
    ])
    
    # Guidance content
    differential_diagnosis = models.JSONField(default=list, help_text="Ranked differential diagnoses")
    recommended_tests = models.JSONField(default=list)
    treatment_protocol = models.JSONField(default=dict, help_text="MOH-aligned treatment protocol")
    referral_criteria = models.JSONField(default=list)
    patient_counseling_points = models.JSONField(default=list)
    
    # Validation gate (Section 8.2)
    drafted_by = models.CharField(max_length=100)
    reviewed_by_clinician_1 = models.CharField(max_length=100, blank=True)
    reviewed_by_clinician_2 = models.CharField(max_length=100, blank=True)
    infectious_disease_specialist = models.CharField(max_length=100, blank=True)
    moh_signatory = models.CharField(max_length=100, blank=True)
    
    validation_status = models.CharField(max_length=20, choices=[
        ("draft", "Draft"),
        ("under_review", "Under Review"),
        ("clinician_approved", "Clinician Approved"),
        ("moh_approved", "MOH Approved"),
        ("deployed", "Deployed"),
        ("deprecated", "Deprecated")
    ], default="draft")
    
    version = models.PositiveIntegerField(default=1)
    previous_version = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    deployed_at = models.DateTimeField(null=True, blank=True)
    annual_review_due = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["sti_type", "risk_level", "validation_status"]),
            models.Index(fields=["version", "validation_status"]),
        ]

class PatientRiskAlert(models.Model):
    """
    Alert when patient risk exceeds clinical threshold (score > 0.7).
    Spec Section 3.2: Risk scores above 0.7 trigger mandatory clinical review flag.
    """
    alert_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Patient reference (anonymous)
    anonymous_id = models.CharField(max_length=64, db_index=True)
    
    # Risk details
    risk_score = models.FloatField()
    risk_level = models.CharField(max_length=20)
    sti_probabilities = models.JSONField(default=dict)
    top_features = models.JSONField(default=list, help_text="Top 3 contributing features (SHAP)")
    
    # Alert routing
    assigned_clinician = models.ForeignKey(ClinicianProfile, on_delete=models.SET_NULL, null=True, related_name="assigned_alerts")
    facility_county = models.CharField(max_length=50)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ("new", "New"),
        ("acknowledged", "Acknowledged"),
        ("under_review", "Under Review"),
        ("reviewed", "Reviewed"),
        ("escalated", "Escalated"),
        ("resolved", "Resolved")
    ], default="new")
    
    # Clinical actions
    clinician_notes = models.TextField(blank=True)
    recommended_action = models.CharField(max_length=50, blank=True)
    test_orders = models.JSONField(default=list, blank=True)
    referral_made = models.BooleanField(default=False)
    referral_destination = models.CharField(max_length=200, blank=True)
    
    # Timestamps
    triggered_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-triggered_at"]
        indexes = [
            models.Index(fields=["status", "facility_county"]),
            models.Index(fields=["anonymous_id", "triggered_at"]),
            models.Index(fields=["assigned_clinician", "status"]),
        ]

class PopulationRiskSummary(models.Model):
    """
    Weekly aggregated risk profile for clinician's patient population.
    Spec Section 7.2: Aggregate risk profile for patient population.
    """
    summary_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Scope
    facility_county = models.CharField(max_length=50)
    facility_sub_county = models.CharField(max_length=50, blank=True)
    reporting_period_start = models.DateField()
    reporting_period_end = models.DateField()
    
    # Risk distribution
    total_patients_assessed = models.PositiveIntegerField(default=0)
    low_risk_count = models.PositiveIntegerField(default=0)
    moderate_risk_count = models.PositiveIntegerField(default=0)
    high_risk_count = models.PositiveIntegerField(default=0)
    critical_risk_count = models.PositiveIntegerField(default=0)
    
    # STI breakdown
    sti_distribution = models.JSONField(default=dict, help_text="Counts per STI type")
    
    # Alerts
    new_alerts_this_period = models.PositiveIntegerField(default=0)
    resolved_alerts_this_period = models.PositiveIntegerField(default=0)
    avg_time_to_acknowledgment_hours = models.FloatField(null=True)
    
    # Trends
    week_over_week_delta = models.FloatField(null=True, help_text="Percentage change in critical alerts")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reporting_period_end"]
        unique_together = [["facility_county", "facility_sub_county", "reporting_period_end"]]

class AuditLog(models.Model):
    """
    Immutable audit log of all predictions, inputs, and guidance outputs.
    Spec Section 3.1: Required for regulatory review.
    """
    log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Action details
    action_type = models.CharField(max_length=50, choices=[
        ("prediction_viewed", "Prediction Viewed"),
        ("guidance_accessed", "Guidance Accessed"),
        ("alert_acknowledged", "Alert Acknowledged"),
        ("alert_resolved", "Alert Resolved"),
        ("threshold_override", "Threshold Override"),
        ("patient_referred", "Patient Referred"),
        ("test_ordered", "Test Ordered"),
        ("guidance_approved", "Guidance Approved"),
        ("guidance_deployed", "Guidance Deployed")
    ])
    
    # Actor
    clinician = models.ForeignKey(ClinicianProfile, on_delete=models.SET_NULL, null=True)
    anonymous_id = models.CharField(max_length=64, blank=True, db_index=True)
    
    # Data accessed
    risk_score = models.FloatField(null=True)
    guidance_version = models.PositiveIntegerField(null=True)
    model_version = models.CharField(max_length=50, blank=True)
    
    # Context
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    
    # Immutable timestamp
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["clinician", "action_type"]),
            models.Index(fields=["anonymous_id", "timestamp"]),
        ]