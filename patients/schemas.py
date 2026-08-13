from ninja import Schema
from datetime import date, datetime
from typing import Optional
from pydantic import Field


class PatientCreateSchema(Schema):
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str = Field(..., pattern='^[MFOU]$')
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
    address: Optional[str] = ""
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    age: int
    age_group: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    county: Optional[str] = ""
    sub_county: Optional[str] = ""
    ward: Optional[str] = ""
    marital_status: str
    # The full risk-factor profile, so the patient detail page and the
    # re-assessment form can show what was actually recorded.
    number_of_partners_12m: int
    number_of_partners_lifetime: int
    condom_use_frequency: float
    substance_use: bool
    substance_type: Optional[str] = ""
    prior_sti_history: bool
    prior_sti_types: Optional[str] = ""
    hiv_status_known: bool
    hiv_status: str
    symptoms_present: bool
    symptom_description: Optional[str] = ""
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PatientListSchema(Schema):
    id: int
    patient_id: str
    full_name: str
    age: int
    gender: str
    county: Optional[str] = ""
    is_active: bool
    created_at: datetime


class PatientUpdateSchema(Schema):
    """
    Every field is optional and applied with exclude_unset, so a caller can
    PATCH-style update just what changed. It mirrors PatientCreateSchema's
    risk fields — without them, re-assessing a patient silently dropped the
    updated risk factors and predicted on stale data.
    """
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, pattern='^[MFOU]$')
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    county: Optional[str] = None
    sub_county: Optional[str] = None
    ward: Optional[str] = None
    marital_status: Optional[str] = None
    number_of_partners_12m: Optional[int] = None
    number_of_partners_lifetime: Optional[int] = None
    condom_use_frequency: Optional[float] = Field(None, ge=0.0, le=1.0)
    substance_use: Optional[bool] = None
    substance_type: Optional[str] = None
    prior_sti_history: Optional[bool] = None
    prior_sti_types: Optional[str] = None
    hiv_status_known: Optional[bool] = None
    hiv_status: Optional[str] = None
    symptoms_present: Optional[bool] = None
    symptom_description: Optional[str] = None
    is_active: Optional[bool] = None
