from django.db import models
from django.contrib.auth.models import User


class AuditLog(models.Model):
    ACTION_TYPES = [
        ('create', 'Create'),
        ('read', 'Read'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('predict', 'Prediction'),
        ('export', 'Data Export'),
        ('login', 'Login'),
        ('logout', 'Logout'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    user_name = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    
    # What was affected
    resource_type = models.CharField(max_length=50)  # e.g., 'Patient', 'Prediction'
    resource_id = models.CharField(max_length=100, blank=True)
    
    # Details
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Before/After for updates
    previous_state = models.JSONField(default=dict, blank=True)
    new_state = models.JSONField(default=dict, blank=True)
    
    # Consent tracking
    consent_obtained = models.BooleanField(default=False)
    consent_type = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'action', 'created_at']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]
    
    def __str__(self):
        return f"{self.user_name} {self.action} {self.resource_type} at {self.created_at}"


class DataRetentionPolicy(models.Model):
    data_type = models.CharField(max_length=50, unique=True)
    retention_days = models.PositiveIntegerField()
    anonymize_after_days = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.data_type}: {self.retention_days} days"


class PatientConsent(models.Model):
    from patients.models import Patient
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='consents')
    consent_type = models.CharField(max_length=50)  # screening, research, data_sharing
    granted = models.BooleanField(default=False)
    granted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    document_version = models.CharField(max_length=20, default='1.0')
    witness_name = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['patient', 'consent_type']
    
    def __str__(self):
        return f"{self.patient.patient_id} - {self.consent_type}: {'Yes' if self.granted else 'No'}"