from django.db import models

# Create your models here.
import uuid

class ReportType(models.TextChoices):
    WEEKLY_SUMMARY = "weekly", "Weekly Summary"
    MONTHLY_BURDEN = "monthly", "Monthly Burden Estimate"
    OUTBREAK_ALERT = "outbreak", "Outbreak Alert"
    ANNUAL_REVIEW = "annual", "Annual Review"
    AD_HOC = "ad_hoc", "Ad-hoc Request"

class ReportFormat(models.TextChoices):
    CSV = "csv", "CSV"
    JSON = "json", "JSON"
    PDF = "pdf", "PDF"
    XLSX = "xlsx", "Excel"
    HL7 = "hl7", "HL7 FHIR"

class ReportStatus(models.TextChoices):
    GENERATING = "generating", "Generating"
    READY = "ready", "Ready for Download"
    SENT = "sent", "Sent to Recipient"
    FAILED = "failed", "Generation Failed"

class SurveillanceReport(models.Model):
    """
    Automated surveillance reporting aligned to WHO standards.
    Spec Section 7.4: Weekly automated summary reports aligned to WHO reporting standards.
    """
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_type = models.CharField(max_length=20, choices=ReportType.choices)
    
    # Reporting period
    period_start = models.DateField()
    period_end = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    
    # Geographic scope
    scope_national = models.BooleanField(default=True)
    counties_included = models.JSONField(default=list)
    
    # Content
    total_assessments = models.PositiveIntegerField(default=0)
    total_confirmed_cases = models.PositiveIntegerField(default=0)
    sti_breakdown = models.JSONField(default=dict, help_text="Counts per STI type")
    risk_distribution = models.JSONField(default=dict)
    
    # Demographics
    age_distribution = models.JSONField(default=dict)
    sex_distribution = models.JSONField(default=dict)
    geographic_distribution = models.JSONField(default=dict)
    
    # Testing and treatment metrics
    tests_conducted = models.PositiveIntegerField(default=0)
    tests_positive = models.PositiveIntegerField(default=0)
    treatment_initiated = models.PositiveIntegerField(default=0)
    treatment_completed = models.PositiveIntegerField(default=0)
    
    # Coverage gaps
    testing_coverage_rate = models.FloatField(default=0.0)
    untested_high_risk_estimate = models.PositiveIntegerField(default=0)
    facility_gaps = models.JSONField(default=list)
    
    # WHO alignment
    who_indicator_codes = models.JSONField(default=list)
    who_submission_ready = models.BooleanField(default=False)
    
    # Export
    status = models.CharField(max_length=20, choices=ReportStatus.choices, default=ReportStatus.GENERATING)
    file_path = models.CharField(max_length=500, blank=True)
    file_format = models.CharField(max_length=10, choices=ReportFormat.choices, default=ReportFormat.CSV)
    file_size_bytes = models.PositiveIntegerField(default=0)
    
    # Distribution
    sent_to_who = models.BooleanField(default=False)
    sent_to_moh = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["report_type", "period_end"]),
            models.Index(fields=["scope_national", "generated_at"]),
        ]

class PolicyDashboardMetric(models.Model):
    """
    Policy dashboard metrics for MOH decision makers.
    Spec Section 7.4: Policy dashboard with STI burden estimates, testing coverage gaps, treatment uptake rates.
    """
    metric_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Metric classification
    category = models.CharField(max_length=50, choices=[
        ("burden", "STI Burden"),
        ("coverage", "Testing Coverage"),
        ("treatment", "Treatment Uptake"),
        ("forecast", "Forecast"),
        ("inequity", "Health Inequity")
    ])
    indicator_name = models.CharField(max_length=100)
    
    # Geographic scope
    county = models.CharField(max_length=50, blank=True, db_index=True)
    sub_county = models.CharField(max_length=50, blank=True)
    
    # Values
    current_value = models.FloatField()
    previous_value = models.FloatField(null=True)
    target_value = models.FloatField(null=True)
    unit = models.CharField(max_length=50, blank=True)
    
    # Trend
    trend_direction = models.CharField(max_length=20, choices=[
        ("improving", "Improving"),
        ("worsening", "Worsening"),
        ("stable", "Stable"),
        ("insufficient_data", "Insufficient Data")
    ])
    trend_percentage = models.FloatField(null=True)
    
    # Time period
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Data quality
    data_quality_score = models.FloatField(default=1.0)
    data_source = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [["category", "indicator_name", "county", "period_end"]]

class OutbreakNotificationConfig(models.Model):
    """
    Configurable alert thresholds for outbreak notification.
    Spec Section 7.4: Configurable alert thresholds for outbreak notification triggers.
    """
    config_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Trigger conditions
    sti_type = models.CharField(max_length=20)
    county = models.CharField(max_length=50, blank=True)
    
    threshold_type = models.CharField(max_length=20, choices=[
        ("incidence_rate", "Incidence Rate per 100k"),
        ("case_count", "Absolute Case Count"),
        ("percentage_increase", "Week-over-Week % Increase"),
        ("forecast_exceedance", "Forecast Exceedance")
    ])
    threshold_value = models.FloatField()
    
    # Notification settings
    notify_moh = models.BooleanField(default=True)
    notify_who = models.BooleanField(default=False)
    notify_county_officers = models.BooleanField(default=True)
    
    # Recipients
    email_recipients = models.JSONField(default=list)
    sms_recipients = models.JSONField(default=list)
    
    is_active = models.BooleanField(default=True)
    created_by = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

class OutbreakAlertHistory(models.Model):
    """
    Historical record of outbreak alerts sent.
    """
    alert_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Trigger details
    trigger_config = models.ForeignKey(OutbreakNotificationConfig, on_delete=models.SET_NULL, null=True)
    sti_type = models.CharField(max_length=20)
    county = models.CharField(max_length=50)
    
    # Triggered values
    actual_value = models.FloatField()
    threshold_value = models.FloatField()
    
    # Notification sent
    notifications_sent = models.JSONField(default=list)
    notification_timestamp = models.DateTimeField(auto_now_add=True)
    
    # Response tracking
    acknowledged_by = models.CharField(max_length=100, blank=True)
    response_actions = models.JSONField(default=list)
    resolved_at = models.DateTimeField(null=True, blank=True)

class WHODataExport(models.Model):
    """
    WHO-aligned data export for international surveillance.
    Spec Section 7.4: CSV and JSON export of aggregated non-identifiable surveillance data.
    """
    export_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Export metadata
    export_format = models.CharField(max_length=10, choices=ReportFormat.choices)
    data_period_start = models.DateField()
    data_period_end = models.DateField()
    
    # Content summary
    record_count = models.PositiveIntegerField()
    counties_covered = models.JSONField(default=list)
    sti_types_included = models.JSONField(default=list)
    
    # WHO metadata
    who_country_code = models.CharField(max_length=10, default="KEN")
    who_reporting_period = models.CharField(max_length=20)
    
    # File
    file_path = models.CharField(max_length=500)
    file_size_bytes = models.PositiveIntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)
    
    # Transmission
    transmitted_to_who = models.BooleanField(default=False)
    transmitted_at = models.DateTimeField(null=True, blank=True)
    transmission_confirmation = models.CharField(max_length=200, blank=True)

class GridCell(models.Model):
    """Geographic grid cell for spatial aggregation"""
    cell_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    county = models.CharField(max_length=50, db_index=True)
    sub_county = models.CharField(max_length=50, blank=True)
    population_estimate = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = [["county", "sub_county"]]

    def __str__(self):
        return f"{self.county} - {self.sub_county}"


class AggregatedIncident(models.Model):
    """Aggregated STI incident data for surveillance reporting"""
    incident_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grid_cell = models.ForeignKey(GridCell, on_delete=models.CASCADE, related_name="incidents")
    sti_type = models.CharField(max_length=50, db_index=True)
    period_start = models.DateField()
    period_end = models.DateField()
    incident_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end"]
        indexes = [
            models.Index(fields=["sti_type", "period_end"]),
            models.Index(fields=["period_start", "period_end"]),
        ]