from ninja import Router
from django.shortcuts import get_object_or_404
from django.db.models import Q
from typing import List, Optional
from .models import Patient, PatientVisit
from .schemas import (
    PatientCreateSchema, PatientOutSchema, 
    PatientListSchema, PatientUpdateSchema
)

router = Router(tags=["Patients"])


@router.post("/", response=PatientOutSchema)
def create_patient(request, payload: PatientCreateSchema):
    patient = Patient.objects.create(**payload.dict())
    return patient


@router.get("/", response=List[PatientListSchema])
def list_patients(
    request, 
    search: Optional[str] = None,
    county: Optional[str] = None,
    gender: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0
):
    qs = Patient.objects.all()
    if search:
        qs = qs.filter(
            Q(patient_id__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(phone__icontains=search)
        )
    if county:
        qs = qs.filter(county__iexact=county)
    if gender:
        qs = qs.filter(gender=gender)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs[offset:offset + limit]


@router.get("/{patient_id}", response=PatientOutSchema)
def get_patient(request, patient_id: str):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    return patient


@router.put("/{patient_id}", response=PatientOutSchema)
def update_patient(request, patient_id: str, payload: PatientUpdateSchema):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    for attr, value in payload.dict(exclude_unset=True).items():
        setattr(patient, attr, value)
    patient.save()
    return patient


@router.delete("/{patient_id}")
def delete_patient(request, patient_id: str):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    patient.is_active = False
    patient.save()
    return {"success": True, "message": "Patient deactivated"}


@router.get("/{patient_id}/visits")
def get_patient_visits(request, patient_id: str):
    patient = get_object_or_404(Patient, patient_id=patient_id)
    visits = patient.visits.all().values()
    return {"patient_id": patient_id, "visits": list(visits)}