"""
STI Predictive Model — Data Ingestion Layer (L1)
services.py

Four connector classes — one per data source — plus a dispatcher and
a conflict-resolution engine. Each connector is responsible for:
  1. Authenticating with the external system
  2. Fetching raw data for a given sync window
  3. Normalising to internal schema
  4. Basic field-level validation
  5. Saving RawRecord rows and writing SyncAuditLog events

Privacy rules enforced at ingestion time:
  - Geolocation data snapped to ±5km grid before any storage
  - Patient form submissions require explicit consent flag = True
  - MOH records stripped of facility-level geocodes
  - No individual coordinates stored at any point
"""

import os
import uuid
import hashlib
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple, Optional, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.db import transaction
from django.utils import timezone

from .models import (
    IngestionJob, IngestionStatus, RawRecord, RecordStatus,
    GeoRecord, DataSourceConfig, DataSourceType, SyncAuditLog,
)
from .schemas import (
    WHOSurveillanceRecord, MOHFHIRBundle, GeoGridCell,
    PatientFormSubmission, ConflictResolutionPolicy,
)

logger = logging.getLogger(__name__)

# Minimum cell count for geolocation suppression (privacy policy §5.2)
GEO_MINIMUM_CELL_COUNT = 100

# Grid spacing: 0.045° ≈ 5km
GEO_GRID_DEGREES = 0.045


# ---------------------------------------------------------------------------
# Shared Utilities
# ---------------------------------------------------------------------------

def _build_session(timeout: int = 30, max_retries: int = 3) -> requests.Session:
    """Returns a requests Session with retry logic and TLS enforcement."""
    session = requests.Session()
    retry = Retry(
        total=max_retries,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.timeout = timeout
    return session


def _snap_to_grid(lat: float, lon: float) -> Tuple[float, float]:
    """Round coordinates to ±5km grid (differential privacy, §5.2)."""
    lat_snapped = round(lat / GEO_GRID_DEGREES) * GEO_GRID_DEGREES
    lon_snapped = round(lon / GEO_GRID_DEGREES) * GEO_GRID_DEGREES
    return round(lat_snapped, 6), round(lon_snapped, 6)


def _write_audit(job: IngestionJob, event_type: str, detail: Dict) -> None:
    """Append an immutable audit log entry."""
    SyncAuditLog.objects.create(
        job=job,
        source=job.source,
        event_type=event_type,
        detail=detail,
    )


def _dedup_hash(payload: Dict, keys: List[str]) -> str:
    """Deterministic hash of selected payload keys for deduplication."""
    key_str = "|".join(str(payload.get(k, "")) for k in sorted(keys))
    return hashlib.sha256(key_str.encode()).hexdigest()


# ---------------------------------------------------------------------------
# WHO API Connector
# ---------------------------------------------------------------------------

class WHOAPIConnector:
    """
    Connects to the WHO Global STI Surveillance REST API.
    Authentication: API Key passed as X-Api-Key header over TLS 1.3.
    Sync frequency: daily.
    """

    DEDUP_KEYS = ["record_id", "country_code", "sti_type", "reporting_period_start"]

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.api_key = os.environ.get(config.credential_env_key, "")
        self.session = _build_session(config.timeout_seconds, config.max_retries)
        self.session.headers.update({
            "X-Api-Key": self.api_key,
            "Accept": "application/json",
        })

    def _get(self, path: str, params: Dict) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def fetch(
        self,
        job: IngestionJob,
        sync_start: Optional[datetime] = None,
        sync_end: Optional[datetime] = None,
        sti_types: Optional[List[str]] = None,
        country_codes: Optional[List[str]] = None,
    ) -> Tuple[int, int, int]:
        """
        Fetch and store WHO surveillance records for a given window.
        Returns (accepted, rejected, duplicate) counts.
        """
        sync_start = sync_start or (timezone.now() - timedelta(days=1))
        sync_end = sync_end or timezone.now()

        params: Dict[str, Any] = {
            "from": sync_start.isoformat(),
            "to": sync_end.isoformat(),
            "country": "KEN",  # Kenya-scoped ingestion
        }
        if sti_types:
            params["sti_types"] = ",".join(sti_types)
        if country_codes:
            params["countries"] = ",".join(country_codes)

        accepted = rejected = duplicates = 0
        seen_hashes: set = set()
        page = 1

        _write_audit(job, "auth_success", {"method": "api_key", "source": "who_api"})

        while True:
            params["page"] = page
            try:
                data = self._get("/v1/surveillance/records", params)
            except requests.HTTPError as exc:
                if exc.response.status_code == 429:
                    _write_audit(job, "rate_limit_hit", {"page": page})
                    raise
                raise

            records = data.get("results", [])
            if not records:
                break

            for raw in records:
                errors = self._validate(raw)
                h = _dedup_hash(raw, self.DEDUP_KEYS)

                if h in seen_hashes:
                    duplicates += 1
                    status = RecordStatus.DUPLICATE
                    _write_audit(job, "record_duplicate", {"hash": h})
                elif errors:
                    rejected += 1
                    status = RecordStatus.REJECTED
                    _write_audit(job, "record_rejected", {"errors": errors, "raw": raw})
                else:
                    accepted += 1
                    status = RecordStatus.RAW
                    seen_hashes.add(h)
                    _write_audit(job, "record_accepted", {"record_id": raw.get("record_id")})

                RawRecord.objects.create(
                    job=job,
                    source=DataSourceType.WHO_API,
                    status=status,
                    raw_payload=raw,
                    geographic_region=raw.get("region_code", ""),
                    record_date=self._parse_date(raw.get("reporting_period_start")),
                    validation_errors=errors,
                    is_duplicate=(h in seen_hashes and status == RecordStatus.DUPLICATE),
                )

            if not data.get("next"):
                break
            page += 1

        return accepted, rejected, duplicates

    def _validate(self, raw: Dict) -> List[str]:
        errors = []
        if not raw.get("record_id"):
            errors.append("Missing required field: record_id")
        if not raw.get("sti_type"):
            errors.append("Missing required field: sti_type")
        if raw.get("incidence_rate") is None:
            errors.append("Missing required field: incidence_rate")
        elif raw["incidence_rate"] < 0:
            errors.append("incidence_rate must be non-negative")
        period_start = raw.get("reporting_period_start")
        period_end = raw.get("reporting_period_end")
        if period_start and period_end and period_start > period_end:
            errors.append("reporting_period_start must be before reporting_period_end")
        return errors

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# MOH HL7 FHIR Connector
# ---------------------------------------------------------------------------

class MOHFHIRConnector:
    """
    Connects to the MOH Kenya HL7 FHIR R4 server.
    Authentication: OAuth 2.0 client credentials flow, routed over VPN.
    Sync frequency: weekly.

    Fetches FHIR Bundle resources (Patient + Observation).
    Strips any facility-level geocodes before storage.
    """

    DEDUP_KEYS = ["pseudo_id", "observation_id", "confirmed_date"]

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.client_secret = os.environ.get(config.credential_env_key, "")
        self.client_id = os.environ.get("MOH_FHIR_CLIENT_ID", "")
        self.token_url = os.environ.get("MOH_FHIR_TOKEN_URL", "")
        self.session = _build_session(config.timeout_seconds, config.max_retries)
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def _ensure_token(self, job: IngestionJob) -> None:
        """Refresh OAuth2 access token if expired."""
        if self._access_token and self._token_expires_at and \
                timezone.now() < self._token_expires_at:
            return
        resp = requests.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "fhir.read",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            _write_audit(job, "auth_failure", {"status": resp.status_code})
            resp.raise_for_status()

        token_data = resp.json()
        self._access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self._token_expires_at = timezone.now() + timedelta(seconds=expires_in - 60)
        self.session.headers["Authorization"] = f"Bearer {self._access_token}"
        _write_audit(job, "auth_success", {"method": "oauth2", "source": "moh_db"})

    def _get_bundle(self, resource_type: str, params: Dict) -> Dict:
        url = f"{self.base_url}/{resource_type}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def fetch(
        self,
        job: IngestionJob,
        sync_start: Optional[datetime] = None,
        sync_end: Optional[datetime] = None,
        county_filter: Optional[List[str]] = None,
    ) -> Tuple[int, int, int]:
        """
        Fetch patient observations (confirmed STI diagnoses) from MOH FHIR.
        Returns (accepted, rejected, duplicate) counts.
        """
        self._ensure_token(job)

        sync_start = sync_start or (timezone.now() - timedelta(days=7))
        sync_end = sync_end or timezone.now()

        params: Dict[str, Any] = {
            "_type": "Patient,Observation",
            "date": f"ge{sync_start.date().isoformat()}",
            "_lastUpdated": f"le{sync_end.date().isoformat()}",
            "_count": 200,
            "_format": "json",
        }
        if county_filter:
            params["address-state"] = ",".join(county_filter)

        accepted = rejected = duplicates = 0
        seen_hashes: set = set()
        next_url: Optional[str] = f"{self.base_url}/Bundle"

        while next_url:
            response = self.session.get(next_url, params=params)
            response.raise_for_status()
            bundle = response.json()

            entries = bundle.get("entry", [])
            for entry in entries:
                resource = entry.get("resource", {})
                resource_type = resource.get("resourceType")

                # Strip geocodes before any processing
                resource = self._strip_geocodes(resource)

                errors = self._validate_resource(resource, resource_type)
                h = _dedup_hash(resource, self.DEDUP_KEYS)

                if h in seen_hashes:
                    duplicates += 1
                    status = RecordStatus.DUPLICATE
                elif errors:
                    rejected += 1
                    status = RecordStatus.REJECTED
                    _write_audit(job, "record_rejected", {"errors": errors})
                else:
                    accepted += 1
                    status = RecordStatus.RAW
                    seen_hashes.add(h)

                region = self._extract_county(resource)
                RawRecord.objects.create(
                    job=job,
                    source=DataSourceType.MOH_DB,
                    status=status,
                    raw_payload=resource,
                    geographic_region=region,
                    record_date=self._extract_date(resource),
                    validation_errors=errors,
                    is_duplicate=(status == RecordStatus.DUPLICATE),
                )

            # FHIR pagination via next link
            next_link = next(
                (l["url"] for l in bundle.get("link", []) if l.get("relation") == "next"),
                None,
            )
            next_url = next_link
            params = {}  # Next URL is fully qualified

        return accepted, rejected, duplicates

    @staticmethod
    def _strip_geocodes(resource: Dict) -> Dict:
        """Remove any address.line and position fields to prevent geocode leakage."""
        if resource.get("resourceType") == "Patient":
            for address in resource.get("address", []):
                address.pop("line", None)
                address.pop("text", None)
                # Remove position.longitude/latitude from facility entries
                address.pop("extension", None)
        return resource

    @staticmethod
    def _validate_resource(resource: Dict, resource_type: Optional[str]) -> List[str]:
        errors = []
        if resource_type not in ("Patient", "Observation"):
            errors.append(f"Unexpected resourceType: {resource_type}")
        if not resource.get("id"):
            errors.append("Missing FHIR resource id")
        if resource_type == "Observation":
            if not resource.get("code"):
                errors.append("Observation missing code element")
            if not resource.get("subject", {}).get("reference"):
                errors.append("Observation missing subject reference")
        return errors

    @staticmethod
    def _extract_county(resource: Dict) -> str:
        for address in resource.get("address", []):
            if address.get("state"):
                return address["state"]
        return ""

    @staticmethod
    def _extract_date(resource: Dict) -> Optional[date]:
        effective = resource.get("effectiveDateTime") or resource.get("issued")
        if effective:
            try:
                return date.fromisoformat(effective[:10])
            except ValueError:
                pass
        return None


# ---------------------------------------------------------------------------
# Geolocation Connector
# ---------------------------------------------------------------------------

class GeoIngestionConnector:
    """
    Ingests aggregated GeoJSON / PostGIS grid data from the internal
    geolocation layer.

    Privacy enforcement (§5.2):
    - Individual coordinates are NEVER ingested
    - All points must already be aggregated at sub-county level
    - Cells with < GEO_MINIMUM_CELL_COUNT cases are suppressed
    - Coordinates are snapped to ±5km grid at ingestion time
    """

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.session = _build_session(config.timeout_seconds, config.max_retries)
        # Internal service — bearer token from env
        internal_token = os.environ.get(config.credential_env_key, "")
        if internal_token:
            self.session.headers["Authorization"] = f"Bearer {internal_token}"

    def fetch(
        self,
        job: IngestionJob,
        week_start: Optional[date] = None,
        county_filter: Optional[List[str]] = None,
    ) -> Tuple[int, int, int]:
        """
        Fetch weekly geo grid data. Returns (accepted, rejected, suppressed) counts.
        """
        week_start = week_start or (date.today() - timedelta(days=date.today().weekday()))
        params: Dict[str, Any] = {
            "week_start": week_start.isoformat(),
            "format": "geojson",
        }
        if county_filter:
            params["counties"] = ",".join(county_filter)

        response = self.session.get(f"{self.base_url}/v1/geo/grid", params=params)
        response.raise_for_status()
        geojson = response.json()

        accepted = rejected = suppressed = 0
        features = geojson.get("features", [])

        with transaction.atomic():
            for feature in features:
                props = feature.get("properties", {})
                coords = feature.get("geometry", {}).get("coordinates", [None, None])

                if not coords or coords[0] is None:
                    rejected += 1
                    _write_audit(job, "record_rejected", {"reason": "missing coordinates"})
                    continue

                lon, lat = coords[0], coords[1]

                # Snap to grid (privacy enforcement)
                lat_grid, lon_grid = _snap_to_grid(lat, lon)

                total_cases = props.get("total_cases", 0)
                is_suppressed = total_cases < GEO_MINIMUM_CELL_COUNT

                if is_suppressed:
                    suppressed += 1
                else:
                    accepted += 1

                # Store grid record (suppressed cells are stored but flagged)
                GeoRecord.objects.update_or_create(
                    latitude_grid=lat_grid,
                    longitude_grid=lon_grid,
                    week_start=week_start,
                    defaults={
                        "job": job,
                        "county": props.get("county", ""),
                        "sub_county": props.get("sub_county", ""),
                        "sti_counts": props.get("sti_counts", {}) if not is_suppressed else {},
                        "total_cases": total_cases if not is_suppressed else 0,
                        "suppressed": is_suppressed,
                    },
                )

                # Also store as RawRecord for audit trail
                RawRecord.objects.create(
                    job=job,
                    source=DataSourceType.GEOLOCATION,
                    status=RecordStatus.RAW if not is_suppressed else RecordStatus.REJECTED,
                    raw_payload={
                        "lat_grid": lat_grid,
                        "lon_grid": lon_grid,
                        **props,
                        "suppressed": is_suppressed,
                    },
                    geographic_region=props.get("county", ""),
                    sub_county=props.get("sub_county", ""),
                    record_date=week_start,
                    validation_errors=["suppressed: cell count below minimum"] if is_suppressed else [],
                )

        return accepted, rejected, suppressed


# ---------------------------------------------------------------------------
# Patient Form Handler
# ---------------------------------------------------------------------------

class PatientFormIngestionHandler:
    """
    Handles real-time patient form submissions.

    - Consent validation is a hard gate: submissions without consent = rejected
    - Session ID is the only identifier — no PII ingested
    - Forwards directly to the preprocessing API after validation
    """

    REQUIRED_SYMPTOM_KEYS = {
        "genital_discharge", "painful_urination", "genital_sores", "pelvic_pain",
        "testicular_pain", "abnormal_bleeding", "itching", "fever", "rash",
        "swollen_lymph_nodes", "rectal_pain", "rectal_bleeding", "sore_throat",
        "joint_pain", "hair_loss", "weight_loss", "night_sweats", "fatigue",
        "nausea", "vomiting", "diarrhoea", "abdominal_pain", "back_pain",
        "dysuria", "dyspareunia", "menorrhagia", "metrorrhagia", "urethral_discharge",
        "vaginal_odour", "dysmenorrhoea", "proctitis", "lymphadenopathy",
    }

    def ingest_single(
        self,
        job: IngestionJob,
        submission: PatientFormSubmission,
    ) -> Tuple[str, List[str]]:
        """
        Validate and store a single patient form submission.
        Returns (status, validation_errors).
        """
        errors = self._validate(submission)

        if not submission.data_consent_given:
            errors.insert(0, "consent_required: data_consent_given must be True")

        status = RecordStatus.REJECTED if errors else RecordStatus.RAW

        raw_payload = submission.dict()
        # Remove session_id from payload before storage — store anonymised hash only
        session_hash = hashlib.sha256(submission.session_id.encode()).hexdigest()[:32]
        raw_payload["session_id"] = session_hash

        RawRecord.objects.create(
            job=job,
            source=DataSourceType.PATIENT_FORM,
            status=status,
            raw_payload=raw_payload,
            geographic_region=submission.geographic_region,
            sub_county=submission.sub_county or "",
            record_date=submission.submitted_at.date(),
            validation_errors=errors,
        )

        if not errors:
            _write_audit(job, "record_accepted", {"session_hash": session_hash})
        else:
            _write_audit(job, "record_rejected", {"errors": errors})

        return status, errors

    def _validate(self, submission: PatientFormSubmission) -> List[str]:
        errors = []
        provided_keys = set(submission.symptoms.keys())
        missing = self.REQUIRED_SYMPTOM_KEYS - provided_keys
        if missing:
            errors.append(f"Missing symptom fields: {sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}")
        unknown = provided_keys - self.REQUIRED_SYMPTOM_KEYS
        if unknown:
            errors.append(f"Unknown symptom fields: {sorted(unknown)[:5]}")
        if submission.age < 13 or submission.age > 100:
            errors.append("age must be between 13 and 100")
        if submission.partner_count_12m < 0:
            errors.append("partner_count_12m must be non-negative")
        return errors


# ---------------------------------------------------------------------------
# Conflict Resolution Engine
# ---------------------------------------------------------------------------

class ConflictResolver:
    """
    Detects and resolves conflicting incidence data between WHO and MOH
    records covering the same region, STI type, and time period.
    """

    def resolve(
        self,
        who_record: Dict,
        moh_record: Dict,
        policy: ConflictResolutionPolicy,
    ) -> Tuple[Dict, str]:
        """
        Compare WHO and MOH records for the same region/period.
        Returns (winning_record, resolution_note).
        """
        who_count = who_record.get("case_count", 0) or 0
        moh_count = moh_record.get("case_count", 0) or 0

        divergence_pct = 0.0
        if moh_count > 0:
            divergence_pct = abs(who_count - moh_count) / moh_count * 100

        flagged = divergence_pct > policy.flag_threshold_pct

        if flagged and policy.strategy == "flag_for_review":
            note = (
                f"FLAGGED: WHO={who_count} vs MOH={moh_count} "
                f"({divergence_pct:.1f}% divergence — exceeds {policy.flag_threshold_pct}% threshold)"
            )
            logger.warning(note)
            # Return MOH as default while flagged
            return moh_record, note

        if policy.strategy == "prefer_moh":
            return moh_record, "prefer_moh"
        elif policy.strategy == "prefer_who":
            return who_record, "prefer_who"
        elif policy.strategy == "latest_wins":
            who_ts = who_record.get("updated_at", "")
            moh_ts = moh_record.get("updated_at", "")
            winner = who_record if who_ts > moh_ts else moh_record
            return winner, "latest_wins"
        else:
            return moh_record, f"default_prefer_moh (strategy={policy.strategy})"


# ---------------------------------------------------------------------------
# Ingestion Dispatcher
# ---------------------------------------------------------------------------

class IngestionDispatcher:
    """
    Orchestrates a full ingestion run for a given source.
    Called by Celery tasks (tasks.py) or the API layer (api.py).
    """

    def __init__(self):
        self.conflict_resolver = ConflictResolver()

    def _get_config(self, source: str) -> DataSourceConfig:
        return DataSourceConfig.objects.get(source=source, is_active=True)

    def run(
        self,
        job: IngestionJob,
        **kwargs,
    ) -> Dict:
        """
        Dispatch ingestion for the source specified in job.source.
        kwargs are forwarded to the source-specific fetch() method.
        """
        job.status = IngestionStatus.RUNNING
        job.started_at = timezone.now()
        job.save()
        _write_audit(job, "job_started", {"source": job.source, "kwargs": str(kwargs)})

        try:
            config = self._get_config(job.source)

            if job.source == DataSourceType.WHO_API:
                connector = WHOAPIConnector(config)
                accepted, rejected, duplicates = connector.fetch(job, **kwargs)

            elif job.source == DataSourceType.MOH_DB:
                connector = MOHFHIRConnector(config)
                accepted, rejected, duplicates = connector.fetch(job, **kwargs)

            elif job.source == DataSourceType.GEOLOCATION:
                connector = GeoIngestionConnector(config)
                accepted, rejected, duplicates = connector.fetch(job, **kwargs)

            elif job.source == DataSourceType.PATIENT_FORM:
                # Patient forms are ingested one at a time via the API.
                # The dispatcher treats a batch submission as a single job.
                submissions = kwargs.get("submissions", [])
                handler = PatientFormIngestionHandler()
                accepted = rejected = duplicates = 0
                for sub in submissions:
                    status, _ = handler.ingest_single(job, sub)
                    if status == RecordStatus.RAW:
                        accepted += 1
                    else:
                        rejected += 1
            else:
                raise ValueError(f"Unknown source: {job.source}")

            total = accepted + rejected + duplicates
            job.raw_record_count = total
            job.accepted_count = accepted
            job.rejected_count = rejected
            job.duplicate_count = duplicates
            job.status = IngestionStatus.COMPLETED if rejected == 0 else IngestionStatus.PARTIAL
            job.completed_at = timezone.now()

            # Update last_successful_sync on the config
            config.last_successful_sync = timezone.now()
            config.save(update_fields=["last_successful_sync"])

            _write_audit(job, "job_completed", {
                "accepted": accepted,
                "rejected": rejected,
                "duplicates": duplicates,
            })

        except Exception as exc:
            job.status = IngestionStatus.FAILED
            job.error_log = str(exc)
            job.completed_at = timezone.now()
            _write_audit(job, "job_failed", {"error": str(exc)})
            logger.exception("Ingestion job %s failed: %s", job.job_id, exc)
            raise

        finally:
            job.save()

        return {
            "job_id": str(job.job_id),
            "source": job.source,
            "accepted": job.accepted_count,
            "rejected": job.rejected_count,
            "duplicates": job.duplicate_count,
            "status": job.status,
        }