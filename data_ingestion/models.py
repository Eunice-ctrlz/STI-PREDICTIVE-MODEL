"""
STI Predictive Model — Data Ingestion Layer (L1)
models.py

Tracks raw records, sync jobs, source configurations, and ingestion audit logs
for all four data sources: WHO API, MOH FHIR, Geolocation, and Patient Forms.
"""

import uuid
from django.db import models


class DataSourceType(models.TextChoices):
    WHO_API = "who_api", "WHO Global Surveillance API"
    MOH_DB = "moh_db", "MOH Kenya HL7 FHIR Database"
    GEOLOCATION = "geolocation", "Geolocation / PostGIS Layer"
    PATIENT_FORM = "patient_form", "Patient Input Form"


class IngestionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    PARTIAL = "partial", "Partial — Some Records Failed"
    FAILED = "failed", "Failed"


class RecordStatus(models.TextChoices):
    RAW = "raw", "Raw — Not Yet Forwarded"
    FORWARDED = "forwarded", "Forwarded to Preprocessing"
    REJECTED = "rejected", "Rejected — Validation Failed"
    DUPLICATE = "duplicate", "Duplicate — Skipped"


# ---------------------------------------------------------------------------
# Source Configuration
# ---------------------------------------------------------------------------

class DataSourceConfig(models.Model):
    """
    Stores per-source connection settings and sync schedules.
    One row per data source. Credentials are referenced by name
    from environment variables — never stored in plaintext.
    """
    source = models.CharField(
        max_length=20,
        choices=DataSourceType.choices,
        unique=True,
    )
    base_url = models.URLField(help_text="API or FHIR base URL for this source")
    auth_method = models.CharField(
        max_length=20,
        choices=[
            ("api_key", "API Key + TLS"),
            ("oauth2", "OAuth 2.0 + VPN"),
            ("internal", "Internal / No Auth"),
            ("anon_tls", "Anonymous ID + TLS"),
        ],
        default="api_key",
    )
    # References environment variable name, not the actual credential
    credential_env_key = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name of the env var holding the API key or client secret",
    )
    sync_frequency = models.CharField(
        max_length=20,
        choices=[
            ("realtime", "Real-time"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
        ],
        default="daily",
    )
    is_active = models.BooleanField(default=True)
    timeout_seconds = models.PositiveIntegerField(default=30)
    max_retries = models.PositiveIntegerField(default=3)
    last_successful_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Data Source Configuration"

    def __str__(self):
        return f"{self.get_source_display()} ({self.sync_frequency})"


# ---------------------------------------------------------------------------
# Ingestion Job
# ---------------------------------------------------------------------------

class IngestionJob(models.Model):
    """
    One row per ingestion run (scheduled or triggered).
    Tracks progress and record-level statistics.
    """
    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=20, choices=DataSourceType.choices)
    status = models.CharField(
        max_length=20,
        choices=IngestionStatus.choices,
        default=IngestionStatus.PENDING,
    )
    triggered_by = models.CharField(
        max_length=20,
        choices=[
            ("scheduler", "Scheduler"),
            ("api", "API Call"),
            ("manual", "Manual"),
        ],
        default="scheduler",
    )

    # Record counters
    raw_record_count = models.PositiveIntegerField(default=0)
    accepted_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    forwarded_count = models.PositiveIntegerField(default=0)

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Source-specific sync window
    sync_window_start = models.DateTimeField(null=True, blank=True)
    sync_window_end = models.DateTimeField(null=True, blank=True)

    # Audit
    error_log = models.TextField(blank=True)
    preprocessing_job_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="UUID of the downstream PreprocessingJob this data was forwarded to",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"IngestionJob({self.source}, {self.status}, {self.created_at:%Y-%m-%d})"


# ---------------------------------------------------------------------------
# Raw Records
# ---------------------------------------------------------------------------

class RawRecord(models.Model):
    """
    Stores each raw record exactly as received from its source,
    before any preprocessing or transformation.

    Privacy note: patient form submissions are already pseudonymised
    at point of capture (anonymous session ID only). WHO and MOH
    records may contain regional identifiers that are stripped
    before forwarding to preprocessing.
    """
    record_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        IngestionJob,
        on_delete=models.CASCADE,
        related_name="raw_records",
    )
    source = models.CharField(max_length=20, choices=DataSourceType.choices)
    status = models.CharField(
        max_length=20,
        choices=RecordStatus.choices,
        default=RecordStatus.RAW,
    )

    # The raw payload as received (JSON)
    raw_payload = models.JSONField(help_text="Verbatim payload from source")

    # Extracted top-level fields for fast querying (denormalised)
    geographic_region = models.CharField(max_length=100, blank=True)
    sub_county = models.CharField(max_length=100, blank=True)
    record_date = models.DateField(null=True, blank=True)

    # Validation
    validation_errors = models.JSONField(
        default=list,
        help_text="List of field-level validation error messages",
    )
    is_duplicate = models.BooleanField(default=False)
    duplicate_of = models.UUIDField(
        null=True,
        blank=True,
        help_text="record_id of the original record this duplicates",
    )

    # Forwarding
    forwarded_at = models.DateTimeField(null=True, blank=True)
    preprocessing_record_id = models.UUIDField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["source", "status"]),
            models.Index(fields=["geographic_region"]),
            models.Index(fields=["record_date"]),
        ]

    def __str__(self):
        return f"RawRecord({self.source}, {self.status})"


# ---------------------------------------------------------------------------
# Geolocation Record (extension of RawRecord for spatial data)
# ---------------------------------------------------------------------------

class GeoRecord(models.Model):
    """
    Holds aggregated, grid-snapped geospatial data ingested
    from the PostGIS / GeoJSON layer. Never stores individual
    coordinates — all points are rounded to ±5km grid before
    insertion as per the differential privacy policy.
    """
    geo_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        IngestionJob,
        on_delete=models.CASCADE,
        related_name="geo_records",
    )
    # Grid-snapped coordinates (differential privacy applied at ingestion)
    latitude_grid = models.FloatField(help_text="Latitude rounded to ±5km grid")
    longitude_grid = models.FloatField(help_text="Longitude rounded to ±5km grid")
    county = models.CharField(max_length=100)
    sub_county = models.CharField(max_length=100, blank=True)

    # Aggregated counts per STI type (minimum cell size = 100 records)
    sti_counts = models.JSONField(
        default=dict,
        help_text="Dict of STI type → case count within this grid cell",
    )
    total_cases = models.PositiveIntegerField(default=0)
    suppressed = models.BooleanField(
        default=False,
        help_text="True if cell count < 100 and output is suppressed",
    )

    week_start = models.DateField(help_text="Monday of the reporting week")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("latitude_grid", "longitude_grid", "week_start")]
        indexes = [
            models.Index(fields=["county", "week_start"]),
        ]

    def __str__(self):
        return f"GeoRecord({self.county}, {self.week_start})"


# ---------------------------------------------------------------------------
# Sync Audit Log
# ---------------------------------------------------------------------------

class SyncAuditLog(models.Model):
    """
    Immutable append-only audit trail for all ingestion events.
    Required for regulatory compliance (Kenya Data Protection Act 2019).
    Records are never updated or deleted.
    """
    log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        IngestionJob,
        on_delete=models.PROTECT,  # Never cascade — audit logs are permanent
        related_name="audit_logs",
    )
    source = models.CharField(max_length=20, choices=DataSourceType.choices)
    event_type = models.CharField(
        max_length=40,
        choices=[
            ("job_started", "Job Started"),
            ("job_completed", "Job Completed"),
            ("job_failed", "Job Failed"),
            ("record_accepted", "Record Accepted"),
            ("record_rejected", "Record Rejected"),
            ("record_duplicate", "Record Duplicate"),
            ("record_forwarded", "Record Forwarded to Preprocessing"),
            ("auth_success", "Authentication Succeeded"),
            ("auth_failure", "Authentication Failed"),
            ("rate_limit_hit", "Rate Limit Hit"),
            ("conflict_resolved", "Conflict Resolved"),
        ],
    )
    detail = models.JSONField(default=dict, help_text="Event-specific payload")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["source", "event_type"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        return f"AuditLog({self.source}, {self.event_type}, {self.timestamp:%Y-%m-%d %H:%M})"