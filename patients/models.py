from django.db import models

# Create your models here.
from django.db import models
import uuid

class SessionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Assessment Completed"
    EXPIRED = "expired", "Session Expired"
    CONVERTED = "converted", "Tested at Clinic"

class AnonymousSession(models.Model):
    """
    Privacy-first anonymous session.
    Spec Section 7.1: No personally identifiable information collected or stored.
    """
    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # No name, phone, email, or national ID — ever
    # Session is identified only by this random UUID
    
    # Session metadata
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    
    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE
    )
    
    # Consent flags
    consent_testing_reminder = models.BooleanField(default=False)
    consent_result_tracking = models.BooleanField(default=False)
    
    # Geographic context (county only — no precise location)
    county = models.CharField(max_length=50, blank=True, db_index=True)
    sub_county = models.CharField(max_length=50, blank=True)
    
    # Device fingerprint (hashed, for abuse prevention only)
    device_hash = models.CharField(max_length=64, blank=True, help_text="Hashed device fingerprint for rate limiting")
    
    class Meta:
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["device_hash", "created_at"]),
        ]
    
    def is_expired(self) -> bool:
        from django.utils import timezone
        return timezone.now() > self.expires_at

class PatientAssessment(models.Model):
    """
    A single risk assessment within an anonymous session.
    """
    assessment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AnonymousSession, on_delete=models.CASCADE, related_name="assessments")
    
    # Raw inputs (stored temporarily, deleted after 90 days per Section 5.2)
    symptoms_reported = models.JSONField(default=dict, help_text="32 symptom responses")
    behaviours_reported = models.JSONField(default=dict)
    demographics_reported = models.JSONField(default=dict)  # age, sex only — no names
    
    # Processed results (from preprocessing pipeline)
    risk_score = models.FloatField(null=True)
    risk_level = models.CharField(max_length=20, blank=True)
    sti_probabilities = models.JSONField(default=dict)
    top_contributing_factors = models.JSONField(default=list)
    
    # Assessment metadata
    completed_at = models.DateTimeField(auto_now_add=True)
    follow_up_scheduled = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-completed_at"]

class TestingReminder(models.Model):
    """
    Consent-based testing reminder.
    Spec Section 7.1: Consent-based testing reminder notifications.
    """
    reminder_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AnonymousSession, on_delete=models.CASCADE, related_name="reminders")
    
    # Reminder settings (no contact info stored — patient must return with session ID)
    scheduled_date = models.DateField()
    reminder_type = models.CharField(max_length=20, choices=[
        ("3_day", "3 Day Follow-up"),
        ("1_week", "1 Week Follow-up"),
        ("2_week", "2 Week Follow-up"),
        ("1_month", "1 Month Follow-up"),
        ("3_month", "3 Month Follow-up")
    ])
    
    # Status
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged = models.BooleanField(default=False)
    
    # Privacy: no SMS, no email, no push notification
    # Patient must proactively check back using session ID
    
    created_at = models.DateTimeField(auto_now_add=True)

class ResultTracking(models.Model):
    """
    Anonymous result tracking over time.
    Spec Section 7.1: Anonymised result tracking over time.
    """
    tracking_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AnonymousSession, on_delete=models.CASCADE, related_name="results")
    
    # Patient self-reported result (not verified by system)
    test_date = models.DateField()
    test_type = models.CharField(max_length=50)  # e.g., "HIV rapid", "Chlamydia PCR"
    self_reported_result = models.CharField(max_length=20, choices=[
        ("negative", "Negative"),
        ("positive", "Positive"),
        ("inconclusive", "Inconclusive"),
        ("pending", "Pending")
    ])
    
    # Trend analysis
    previous_risk_score = models.FloatField(null=True)
    current_risk_score = models.FloatField(null=True)
    
    # No linkage to clinic records — purely patient-managed
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

class PatientEducationContent(models.Model):
    """
    Plain-language educational content per risk level.
    Clinically validated before deployment (Section 8.2).
    """
    content_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    risk_level = models.CharField(max_length=20, choices=[
        ("low", "Low"),
        ("moderate", "Moderate"),
        ("high", "High"),
        ("critical", "Critical")
    ])
    
    title = models.CharField(max_length=200)
    plain_language_summary = models.TextField()
    what_to_do_next = models.JSONField(default=list)
    when_to_seek_care = models.TextField()
    prevention_tips = models.JSONField(default=list)
    myth_busters = models.JSONField(default=list)
    
    # Validation
    validated_by = models.CharField(max_length=100)
    validated_at = models.DateTimeField()
    review_due = models.DateField()
    
    # Language
    language = models.CharField(max_length=10, default="en")  # en, sw, etc.
    
    class Meta:
        unique_together = [["risk_level", "language"]]