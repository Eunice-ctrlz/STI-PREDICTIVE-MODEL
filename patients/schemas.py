from ninja import Schema
from datetime import date, datetime
from typing import Optional, List
from pydantic import Field


class PatientCreateSchema(Schema):
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str = Field(..., regex='^[MFOU]$')
    phone: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""
    marital_status: Optional[str] = "single"
    number_of_partners_12m: Optional[int] = 0
    number_of_partners_lifetime: Optional[int] = 0
    condom_use_frequency: Optional[float] = Field(0.0, ge=0.0, le=1.0)
    substance_use: Optional[bool] = False
    substance_type: Optional[str] = ""
    prior_sti_history: Optional[bool] = False
    prior_sti_types: Optional[str] = ""
    hiv_status_known: Optional[bool] = False
    hiv_status: Optional[str] = "unknown"
    symptoms_present: Optional[bool] = False
    symptom_description: Optional[str] = ""
    county: Optional[str] = ""
    sub_county: Optional[str] = ""
    ward: Optional[str] = ""


class PatientOutSchema(Schema):
    id: int
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    age: int
    age_group: str
    phone: str
    email: str
    county: str
    sub_county: str
    ward: str
    marital_status: str
    number_of_partners_12m: int
    condom_use_frequency: float
    substance_use: bool
    prior_sti_history: bool
    hiv_status: str
    symptoms_present: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PatientListSchema(Schema):
    id: int
    patient_id: str
    full_name: str
    age: int
    gender: str
    county: str
    is_active: bool
    created_at: datetime


class PatientUpdateSchema(Schema):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    number_of_partners_12m: Optional[int] = None
    condom_use_frequency: Optional[float] = None
    substance_use: Optional[bool] = None
    symptoms_present: Optional[bool] = None
    is_active: Optional[bool] = None