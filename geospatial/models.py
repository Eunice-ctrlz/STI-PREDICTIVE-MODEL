from django.contrib.gis.db import models as gis_models
from django.db import models


class GeographicRiskZone(models.Model):
    RISK_LEVELS = [
        ('low', 'Low'),
        ('moderate', 'Moderate'),
        ('high', 'High'),
        ('very_high', 'Very High'),
    ]
    
    name = models.CharField(max_length=200)
    county = models.CharField(max_length=100, db_index=True)
    sub_county = models.CharField(max_length=100, blank=True)
    ward = models.CharField(max_length=100, blank=True)
    
    # GeoDjango fields
    boundary = gis_models.PolygonField(null=True, blank=True, srid=4326)
    centroid = gis_models.PointField(null=True, blank=True, srid=4326)
    
    # Risk metrics
    risk_level = models.CharField(max_length=20, choices=RISK_LEVELS)
    risk_score = models.FloatField()
    population_at_risk = models.PositiveIntegerField(default=0)
    total_screenings = models.PositiveIntegerField(default=0)
    positive_cases = models.PositiveIntegerField(default=0)
    
    # Temporal
    period_start = models.DateField()
    period_end = models.DateField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['county', 'risk_level']),
            models.Index(fields=['period_start', 'period_end']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.risk_level}"


class FacilityLocation(models.Model):
    from clinicians.models import Facility
    
    facility = models.OneToOneField(Facility, on_delete=models.CASCADE, related_name='geo')
    catchment_area = gis_models.PolygonField(null=True, blank=True, srid=4326)
    service_radius_km = models.FloatField(default=5.0)
    
    def __str__(self):
        return f"Geo: {self.facility.name}"