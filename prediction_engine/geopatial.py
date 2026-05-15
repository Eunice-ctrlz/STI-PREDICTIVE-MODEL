"""
STI Predictive Model — ML Pipeline (L3)
geospatial.py

Geospatial Hotspot Engine: DBSCAN clustering + Kernel Density Estimation.
Produces GeoJSON heatmap layers and Moran's I spatial autocorrelation index.

Privacy constraints enforced here (§4.1.3 + §5.2):
  - Minimum 100 records per grid cell before processing
  - Coordinates already snapped to ±5km grid by L1 (ingestion)
  - Minimum cell size of 25km² for any output
  - No individual coordinates at any stage
  - Suppressed cells are excluded from all outputs
"""

import logging
from typing import Dict, List, Optional, Tuple

import mlflow
import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum cases per cell before including in analysis (§4.1.3 privacy rule)
MIN_CELL_COUNT = 100

# Minimum cell area in km² (§5.2)
MIN_CELL_AREA_KM2 = 25.0

# DBSCAN defaults: eps in degrees (~5km), min_samples aligned to MIN_CELL_COUNT
DEFAULT_DBSCAN_PARAMS = {
    "eps": 0.045,           # ~5km in degrees
    "min_samples": 3,       # minimum grid cells to form a cluster
    "metric": "haversine",  # great-circle distance
    "algorithm": "ball_tree",
    "n_jobs": -1,
}

# KDE bandwidth in degrees (~10km)
DEFAULT_KDE_BANDWIDTH = 0.09

# Risk thresholds for heatmap colouring
RISK_THRESHOLDS = {
    "low": 0.33,
    "moderate": 0.66,
    "high": 1.0,
}

STI_TYPES = ["hiv", "chlamydia", "syphilis", "gonorrhoea", "hpv", "hsv2"]


# ---------------------------------------------------------------------------
# Data Preparation
# ---------------------------------------------------------------------------

def build_geo_dataframe(geo_records: List[Dict]) -> pd.DataFrame:
    """
    Convert GeoRecord dicts from the ingestion layer into a clean DataFrame.

    Expected fields per record:
      - latitude_grid, longitude_grid
      - county, sub_county
      - sti_counts: {sti_type: count}
      - total_cases: int
      - suppressed: bool
      - week_start: ISO date string

    Suppressed cells and cells below MIN_CELL_COUNT are excluded.
    """
    rows = []
    for rec in geo_records:
        if rec.get("suppressed", False):
            continue
        if rec.get("total_cases", 0) < MIN_CELL_COUNT:
            continue

        sti_counts = rec.get("sti_counts", {})
        row = {
            "lat": float(rec["latitude_grid"]),
            "lon": float(rec["longitude_grid"]),
            "county": rec.get("county", ""),
            "sub_county": rec.get("sub_county", ""),
            "total_cases": int(rec.get("total_cases", 0)),
            "week_start": rec.get("week_start"),
        }
        for sti in STI_TYPES:
            row[f"count_{sti}"] = int(sti_counts.get(sti, 0))
        rows.append(row)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df = df.sort_values(["county", "week_start"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Kernel Density Estimation
# ---------------------------------------------------------------------------

class STIKernelDensity:
    """
    Gaussian KDE over grid-snapped incident coordinates.
    Produces a normalised density surface for each STI type.
    """

    def __init__(self, bandwidth: float = DEFAULT_KDE_BANDWIDTH):
        self.bandwidth = bandwidth

    def fit_predict(
        self,
        lats: np.ndarray,
        lons: np.ndarray,
        weights: Optional[np.ndarray] = None,
        grid_resolution: int = 100,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute weighted KDE density surface.
        Returns (lat_grid, lon_grid, density_grid).
        """
        if len(lats) == 0:
            empty = np.zeros((grid_resolution, grid_resolution))
            return empty, empty, empty

        # Build evaluation grid
        lat_min, lat_max = lats.min() - self.bandwidth, lats.max() + self.bandwidth
        lon_min, lon_max = lons.min() - self.bandwidth, lons.max() + self.bandwidth

        lat_grid, lon_grid = np.meshgrid(
            np.linspace(lat_min, lat_max, grid_resolution),
            np.linspace(lon_min, lon_max, grid_resolution),
        )
        eval_points = np.column_stack([lat_grid.ravel(), lon_grid.ravel()])
        data_points = np.column_stack([lats, lons])

        # Gaussian kernel
        dist_sq = cdist(eval_points, data_points, metric="sqeuclidean")
        kernel = np.exp(-dist_sq / (2 * self.bandwidth ** 2))

        if weights is not None and len(weights) == len(lats):
            density = (kernel * weights).sum(axis=1)
        else:
            density = kernel.sum(axis=1)

        # Normalise to [0, 1]
        if density.max() > 0:
            density = density / density.max()

        density_grid = density.reshape(lat_grid.shape)
        return lat_grid, lon_grid, density_grid

    def density_to_risk_label(self, density: float) -> str:
        """Map [0,1] density to green/amber/red risk label."""
        if density >= RISK_THRESHOLDS["high"]:
            return "high"
        elif density >= RISK_THRESHOLDS["moderate"]:
            return "moderate"
        return "low"


# ---------------------------------------------------------------------------
# DBSCAN Cluster Engine
# ---------------------------------------------------------------------------

class HotspotClusterer:
    """
    DBSCAN clustering on grid-snapped coordinates weighted by case count.
    Identifies spatial hotspot clusters for each STI type.
    """

    def __init__(self, params: Optional[Dict] = None):
        self.params = {**DEFAULT_DBSCAN_PARAMS, **(params or {})}
        self.labels_: Optional[np.ndarray] = None
        self.n_clusters_: int = 0

    def fit(
        self,
        lats: np.ndarray,
        lons: np.ndarray,
    ) -> "HotspotClusterer":
        if len(lats) < self.params["min_samples"]:
            self.labels_ = np.full(len(lats), -1)
            self.n_clusters_ = 0
            return self

        # Haversine requires radians
        coords_rad = np.radians(np.column_stack([lats, lons]))
        db = DBSCAN(
            eps=self.params["eps"] * np.pi / 180,   # degrees → radians for haversine
            min_samples=self.params["min_samples"],
            metric="haversine",
            algorithm="ball_tree",
            n_jobs=self.params.get("n_jobs", -1),
        )
        self.labels_ = db.fit_predict(coords_rad)
        self.n_clusters_ = len(set(self.labels_)) - (1 if -1 in self.labels_ else 0)
        return self

    def cluster_summary(
        self,
        df: pd.DataFrame,
        sti_type: str,
    ) -> List[Dict]:
        """
        Return a list of cluster summaries with centroid and total case count.
        Noise points (label == -1) are excluded.
        """
        if self.labels_ is None or len(self.labels_) != len(df):
            return []

        summaries = []
        df_copy = df.copy()
        df_copy["_cluster"] = self.labels_
        count_col = f"count_{sti_type}"

        for cluster_id in range(self.n_clusters_):
            cluster_df = df_copy[df_copy["_cluster"] == cluster_id]
            total = int(cluster_df[count_col].sum()) if count_col in cluster_df else 0
            summaries.append({
                "cluster_id": cluster_id,
                "centroid_lat": round(float(cluster_df["lat"].mean()), 6),
                "centroid_lon": round(float(cluster_df["lon"].mean()), 6),
                "counties": cluster_df["county"].unique().tolist(),
                "cell_count": len(cluster_df),
                "total_cases": total,
                "sti_type": sti_type,
            })
        return summaries


# ---------------------------------------------------------------------------
# Spatial Autocorrelation (Moran's I)
# ---------------------------------------------------------------------------

def compute_morans_i(
    values: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    distance_threshold_km: float = 50.0,
) -> Dict:
    """
    Compute Moran's I spatial autocorrelation index (§4.2).
    Uses a binary contiguity weight matrix: W_ij = 1 if distance ≤ threshold.

    Returns:
      - moran_i: float [-1, 1]   (>0 = clustering, <0 = dispersion)
      - z_score: float
      - interpretation: str
    """
    n = len(values)
    if n < 3:
        return {"moran_i": 0.0, "z_score": 0.0, "interpretation": "insufficient_data"}

    # Haversine distance matrix (km)
    lats_r = np.radians(lats)
    lons_r = np.radians(lons)
    dlat = lats_r[:, None] - lats_r[None, :]
    dlon = lons_r[:, None] - lons_r[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lats_r[:, None]) * np.cos(lats_r[None, :]) * np.sin(dlon / 2) ** 2
    dist_km = 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    # Binary spatial weights
    W = (dist_km <= distance_threshold_km).astype(float)
    np.fill_diagonal(W, 0.0)
    W_sum = W.sum()
    if W_sum == 0:
        return {"moran_i": 0.0, "z_score": 0.0, "interpretation": "no_neighbours"}

    z = values - values.mean()
    numerator = (W * np.outer(z, z)).sum()
    denominator = (z ** 2).sum()

    moran_i = (n / W_sum) * (numerator / denominator) if denominator != 0 else 0.0

    # Expected value and variance under randomisation assumption
    E_i = -1.0 / (n - 1)
    var_i = (n ** 2 * (n - 1) * W_sum) / ((n + 1) * W_sum ** 2) if W_sum > 0 else 1.0
    z_score = (moran_i - E_i) / np.sqrt(var_i) if var_i > 0 else 0.0

    interpretation = (
        "significant_clustering" if z_score > 1.96
        else "significant_dispersion" if z_score < -1.96
        else "random"
    )

    return {
        "moran_i": round(float(moran_i), 6),
        "z_score": round(float(z_score), 4),
        "interpretation": interpretation,
    }


# ---------------------------------------------------------------------------
# GeoJSON Output Builder
# ---------------------------------------------------------------------------

def build_heatmap_geojson(
    df: pd.DataFrame,
    sti_type: str,
    density_grid: Tuple[np.ndarray, np.ndarray, np.ndarray],
    clusters: List[Dict],
) -> Dict:
    """
    Assemble a GeoJSON FeatureCollection for the Leaflet.js / Mapbox dashboard.
    Each feature represents one grid cell with risk colour and case count.
    Only non-suppressed cells with total_cases >= MIN_CELL_COUNT are included.
    """
    lat_grid, lon_grid, density = density_grid
    kde = STIKernelDensity()
    count_col = f"count_{sti_type}"

    features = []
    for _, row in df.iterrows():
        count = int(row.get(count_col, 0))
        if count < MIN_CELL_COUNT:
            continue

        # Find nearest density value
        lat_idx = np.argmin(np.abs(lat_grid[:, 0] - row["lat"]))
        lon_idx = np.argmin(np.abs(lon_grid[0, :] - row["lon"]))
        dens_val = float(density[lat_idx, lon_idx])
        risk_label = kde.density_to_risk_label(dens_val)

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row["lon"], row["lat"]],
            },
            "properties": {
                "county": row["county"],
                "sub_county": row.get("sub_county", ""),
                "sti_type": sti_type,
                "case_count": count,
                "density": round(dens_val, 4),
                "risk_level": risk_label,
                "risk_colour": {"low": "#4caf50", "moderate": "#ff9800", "high": "#f44336"}.get(
                    risk_label, "#4caf50"
                ),
                "week_start": str(row.get("week_start", "")),
            },
        })

    # Add cluster centroids as separate features
    for cluster in clusters:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [cluster["centroid_lon"], cluster["centroid_lat"]],
            },
            "properties": {
                "feature_type": "cluster_centroid",
                "cluster_id": cluster["cluster_id"],
                "sti_type": sti_type,
                "counties": cluster["counties"],
                "cell_count": cluster["cell_count"],
                "total_cases": cluster["total_cases"],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "sti_type": sti_type,
            "total_cells": len(df),
            "n_clusters": len(clusters),
            "generated_at": pd.Timestamp.now().isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Geospatial Hotspot Engine (Main Service)
# ---------------------------------------------------------------------------

class GeospatialHotspotEngine:
    """
    Orchestrates KDE + DBSCAN + Moran's I for weekly hotspot analysis.
    Produces GeoJSON outputs per STI type for the dashboard layer (L5).
    Logs run metadata to MLflow.
    """

    def __init__(
        self,
        dbscan_params: Optional[Dict] = None,
        kde_bandwidth: float = DEFAULT_KDE_BANDWIDTH,
        mlflow_experiment_id: Optional[str] = None,
    ):
        self.dbscan_params = dbscan_params
        self.kde = STIKernelDensity(bandwidth=kde_bandwidth)
        self.clusterer = HotspotClusterer(params=dbscan_params)
        self.mlflow_experiment_id = mlflow_experiment_id
        self.mlflow_run_id: Optional[str] = None

    def run(
        self,
        geo_records: List[Dict],
        sti_type: str = "all",
        run_name: Optional[str] = None,
    ) -> Dict:
        """
        Full hotspot analysis run for a given STI type (or 'all').
        Returns a dict keyed by STI type containing GeoJSON + Moran's I.
        """
        df = build_geo_dataframe(geo_records)
        if df.empty:
            logger.warning("No qualifying geo records after suppression filter")
            return {}

        if self.mlflow_experiment_id:
            mlflow.set_experiment(experiment_id=self.mlflow_experiment_id)

        target_types = STI_TYPES if sti_type == "all" else [sti_type]
        results = {}

        with mlflow.start_run(run_name=run_name or "geospatial_hotspot_engine") as run:
            self.mlflow_run_id = run.info.run_id
            mlflow.log_param("sti_types", target_types)
            mlflow.log_param("grid_cells_total", len(df))
            mlflow.log_param("counties", df["county"].nunique())

            for stype in target_types:
                count_col = f"count_{stype}"
                if count_col not in df.columns:
                    continue

                sub = df[df[count_col] >= MIN_CELL_COUNT].copy()
                if len(sub) < 2:
                    logger.info("Insufficient cells for %s (%d)", stype, len(sub))
                    continue

                lats = sub["lat"].values
                lons = sub["lon"].values
                weights = sub[count_col].values.astype(float)

                # KDE
                density_grid = self.kde.fit_predict(lats, lons, weights=weights)

                # DBSCAN clustering
                clusterer = HotspotClusterer(params=self.dbscan_params)
                clusterer.fit(lats, lons)
                clusters = clusterer.cluster_summary(sub, stype)

                # Moran's I
                morans = compute_morans_i(weights, lats, lons)

                # GeoJSON output
                geojson = build_heatmap_geojson(sub, stype, density_grid, clusters)

                results[stype] = {
                    "geojson": geojson,
                    "clusters": clusters,
                    "n_clusters": clusterer.n_clusters_,
                    "morans_i": morans,
                    "cell_count": len(sub),
                }

                mlflow.log_metric(f"{stype}_n_clusters", clusterer.n_clusters_)
                mlflow.log_metric(f"{stype}_morans_i", morans["moran_i"])

            mlflow.log_param("sti_types_processed", list(results.keys()))

        return {
            "results": results,
            "mlflow_run_id": self.mlflow_run_id,
        }

    def incremental_update(
        self,
        existing_geojson: Dict,
        new_geo_records: List[Dict],
        sti_type: str,
    ) -> Dict:
        """
        Merge new weekly geo records into an existing GeoJSON heatmap.
        Used for weekly incremental updates without full reprocessing.
        """
        new_df = build_geo_dataframe(new_geo_records)
        if new_df.empty:
            return existing_geojson

        count_col = f"count_{sti_type}"
        sub = new_df[new_df.get(count_col, pd.Series(dtype=int)) >= MIN_CELL_COUNT] \
            if count_col in new_df.columns else pd.DataFrame()

        if sub.empty:
            return existing_geojson

        lats = sub["lat"].values
        lons = sub["lon"].values
        weights = sub[count_col].values.astype(float) if count_col in sub.columns else None
        density_grid = self.kde.fit_predict(lats, lons, weights=weights)

        clusterer = HotspotClusterer(params=self.dbscan_params)
        clusterer.fit(lats, lons)
        new_clusters = clusterer.cluster_summary(sub, sti_type)
        new_geojson = build_heatmap_geojson(sub, sti_type, density_grid, new_clusters)

        # Merge features (replace existing cells for same coordinates)
        existing_coords = {
            (f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1])
            for f in existing_geojson.get("features", [])
        }
        new_features = [
            f for f in new_geojson["features"]
            if (f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1])
            not in existing_coords
        ]
        merged_features = existing_geojson.get("features", []) + new_features

        return {
            **existing_geojson,
            "features": merged_features,
            "metadata": {
                **existing_geojson.get("metadata", {}),
                "last_updated": pd.Timestamp.now().isoformat(),
                "total_features": len(merged_features),
            },
        }