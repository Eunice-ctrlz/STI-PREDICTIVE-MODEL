from django.db import models
from datetime import date
class Patient(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
        ('U', 'Unknown'),
    ]

    MARITAL_STATUS_CHOICES = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
        ('cohabiting', 'Cohabiting'),
    ]

    HIV_STATUS_CHOICES = [
        ('unknown', 'Unknown'),
        ('negative', 'Negative'),
        ('positive', 'Positive'),
    ]

    patient_id = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='U')
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    sub_county = models.CharField(max_length=100, blank=True, null=True)
    ward = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, default='single')
    number_of_partners_12m = models.IntegerField(default=0)
    number_of_partners_lifetime = models.IntegerField(default=0)
    condom_use_frequency = models.FloatField(default=0.0)
    substance_use = models.BooleanField(default=False)
    substance_type = models.CharField(max_length=255, blank=True, null=True)
    prior_sti_history = models.BooleanField(default=False)
    prior_sti_types = models.CharField(max_length=255, blank=True, null=True)
    hiv_status_known = models.BooleanField(default=False)
    hiv_status = models.CharField(max_length=20, choices=HIV_STATUS_CHOICES, default='unknown')
    symptoms_present = models.BooleanField(default=False)
    symptom_description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def age(self):
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    @property
    def age_group(self):
        age = self.age
        if age < 15:
            return "under_15"
        elif age < 25:
            return "15_24"
        elif age < 35:
            return "25_34"
        elif age < 45:
            return "35_44"
        else:
            return "45_plus"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.patient_id})"
