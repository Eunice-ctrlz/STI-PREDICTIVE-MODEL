from ninja import Router, NinjaAPI
from django.shortcuts import get_object_or_404
from typing import List, Optional
from datetime import date, timedelta
import numpy as np
from django.db.models import Avg

from .schema import (
    GridCellInput, IncidentAggregationInput, HotspotDetectionConfig,
    FacilityQuery, GridCellOut, IncidentAggregateOut, HeatmapLayerOut,
    HotspotAlertOut, FacilityOut, SpatialAnalysisOut, MoransIResult,
    GeoJSONFeatureCollection
)
from .services import SpatialAnalyzer, FacilityFinder, GeospatialPrivacy
from .models import GridCell, AggregatedIncident, HotspotAlert, HealthcareFacility, STIType

api = NinjaAPI(title="STI Geospatial API", version="1.0", urls_namespace="geospatial-api")
router = Router()

@router.post("/grid-cells", response=GridCellOut, tags=["Grid Management"])
def create_grid_cell(request, payload: GridCellInput):
    """
    Create a privacy-compliant grid cell.
    Coordinates are automatically rounded to ±5km grid.
    """
    # Enforce privacy grid
    grid_lat, grid_lon = GeospatialPrivacy.round_to_grid(payload.grid_lat, payload.grid_lon)
    
    cell_id = f"{grid_lat:.4f}_{grid_lon:.4f}"
    
    cell, created = GridCell.objects.get_or_create(
        cell_id=cell_id,
        defaults={
            "grid_lat": grid_lat,
            "grid_lon": grid_lon,
            "county": payload.county,
            "sub_county": payload.sub_county,
            "population_estimate": payload.population_estimate,
            "healthcare_access_index": payload.healthcare_access_index,
            "road_network_score": payload.road_network_score
        }
    )
    
    return GridCellOut(
        cell_id=cell.cell_id,
        grid_lat=cell.grid_lat,
        grid_lon=cell.grid_lon,
        county=cell.county,
        sub_county=cell.sub_county,
        population_estimate=cell.population_estimate,
        healthcare_access_index=cell.healthcare_access_index,
        road_network_score=cell.road_network_score,
        morans_i=cell.morans_i
    )

@router.post("/incidents/aggregate", response=IncidentAggregateOut, tags=["Incident Aggregation"])
def aggregate_incidents(request, payload: IncidentAggregationInput):
    """
    Aggregate anonymised incidents into a grid cell.
    This is the ONLY way incident data enters the geospatial system.
    No individual coordinates are ever stored.
    """
    grid_cell = get_object_or_404(GridCell, cell_id=payload.grid_cell_id)
    
    # Apply differential privacy
    from preprocessing.services import DifferentialPrivacy
    dp = DifferentialPrivacy(epsilon=0.1)
    dp_count = max(0, int(dp.add_laplace_noise(payload.incident_count)))
    
    incident, created = AggregatedIncident.objects.update_or_create(
        grid_cell=grid_cell,
        sti_type=payload.sti_type,
        period_start=payload.period_start,
        defaults={
            "period_end": payload.period_end,
            "incident_count": dp_count,
            "unique_patients_estimate": dp_count,  # Conservative estimate
            "dp_noise_applied": True,
            "dp_epsilon": 0.1
        }
    )
    
    return IncidentAggregateOut(
        id=incident.id,
        grid_cell=GridCellOut(
            cell_id=grid_cell.cell_id,
            grid_lat=grid_cell.grid_lat,
            grid_lon=grid_cell.grid_lon,
            county=grid_cell.county,
            sub_county=grid_cell.sub_county,
            population_estimate=grid_cell.population_estimate,
            healthcare_access_index=grid_cell.healthcare_access_index,
            road_network_score=grid_cell.road_network_score,
            morans_i=grid_cell.morans_i
        ),
        sti_type=incident.sti_type,
        incident_count=incident.incident_count,
        unique_patients_estimate=incident.unique_patients_estimate,
        period_start=incident.period_start,
        period_end=incident.period_end,
        risk_level=incident.risk_level,
        risk_score=incident.risk_score,
        kde_density=incident.kde_density,
        cluster_id=incident.cluster_id,
        is_outlier=incident.is_outlier
    )

@router.post("/analyze", response=SpatialAnalysisOut, tags=["Spatial Analysis"])
def run_spatial_analysis(request, 
                         county: str,
                         sti_type: str = "all",
                         period_days: int = 30,
                         config: Optional[HotspotDetectionConfig] = None):
    """
    Run complete spatial analysis for a county.
    Includes DBSCAN clustering, KDE heatmap, and Moran's I.
    """
    cfg = config.dict() if config else {}
    analyzer = SpatialAnalyzer(cfg)
    
    period_end = date.today()
    period_start = period_end - timedelta(days=period_days)
    
    result = analyzer.analyze_region(county, sti_type, period_start, period_end)
    
    # Find recommended facilities
    facility_finder = FacilityFinder()
    
    # Get centroid of county for facility search
    cells = GridCell.objects.filter(county=county)
    if cells.exists():
        avg_lat = cells.aggregate(avg_lat=Avg('grid_lat'))['avg_lat'] or -1.2921
        avg_lon = cells.aggregate(avg_lon=Avg('grid_lon'))['avg_lon'] or 36.8219
    else:
        avg_lat, avg_lon = -1.2921, 36.8219  # Default Nairobi
    
    facilities = facility_finder.find_nearest(
        lat=avg_lat,
        lon=avg_lon,
        sti_type=sti_type if sti_type != "all" else None,
        max_distance_km=50.0,
        limit=10
    )
    
    return SpatialAnalysisOut(
        county=result["county"],
        sub_county=None,
        sti_type=result["sti_type"],
        analysis_period=result["analysis_period"],
        total_incidents=result["total_incidents"],
        risk_distribution=result.get("risk_distribution", {}),
        morans_i=result.get("morans_i", {}).get("morans_i"),
        hotspot_clusters=result.get("hotspot_clusters", 0),
        outlier_points=result.get("outlier_points", 0),
        avg_healthcare_access=result.get("avg_healthcare_access", 0.0),
        recommended_facilities=[
            FacilityOut(**f) for f in facilities
        ]
    )

@router.get("/heatmap/{county}", response=HeatmapLayerOut, tags=["Heatmap"])
def get_heatmap(request,
                county: str,
                sti_type: str = "all",
                period_days: int = 30):
    """
    Get GeoJSON heatmap layer for a county.
    Returns colour-graded cells: green → amber → red → dark red.
    """
    period_end = date.today()
    period_start = period_end - timedelta(days=period_days)
    
    incidents = AggregatedIncident.objects.filter(
        grid_cell__county=county,
        sti_type=sti_type,
        period_start__gte=period_start
    ).select_related('grid_cell')
    
    features = []
    for inc in incidents:
        cell = inc.grid_cell
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [cell.grid_lon, cell.grid_lat]
            },
            "properties": {
                "risk_level": inc.risk_level,
                "risk_score": round(inc.risk_score, 3),
                "incident_count": inc.incident_count,
                "kde_density": round(inc.kde_density, 6) if inc.kde_density else None,
                "county": cell.county,
                "sub_county": cell.sub_county,
                "population": cell.population_estimate
            }
        }
        features.append(feature)
    
    hotspot_cells = incidents.filter(risk_level__in=["high", "critical"]).count()
    
    return HeatmapLayerOut(
        sti_type=sti_type,
        period_start=period_start,
        period_end=period_end,
        geojson={
            "type": "FeatureCollection",
            "features": features
        },
        total_cells=incidents.count(),
        hotspot_cells=hotspot_cells
    )

@router.get("/alerts", response=List[HotspotAlertOut], tags=["Alerts"])
def list_hotspot_alerts(request,
                        county: Optional[str] = None,
                        sti_type: Optional[str] = None,
                        active_only: bool = True):
    """
    List hotspot alerts for public health officers.
    """
    queryset = HotspotAlert.objects.all()
    
    if active_only:
        queryset = queryset.filter(is_active=True)
    if county:
        queryset = queryset.filter(primary_county=county)
    if sti_type:
        queryset = queryset.filter(sti_type=sti_type)
    
    alerts = queryset.order_by("-created_at")[:50]
    
    return [
        HotspotAlertOut(
            alert_id=alert.alert_id,
            severity=alert.severity,
            sti_type=alert.sti_type,
            primary_county=alert.primary_county,
            affected_sub_counties=alert.affected_sub_counties,
            cluster_size_cells=alert.cluster_size_cells,
            total_incidents=alert.total_incidents,
            population_at_risk=alert.population_at_risk,
            detection_period_start=alert.detection_period_start,
            detection_period_end=alert.detection_period_end,
            forecast_30_day=alert.forecast_30_day,
            forecast_60_day=alert.forecast_60_day,
            forecast_90_day=alert.forecast_90_day,
            year_over_year_delta=alert.year_over_year_delta,
            is_active=alert.is_active,
            geojson_heatmap=alert.geojson_heatmap,
            created_at=alert.created_at
        )
        for alert in alerts
    ]

@router.post("/facilities/nearest", response=List[FacilityOut], tags=["Facility Finder"])
def find_nearest_facilities(request, payload: FacilityQuery):
    """
    Find nearest MOH-registered testing facilities.
    Used by patient dashboard for testing location finder.
    """
    finder = FacilityFinder()
    results = finder.find_nearest(
        lat=payload.lat,
        lon=payload.lon,
        sti_type=payload.sti_type,
        max_distance_km=payload.max_distance_km,
        limit=payload.limit
    )
    
    return [FacilityOut(**r) for r in results]

@router.get("/morans-i/{county}", response=MoransIResult, tags=["Spatial Statistics"])
def compute_morans_i(request,
                   county: str,
                   sti_type: str = "all",
                   period_days: int = 30):
    """
    Compute Moran's I spatial autocorrelation for a county.
    Measures whether STI incidents cluster geographically.
    """
    period_end = date.today()
    period_start = period_end - timedelta(days=period_days)
    
    incidents = AggregatedIncident.objects.filter(
        grid_cell__county=county,
        sti_type=sti_type,
        period_start__gte=period_start
    ).select_related('grid_cell')
    
    if not incidents.exists():
        return MoransIResult(
            morans_i=0.0,
            expected_i=-0.01,
            variance=0.0,
            z_score=0.0,
            p_value=1.0,
            interpretation="No data available for analysis"
        )
    
    coords = []
    counts = []
    for inc in incidents:
        coords.append([inc.grid_cell.grid_lat, inc.grid_cell.grid_lon])
        counts.append(inc.incident_count)
    
    coords = np.array(coords)
    counts = np.array(counts, dtype=float)
    
    analyzer = SpatialAnalyzer({})
    weights = analyzer.build_weights_matrix(coords)
    result = analyzer.compute_morans_i(counts, weights)
    
    return MoransIResult(**result)

# Register router
api.add_router("/geospatial/", router)