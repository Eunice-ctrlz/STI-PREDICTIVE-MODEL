from django.db import models
from django.contrib.auth.models import User


class Facility(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    county = models.CharField(max_length=100)
    sub_county = models.CharField(max_length=100)
    ward = models.CharField(max_length=100)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    facility_type = models.CharField(
        max_length=50,
        choices=[
            ('hospital', 'Hospital'),
            ('health_center', 'Health Center'),
            ('dispensary', 'Dispensary'),
            ('clinic', 'Clinic'),
        ],
        default='health_center'
    )
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Facilities"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"


class Clinician(models.Model):
    ROLE_CHOICES = [
        ('doctor', 'Doctor'),
        ('nurse', 'Nurse'),
        ('clinical_officer', 'Clinical Officer'),
        ('lab_tech', 'Laboratory Technician'),
        ('counselor', 'Counselor'),
        ('admin', 'Administrator'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    staff_id = models.CharField(max_length=50, unique=True)
    phone = models.CharField(max_length=20)
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)
    facility = models.ForeignKey(Facility, on_delete=models.SET_NULL, null=True, related_name='clinicians')
    license_number = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.staff_id} - {self.user.get_full_name()}"