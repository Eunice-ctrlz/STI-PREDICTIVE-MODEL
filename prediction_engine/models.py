from django.db import models
from patients.models import Patient
from clinicians.models import Clinician


class RiskPrediction(models.Model):
    RISK_LEVELS = [
        ('low', 'Low Risk'),
        ('moderate', 'Moderate Risk'),
        ('high', 'High Risk'),
        ('very_high', 'Very High Risk'),
    ]
    
    STI_TYPES = [
        ('hiv', 'HIV'),
        ('syphilis', 'Syphilis'),
        ('gonorrhea', 'Gonorrhea'),
        ('chlamydia', 'Chlamydia'),
        ('hepatitis_b', 'Hepatitis B'),
        ('hpv', 'HPV'),
        ('general', 'General STI Risk'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='predictions')
    clinician = models.ForeignKey(Clinician, on_delete=models.SET_NULL, null=True, blank=True)
    sti_type = models.CharField(max_length=20, choices=STI_TYPES, default='general')
    
    # Prediction outputs
    risk_score = models.FloatField(help_text="Probability 0.0 - 1.0")
    risk_level = models.CharField(max_length=20, choices=RISK_LEVELS)
    confidence_interval_lower = models.FloatField(null=True, blank=True)
    confidence_interval_upper = models.FloatField(null=True, blank=True)
    
    # Feature importance (stored as JSON)
    top_risk_factors = models.JSONField(default=dict, blank=True)
    
    # Input features snapshot (for reproducibility)
    input_features = models.JSONField(default=dict)
    
    # Model metadata
    model_version = models.CharField(max_length=50)
    model_name = models.CharField(max_length=100)
    
    # Recommendations
    recommended_tests = models.JSONField(default=list, blank=True)
    recommended_actions = models.TextField(blank=True)
    
    # Validation
    validated_by_clinician = models.BooleanField(default=False)
    clinician_notes = models.TextField(blank=True)
    actual_outcome = models.CharField(max_length=50, blank=True)  # For model retraining
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient', 'sti_type', 'created_at']),
            models.Index(fields=['risk_level', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.patient.patient_id} - {self.sti_type} - {self.risk_level} ({self.risk_score:.2f})"


class ModelPerformanceMetric(models.Model):
    model_version = models.CharField(max_length=50, db_index=True)
    sti_type = models.CharField(max_length=20, choices=RiskPrediction.STI_TYPES)
    auc_roc = models.FloatField()
    precision = models.FloatField()
    recall = models.FloatField()
    f1_score = models.FloatField()
    accuracy = models.FloatField()
    calibration_slope = models.FloatField(null=True, blank=True)
    brier_score = models.FloatField(null=True, blank=True)
    evaluated_on = models.DateField()
    sample_size = models.PositiveIntegerField()
    
    class Meta:
        ordering = ['-evaluated_on']
    
    def __str__(self):
        return f"{self.model_version} - {self.sti_type} - AUC: {self.auc_roc:.3f}"