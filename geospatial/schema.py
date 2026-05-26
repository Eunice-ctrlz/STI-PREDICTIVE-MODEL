from ninja import Schema, Field
from typing import List, Dict, Optional, Literal, Tuple, Annotated
from uuid import UUID
from datetime import date, datetime
from pydantic import confloat, conint

# --- Input Schemas ---

class GridCellInput(Schema):
    """Input for creating/updating a grid cell"""
    grid_lat: float = Field(..., ge=-5.0, le=6.0, description="Rounded latitude")
    grid_lon: float = Field(..., ge=33.0, le=42.0, description="Rounded longitude")
    county: str = Field(..., min_length=1, max_length=50)
    sub_county: str = Field(..., min_length=1, max_length=50)
    population_estimate: Annotated[int, Field(ge=0)] = 0
    healthcare_access_index: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    road_network_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0

class IncidentAggregationInput(Schema):
    """Input for aggregating incidents into a grid cell"""
    grid_cell_id: str
    sti_type: Literal["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2", "all"]
    incident_count: Annotated[int, Field(ge=0)]
    period_start: date
    period_end: date

class HotspotDetectionConfig(Schema):
    """Configuration for hotspot detection algorithms"""
    # DBSCAN parameters
    dbscan_eps_km: Annotated[float, Field(ge=1.0, le=50.0)] = 10.0
    dbscan_min_samples: Annotated[int, Field(ge=3, le=100)] = 5
    
    # KDE parameters
    kde_bandwidth_km: Annotated[float, Field(ge=1.0, le=50.0)] = 15.0
    
    # Risk thresholds
    low_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.25
    moderate_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.50
    high_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.75
    
    # Temporal window
    analysis_period_days: Annotated[int, Field(ge=7, le=365)] = 30
    
    # Privacy
    apply_differential_privacy: bool = True
    dp_epsilon: Annotated[float, Field(gt=0, le=1.0)] = 0.1
    min_cell_size_km2: Annotated[int, Field(ge=25)] = 25

class FacilityQuery(Schema):
    """Query for finding nearest healthcare facilities"""
    lat: float = Field(..., ge=-5.0, le=6.0)
    lon: float = Field(..., ge=33.0, le=42.0)
    sti_type: Optional[Literal["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2"]] = None
    max_distance_km: Annotated[float, Field(ge=1.0, le=200.0)] = 50.0
    limit: Annotated[int, Field(ge=1, le=50)] = 10

# --- Output Schemas ---

class GridCellOut(Schema):
    cell_id: str
    grid_lat: float
    grid_lon: float
    county: str
    sub_county: str
    population_estimate: int
    healthcare_access_index: float
    road_network_score: float
    morans_i: Optional[float]

class IncidentAggregateOut(Schema):
    id: UUID
    grid_cell: GridCellOut
    sti_type: str
    incident_count: int
    unique_patients_estimate: int
    period_start: date
    period_end: date
    risk_level: str
    risk_score: float
    kde_density: Optional[float]
    cluster_id: Optional[int]
    is_outlier: bool

class GeoJSONFeature(Schema):
    """GeoJSON Feature for map rendering"""
    type: Literal["Feature"] = "Feature"
    geometry: Dict
    properties: Dict

class GeoJSONFeatureCollection(Schema):
    """GeoJSON FeatureCollection for heatmap layers"""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[GeoJSONFeature]

class HeatmapLayerOut(Schema):
    """Heatmap layer for a specific STI type"""
    sti_type: str
    period_start: date
    period_end: date
    geojson: GeoJSONFeatureCollection
    color_scale: Dict[str, str] = {
        "low": "#22c55e",      # green
        "moderate": "#f59e0b",  # amber
        "high": "#ef4444",      # red
        "critical": "#7f1d1d"   # dark red
    }
    total_cells: int
    hotspot_cells: int

class HotspotAlertOut(Schema):
    alert_id: UUID
    severity: str
    sti_type: str
    primary_county: str
    affected_sub_counties: List[str]
    cluster_size_cells: int
    total_incidents: int
    population_at_risk: int
    detection_period_start: date
    detection_period_end: date
    forecast_30_day: Optional[float]
    forecast_60_day: Optional[float]
    forecast_90_day: Optional[float]
    year_over_year_delta: Optional[float]
    is_active: bool
    geojson_heatmap: Dict
    created_at: datetime

class FacilityOut(Schema):
    facility_id: str
    name: str
    county: str
    sub_county: str
    lat: float
    lon: float
    services: List[str]
    distance_km: Optional[float]
    is_moh_registered: bool

class SpatialAnalysisOut(Schema):
    """Complete spatial analysis for a region"""
    county: str
    sub_county: Optional[str]
    sti_type: str
    analysis_period: str
    total_incidents: int
    risk_distribution: Dict[str, int]
    morans_i: Optional[float]
    hotspot_clusters: int
    outlier_points: int
    avg_healthcare_access: float
    recommended_facilities: List[FacilityOut]

class MoransIResult(Schema):
    """Spatial autocorrelation result"""
    morans_i: float
    expected_i: float
    variance: float
    z_score: float
    p_value: float
    interpretation: str