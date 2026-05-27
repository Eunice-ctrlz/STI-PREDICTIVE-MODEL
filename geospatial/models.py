from django.db import models
import uuid

class STIType(models.TextChoices):
    HIV = "hiv", "HIV"
    CHLAMYDIA = "chlamydia", "Chlamydia"
    SYPHILIS = "syphilis", "Syphilis"
    GONORRHOEA = "gonorrhoea", "Gonorrhoea"
    HPV = "hpv", "HPV"
    HSV2 = "hsv2", "HSV-2"
    ALL = "all", "All STIs Combined"

class RiskLevel(models.TextChoices):
    LOW = "low", "Low"
    MODERATE = "moderate", "Moderate"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"

class GridCell(models.Model):
    """
    Aggregated spatial grid cell for privacy-compliant hotspot mapping.
    Minimum 25km² per spec Section 4.1.3 and 5.2.
    """
    cell_id = models.CharField(max_length=50, primary_key=True, db_index=True)
    
    # Grid coordinates (rounded to ±5km)
    grid_lat = models.FloatField()
    grid_lon = models.FloatField()
    
    # Geographic boundaries
    county = models.CharField(max_length=50, db_index=True)
    sub_county = models.CharField(max_length=50, db_index=True)
    
    # Stored as plain latitude/longitude so the project can run without GIS libs
    centroid_lat = models.FloatField(null=True, blank=True)
    centroid_lon = models.FloatField(null=True, blank=True)
    boundary = models.JSONField(null=True, blank=True)
    
    # Population context
    population_estimate = models.PositiveIntegerField(default=0)
    healthcare_access_index = models.FloatField(default=0.0)
    road_network_score = models.FloatField(default=0.0)
    
    # Spatial autocorrelation (Moran's I)
    morans_i = models.FloatField(null=True, help_text="Spatial autocorrelation index")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["county", "sub_county"]),
            models.Index(fields=["grid_lat", "grid_lon"]),
            models.Index(fields=["centroid_lat", "centroid_lon"]),
        ]
        unique_together = [["grid_lat", "grid_lon"]]

class AggregatedIncident(models.Model):
    """
    Anonymised incident counts per grid cell.
    No individual geolocation — only aggregated counts.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grid_cell = models.ForeignKey(GridCell, on_delete=models.CASCADE, related_name="incidents")
    sti_type = models.CharField(max_length=20, choices=STIType.choices, db_index=True)
    
    # Aggregated counts (never individual records)
    incident_count = models.PositiveIntegerField(default=0)
    unique_patients_estimate = models.PositiveIntegerField(default=0)
    
    # Time period
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Risk classification
    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, default=RiskLevel.LOW)
    risk_score = models.FloatField(default=0.0, help_text="Normalised risk score 0-1")
    
    # KDE density value
    kde_density = models.FloatField(null=True, help_text="Kernel Density Estimation value")
    
    # DBSCAN cluster membership
    cluster_id = models.IntegerField(null=True, help_text="DBSCAN cluster label")
    is_outlier = models.BooleanField(default=False, help_text="DBSCAN noise point")
    
    # Differential privacy applied
    dp_noise_applied = models.BooleanField(default=True)
    dp_epsilon = models.FloatField(default=0.1)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["sti_type", "period_start", "period_end"]),
            models.Index(fields=["risk_level", "grid_cell"]),
            models.Index(fields=["cluster_id"]),
        ]
        unique_together = [["grid_cell", "sti_type", "period_start"]]

class HotspotAlert(models.Model):
    """
    Automated hotspot detection alerts for public health officers.
    """
    alert_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Alert classification
    severity = models.CharField(max_length=20, choices=RiskLevel.choices)
    sti_type = models.CharField(max_length=20, choices=STIType.choices)
    
    # Affected area
    primary_county = models.CharField(max_length=50)
    affected_sub_counties = models.JSONField(default=list)
    
    # Cluster statistics
    cluster_size_cells = models.PositiveIntegerField()
    total_incidents = models.PositiveIntegerField()
    population_at_risk = models.PositiveIntegerField()
    
    # Temporal
    detection_period_start = models.DateField()
    detection_period_end = models.DateField()
    forecast_30_day = models.FloatField(null=True)
    forecast_60_day = models.FloatField(null=True)
    forecast_90_day = models.FloatField(null=True)
    
    # Trend analysis
    year_over_year_delta = models.FloatField(null=True, help_text="Percentage change vs same period last year")
    
    # Alert status
    is_active = models.BooleanField(default=True)
    acknowledged_by = models.CharField(max_length=100, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    
    # GeoJSON for map rendering
    geojson_heatmap = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

class HealthcareFacility(models.Model):
    """
    MOH-registered clinics for testing location finder.
    """
    facility_id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=200)
    county = models.CharField(max_length=50, db_index=True)
    sub_county = models.CharField(max_length=50, db_index=True)
    
    lat = models.FloatField()
    lon = models.FloatField()
    services = models.JSONField(default=list, help_text="List of STI testing services offered")
    operating_hours = models.JSONField(default=dict)
    contact_phone = models.CharField(max_length=20, blank=True)
    
    is_moh_registered = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    # Distance metrics (computed)
    catchment_population = models.PositiveIntegerField(default=0)
    
    class Meta:
        indexes = [
            models.Index(fields=["lat", "lon"]),
            models.Index(fields=["county", "is_active"]),
        ]