from ninja import Schema
from datetime import datetime
from typing import Optional


class FacilitySchema(Schema):
    id: int
    name: str
    code: str
    county: str
    sub_county: str
    ward: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    facility_type: str


class ClinicianOutSchema(Schema):
    id: int
    staff_id: str
    username: str
    full_name: str
    phone: str
    role: str
    facility: Optional[FacilitySchema] = None
    is_active: bool
    created_at: datetime