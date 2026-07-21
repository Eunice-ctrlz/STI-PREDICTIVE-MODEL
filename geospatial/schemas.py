from ninja import Schema
from typing import Optional


class GeoRiskZoneSchema(Schema):
    id: int
    name: str
    county: str
    sub_county: str
    ward: str
    risk_level: str
    risk_score: float
    population_at_risk: int
    total_screenings: int
    positive_cases: int
    period_start: str
    period_end: str

    # GeoDjango geometry fields aren't JSON-serializable by default,
    # so expose simple lat/lng derived from the centroid instead.
    lat: Optional[float] = None
    lng: Optional[float] = None

    @staticmethod
    def resolve_lat(obj):
        return obj.centroid.y if obj.centroid else None

    @staticmethod
    def resolve_lng(obj):
        return obj.centroid.x if obj.centroid else None


class HeatmapPointSchema(Schema):
    lat: float
    lng: float
    intensity: float
    county: str
    sub_county: str
    patient_count: int
    high_risk_count: int