from ninja import Router
from typing import List, Optional
from django.db.models import Count
from datetime import datetime, timedelta
from .models import AuditLog, PatientConsent, DataRetentionPolicy

router = Router(tags=["Compliance"])


@router.get("/audit-logs")
def list_audit_logs(
    request,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    days: int = 7
):
    since = datetime.now() - timedelta(days=days)
    qs = AuditLog.objects.filter(created_at__gte=since)
    
    if user_id:
        qs = qs.filter(user_id=user_id)
    if action:
        qs = qs.filter(action=action)
    if resource_type:
        qs = qs.filter(resource_type=resource_type)
    
    return list(qs.values().order_by('-created_at')[:100])


@router.get("/audit-logs/summary")
def get_audit_summary(request, days: int = 30):
    since = datetime.now() - timedelta(days=days)
    qs = AuditLog.objects.filter(created_at__gte=since)
    
    return {
        'total_actions': qs.count(),
        'by_action': dict(qs.values('action').annotate(count=Count('id')).values_list('action', 'count')),
        'by_resource': dict(qs.values('resource_type').annotate(count=Count('id')).values_list('resource_type', 'count')),
        'by_user': list(qs.values('user_name').annotate(count=Count('id')).order_by('-count')[:10]),
    }


@router.get("/consents/{patient_id}")
def get_patient_consents(request, patient_id: str):
    from patients.models import Patient
    patient = Patient.objects.filter(patient_id=patient_id).first()
    if not patient:
        return {"error": "Patient not found"}
    
    consents = list(patient.consents.values())
    return {"patient_id": patient_id, "consents": consents}


@router.get("/retention-policies")
def list_retention_policies(request):
    return list(DataRetentionPolicy.objects.filter(is_active=True).values())