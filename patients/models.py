from django.db import models
from django.contrib.auth.models import User


class Patient(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
        ('U', 'Unknown/Prefer not to say'),
    ]
    
    MARITAL_STATUS = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
        ('cohabiting', 'Cohabiting'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    patient_id = models.CharField(max_length=50, unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    # Risk factors
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS, default='single')
    number_of_partners_12m = models.PositiveIntegerField(default=0)
    number_of_partners_lifetime = models.PositiveIntegerField(default=0)
    condom_use_frequency = models.FloatField(
        help_text="0=Never, 0.25=Rarely, 0.5=Sometimes, 0.75=Often, 1.0=Always",
        default=0.0
    )
    substance_use = models.BooleanField(default=False)
    substance_type = models.CharField(max_length=200, blank=True)
    prior_sti_history = models.BooleanField(default=False)
    prior_sti_types = models.CharField(max_length=300, blank=True)
    hiv_status_known = models.BooleanField(default=False)
    hiv_status = models.CharField(
        max_length=20,
        choices=[('negative', 'Negative'), ('positive', 'Positive'), ('unknown', 'Unknown')],
        default='unknown'
    )
    symptoms_present = models.BooleanField(default=False)
    symptom_description = models.TextField(blank=True)
    
    # Geographic
    county = models.CharField(max_length=100, blank=True)
    sub_county = models.CharField(max_length=100, blank=True)
    ward = models.CharField(max_length=100, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['county', 'sub_county']),
            models.Index(fields=['gender', 'age_group']),
        ]
    
    @property
    def age(self):
        from datetime import date
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
    @property
    def age_group(self):
        age = self.age
        if age < 15: return '<15'
        elif age < 20: return '15-19'
        elif age < 25: return '20-24'
        elif age < 30: return '25-29'
        elif age < 35: return '30-34'
        elif age < 40: return '35-39'
        elif age < 50: return '40-49'
        else: return '50+'
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def __str__(self):
        return f"{self.patient_id} - {self.full_name}"


class PatientVisit(models.Model):
    VISIT_TYPE = [
        ('screening', 'Screening'),
        ('follow_up', 'Follow-up'),
        ('treatment', 'Treatment'),
        ('counseling', 'Counseling'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    visit_date = models.DateTimeField(auto_now_add=True)
    visit_type = models.CharField(max_length=20, choices=VISIT_TYPE, default='screening')
    facility = models.CharField(max_length=200, blank=True)
    clinician_notes = models.TextField(blank=True)
    tests_conducted = models.JSONField(default=dict, blank=True)
    test_results = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"Visit {self.id} - {self.patient.patient_id} on {self.visit_date.date()}"