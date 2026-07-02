from ninja import Schema
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import Field


class PredictionRequestSchema(Schema):
    patient_id: str
    sti_type: Optional[str] = "general"
    model_version: Optional[str] = "sti_risk_v1"


class PredictionResultSchema(Schema):
    id: int
    patient_id: str
    patient_name: str
    sti_type: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str
    confidence_interval_lower: Optional[float] = None
    confidence_interval_upper: Optional[float] = None
    top_risk_factors: Dict
    recommended_tests: List[str]
    recommended_actions: str
    model_version: str
    model_name: str
    validated_by_clinician: bool
    created_at: datetime


class BatchPredictionSchema(Schema):
    patient_ids: List[str]
    sti_type: Optional[str] = "general"


class RiskStatsSchema(Schema):
    total_predictions: int
    risk_distribution: Dict[str, int]
    avg_risk_score: float
    model_version: str
    period: str