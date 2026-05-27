import uuid
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta, date
from collections import defaultdict
from scipy.spatial.distance import cdist
from sklearn.neighbors import KernelDensity
from sklearn.cluster import DBSCAN

from django.db.models import Count, Avg, Sum, F

from .models import GridCell, AggregatedIncident, HotspotAlert, HealthcareFacility, STIType, RiskLevel
from preprocessing.services import DifferentialPrivacy

class GeospatialPrivacy:
    """
    Privacy controls for geospatial data.
    Enforces ±5km grid rounding and minimum 25km² cell size.
    """
    
    GRID_SIZE_KM = 5.0  # ±5km as per spec Section 4.1.3
    DEGREES_PER_KM = 0.009  # Approximate conversion
    
    @classmethod
    def round_to_grid(cls, lat: float, lon: float) -> Tuple[float, float]:
        """Round coordinates to privacy-preserving grid"""
        grid_deg = cls.GRID_SIZE_KM * cls.DEGREES_PER_KM
        lat_rounded = round(lat / grid_deg) * grid_deg
        lon_rounded = round(lon / grid_deg) * grid_deg
        return round(lat_rounded, 4), round(lon_rounded, 4)
    
    @classmethod
    def validate_cell_size(cls, lat: float, lon: float) -> bool:
        """Verify grid cell meets minimum 25km² requirement"""
        # At equator: 0.045° ≈ 5km → 25km²
        # Kenya is near equator, approximation is valid
        grid_deg = cls.GRID_SIZE_KM * cls.DEGREES_PER_KM
        cell_area_km2 = (grid_deg / cls.DEGREES_PER_KM) ** 2
        return cell_area_km2 >= 25.0

class KDEHeatmapEngine:
    """
    Kernel Density Estimation for smooth heatmap generation.
    Spec Section 4.1.3: KDE for heatmap generation.
    """
    
    def __init__(self, bandwidth_km: float = 15.0):
        # Convert km to approximate degrees for sklearn
        self.bandwidth = bandwidth_km * GeospatialPrivacy.DEGREES_PER_KM
        self.kde = None
    
    def fit(self, coordinates: np.ndarray, weights: Optional[np.ndarray] = None):
        """
        Fit KDE model to grid cell coordinates.
        
        Args:
            coordinates: Nx2 array of [lat, lon]
            weights: Optional incident counts per cell
        """
        self.kde = KernelDensity(
            bandwidth=self.bandwidth,
            kernel='gaussian',
            metric='haversine'
        )
        # Convert to radians for haversine
        coords_rad = np.radians(coordinates)
        self.kde.fit(coords_rad, sample_weight=weights)
        return self
    
    def score_samples(self, coordinates: np.ndarray) -> np.ndarray:
        """Get log-density for coordinates"""
        coords_rad = np.radians(coordinates)
        return self.kde.score_samples(coords_rad)
    
    def generate_density_grid(self, 
                            bounds: Tuple[float, float, float, float],
                            resolution: int = 100) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate density grid for heatmap rendering.
        
        Returns:
            lat_grid, lon_grid, density_values
        """
        min_lat, max_lat, min_lon, max_lon = bounds
        
        lat_range = np.linspace(min_lat, max_lat, resolution)
        lon_range = np.linspace(min_lon, max_lon, resolution)
        lon_grid, lat_grid = np.meshgrid(lon_range, lat_range)
        
        coords = np.vstack([lat_grid.ravel(), lon_grid.ravel()]).T
        coords_rad = np.radians(coords)
        
        log_density = self.kde.score_samples(coords_rad)
        density = np.exp(log_density)
        
        return lat_grid, lon_grid, density.reshape(resolution, resolution)

class DBSCANClusterEngine:
    """
    Density-Based Spatial Clustering for hotspot identification.
    Spec Section 4.1.3: DBSCAN clustering.
    """
    
    def __init__(self, eps_km: float = 10.0, min_samples: int = 5):
        # Convert km to degrees (approximate near equator)
        self.eps = eps_km * GeospatialPrivacy.DEGREES_PER_KM
        self.min_samples = min_samples
        self.model = None
        self.labels = None
    
    def fit(self, coordinates: np.ndarray, weights: Optional[np.ndarray] = None):
        """
        Run DBSCAN on grid cell coordinates.
        
        Args:
            coordinates: Nx2 array of [lat, lon]
            weights: Optional sample weights
        """
        self.model = DBSCAN(
            eps=self.eps,
            min_samples=self.min_samples,
            metric='haversine'
        )
        # DBSCAN doesn't support sample weights directly, 
        # so we replicate points by weight
        if weights is not None:
            coords_weighted = []
            for coord, w in zip(coordinates, weights):
                # Replicate each point weight times (capped at reasonable max)
                reps = min(int(w), 50)
                coords_weighted.extend([coord] * reps)
            coordinates = np.array(coords_weighted)
        
        coords_rad = np.radians(coordinates)
        self.model.fit(coords_rad)
        self.labels = self.model.labels_
        return self
    
    def get_cluster_summary(self) -> Dict:
        """Get summary of clustering results"""
        n_clusters = len(set(self.labels)) - (1 if -1 in self.labels else 0)
        n_outliers = list(self.labels).count(-1)
        return {
            "n_clusters": n_clusters,
            "n_outliers": n_outliers,
            "cluster_ids": sorted(set(self.labels) - {-1})
        }

class SpatialAnalyzer:
    """
    Main geospatial analysis service.
    Combines DBSCAN, KDE, Moran's I, and risk classification.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.dp = DifferentialPrivacy(
            epsilon=config.get("dp_epsilon", 0.1),
            sensitivity=1.0
        )
        self.kde_engine = KDEHeatmapEngine(
            bandwidth_km=config.get("kde_bandwidth_km", 15.0)
        )
        self.dbscan_engine = DBSCANClusterEngine(
            eps_km=config.get("dbscan_eps_km", 10.0),
            min_samples=config.get("dbscan_min_samples", 5)
        )
    
    def compute_morans_i(self, values: np.ndarray, weights_matrix: np.ndarray) -> Dict:
        """
        Compute Moran's I spatial autocorrelation.
        Spec Section 4.2: Moran's I at county level.
        
        Moran's I measures whether similar values cluster geographically.
        I > 0: positive spatial autocorrelation (clustering)
        I ≈ 0: random distribution
        I < 0: dispersion
        """
        n = len(values)
        z = values - np.mean(values)
        
        # Row-standardize weights
        w_sum = weights_matrix.sum()
        if w_sum == 0:
            return {"morans_i": 0.0, "z_score": 0.0, "p_value": 1.0}
        
        # Moran's I formula
        numerator = np.sum(weights_matrix * np.outer(z, z))
        denominator = np.sum(z ** 2)
        
        if denominator == 0:
            return {"morans_i": 0.0, "z_score": 0.0, "p_value": 1.0}
        
        morans_i = (n / w_sum) * (numerator / denominator)
        
        # Expected value under null hypothesis
        expected_i = -1 / (n - 1)
        
        # Variance (simplified approximation)
        s1 = np.sum((weights_matrix + weights_matrix.T) ** 2) / 2
        s2 = np.sum((weights_matrix.sum(axis=1) + weights_matrix.sum(axis=0)) ** 2)
        s3 = (np.sum(z**4) / n) / (denominator / n)**2
        s4 = (n**2 - 3*n + 3) * s1 - n*s2 + 3*w_sum**2
        s5 = (n**2 - n) * s1 - 2*n*s2 + 6*w_sum**2
        
        variance = (n * s4 - s3 * s5) / ((n-1) * (n-2) * (n-3) * w_sum**2) - expected_i**2
        
        # Z-score
        z_score = (morans_i - expected_i) / np.sqrt(variance) if variance > 0 else 0
        
        # Simple p-value (two-tailed)
        from scipy.stats import norm
        p_value = 2 * (1 - norm.cdf(abs(z_score))) if z_score != 0 else 1.0
        
        # Interpretation
        if morans_i > 0.3:
            interpretation = "Strong positive spatial autocorrelation - significant clustering"
        elif morans_i > 0.1:
            interpretation = "Moderate positive spatial autocorrelation"
        elif morans_i > -0.1:
            interpretation = "No significant spatial pattern"
        else:
            interpretation = "Negative spatial autocorrelation - dispersed pattern"
        
        return {
            "morans_i": round(morans_i, 4),
            "expected_i": round(expected_i, 4),
            "variance": round(variance, 6),
            "z_score": round(z_score, 4),
            "p_value": round(p_value, 4),
            "interpretation": interpretation
        }
    
    def build_weights_matrix(self, coordinates: np.ndarray, threshold_km: float = 50.0) -> np.ndarray:
        """Build spatial weights matrix using distance threshold"""
        # Haversine distance in km
        from sklearn.metrics.pairwise import haversine_distances
        coords_rad = np.radians(coordinates)
        distances = haversine_distances(coords_rad) * 6371  # Earth radius in km
        
        # Binary weights: 1 if within threshold, 0 otherwise
        weights = (distances <= threshold_km).astype(float)
        np.fill_diagonal(weights, 0)  # No self-weight
        
        return weights
    
    def classify_risk(self, incident_count: int, population: int, 
                      kde_density: float, healthcare_access: float) -> Tuple[str, float]:
        """
        Classify grid cell risk level.
        
        Risk score combines:
        - Normalised incident rate (per 1000 population)
        - KDE density (spatial concentration)
        - Healthcare access inverse (lower access = higher risk)
        """
        if population > 0:
            incident_rate = (incident_count / population) * 1000
        else:
            incident_rate = incident_count
        
        # Normalise components to 0-1
        rate_score = min(incident_rate / 10.0, 1.0)  # Cap at 10 per 1000
        density_score = min(kde_density / np.percentile([kde_density], 90) if kde_density > 0 else 0, 1.0)
        access_penalty = 1.0 - healthcare_access  # Lower access = higher risk
        
        # Weighted combination
        risk_score = (
            0.4 * rate_score +
            0.35 * density_score +
            0.25 * access_penalty
        )
        
        # Apply differential privacy noise
        risk_score = self.dp.add_laplace_noise(risk_score)
        risk_score = max(0.0, min(1.0, risk_score))
        
        # Classify
        thresholds = {
            "low": self.config.get("low_threshold", 0.25),
            "moderate": self.config.get("moderate_threshold", 0.50),
            "high": self.config.get("high_threshold", 0.75)
        }
        
        if risk_score >= thresholds["high"]:
            return RiskLevel.CRITICAL, risk_score
        elif risk_score >= thresholds["moderate"]:
            return RiskLevel.HIGH, risk_score
        elif risk_score >= thresholds["low"]:
            return RiskLevel.MODERATE, risk_score
        else:
            return RiskLevel.LOW, risk_score
    
    def analyze_region(self, county: str, sti_type: str,
                       period_start: date, period_end: date) -> Dict:
        """
        Complete spatial analysis for a county/sub-county.
        """
        # Get aggregated incidents
        incidents = AggregatedIncident.objects.filter(
            grid_cell__county=county,
            sti_type=sti_type,
            period_start__gte=period_start,
            period_end__lte=period_end
        ).select_related('grid_cell')
        
        if not incidents.exists():
            return {
                "county": county,
                "sti_type": sti_type,
                "total_incidents": 0,
                "message": "No data available for this period"
            }
        
        # Extract data for analysis
        cells = []
        coords = []
        counts = []
        populations = []
        access_scores = []
        
        for inc in incidents:
            cell = inc.grid_cell
            cells.append(cell)
            coords.append([cell.grid_lat, cell.grid_lon])
            counts.append(inc.incident_count)
            populations.append(cell.population_estimate)
            access_scores.append(cell.healthcare_access_index)
        
        coords = np.array(coords)
        counts = np.array(counts, dtype=float)
        populations = np.array(populations)
        access_scores = np.array(access_scores)
        
        # Apply differential privacy to counts
        dp_counts = np.array([
            max(0, self.dp.add_laplace_noise(c)) for c in counts
        ])
        
        # Run DBSCAN clustering
        self.dbscan_engine.fit(coords, weights=dp_counts.astype(int))
        cluster_summary = self.dbscan_engine.get_cluster_summary()
        
        # Run KDE
        self.kde_engine.fit(coords, weights=dp_counts)
        densities = np.exp(self.kde_engine.score_samples(coords))
        
        # Compute Moran's I
        weights_matrix = self.build_weights_matrix(coords)
        morans_result = self.compute_morans_i(dp_counts, weights_matrix)
        
        # Classify each cell and update database
        risk_distribution = defaultdict(int)
        for i, (inc, density) in enumerate(zip(incidents, densities)):
            risk_level, risk_score = self.classify_risk(
                int(dp_counts[i]),
                populations[i],
                density,
                access_scores[i]
            )
            risk_distribution[risk_level] += 1
            
            # Update incident record
            inc.kde_density = density
            inc.risk_score = risk_score
            inc.risk_level = risk_level
            inc.cluster_id = self.dbscan_engine.labels_[i] if self.dbscan_engine.labels_[i] != -1 else None
            inc.is_outlier = self.dbscan_engine.labels_[i] == -1
            inc.save()
        
        # Generate GeoJSON for map
        geojson = self._generate_geojson(incidents)
        
        # Create hotspot alert if critical cells found
        critical_cells = [inc for inc in incidents if inc.risk_level == RiskLevel.CRITICAL]
        if len(critical_cells) >= 3:
            self._create_hotspot_alert(
                county, sti_type, period_start, period_end,
                critical_cells, cluster_summary, morans_result
            )
        
        return {
            "county": county,
            "sti_type": sti_type,
            "analysis_period": f"{period_start} to {period_end}",
            "total_incidents": int(np.sum(dp_counts)),
            "risk_distribution": dict(risk_distribution),
            "morans_i": morans_result,
            "hotspot_clusters": cluster_summary["n_clusters"],
            "outlier_points": cluster_summary["n_outliers"],
            "avg_healthcare_access": round(float(np.mean(access_scores)), 3),
            "geojson": geojson
        }
    
    def _generate_geojson(self, incidents) -> Dict:
        """Generate GeoJSON FeatureCollection for Leaflet/Mapbox"""
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
                    "cell_id": cell.cell_id,
                    "county": cell.county,
                    "sub_county": cell.sub_county,
                    "incident_count": inc.incident_count,
                    "risk_level": inc.risk_level,
                    "risk_score": round(inc.risk_score, 3),
                    "kde_density": round(inc.kde_density, 6) if inc.kde_density else None,
                    "cluster_id": inc.cluster_id,
                    "is_outlier": inc.is_outlier,
                    "population": cell.population_estimate,
                    "healthcare_access": cell.healthcare_access_index
                }
            }
            features.append(feature)
        
        return {
            "type": "FeatureCollection",
            "features": features
        }
    
    def _create_hotspot_alert(self, county: str, sti_type: str,
                              period_start: date, period_end: date,
                              critical_cells, cluster_summary, morans_result):
        """Create a hotspot alert for public health officers"""
        # Get affected sub-counties
        sub_counties = list(set(
            inc.grid_cell.sub_county for inc in critical_cells
        ))
        
        # Calculate population at risk
        population_at_risk = sum(
            inc.grid_cell.population_estimate for inc in critical_cells
        )
        
        # Total incidents in critical cells
        total_incidents = sum(inc.incident_count for inc in critical_cells)
        
        # Generate alert GeoJSON (only critical cells)
        geojson = self._generate_geojson(critical_cells)
        
        HotspotAlert.objects.create(
            severity=RiskLevel.CRITICAL,
            sti_type=sti_type,
            primary_county=county,
            affected_sub_counties=sub_counties,
            cluster_size_cells=len(critical_cells),
            total_incidents=total_incidents,
            population_at_risk=population_at_risk,
            detection_period_start=period_start,
            detection_period_end=period_end,
            geojson_heatmap=geojson
        )

class FacilityFinder:
    """
    Find nearest MOH-registered testing facilities.
    Used by patient dashboard (Section 7.1).
    """
    
    def find_nearest(self, lat: float, lon: float,
                     sti_type: Optional[str] = None,
                     max_distance_km: float = 50.0,
                     limit: int = 10) -> List[Dict]:
        """
        Find nearest healthcare facilities using an in-memory haversine calculation.
        """
        queryset = HealthcareFacility.objects.filter(
            is_active=True,
            is_moh_registered=True
        )
        
        if sti_type:
            # Filter facilities offering specific STI testing
            queryset = queryset.filter(services__contains=[sti_type])

        facilities = []
        for facility in queryset:
            distance_km = self._haversine_km(lat, lon, facility.lat, facility.lon)
            if distance_km <= max_distance_km:
                facilities.append((distance_km, facility))

        facilities.sort(key=lambda item: item[0])
        facilities = facilities[:limit]
        
        results = []
        for distance_km, facility in facilities:
            results.append({
                "facility_id": facility.facility_id,
                "name": facility.name,
                "county": facility.county,
                "sub_county": facility.sub_county,
                "lat": facility.lat,
                "lon": facility.lon,
                "services": facility.services,
                "distance_km": round(distance_km, 2),
                "is_moh_registered": facility.is_moh_registered
            })
        
        return results

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Compute distance between two coordinates in kilometers."""
        if lat2 is None or lon2 is None:
            return float("inf")

        radius_km = 6371.0
        lat1_rad, lon1_rad = np.radians([lat1, lon1])
        lat2_rad, lon2_rad = np.radians([lat2, lon2])

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
        return float(2 * radius_km * np.arcsin(np.sqrt(a)))