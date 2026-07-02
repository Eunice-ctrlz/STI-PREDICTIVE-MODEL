from ninja import Schema
from typing import Optional, List


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


class HeatmapPointSchema(Schema):
    lat: float
    lng: float
    intensity: float  # 0-1 risk score
    county: str
    patient_count: int