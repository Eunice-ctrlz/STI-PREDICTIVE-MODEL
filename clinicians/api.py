from ninja import Router
from django.shortcuts import get_object_or_404
from typing import List
from .models import Facility, Clinician
from .schemas import FacilitySchema, ClinicianOutSchema

router = Router(tags=["Clinicians"])


@router.get("/facilities", response=List[FacilitySchema])
def list_facilities(request, county: str = None):
    qs = Facility.objects.filter(is_active=True)
    if county:
        qs = qs.filter(county__iexact=county)
    return qs


@router.get("/facilities/{facility_id}", response=FacilitySchema)
def get_facility(request, facility_id: int):
    return get_object_or_404(Facility, id=facility_id, is_active=True)


@router.get("/", response=List[ClinicianOutSchema])
def list_clinicians(request, facility_id: int = None, role: str = None):
    qs = Clinician.objects.filter(is_active=True)
    if facility_id:
        qs = qs.filter(facility_id=facility_id)
    if role:
        qs = qs.filter(role=role)
    return qs